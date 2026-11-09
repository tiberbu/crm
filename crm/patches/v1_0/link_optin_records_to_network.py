"""Link Opt-In pipeline records to CRM Opt-In Network for User Permissions.

The existing ``network_slug`` fields are retained for public links and old
installations.  This patch adds optional Link fields, then fills only empty
values from the strongest existing relationship.  It is safe on CRM-only sites
where ERPNext transaction doctypes are absent and safe to run more than once.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from crm.utils.optin_network import network_name

_LINK_LABELS = {
	"CRM Lead": "Opt-In Network",
	"CRM Deal": "Opt-In Network",
	"CRM Opt-In Submission": "Opt-In Network",
	"CRM Contract": "Opt-In Network",
	"Quotation": "Opt-In Network",
	"Sales Order": "Opt-In Network",
	"Sales Invoice": "Opt-In Network",
	"Payment Entry": "Opt-In Network",
	"CRM Onboarding Request": "Opt-In Network",
	"CRM Partner Rebate Voucher": "Opt-In Network",
	"CRM Sales Commission": "Opt-In Network",
}


def _available(doctype):
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def _create_link_fields():
	fields = {}
	for doctype, label in _LINK_LABELS.items():
		if not _available(doctype):
			continue
		fields[doctype] = [
			{
				"fieldname": "optin_network",
				"fieldtype": "Link",
				"label": label,
				"options": "CRM Opt-In Network",
				"insert_after": "network_slug"
				if doctype in ("CRM Opt-In Submission", "CRM Contract")
				else "optin_submission"
				if doctype == "CRM Deal"
				else "crm_deal"
				if doctype in ("Quotation", "Sales Invoice")
				else "deal"
				if doctype in ("CRM Onboarding Request", "CRM Partner Rebate Voucher", "CRM Sales Commission")
				else None,
				"read_only": 1,
				"no_copy": 1,
				"in_list_view": 0,
				"in_standard_filter": 1,
			}
		]
	# ``insert_after`` cannot be None on some Frappe versions.  Omitting it is
	# preferable to making a migration fail on a custom/older ERPNext schema.
	for entries in fields.values():
		for field in entries:
			if not field["insert_after"]:
				field.pop("insert_after", None)
	if fields:
		create_custom_fields(fields, ignore_validate=True)

	# These child fields make the internal-user route and its reminder cadence
	# durable without changing the standard Contract Signatory DocType.  They are
	# safe on older installs and are intentionally created only when that child
	# DocType exists.
	if _available("CRM Contract Signatory"):
		create_custom_fields(
			{
				"CRM Contract Signatory": [
					{
						"fieldname": "crm_internal_action_notified_at",
						"fieldtype": "Datetime",
						"label": "CRM Action Available Since",
						"read_only": 1,
						"no_copy": 1,
					},
					{
						"fieldname": "crm_last_reminder_at",
						"fieldtype": "Datetime",
						"label": "Last CRM Action Reminder Sent",
						"read_only": 1,
						"no_copy": 1,
					},
				]
			},
			ignore_validate=True,
		)


def _has_link(doctype):
	try:
		return _available(doctype) and frappe.db.has_column(doctype, "optin_network")
	except Exception:
		return False


def _set_if_empty(doctype, name, slug):
	slug = network_name(slug)
	if not slug or not _has_link(doctype):
		return False
	try:
		if frappe.utils.cstr(frappe.db.get_value(doctype, name, "optin_network") or "").strip():
			return False
		frappe.db.set_value(doctype, name, "optin_network", slug, update_modified=False)
		return True
	except Exception:
		return False


def _network_by_submission():
	result = {}
	if not _available("CRM Opt-In Submission"):
		return result
	fields = ["name", "network_slug"]
	if _has_link("CRM Opt-In Submission"):
		fields.append("optin_network")
	for row in frappe.get_list(
		"CRM Opt-In Submission",
		fields=fields,
		limit_page_length=0,
		ignore_permissions=True,
	):
		candidates = {
			value
			for value in (network_name(row.get("optin_network")), network_name(row.get("network_slug")))
			if value
		}
		slug = next(iter(candidates)) if len(candidates) == 1 else ""
		if slug:
			result[row.name] = slug
			_set_if_empty("CRM Opt-In Submission", row.name, slug)
	return result


def _network_by_deal(submissions):
	result = {}
	if not _available("CRM Deal"):
		return result
	fields = ["name"]
	if frappe.db.has_column("CRM Deal", "optin_submission"):
		fields.append("optin_submission")
	if _has_link("CRM Deal"):
		fields.append("optin_network")
	for row in frappe.get_list(
		"CRM Deal",
		fields=fields,
		limit_page_length=0,
		ignore_permissions=True,
	):
		candidates = {
			value
			for value in (
				network_name(row.get("optin_network")),
				submissions.get(row.get("optin_submission")),
			)
			if value
		}
		if len(candidates) > 1:
			continue
		slug = next(iter(candidates), "")
		if slug:
			result[row.name] = slug
			_set_if_empty("CRM Deal", row.name, slug)
	return result


def _backfill_leads():
	if not _available("CRM Lead") or not _has_link("CRM Lead"):
		return
	for row in frappe.get_list(
		"CRM Lead",
		fields=["name", "optin_network", "optin_network_slug"],
		limit_page_length=0,
		ignore_permissions=True,
	):
		_set_if_empty("CRM Lead", row.name, row.get("optin_network") or row.get("optin_network_slug"))


def _backfill_contracts(deals, quotations):
	if not _available("CRM Contract"):
		return
	fields = ["name", "network_slug", "deal"]
	if frappe.db.has_column("CRM Contract", "quote"):
		fields.append("quote")
	if _has_link("CRM Contract"):
		fields.append("optin_network")
	for row in frappe.get_list(
		"CRM Contract",
		fields=fields,
		limit_page_length=0,
		ignore_permissions=True,
	):
		candidates = {
			value
			for value in (
				network_name(row.get("network_slug")),
				deals.get(row.get("deal")),
				quotations.get(row.get("quote")),
			)
			if value
		}
		if len(candidates) > 1:
			continue
		slug = next(iter(candidates), "")
		_set_if_empty("CRM Contract", row.name, slug)


def _backfill_quotations(deals, submissions):
	if not _available("Quotation"):
		return
	fields = ["name"]
	if frappe.db.has_column("Quotation", "crm_deal"):
		fields.append("crm_deal")
	if frappe.db.has_column("Quotation", "crm_optin_submission"):
		fields.append("crm_optin_submission")
	if _has_link("Quotation"):
		fields.append("optin_network")
	for row in frappe.get_list(
		"Quotation",
		fields=fields,
		limit_page_length=0,
		ignore_permissions=True,
	):
		candidates = {
			value
			for value in (
				network_name(row.get("optin_network")),
				deals.get(row.get("crm_deal")),
				submissions.get(row.get("crm_optin_submission")),
			)
			if value
		}
		if len(candidates) == 1:
			_set_if_empty("Quotation", row.name, next(iter(candidates)))


def _quotation_networks(deals, submissions):
	result = {}
	if not _available("Quotation") or not _has_link("Quotation"):
		return result
	fields = ["name", "optin_network"]
	for fieldname in ("crm_deal", "crm_optin_submission"):
		if frappe.db.has_column("Quotation", fieldname):
			fields.append(fieldname)
	for row in frappe.get_list("Quotation", fields=fields, limit_page_length=0, ignore_permissions=True):
		candidates = {
			value
			for value in (
				network_name(row.get("optin_network")),
				deals.get(row.get("crm_deal")),
				submissions.get(row.get("crm_optin_submission")),
			)
			if value
		}
		if len(candidates) == 1:
			result[row.name] = next(iter(candidates))
	return result


def _backfill_orders(submissions, deals, quotations):
	if not _available("Sales Order"):
		return
	fields = ["name"]
	for fieldname in ("crm_optin_submission", "crm_deal", "crm_optin_quotation", "quotation"):
		if frappe.db.has_column("Sales Order", fieldname):
			fields.append(fieldname)
	if _has_link("Sales Order"):
		fields.append("optin_network")
	for row in frappe.get_list("Sales Order", fields=fields, limit_page_length=0, ignore_permissions=True):
		candidates = {
			value
			for value in (
				submissions.get(row.get("crm_optin_submission")),
				deals.get(row.get("crm_deal")),
				quotations.get(row.get("crm_optin_quotation")),
				quotations.get(row.get("quotation")),
			)
			if value
		}
		current = network_name(row.get("optin_network"))
		if len(candidates) > 1 or (current and candidates and current not in candidates):
			continue
		_set_if_empty("Sales Order", row.name, next(iter(candidates), ""))


def _backfill_invoices(deals, quotations):
	if not _available("Sales Invoice"):
		return
	fields = ["name"]
	for fieldname in ("crm_optin_submission", "crm_deal", "crm_quotation"):
		if frappe.db.has_column("Sales Invoice", fieldname):
			fields.append(fieldname)
	if _has_link("Sales Invoice"):
		fields.append("optin_network")
	for row in frappe.get_list(
		"Sales Invoice",
		fields=fields,
		limit_page_length=0,
		ignore_permissions=True,
	):
		candidates = {
			value
			for value in (
				quotations.get(row.get("crm_quotation")),
				deals.get(row.get("crm_deal")),
				submissions.get(row.get("crm_optin_submission")),
			)
			if value
		}
		current = network_name(row.get("optin_network"))
		if len(candidates) > 1 or (current and candidates and current not in candidates):
			continue
		slug = next(iter(candidates), "")
		_set_if_empty("Sales Invoice", row.name, slug)


def _backfill_payments():
	if not _available("Payment Entry") or not _has_link("Payment Entry"):
		return
	if not _available("Sales Invoice") or not _has_link("Sales Invoice"):
		return
	for row in frappe.get_list(
		"Payment Entry", fields=["name", "optin_network"], limit_page_length=0, ignore_permissions=True
	):
		if row.get("optin_network"):
			continue
		try:
			payment = frappe.get_doc("Payment Entry", row.name)
			networks = set()
			for reference in payment.references or []:
				if reference.reference_doctype != "Sales Invoice":
					continue
				slug = frappe.utils.cstr(
					frappe.db.get_value("Sales Invoice", reference.reference_name, "optin_network") or ""
				).strip()
				if slug:
					networks.add(slug)
			if len(networks) == 1:
				_set_if_empty("Payment Entry", row.name, next(iter(networks)))
		except Exception:
			continue


def _backfill_deal_linked_docs(deals):
	for doctype in ("CRM Onboarding Request", "CRM Partner Rebate Voucher", "CRM Sales Commission"):
		if not _available(doctype) or not _has_link(doctype):
			continue
		for row in frappe.get_list(
			doctype, fields=["name", "optin_network", "deal"], limit_page_length=0, ignore_permissions=True
		):
			_set_if_empty(doctype, row.name, deals.get(row.get("deal")))


def _add_conflict(conflicts, doctype, name, sources):
	"""Append populated but unresolved or contradictory Network references."""
	raw = {key: frappe.utils.cstr(value or "").strip() for key, value in sources.items() if value}
	values = {key: network_name(value) for key, value in raw.items()}
	unique = set(values.values()) - {""}
	if len(unique) > 1 or any(not value for value in values.values()):
		conflicts.append({"doctype": doctype, "name": name, "sources": raw})
	return conflicts


def collect_conflict_inventory():
	"""Read-only report of records whose canonical Network sources disagree."""
	conflicts = []
	def add(doctype, name, sources):
		_add_conflict(conflicts, doctype, name, sources)

	submissions = {}
	if _available("CRM Opt-In Submission"):
		fields = ["name", "network_slug"]
		if _has_link("CRM Opt-In Submission"):
			fields.append("optin_network")
		for row in frappe.get_all("CRM Opt-In Submission", fields=fields, limit_page_length=0):
			add("CRM Opt-In Submission", row.name, {"optin_network": row.get("optin_network"), "network_slug": row.get("network_slug")})
			values = {network_name(row.get("optin_network")), network_name(row.get("network_slug"))} - {""}
			if len(values) == 1:
				submissions[row.name] = next(iter(values))

	deals = {}
	if _available("CRM Deal"):
		fields = ["name"]
		if frappe.db.has_column("CRM Deal", "optin_submission"):
			fields.append("optin_submission")
		if _has_link("CRM Deal"):
			fields.append("optin_network")
		for row in frappe.get_all("CRM Deal", fields=fields, limit_page_length=0):
			source = submissions.get(row.get("optin_submission"))
			add("CRM Deal", row.name, {"optin_network": row.get("optin_network"), "submission": source})
			values = {network_name(row.get("optin_network")), network_name(source)} - {""}
			if len(values) == 1:
				deals[row.name] = next(iter(values))

	quotations = {}
	if _available("Quotation"):
		fields = ["name"]
		for fieldname in ("crm_deal", "crm_optin_submission"):
			if frappe.db.has_column("Quotation", fieldname):
				fields.append(fieldname)
		if _has_link("Quotation"):
			fields.append("optin_network")
		for row in frappe.get_all("Quotation", fields=fields, limit_page_length=0):
			add("Quotation", row.name, {
				"optin_network": row.get("optin_network"),
				"deal": deals.get(row.get("crm_deal")),
				"submission": submissions.get(row.get("crm_optin_submission")),
			})
			values = {
				network_name(row.get("optin_network")),
				network_name(deals.get(row.get("crm_deal"))),
				network_name(submissions.get(row.get("crm_optin_submission"))),
			} - {""}
			if len(values) == 1:
				quotations[row.name] = next(iter(values))

	for doctype, fields in (
		("CRM Contract", ("network_slug", "deal", "quote")),
		("Sales Order", ("crm_optin_submission", "crm_deal", "crm_optin_quotation", "quotation")),
		("Sales Invoice", ("crm_optin_submission", "crm_deal", "crm_quotation")),
	):
		if not _available(doctype):
			continue
		selected = ["name"]
		for fieldname in (*fields, "optin_network"):
			if frappe.db.has_column(doctype, fieldname):
				selected.append(fieldname)
		for row in frappe.get_all(doctype, fields=selected, limit_page_length=0):
			sources = {"optin_network": row.get("optin_network")}
			for fieldname in fields:
				value = row.get(fieldname)
				if fieldname == "network_slug":
					sources[fieldname] = value
				elif fieldname == "crm_optin_submission":
					sources[fieldname] = submissions.get(value)
				elif fieldname == "crm_deal":
					sources[fieldname] = deals.get(value)
				elif fieldname in ("crm_optin_quotation", "quotation", "crm_quotation", "quote"):
					sources[fieldname] = quotations.get(value)
			add(doctype, row.name, sources)

	if _available("Payment Entry"):
		fields = ["name"]
		if _has_link("Payment Entry"):
			fields.append("optin_network")
		for row in frappe.get_all("Payment Entry", fields=fields, limit_page_length=0):
			sources = {"optin_network": row.get("optin_network")}
			try:
				payment = frappe.get_doc("Payment Entry", row.name)
				for index, reference in enumerate(payment.references or []):
					if reference.reference_doctype == "Sales Invoice":
						sources[f"invoice_{index + 1}"] = frappe.db.get_value(
							"Sales Invoice", reference.reference_name, "optin_network"
						)
			except Exception:
				continue
			add("Payment Entry", row.name, sources)

	for doctype in ("CRM Onboarding Request", "CRM Partner Rebate Voucher", "CRM Sales Commission"):
		if not _available(doctype):
			continue
		fields = ["name", "deal"]
		if _has_link(doctype):
			fields.append("optin_network")
		for row in frappe.get_all(doctype, fields=fields, limit_page_length=0):
			add(doctype, row.name, {"optin_network": row.get("optin_network"), "deal": deals.get(row.get("deal"))})
	return conflicts


def execute():
	_create_link_fields()
	conflicts = collect_conflict_inventory()
	if conflicts:
		frappe.log_error(
			title="Opt-In Network link conflicts require review",
			message=frappe.as_json(conflicts, indent=2),
		)
	submissions = _network_by_submission()
	_backfill_leads()
	deals = _network_by_deal(submissions)
	_backfill_quotations(deals, submissions)
	quotations = _quotation_networks(deals, submissions)
	_backfill_orders(submissions, deals, quotations)
	_backfill_contracts(deals, quotations)
	_backfill_invoices(deals, quotations)
	_backfill_deal_linked_docs(deals)
	_backfill_payments()
	for doctype in _LINK_LABELS:
		if _available(doctype):
			try:
				frappe.clear_cache(doctype=doctype)
			except Exception:
				pass
