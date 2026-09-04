"""
crm/api/lifecycle.py — Deal lifecycle aggregator (opt-in → contract → finance)

Story:  oh-s1-2 (epic-optin-handoff)

Reverse-resolves the full CareVerse lifecycle chain for a single CRM Deal so the
exec pick-up surfaces (oh-s2-2 Deal Contracting panel, oh-s4-1 Finance AR) can
render a live status strip in one round-trip instead of six.

Rules enforced:
- @frappe.whitelist() on the public API.
- frappe.get_list() for every SELECT — no frappe.db.sql() SELECTs, no frappe.get_all().
- No ignore_permissions: gated by the caller's CRM Deal read permission
  (mirrors crm/api/activities.py:get_deal_activities), and every sub-resource
  read is independently permission-scoped by get_list. A caller who can read the
  Deal but not a sub-doctype (e.g. a Sales User vs the Network-Coordinator-scoped
  CRM Opt-In Submission) sees that link as None rather than an exception.
- No f-strings in log/error messages — % formatting only.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from crm.api.quotes import _normalise_quote_totals
from crm.utils.price_list_history import read_history


@frappe.whitelist()
def get_deal_lifecycle(deal: str) -> dict:
	"""
	Return the resolved lifecycle chain for one CRM Deal:

	    {
	      "submission":    {"ref", "status"} | None,
	      "quotation":     {"name", "status", "docstatus", "net_total", "vat_amount", "grand_total", "price_list", "initial_price_list", "price_list_history"} | None,
	      "quotations":    [{"name", "year_number", "net_total", "vat_amount", "grand_total", ...}],
	      "quotation_commitment": {"year_count", "net_total", "vat_amount", "grand_total"},
	      "contract":      {"name", "status", "workflow_state", "price_list", "excluded_signatories"} | None,
	      "signatories":   [{"row_name", "role", "status", "signed_at", "name", "email"}],
	      "onboarding":    {"name", "approval_status", "n1", "n2", "tiberbu"} | None,
	      "sales_invoice": {"name", "docstatus", "outstanding"} | None,
	    }

	Missing links resolve to None (or [] for signatories); an incomplete chain
	never raises. Scoped by the caller's CRM Deal read permission.
	"""
	# Gate on Deal read — mirrors crm/api/activities.py:get_deal_activities.
	if not frappe.has_permission("CRM Deal", "read", deal):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	submission = _resolve_submission(deal)
	quotation = _resolve_quotation(deal)
	contract = _resolve_contract(deal, quotation)
	quotations = _resolve_quotations(deal)
	quotation_commitment = _quotation_commitment(quotations)

	return {
		"submission": submission,
		"quotation": quotation,
		"quotations": quotations,
		"quotation_commitment": quotation_commitment,
		"contract": contract,
		"signatories": _resolve_signatories(contract["name"] if contract else None),
		"onboarding": _resolve_onboarding(deal),
		"sales_invoice": _resolve_sales_invoice(quotation["name"] if quotation else None, submission),
		"sales_invoices": _resolve_sales_invoices(quotations, submission),
	}


# ---------------------------------------------------------------------------
# Private resolvers — each is a permission-scoped frappe.get_list() read.
# ---------------------------------------------------------------------------


def _can_read(doctype: str) -> bool:
	"""True if the caller has doctype-level read — prevents get_list from raising."""
	return bool(frappe.has_permission(doctype, "read"))


def _resolve_submission(deal: str) -> dict | None:
	if not _can_read("CRM Opt-In Submission"):
		return None
	rows = frappe.get_list(
		"CRM Opt-In Submission",
		filters={"deal": deal},
		fields=["name", "status"],
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return None
	return {"ref": rows[0].name, "status": rows[0].status}


def _resolve_quotation(deal: str) -> dict | None:
	if not _can_read("Quotation"):
		return None
	fields = [
		"name",
		"status",
		"docstatus",
		"net_total",
		"total_taxes_and_charges",
		"grand_total",
		"selling_price_list",
	]
	for fieldname in ("vat_amount", "company", "taxes_and_charges"):
		if frappe.db.has_column("Quotation", fieldname):
			fields.append(fieldname)
	for fieldname in ("crm_initial_price_list", "crm_price_list_history"):
		if frappe.db.has_column("Quotation", fieldname):
			fields.append(fieldname)
	rows = frappe.get_list(
		"Quotation",
		filters={"crm_deal": deal},
		fields=fields,
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return None
	r = rows[0]
	_normalise_quote_totals(r)
	return {
		"name": r.name,
		"status": r.status,
		"docstatus": r.docstatus,
		"net_total": r.get("net_total") or 0,
		"vat_amount": r.get("vat_amount") or r.get("total_taxes_and_charges") or 0,
		"grand_total": r.grand_total,
		"price_list": r.get("selling_price_list") or "Standard Selling",
		"initial_price_list": r.get("crm_initial_price_list")
		or r.get("selling_price_list")
		or "Standard Selling",
		"price_list_history": read_history(r),
	}


def _resolve_quotations(deal: str) -> list[dict]:
	"""Return every yearly quotation while retaining the singular legacy field."""
	if not _can_read("Quotation"):
		return []
	fields = [
		"name",
		"status",
		"docstatus",
		"net_total",
		"total_taxes_and_charges",
		"grand_total",
		"selling_price_list",
		"creation",
	]
	for fieldname in (
		"crm_initial_price_list",
		"crm_price_list_history",
		"crm_optin_year",
		"crm_optin_submission",
	):
		if frappe.db.has_column("Quotation", fieldname):
			fields.append(fieldname)
	for fieldname in ("vat_amount", "company", "taxes_and_charges"):
		if frappe.db.has_column("Quotation", fieldname):
			fields.append(fieldname)
	rows = frappe.get_list(
		"Quotation", filters={"crm_deal": deal}, fields=fields, order_by="creation asc", limit_page_length=0
	)
	return [_normalised_quotation_row(row, index) for index, row in enumerate(rows, 1)]


def _normalised_quotation_row(row, index):
	_normalise_quote_totals(row)
	return {
		"name": row.name,
		"year_number": frappe.utils.cint(row.get("crm_optin_year") or index),
		"status": row.status,
		"docstatus": row.docstatus,
		"net_total": row.get("net_total") or 0,
		"vat_amount": row.get("vat_amount") or row.get("total_taxes_and_charges") or 0,
		"grand_total": row.grand_total,
		"price_list": row.get("selling_price_list") or "Standard Selling",
		"initial_price_list": row.get("crm_initial_price_list")
		or row.get("selling_price_list")
		or "Standard Selling",
		"price_list_history": read_history(row),
	}


def _quotation_commitment(quotations: list[dict]) -> dict:
	"""Sum the current yearly quotation totals for CRM approval surfaces."""
	return {
		"year_count": len(quotations),
		"net_total": round(sum(float(row.get("net_total") or 0) for row in quotations), 2),
		"vat_amount": round(sum(float(row.get("vat_amount") or 0) for row in quotations), 2),
		"grand_total": round(sum(float(row.get("grand_total") or 0) for row in quotations), 2),
	}


def _resolve_contract(deal: str, quotation: dict | None = None) -> dict | None:
	if not _can_read("CRM Contract"):
		return None
	fields = ["name", "status", "workflow_state", "quote"]
	for fieldname in (
		"initial_price_list",
		"negotiated_price_list",
		"price_list_history",
		"tiberbu_signing_requirement",
		"excluded_signatories",
		"quote_names_json",
	):
		if frappe.db.has_column("CRM Contract", fieldname):
			fields.append(fieldname)
	rows = frappe.get_list(
		"CRM Contract",
		filters={"deal": deal},
		fields=fields,
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return None
	r = rows[0]
	price_history = read_history(r, "price_list_history")
	excluded_signatories = []
	try:
		parsed_exclusions = json.loads(r.get("excluded_signatories") or "[]")
		if isinstance(parsed_exclusions, list):
			excluded_signatories = [
				{
					"role": frappe.utils.cstr(entry.get("role") or "").strip(),
					"email": frappe.utils.cstr(entry.get("email") or "").strip().lower(),
				}
				for entry in parsed_exclusions
				if isinstance(entry, dict) and entry.get("role") and entry.get("email")
			]
	except (TypeError, ValueError):
		pass
	initial = r.get("initial_price_list") or (quotation or {}).get("initial_price_list") or ""
	negotiated = r.get("negotiated_price_list") or (quotation or {}).get("price_list") or initial
	return {
		"name": r.name,
		"status": r.status,
		"workflow_state": r.workflow_state,
		"tiberbu_signing_requirement": r.get("tiberbu_signing_requirement") or "All must sign",
		"excluded_signatories": excluded_signatories,
		"price_list": {
			"initial": initial or negotiated,
			"negotiated": negotiated or initial,
			"history": price_history or (quotation or {}).get("price_list_history", []),
		},
		"quotation_names": _parse_names(r.get("quote_names_json")),
	}


def _parse_names(value):
	try:
		parsed = json.loads(value or "[]")
	except (TypeError, ValueError, json.JSONDecodeError):
		return []
	return (
		[frappe.utils.cstr(item).strip() for item in parsed if frappe.utils.cstr(item).strip()]
		if isinstance(parsed, list)
		else []
	)


def _resolve_signatories(contract: str | None) -> list:
	"""Read signatory child rows off the parent Contract.

	frappe.get_list() on a child DocType silently drops non-standard fields
	(it returns `name` only), so we load the parent and read its child table —
	a permission-respecting single-document read, not get_all()/db.sql().
	"""
	if not contract or not _can_read("CRM Contract"):
		return []
	doc = frappe.get_doc("CRM Contract", contract)
	return [
		{
			"row_name": r.name,
			"role": r.signatory_role,
			"status": r.status,
			"signed_at": r.signed_at,
			"name": r.signatory_name,
			"email": r.signatory_email,
			"phone": r.signatory_phone,
		}
		for r in doc.signatories
	]


def _resolve_onboarding(deal: str) -> dict | None:
	if not _can_read("CRM Onboarding Request"):
		return None
	rows = frappe.get_list(
		"CRM Onboarding Request",
		filters={"deal": deal},
		fields=[
			"name",
			"approval_status",
			"network_approver_1_approved",
			"network_approver_2_approved",
			"tiberbu_approver_approved",
		],
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return None
	r = rows[0]
	return {
		"name": r.name,
		"approval_status": r.approval_status,
		"n1": r.network_approver_1_approved,
		"n2": r.network_approver_2_approved,
		"tiberbu": r.tiberbu_approver_approved,
	}


def _resolve_sales_invoice(quotation: str | None, submission: dict | None = None) -> dict | None:
	if not _can_read("Sales Invoice"):
		return None
	filter_candidates = []
	if submission and submission.get("ref") and frappe.db.has_column("Sales Invoice", "crm_optin_submission"):
		filter_candidates.append({"crm_optin_submission": submission["ref"]})
	if quotation and frappe.db.has_column("Sales Invoice", "crm_optin_quotation"):
		filter_candidates.append({"crm_optin_quotation": quotation})
	if quotation and frappe.db.has_column("Sales Invoice", "crm_quotation"):
		filter_candidates.append({"crm_quotation": quotation})
	if not filter_candidates:
		return None
	rows = []
	for filters in filter_candidates:
		rows = frappe.get_list(
			"Sales Invoice",
			filters=filters,
			fields=["name", "docstatus", "outstanding_amount"],
			order_by="creation desc",
			limit=1,
		)
		if rows:
			break
	if not rows:
		return None
	r = rows[0]
	return {"name": r.name, "docstatus": r.docstatus, "outstanding": r.outstanding_amount}


def _resolve_sales_invoices(quotations: list[dict], submission: dict | None = None) -> list[dict]:
	if not _can_read("Sales Invoice") or not quotations:
		return []
	quote_names = [row["name"] for row in quotations]
	fields = ["name", "docstatus", "outstanding_amount", "creation"]
	if frappe.db.has_column("Sales Invoice", "crm_optin_submission") and submission and submission.get("ref"):
		filters = {"crm_optin_submission": submission["ref"]}
	elif frappe.db.has_column("Sales Invoice", "crm_quotation"):
		filters = {"crm_quotation": ["in", quote_names]}
	else:
		filters = None
	if not filters:
		return []
	rows = frappe.get_list(
		"Sales Invoice", filters=filters, fields=fields, order_by="creation asc", limit_page_length=0
	)
	return [
		{"name": row.name, "docstatus": row.docstatus, "outstanding": row.outstanding_amount} for row in rows
	]
