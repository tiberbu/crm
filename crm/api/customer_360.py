"""
crm/api/customer_360.py — Customer 360 aggregator (partner, orders, provisioning, billing)

Story: customer-360 (planning artifact _bmad-output/customer-360)

One org-centric round-trip so an admin can trace everything about a customer from a single
Deal (inquiry-call scenario) or from the Customer 360 nav page (customer without a deal):

- partner attribution (Value Express opt-in network and/or legacy CRM Partner via lead)
- customer-wide package payment state + pending orders
- per-facility provisioning status (memberships) + per-deal onboarding requests
- quotes, orders and billing (invoices, outstanding, payments)
- facility scope: one facility's records (attributed with the CX portal rule), with the
  owner organization's full picture one toggle away
  (planning artifact _bmad-output/customer-360-facility-scope)

Rules enforced (mirror crm/api/lifecycle.py):
- @frappe.whitelist() on the public API.
- frappe.get_list() for every SELECT — no frappe.db.sql() SELECTs, no frappe.get_all().
- No ignore_permissions: the deal-scoped entry is gated by the caller's CRM Deal read
  permission (same contract as get_deal_lifecycle); the org-only entry and search are
  manager-gated. Every sub-resource read is independently permission-scoped; a caller
  who can read the Deal but not a sub-doctype sees that link as None (or []) rather
  than an exception.
- Custom fields are only selected when frappe.db.has_column() confirms them.
- No f-strings in log/error messages — % formatting only.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr, date_diff, getdate, nowdate

from crm.utils.portal_commercial import attribute_facilities
from crm.utils.token_facility import facility_mfls_for_fid

MANAGER_ROLES = ("System Manager", "Sales Manager")


def _is_manager() -> bool:
	return any(role in MANAGER_ROLES for role in frappe.get_roles())


def _can_read(doctype: str) -> bool:
	"""True if the caller has doctype-level read — prevents get_list from raising."""
	return bool(frappe.has_permission(doctype, "read"))


@frappe.whitelist()
def get_customer_360(
	organization: str | None = None,
	deal: str | None = None,
	facility: str | None = None,
	scope: str | None = None,
) -> dict:
	"""
	Return the 360-degree picture for a customer: deal-scoped, org-centric or facility-scoped.

	    {
	      "organization": {...} | None,
	      "deal": {...} | None,
	      "partners": [{kind, ref, name, ...}],
	      "summary": {package_paid, paid_amount, open_orders, open_amount,
	             sites_total, sites_live, outstanding, invoices, quotes},
	      "orders": [...], "quotes": [...], "invoices": [...], "payments": [...],
	      "facilities": [...], "onboarding": [...], "deals": [...],
	      "scope": {mode, facility, can_widen, unattributed}
	    }

	``facility`` (a CRM Pre-Qualified Facility name) opens the facility lens: ``scope`` defaults
	to ``"facility"`` and keeps only that facility's records; ``scope="organization"`` widens to
	its owner organization's full picture. Orders, quotes and invoices are attributed to
	facilities with the CX portal rule (``attribute_facilities``, SPEC 4.1).

	Missing links resolve to None/[]; an incomplete chain never raises.
	"""
	organization = (organization or "").strip()
	deal = (deal or "").strip()
	facility = (facility or "").strip()
	if not organization and not deal and not facility:
		frappe.throw(_("Missing customer reference"), frappe.ValidationError)

	if deal:
		# Same contract as crm/api/lifecycle.py:get_deal_lifecycle.
		if not frappe.has_permission("CRM Deal", "read", deal):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		deal_doc = frappe.get_doc("CRM Deal", deal)
		if not organization:
			organization = deal_doc.organization or ""
	elif not _is_manager():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	facility_ref = None
	if facility:
		facility_ref = _resolve_facility_ref(facility)
		if not facility_ref:
			frappe.throw(_("Facility not found"), frappe.DoesNotExistError)
		if not organization and not deal:
			organization = facility_ref["organization"] or ""
	mode = "facility" if facility_ref and (scope or "facility") != "organization" else "organization"
	if facility_ref and not organization and not deal:
		mode = "facility"  # no owner to widen to

	organization_data = _resolve_organization(organization)
	deal_data = _resolve_deal(deal) if deal else None
	all_facilities = _resolve_facilities(organization)
	if facility_ref and not any(row["name"] == facility_ref["name"] for row in all_facilities):
		all_facilities.extend(_facility_rows([facility_ref["name"]]))
	org_deals = [deal] if deal else _org_deal_names(organization)

	facility_keys: set[str] = set()
	facility_deals: list[str] = []
	if facility_ref:
		facility_keys = _facility_keys(facility_ref)
		facility_deals = _facility_deal_names(facility_ref, facility_keys, org_deals, all_facilities)
	finance_deals = list(dict.fromkeys(org_deals + facility_deals))
	customers = _billing_customers(organization, finance_deals, all_facilities)
	account_mfls = [row["mfl_code"] for row in all_facilities if row.get("mfl_code")]
	orders, quotes, invoices, payments = _resolve_finance(finance_deals, customers, account_mfls)

	unattributed = {"orders": 0, "quotes": 0, "invoices": 0}
	if mode == "facility":
		orders, unattributed["orders"] = _scope_rows(orders, facility_keys)
		quotes, unattributed["quotes"] = _scope_rows(quotes, facility_keys)
		invoices, unattributed["invoices"] = _scope_rows(invoices, facility_keys)
		in_scope = {row["name"] for row in invoices}
		payments = [row for row in payments if in_scope.intersection(row.get("invoices") or [])]
		facilities = [row for row in all_facilities if row["name"] == facility_ref["name"]]
		networks = [m["network"] for row in facilities for m in row["memberships"] if m.get("network")]
		partners = _resolve_partners(None, organization, deal_names=facility_deals, networks=networks)
		deals = _resolve_deals(organization, names=facility_deals)
		onboarding = _resolve_onboarding(facility_deals)
	else:
		facilities = all_facilities
		partners = _resolve_partners(deal, organization)
		deals = _resolve_deals(organization)
		onboarding = _resolve_onboarding(org_deals)

	return {
		"organization": organization_data,
		"deal": deal_data,
		"partners": partners,
		"summary": _build_summary(orders, invoices, facilities, quotes),
		"orders": orders,
		"quotes": quotes,
		"invoices": invoices,
		"payments": payments,
		"facilities": facilities,
		"onboarding": onboarding,
		"deals": deals,
		"scope": {
			"mode": mode,
			"facility": facility_ref,
			"can_widen": bool(facility_ref and organization_data),
			"unattributed": unattributed,
		},
	}


@frappe.whitelist()
def search_customer_360(query: str, limit: int = 10) -> dict:
	"""Manager-gated debounced-search backend for the Customer 360 nav page."""
	query = (query or "").strip()
	if len(query) < 3:
		return {"organizations": [], "deals": [], "facilities": []}
	if not _is_manager():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	limit = max(1, min(int(limit or 10), 25))
	like = "%%%s%%" % query

	result = {"organizations": [], "deals": [], "facilities": []}
	if _can_read("CRM Organization"):
		rows = frappe.get_list(
			"CRM Organization",
			filters={"organization_name": ["like", like]},
			fields=["name", "organization_name"],
			order_by="creation desc",
			limit_page_length=limit,
		)
		result["organizations"] = [{"name": r.name, "label": r.organization_name or r.name} for r in rows]
	if _can_read("CRM Deal"):
		rows = frappe.get_list(
			"CRM Deal",
			filters={"name": ["like", like]},
			fields=["name", "organization", "status", "deal_value"],
			order_by="creation desc",
			limit_page_length=limit,
		)
		result["deals"] = [
			{
				"name": r.name,
				"organization": r.organization,
				"status": r.status,
				"deal_value": r.deal_value,
			}
			for r in rows
		]
		if _can_read("CRM Organization"):
			org_names = [
				row.name
				for row in frappe.get_list(
					"CRM Organization",
					filters={"organization_name": ["like", like]},
					fields=["name"],
					limit_page_length=limit,
				)
			]
			if org_names:
				existing = {row["name"] for row in result["deals"]}
				rows = frappe.get_list(
					"CRM Deal",
					filters={"organization": ["in", org_names]},
					fields=["name", "organization", "status", "deal_value"],
					order_by="creation desc",
					limit_page_length=limit,
				)
				for r in rows:
					if r.name not in existing:
						result["deals"].append(
							{
								"name": r.name,
								"organization": r.organization,
								"status": r.status,
								"deal_value": r.deal_value,
							}
						)
						existing.add(r.name)
						if len(result["deals"]) >= limit:
							break
	if _can_read("CRM Pre-Qualified Facility"):
		# One query: a facility matches on its name, MFL code or Facility ID (HFR FID).
		rows = frappe.get_list(
			"CRM Pre-Qualified Facility",
			or_filters={
				"facility_name": ["like", like],
				"mfl_code": ["like", like],
				"hfr_facility_id": ["like", like],
			},
			fields=["name", "facility_name", "mfl_code", "hfr_facility_id", "organization"],
			order_by="creation desc",
			limit_page_length=limit,
		)
		org_map = _org_doc_names([row.organization for row in rows if row.organization])
		result["facilities"] = [
			{
				"name": r.name,
				"label": r.facility_name or r.name,
				"mfl_code": r.mfl_code,
				"hfr_facility_id": r.get("hfr_facility_id") or "",
				"organization": org_map.get(r.organization),
				"organization_name": r.organization or "",
			}
			for r in rows
		]
	return result


def _org_doc_names(organization_labels: list[str]) -> dict:
	"""Map organization_name (display label) -> CRM Organization document name."""
	labels = sorted({label for label in organization_labels if label})
	if not labels or not _can_read("CRM Organization"):
		return {}
	rows = frappe.get_list(
		"CRM Organization",
		filters={"organization_name": ["in", labels]},
		fields=["name", "organization_name"],
		limit_page_length=0,
	)
	return {row.organization_name: row.name for row in rows}


# ---------------------------------------------------------------------------
# Private resolvers — each is a permission-scoped frappe.get_list() read.
# ---------------------------------------------------------------------------


def _org_name(organization: str) -> str:
	"""Normalise an org reference to its organization_name (searchable label)."""
	if not organization:
		return ""
	if frappe.db.exists("CRM Organization", organization):
		return frappe.db.get_value("CRM Organization", organization, "organization_name") or organization
	return organization


def _resolve_organization(organization: str) -> dict | None:
	if not organization or not _can_read("CRM Organization"):
		return None
	doc = frappe.get_doc("CRM Organization", organization)
	return {
		"name": doc.name,
		"organization_name": doc.organization_name or doc.name,
		"industry": doc.industry,
		"territory": doc.territory,
		"website": doc.website,
		"no_of_employees": doc.no_of_employees,
		"annual_revenue": doc.annual_revenue,
		"currency": doc.currency,
	}


def _resolve_deal(deal: str) -> dict | None:
	if not deal or not _can_read("CRM Deal"):
		return None
	doc = frappe.get_doc("CRM Deal", deal)
	return {
		"name": doc.name,
		"status": doc.status,
		"deal_value": doc.deal_value,
		"currency": doc.currency,
		"deal_owner": doc.deal_owner,
		"email": doc.email,
		"phone": doc.phone,
		"mobile_no": doc.mobile_no,
		"creation": doc.creation,
	}


def _resolve_partners(
	deal: str | None, organization: str, deal_names: list[str] | None = None, networks=()
) -> list[dict]:
	"""Partner attribution for one deal, the union across the customer's deals, or — in
	facility scope — the facility's membership networks plus the facility's deals."""
	partners: list[dict] = []
	seen: set[str] = set()

	def add_network(ref: str) -> None:
		if not ref or ref in seen or not _can_read("CRM Opt-In Network"):
			return
		doc = frappe.db.get_value(
			"CRM Opt-In Network",
			ref,
			["name", "display_name", "partner_id", "contact_email", "logo_url"],
			as_dict=True,
		)
		if not doc:
			return
		seen.add(ref)
		partners.append(
			{
				"kind": "network",
				"ref": ref,
				"name": doc.display_name or doc.name,
				"partner_id": doc.partner_id,
				"contact_email": doc.contact_email,
				"display_name": doc.display_name,
				"logo_url": doc.logo_url,
			}
		)

	def add_legacy(ref: str) -> None:
		if not ref or ref in seen or not _can_read("CRM Partner"):
			return
		doc = frappe.db.get_value(
			"CRM Partner", ref, ["name", "partner_name", "partner_type", "partner_rm"], as_dict=True
		)
		if not doc:
			return
		seen.add(ref)
		partners.append(
			{
				"kind": "legacy",
				"ref": ref,
				"name": doc.partner_name or doc.name,
				"partner_type": doc.partner_type,
				"partner_rm": doc.partner_rm,
			}
		)

	def from_deal(deal_name: str) -> None:
		if not _can_read("CRM Deal"):
			return
		row = frappe.db.get_value(
			"CRM Deal",
			deal_name,
			["organization", "lead"]
			+ (["optin_network"] if frappe.db.has_column("CRM Deal", "optin_network") else []),
			as_dict=True,
		)
		if not row:
			return
		if row.get("optin_network"):
			add_network(row.optin_network)
		if row.get("lead") and _can_read("CRM Lead"):
			partner = frappe.db.get_value("CRM Lead", row.lead, "partner")
			if partner:
				add_legacy(partner)

	for network in networks or ():
		add_network(network)
	if deal_names is not None:
		for deal_name in deal_names:
			from_deal(deal_name)
	elif deal:
		from_deal(deal)
	else:
		for deal_name in _org_deal_names(organization):
			from_deal(deal_name)
	return partners


def _org_deal_names(organization: str) -> list[str]:
	if not organization or not _can_read("CRM Deal"):
		return []
	rows = frappe.get_list(
		"CRM Deal",
		filters={"organization": organization},
		fields=["name"],
		order_by="creation desc",
		limit_page_length=0,
	)
	return [row.name for row in rows]


def _resolve_deals(organization: str, names: list[str] | None = None) -> list[dict]:
	"""The organization's deals, or (facility scope) exactly the named deals."""
	if not _can_read("CRM Deal"):
		return []
	if names is not None:
		if not names:
			return []
		deal_filters = {"name": ["in", names]}
	elif organization:
		deal_filters = {"organization": organization}
	else:
		return []
	rows = frappe.get_list(
		"CRM Deal",
		filters=deal_filters,
		fields=[
			"name",
			"status",
			"deal_value",
			"currency",
			"deal_owner",
			"closed_date",
			"source",
			"creation",
		],
		order_by="creation desc",
		limit_page_length=0,
	)
	# Partner attribution per deal (network only; the cheap, current path).
	network_field = "optin_network" if frappe.db.has_column("CRM Deal", "optin_network") else None
	network_names = {}
	if network_field:
		with_net = frappe.get_list(
			"CRM Deal",
			filters={**deal_filters, network_field: ["is", "set"]},
			fields=["name", network_field],
			limit_page_length=0,
		)
		if with_net and _can_read("CRM Opt-In Network"):
			for row in with_net:
				display = frappe.db.get_value("CRM Opt-In Network", row.get(network_field), "display_name")
				if display:
					network_names[row.name] = display
	return [
		{
			"name": r.name,
			"status": r.status,
			"deal_value": r.deal_value,
			"currency": r.currency,
			"deal_owner": r.deal_owner,
			"closed_date": r.closed_date,
			"source": r.source,
			"partner": network_names.get(r.name),
		}
		for r in rows
	]


ITEM_MFL_FIELD = "crm_optin_facility_mfl_code"
HEADER_MFL_FIELD = "crm_token_facility_mfl"


def _resolve_finance(deals: list[str], customer_names: list[str], account_mfls: list[str]):
	"""Orders, quotes, invoices and payments for the deals and billing customers.

	Every order, quote and invoice row carries ``facility_mfls`` (the CX portal rule,
	SPEC 4.1); every payment carries the ``invoices`` it settles.
	"""
	if not deals and not customer_names:
		return [], [], [], []

	# Opt-In Submissions for these deals (orders and invoices are stamped with them).
	ois_names = []
	if deals and _can_read("CRM Opt-In Submission"):
		ois_names = [
			row.name
			for row in frappe.get_list(
				"CRM Opt-In Submission",
				filters={"deal": ["in", deals]},
				fields=["name"],
				limit_page_length=0,
			)
		]

	quotes = _resolve_quotes(deals, customer_names)
	quote_names = [row["name"] for row in quotes]
	orders = _resolve_orders(ois_names, quote_names, customer_names)
	invoices = _resolve_invoices(ois_names, quote_names, customer_names)
	payments = _resolve_payments(customer_names)
	refs = _payment_invoice_refs([row["name"] for row in payments])
	for row in payments:
		row["invoices"] = refs.get(row["name"], [])

	ois_mfls = _ois_facility_mfls(
		sorted({row.get("_ois") for row in orders + quotes + invoices if row.get("_ois")} | set(ois_names))
	)
	for doctype, item_doctype, rows in (
		("Quotation", "Quotation Item", quotes),
		("Sales Order", "Sales Order Item", orders),
		("Sales Invoice", "Sales Invoice Item", invoices),
	):
		item_mfls = _item_facility_mfls(doctype, item_doctype, [row["name"] for row in rows])
		for row in rows:
			row["facility_mfls"] = attribute_facilities(
				row.pop("_header_mfl", ""),
				item_mfls.get(row["name"], []),
				ois_mfls.get(row.pop("_ois", "") or "", []),
				account_mfls,
			)
	return orders, quotes, invoices, payments


def _optional_columns(doctype: str, columns) -> list[str]:
	return [column for column in columns if frappe.db.has_column(doctype, column)]


def _collect(doctype: str, candidates: list[dict], fields: list[str], limit: int) -> list:
	"""Run each candidate filter and keep the first occurrence of every document."""
	rows, seen = [], set()
	for filters in candidates:
		for row in frappe.get_list(
			doctype, filters=filters, fields=fields, order_by="creation desc", limit_page_length=limit
		):
			if row.name not in seen:
				rows.append(row)
				seen.add(row.name)
	return rows


def _resolve_quotes(deals: list[str], customer_names: list[str]) -> list[dict]:
	if not _can_read("Quotation"):
		return []
	candidates = []
	if deals and frappe.db.has_column("Quotation", "crm_deal"):
		candidates.append({"crm_deal": ["in", deals]})
	if customer_names:
		candidates.append({"quotation_to": "Customer", "party_name": ["in", customer_names]})
	if not candidates:
		return []
	fields = ["name", "transaction_date", "valid_till", "grand_total", "currency", "status", "docstatus"]
	fields += _optional_columns("Quotation", (HEADER_MFL_FIELD, "crm_optin_submission"))
	return [
		{
			"name": row.name,
			"transaction_date": row.transaction_date,
			"valid_till": row.valid_till,
			"grand_total": row.grand_total,
			"currency": row.currency,
			"status": row.status,
			"docstatus": row.docstatus,
			"_header_mfl": row.get(HEADER_MFL_FIELD),
			"_ois": row.get("crm_optin_submission"),
		}
		for row in _collect("Quotation", candidates, fields, 200)
	]


def _resolve_orders(
	ois_names: list[str], quote_names: list[str], customer_names: list[str] = ()
) -> list[dict]:
	if not _can_read("Sales Order"):
		return []
	candidates = []
	if ois_names and frappe.db.has_column("Sales Order", "crm_optin_submission"):
		candidates.append({"crm_optin_submission": ["in", ois_names]})
	if quote_names and frappe.db.has_column("Sales Order", "crm_optin_quotation"):
		candidates.append({"crm_optin_quotation": ["in", quote_names]})
	if customer_names:
		# Value Express draft orders are raised against the billing customer only.
		candidates.append({"customer": ["in", list(customer_names)], "docstatus": ["<", 2]})
	if not candidates:
		return []
	fields = ["name", "transaction_date", "grand_total", "currency", "status", "per_billed"]
	fields += _optional_columns(
		"Sales Order", ("crm_token_facility_mfl", "crm_token_package_item", "crm_optin_submission")
	)
	return [
		{
			"name": row.name,
			"transaction_date": row.transaction_date,
			"grand_total": row.grand_total,
			"currency": row.currency,
			"status": row.status,
			"per_billed": row.per_billed,
			"open": (row.per_billed or 0) < 100,
			"crm_token_facility_mfl": row.get("crm_token_facility_mfl"),
			"crm_token_package_item": row.get("crm_token_package_item"),
			"_header_mfl": row.get(HEADER_MFL_FIELD),
			"_ois": row.get("crm_optin_submission"),
		}
		for row in _collect("Sales Order", candidates, fields, 200)
	]


def _resolve_invoices(ois_names: list[str], quote_names: list[str], customer_names: list[str]) -> list[dict]:
	if not _can_read("Sales Invoice"):
		return []
	candidates = []
	if ois_names and frappe.db.has_column("Sales Invoice", "crm_optin_submission"):
		candidates.append({"crm_optin_submission": ["in", ois_names]})
	if quote_names and frappe.db.has_column("Sales Invoice", "crm_quotation"):
		candidates.append({"crm_quotation": ["in", quote_names]})
	if customer_names:
		candidates.append({"customer": ["in", customer_names]})
	if not candidates:
		return []
	fields = [
		"name",
		"creation",
		"grand_total",
		"currency",
		"outstanding_amount",
		"due_date",
		"docstatus",
		"status",
	]
	fields += _optional_columns("Sales Invoice", (HEADER_MFL_FIELD, "crm_optin_submission"))
	today = nowdate()
	return [
		{
			"name": row.name,
			"creation": row.creation,
			"grand_total": row.grand_total,
			"currency": row.currency,
			"outstanding": row.outstanding_amount,
			"due_date": row.due_date,
			"docstatus": row.docstatus,
			"status": row.status,
			"paid": row.docstatus == 1 and (row.outstanding_amount or 0) <= 0,
			"days_overdue": max(0, int(date_diff(today, getdate(row.due_date)))) if row.due_date else 0,
			"_header_mfl": row.get(HEADER_MFL_FIELD),
			"_ois": row.get("crm_optin_submission"),
		}
		for row in _collect("Sales Invoice", candidates, fields, 200)
	]


def _resolve_payments(customer_names: list[str]) -> list[dict]:
	"""Received payments whose party is one of the customer's ERPNext Customers.

	Payment Entry has no `customer` column — the billing party lives in the
	dynamic `party`/`party_type` pair.
	"""
	if not customer_names or not _can_read("Payment Entry"):
		return []
	rows = frappe.get_list(
		"Payment Entry",
		filters={
			"payment_type": "Receive",
			"party_type": "Customer",
			"party": ["in", customer_names],
		},
		fields=["name", "posting_date", "paid_amount", "payment_type", "party"],
		order_by="posting_date desc",
		limit_page_length=100,
	)
	return [
		{
			"name": row.name,
			"posting_date": row.posting_date,
			"paid_amount": row.paid_amount,
			"payment_type": row.payment_type,
			"party": row.party,
		}
		for row in rows
	]


def _payment_invoice_refs(payment_names: list[str]) -> dict:
	"""Map each payment to the Sales Invoices it settles (read through the parent's permission)."""
	result: dict[str, list] = {}
	if not payment_names:
		return result
	for row in frappe.get_list(
		"Payment Entry",
		filters=[
			["name", "in", payment_names],
			["Payment Entry Reference", "reference_doctype", "=", "Sales Invoice"],
		],
		fields=["name", "`tabPayment Entry Reference`.`reference_name` as reference_name"],
		limit_page_length=0,
	):
		bucket = result.setdefault(row.name, [])
		if row.get("reference_name") and row.reference_name not in bucket:
			bucket.append(row.reference_name)
	return result


def _item_facility_mfls(doctype: str, item_doctype: str, names: list[str]) -> dict:
	"""Map each document to the facility codes on its item lines (one read, parent-permissioned)."""
	result: dict[str, list] = {}
	if not names or not frappe.db.has_column(item_doctype, ITEM_MFL_FIELD):
		return result
	for row in frappe.get_list(
		doctype,
		filters={"name": ["in", names]},
		fields=["name", "`tab%s`.`%s` as item_mfl" % (item_doctype, ITEM_MFL_FIELD)],
		limit_page_length=0,
	):
		code = cstr(row.get("item_mfl")).strip()
		bucket = result.setdefault(row.name, [])
		if code and code not in bucket:
			bucket.append(code)
	return result


def _ois_facility_mfls(ois_names: list[str]) -> dict:
	"""Map each Opt-In Submission to the facility codes in its facility snapshot."""
	if not ois_names or not _can_read("CRM Opt-In Submission"):
		return {}
	from crm.api.website_redirect import _submission_facilities

	result = {}
	for row in frappe.get_list(
		"CRM Opt-In Submission",
		filters={"name": ["in", ois_names]},
		fields=["name", "raw_json"],
		limit_page_length=0,
	):
		result[row.name] = [
			cstr(snapshot.get("mfl_code")).strip()
			for snapshot in _submission_facilities(row)
			if cstr(snapshot.get("mfl_code")).strip()
		]
	return result


def _billing_customers(organization: str, deals: list[str], facilities: list[dict]) -> list[str]:
	"""ERPNext Customers billed for this view: the deals' (and the org's) ``cx_customer`` plus
	the in-view facilities' membership customer (Partner Coupon / self-onboarding rows)."""
	names: set[str] = set()
	if frappe.db.has_column("CRM Deal", "cx_customer") and _can_read("CRM Deal"):
		candidates = []
		if organization:
			candidates.append({"organization": organization, "cx_customer": ["is", "set"]})
		if deals:
			candidates.append({"name": ["in", deals], "cx_customer": ["is", "set"]})
		for filters in candidates:
			for row in frappe.get_list(
				"CRM Deal", filters=filters, fields=["cx_customer"], limit_page_length=0
			):
				if row.get("cx_customer"):
					names.add(row.cx_customer)
	for row in facilities:
		for membership in row.get("memberships") or []:
			if membership.get("customer"):
				names.add(membership["customer"])
	return sorted(names)


def _scope_rows(rows: list[dict], facility_keys: set[str]) -> tuple[list[dict], int]:
	"""Keep the rows attributed to the facility; count the ones tied to no facility at all."""
	kept = [
		row
		for row in rows
		if any(cstr(mfl).strip().casefold() in facility_keys for mfl in row.get("facility_mfls") or [])
	]
	unattributed = sum(1 for row in rows if not row.get("facility_mfls"))
	return kept, unattributed


def _resolve_facility_ref(facility: str) -> dict | None:
	"""The selected facility's identity and owner organization (CRM Organization doc name)."""
	if not facility or not _can_read("CRM Pre-Qualified Facility"):
		return None
	rows = frappe.get_list(
		"CRM Pre-Qualified Facility",
		filters={"name": facility},
		fields=["name", "facility_name", "mfl_code", "hfr_facility_id", "organization"],
		limit_page_length=1,
	)
	if not rows:
		return None
	row = rows[0]
	org_label = row.get("organization") or ""
	return {
		"name": row.name,
		"facility_name": row.get("facility_name") or row.name,
		"mfl_code": row.get("mfl_code") or "",
		"hfr_facility_id": row.get("hfr_facility_id") or "",
		"organization": _org_doc_names([org_label]).get(org_label) if org_label else None,
		"organization_name": org_label,
	}


def _facility_keys(facility_ref: dict) -> set[str]:
	"""Casefolded MFL codes that identify the facility: its own plus every MFL CRM records
	for its Facility ID (older documents are keyed by MFL only)."""
	keys = {cstr(facility_ref.get("mfl_code")).strip().casefold()}
	if facility_ref.get("hfr_facility_id"):
		keys.update(mfl.casefold() for mfl in facility_mfls_for_fid(facility_ref["hfr_facility_id"]))
	keys.discard("")
	return keys


def _facility_deal_names(
	facility_ref: dict, facility_keys: set[str], org_deals: list[str], facilities: list[dict]
) -> list[str]:
	"""Deals whose facility table lists this facility (by MFL or Facility ID). When the owner
	has exactly one facility, every owner deal is that facility's deal."""
	if len(facilities) == 1 and facilities[0]["name"] == facility_ref["name"]:
		return list(org_deals)
	if not _can_read("CRM Deal"):
		return []
	candidates = []
	mfls = [facility_ref.get("mfl_code")] + [key for key in facility_keys]
	mfls = sorted({cstr(mfl).strip() for mfl in mfls if cstr(mfl).strip()})
	if mfls:
		candidates.append([["CRM Deal Facility", "mfl_code", "in", mfls]])
	if facility_ref.get("hfr_facility_id"):
		candidates.append([["CRM Deal Facility", "hfr_facility_id", "=", facility_ref["hfr_facility_id"]]])
	names: list[str] = []
	for filters in candidates:
		for row in frappe.get_list(
			"CRM Deal",
			filters=filters,
			fields=["name"],
			order_by="`tabCRM Deal`.`creation` desc",
			limit_page_length=0,
		):
			if row.name not in names:
				names.append(row.name)
	return names


def _resolve_facilities(organization: str) -> list[dict]:
	if not organization or not _can_read("CRM Pre-Qualified Facility"):
		return []
	return _facility_rows(None, organization_label=_org_name(organization))


def _facility_rows(names: list[str] | None, organization_label: str = "") -> list[dict]:
	"""Facility rows with their memberships, by organization label or by facility names."""
	if not _can_read("CRM Pre-Qualified Facility"):
		return []
	filters = {"name": ["in", names]} if names is not None else {"organization": organization_label}
	rows = frappe.get_list(
		"CRM Pre-Qualified Facility",
		filters=filters,
		fields=["name", "mfl_code", "facility_name", "keph_level", "is_self_onboarded", "hfr_facility_id"],
		order_by="creation desc",
		limit_page_length=100,
	)
	network_names = {}
	if rows and _can_read("CRM Opt-In Network"):
		for row in frappe.get_list(
			"CRM Opt-In Network", fields=["name", "display_name"], limit_page_length=0
		):
			network_names[row.name] = row.display_name or row.name
	facilities = []
	for row in rows:
		memberships = []
		try:
			doc = frappe.get_doc("CRM Pre-Qualified Facility", row.name)
		except frappe.DoesNotExistError:
			continue
		for m in doc.memberships:
			memberships.append(
				{
					"network": m.network,
					"display_name": network_names.get(m.network),
					"status": m.status,
					"go_live": bool(m.go_live),
					"opted_in": m.status == "Opted In",
					"self_onboarding": bool(getattr(m, "customer", None)),
					"customer": getattr(m, "customer", None) or None,
					"contact_name": m.contact_name,
					"contact_phone": m.contact_phone,
				}
			)
		facilities.append(
			{
				"name": row.name,
				"mfl_code": row.mfl_code,
				"hfr_facility_id": row.get("hfr_facility_id") or "",
				"facility_name": row.facility_name or row.name,
				"keph_level": row.keph_level,
				"is_self_onboarded": bool(row.is_self_onboarded),
				"memberships": memberships,
			}
		)
	return facilities


def _resolve_onboarding(deals: list[str]) -> list[dict]:
	if not deals or not _can_read("CRM Onboarding Request"):
		return []
	fields = ["name", "deal", "status", "approval_status", "careverse_provisioned_date"]
	rows = frappe.get_list(
		"CRM Onboarding Request",
		filters={"deal": ["in", deals]},
		fields=fields,
		order_by="creation desc",
		limit_page_length=50,
	)
	return [
		{
			"name": row.name,
			"deal": row.deal,
			"status": row.status,
			"approval_status": row.approval_status,
			"careverse_provisioned_date": row.careverse_provisioned_date,
		}
		for row in rows
	]


def _build_summary(
	orders: list[dict], invoices: list[dict], facilities: list[dict], quotes: list[dict] | None = None
) -> dict:
	submitted = [row for row in invoices if row["docstatus"] == 1]
	paid_invoices = [row for row in submitted if (row["outstanding"] or 0) <= 0]
	paid_amount = round(sum((row["grand_total"] or 0) - (row["outstanding"] or 0) for row in submitted), 2)
	outstanding = round(sum((row["outstanding"] or 0) for row in submitted), 2)
	open_orders = [row for row in orders if row["open"]]
	sites_total = 0
	sites_live = 0
	for facility in facilities:
		for membership in facility["memberships"]:
			if membership["status"] == "Declined":
				continue
			sites_total += 1
			if membership["opted_in"] and membership["go_live"]:
				sites_live += 1
	return {
		"package_paid": bool(paid_invoices),
		"paid_amount": paid_amount,
		"open_orders": len(open_orders),
		"open_amount": round(sum(row["grand_total"] or 0 for row in open_orders), 2),
		"sites_total": sites_total,
		"sites_live": sites_live,
		"outstanding": outstanding,
		"invoices": len(invoices),
		"quotes": len(quotes or []),
	}
