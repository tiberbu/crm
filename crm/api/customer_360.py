"""
crm/api/customer_360.py — Customer 360 aggregator (partner, orders, provisioning, billing)

Story: customer-360 (planning artifact _bmad-output/customer-360)

One org-centric round-trip so an admin can trace everything about a customer from a single
Deal (inquiry-call scenario) or from the Customer 360 nav page (customer without a deal):

- partner attribution (Value Express opt-in network and/or legacy CRM Partner via lead)
- customer-wide package payment state + pending orders
- per-facility provisioning status (memberships) + per-deal onboarding requests
- billing (invoices, outstanding, payments)

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
from frappe.utils import date_diff, getdate, nowdate

MANAGER_ROLES = ("System Manager", "Sales Manager")


def _is_manager() -> bool:
	return any(role in MANAGER_ROLES for role in frappe.get_roles())


def _can_read(doctype: str) -> bool:
	"""True if the caller has doctype-level read — prevents get_list from raising."""
	return bool(frappe.has_permission(doctype, "read"))


@frappe.whitelist()
def get_customer_360(organization: str = None, deal: str = None) -> dict:
	"""
	Return the 360-degree picture for a customer, either deal-scoped or org-centric.

	    {
	      "organization": {...} | None,
	      "deal": {...} | None,
	      "partners": [{kind, ref, name, ...}],
	      "summary": {package_paid, paid_amount, open_orders, open_amount,
                     sites_total, sites_live, outstanding, invoices},
	      "orders": [...], "invoices": [...], "payments": [...],
	      "facilities": [...], "onboarding": [...], "deals": [...]
	    }

	Missing links resolve to None/[]; an incomplete chain never raises.
	"""
	organization = (organization or "").strip()
	deal = (deal or "").strip()
	if not organization and not deal:
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

	organization_data = _resolve_organization(organization)
	deal_data = _resolve_deal(deal) if deal else None
	partners = _resolve_partners(deal, organization)
	orders, invoices, payments = _resolve_finance(organization, deal)
	facilities = _resolve_facilities(organization)
	onboarding = _resolve_onboarding(deal, organization)
	deals = _resolve_deals(organization)

	return {
		"organization": organization_data,
		"deal": deal_data,
		"partners": partners,
		"summary": _build_summary(orders, invoices, facilities),
		"orders": orders,
		"invoices": invoices,
		"payments": payments,
		"facilities": facilities,
		"onboarding": onboarding,
		"deals": deals,
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
		result["organizations"] = [
			{"name": r.name, "label": r.organization_name or r.name} for r in rows
		]
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
		rows = frappe.get_list(
			"CRM Pre-Qualified Facility",
			filters={"facility_name": ["like", like]},
			fields=["name", "facility_name", "mfl_code", "organization"],
			order_by="creation desc",
			limit_page_length=limit,
		)
		org_map = _org_doc_names([row.organization for row in rows if row.organization])
		result["facilities"] = [
			{
				"name": r.name,
				"label": r.facility_name or r.name,
				"mfl_code": r.mfl_code,
				"organization": org_map.get(r.organization),
			}
			for r in rows
		]
		if query.isdigit():
			rows = frappe.get_list(
				"CRM Pre-Qualified Facility",
				filters={"mfl_code": ["like", like]},
				fields=["name", "facility_name", "mfl_code", "organization"],
				limit_page_length=limit,
			)
			org_map.update(_org_doc_names([row.organization for row in rows if row.organization]))
			existing = {row["name"] for row in result["facilities"]}
			for r in rows:
				if r.name not in existing:
					result["facilities"].append(
						{
							"name": r.name,
							"label": r.facility_name or r.name,
							"mfl_code": r.mfl_code,
							"organization": org_map.get(r.organization),
						}
					)
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


def _resolve_partners(deal: str | None, organization: str) -> list[dict]:
	"""Partner attribution for one deal, or the union across the customer's deals."""
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
			["organization", "lead"] + (["optin_network"] if frappe.db.has_column("CRM Deal", "optin_network") else []),
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

	if deal:
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


def _resolve_deals(organization: str) -> list[dict]:
	if not organization or not _can_read("CRM Deal"):
		return []
	rows = frappe.get_list(
		"CRM Deal",
		filters={"organization": organization},
		fields=["name", "status", "deal_value", "currency", "deal_owner", "closed_date", "source", "creation"],
		order_by="creation desc",
		limit_page_length=0,
	)
	# Partner attribution per deal (network only; the cheap, current path).
	network_field = "optin_network" if frappe.db.has_column("CRM Deal", "optin_network") else None
	network_names = {}
	if network_field:
		with_net = frappe.get_list(
			"CRM Deal",
			filters={"organization": organization, network_field: ["is", "set"]},
			fields=["name", network_field],
			limit_page_length=0,
		)
		if with_net and _can_read("CRM Opt-In Network"):
			for row in with_net:
				display = frappe.db.get_value(
					"CRM Opt-In Network", row.get(network_field), "display_name"
				)
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


def _resolve_finance(organization: str, deal: str | None):
	"""Customer-wide orders, invoices and payments for the customer's deals."""
	deals = [deal] if deal else _org_deal_names(organization)
	if not deals:
		return [], [], []

	# Opt-In Submissions for these deals (orders and invoices are stamped with them).
	ois_names = []
	if _can_read("CRM Opt-In Submission"):
		ois_names = [
			row.name
			for row in frappe.get_list(
				"CRM Opt-In Submission",
				filters={"deal": ["in", deals]},
				fields=["name"],
				limit_page_length=0,
			)
		]

	# Quotations for these deals (invoice fallback + order fallback).
	quote_names = []
	if _can_read("Quotation") and frappe.db.has_column("Quotation", "crm_deal"):
		quote_names = [
			row.name
			for row in frappe.get_list(
				"Quotation",
				filters={"crm_deal": ["in", deals]},
				fields=["name"],
				limit_page_length=0,
			)
		]

	# ERPNext customer references stamped on these deals (billing party).
	customer_names = []
	if frappe.db.has_column("CRM Deal", "cx_customer"):
		rows = frappe.get_list(
			"CRM Deal",
			filters={"organization": organization, "cx_customer": ["is", "set"]},
			fields=["cx_customer"],
			limit_page_length=0,
		)
		customer_names = sorted({row.cx_customer for row in rows if row.cx_customer})

	orders = _resolve_orders(ois_names, quote_names)
	invoices = _resolve_invoices(ois_names, quote_names, customer_names)
	payments = _resolve_payments(customer_names)
	return orders, invoices, payments


def _resolve_orders(ois_names: list[str], quote_names: list[str]) -> list[dict]:
	if not _can_read("Sales Order"):
		return []
	rows = []
	if ois_names and frappe.db.has_column("Sales Order", "crm_optin_submission"):
		rows.extend(
			frappe.get_list(
				"Sales Order",
				filters={"crm_optin_submission": ["in", ois_names]},
				fields=[
					"name",
					"transaction_date",
					"grand_total",
					"currency",
					"status",
					"per_billed",
				]
				+ (
					["crm_token_facility_mfl", "crm_token_package_item"]
					if frappe.db.has_column("Sales Order", "crm_token_package_item")
					else []
				),
				order_by="creation desc",
				limit_page_length=200,
			)
		)
	if quote_names and frappe.db.has_column("Sales Order", "crm_optin_quotation"):
		existing = {row.name for row in rows}
		for row in frappe.get_list(
			"Sales Order",
			filters={"crm_optin_quotation": ["in", quote_names]},
			fields=[
				"name",
				"transaction_date",
				"grand_total",
				"currency",
				"status",
				"per_billed",
			],
			order_by="creation desc",
			limit_page_length=200,
		):
			if row.name not in existing:
				rows.append(row)
				existing.add(row.name)
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
		}
		for row in rows
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
	rows = []
	seen = set()
	for filters in candidates:
		for row in frappe.get_list(
			"Sales Invoice",
			filters=filters,
			fields=[
				"name",
				"creation",
				"grand_total",
				"currency",
				"outstanding_amount",
				"due_date",
				"docstatus",
				"status",
			],
			order_by="creation desc",
			limit_page_length=200,
		):
			if row.name not in seen:
				rows.append(row)
				seen.add(row.name)
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
		}
		for row in rows
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


def _resolve_facilities(organization: str) -> list[dict]:
	if not organization or not _can_read("CRM Pre-Qualified Facility"):
		return []
	name = _org_name(organization)
	rows = frappe.get_list(
		"CRM Pre-Qualified Facility",
		filters={"organization": name},
		fields=["name", "mfl_code", "facility_name", "keph_level", "is_self_onboarded"],
		order_by="creation desc",
		limit_page_length=100,
	)
	network_names = {}
	if _can_read("CRM Opt-In Network"):
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
					"contact_name": m.contact_name,
					"contact_phone": m.contact_phone,
				}
			)
		facilities.append(
			{
				"name": row.name,
				"mfl_code": row.mfl_code,
				"facility_name": row.facility_name or row.name,
				"keph_level": row.keph_level,
				"is_self_onboarded": bool(row.is_self_onboarded),
				"memberships": memberships,
			}
		)
	return facilities


def _resolve_onboarding(deal: str | None, organization: str) -> list[dict]:
	if not _can_read("CRM Onboarding Request"):
		return []
	deals = [deal] if deal else _org_deal_names(organization)
	if not deals:
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


def _build_summary(orders: list[dict], invoices: list[dict], facilities: list[dict]) -> dict:
	submitted = [row for row in invoices if row["docstatus"] == 1]
	paid_invoices = [row for row in submitted if (row["outstanding"] or 0) <= 0]
	paid_amount = round(
		sum((row["grand_total"] or 0) - (row["outstanding"] or 0) for row in submitted), 2
	)
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
	}
