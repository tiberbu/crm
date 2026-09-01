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
					}
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
		slug = network_name(row.get("optin_network") or row.get("network_slug"))
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
		slug = network_name(row.get("optin_network")) or submissions.get(row.get("optin_submission"))
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
		slug = network_name(row.get("network_slug")) or deals.get(row.get("deal")) or quotations.get(
			row.get("quote")
		)
		_set_if_empty("CRM Contract", row.name, slug)


def _backfill_quotations(deals):
	if not _available("Quotation"):
		return
	fields = ["name"]
	if frappe.db.has_column("Quotation", "crm_deal"):
		fields.append("crm_deal")
	if _has_link("Quotation"):
		fields.append("optin_network")
	for row in frappe.get_list(
		"Quotation",
		fields=fields,
		limit_page_length=0,
		ignore_permissions=True,
	):
		_set_if_empty("Quotation", row.name, deals.get(row.get("crm_deal")))


def _quotation_networks():
	result = {}
	if not _available("Quotation") or not _has_link("Quotation"):
		return result
	for row in frappe.get_list(
		"Quotation", fields=["name", "optin_network"], limit_page_length=0, ignore_permissions=True
	):
		slug = network_name(row.get("optin_network"))
		if slug:
			result[row.name] = slug
	return result


def _backfill_invoices(deals, quotations):
	if not _available("Sales Invoice"):
		return
	fields = ["name"]
	for fieldname in ("crm_deal", "crm_quotation"):
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
		slug = quotations.get(row.get("crm_quotation")) or deals.get(row.get("crm_deal"))
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
			slug = ""
			for reference in payment.references or []:
				if reference.reference_doctype != "Sales Invoice":
					continue
				slug = frappe.utils.cstr(
					frappe.db.get_value("Sales Invoice", reference.reference_name, "optin_network") or ""
				).strip()
				if slug:
					break
			_set_if_empty("Payment Entry", row.name, slug)
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


def execute():
	_create_link_fields()
	submissions = _network_by_submission()
	_backfill_leads()
	deals = _network_by_deal(submissions)
	_backfill_quotations(deals)
	quotations = _quotation_networks()
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
