"""Paged per-facility documents for the CX facility page tabs.

The facility page used to show every order, invoice and payment that
``get_portal_context`` returned, stacked as sections. That payload is capped
(200 per account, 100 orders per facility) and gets heavier as history grows.
This endpoint serves one tab at a time, a page at a time, using the same
facility attribution as ``account_billing`` so rows match what the page
already shows.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from crm.api.portal_commercial import (
	_account_payment_rows,
	_append_mfl,
	account_invoices,
	account_orders,
	for_facility,
)

KINDS = ("order", "invoice", "payment")
INVOICE_STATUSES = ("all", "outstanding")
MAX_PAGE_LENGTH = 50
DEFAULT_PAGE_LENGTH = 20
# Safety ceiling for one customer's history; the response says when it was hit.
HISTORY_CEILING = 5000


def _customer_mfls(customer: str) -> list[str]:
	"""MFLs the customer holds through memberships and its deals' facility rows."""
	mfls: list[str] = []
	if frappe.db.has_column("CRM Facility Membership", "customer"):
		parents = frappe.get_all(
			"CRM Facility Membership",
			filters={"customer": customer},
			pluck="parent",
			ignore_permissions=True,
			limit_page_length=0,
		)
		if parents:
			for mfl in frappe.get_all(
				"CRM Pre-Qualified Facility",
				filters={"name": ["in", list(set(parents))]},
				pluck="mfl_code",
				ignore_permissions=True,
				limit_page_length=0,
			):
				_append_mfl(mfls, mfl)
	deals = (
		frappe.get_all(
			"CRM Deal",
			filters={"cx_customer": customer},
			pluck="name",
			ignore_permissions=True,
			limit_page_length=0,
		)
		if frappe.db.has_column("CRM Deal", "cx_customer")
		else []
	)
	if deals:
		for mfl in frappe.get_all(
			"CRM Deal Facility",
			filters={"parent": ["in", deals]},
			pluck="mfl_code",
			ignore_permissions=True,
			limit_page_length=0,
		):
			_append_mfl(mfls, mfl)
	return mfls


def _authorize(user: str, customer: str, mfl_code: str) -> list[str]:
	"""Return the customer's MFLs, or raise unless the user may see this facility."""
	from crm.api.website_redirect import get_user_customer_names

	if not user or user == "Guest":
		frappe.throw(_("Please sign in to view facility records."), frappe.PermissionError)
	if not customer or customer not in (get_user_customer_names(user) or []):
		frappe.throw(_("Facility not found in your portfolio."), frappe.PermissionError)
	mfls = _customer_mfls(customer)
	key = mfl_code.casefold()
	if not key or not any(cstr(mfl).strip().casefold() == key for mfl in mfls):
		frappe.throw(_("Facility not found in your portfolio."), frappe.PermissionError)
	return mfls


def sort_invoices(rows: list[dict]) -> list[dict]:
	"""Open invoices first by due date, then paid ones newest first (mirrors sortInvoices)."""
	open_rows = [row for row in rows if flt(row.get("amount")) > 0]
	paid_rows = [row for row in rows if flt(row.get("amount")) <= 0]
	open_rows.sort(key=lambda row: (cstr(row.get("due_date")), cstr(row.get("name"))))
	paid_rows.sort(key=lambda row: (cstr(row.get("posting_date")), cstr(row.get("name"))), reverse=True)
	return open_rows + paid_rows


def sort_orders(rows: list[dict]) -> list[dict]:
	"""Newest first, by transaction date then name (mirrors mergeFacilityOrders)."""
	return sorted(
		rows,
		key=lambda row: (cstr(row.get("transaction_date") or row.get("creation")), cstr(row.get("name"))),
		reverse=True,
	)


def sort_payments(rows: list[dict]) -> list[dict]:
	return sorted(rows, key=lambda row: (cstr(row.get("posting_date")), cstr(row.get("name"))), reverse=True)


def matches_search(row: dict, needle: str) -> bool:
	if not needle:
		return True
	haystack = (
		row.get("name"),
		row.get("invoice_number"),
		row.get("reference_no"),
		row.get("display_title"),
		row.get("quotation"),
		*(row.get("sales_orders") or []),
		*(row.get("invoice_names") or []),
	)
	return any(needle in cstr(value).casefold() for value in haystack if value)


def page_rows(rows: list[dict], *, kind: str, status: str, search: str, start: int, page_length: int) -> dict:
	"""Filter, sort and slice already-attributed rows. Pure, so it is unit-tested."""
	outstanding = sum(1 for row in rows if flt(row.get("amount")) > 0) if kind == "invoice" else 0
	filtered = rows
	if kind == "invoice" and status == "outstanding":
		filtered = [row for row in filtered if flt(row.get("amount")) > 0]
	needle = cstr(search).strip().casefold()
	if needle:
		filtered = [row for row in filtered if matches_search(row, needle)]
	sorter = {"order": sort_orders, "invoice": sort_invoices, "payment": sort_payments}[kind]
	filtered = sorter(filtered)
	return {
		"rows": filtered[start : start + page_length],
		"total": len(filtered),
		"start": start,
		"page_length": page_length,
		"counts": {"all": len(rows), "outstanding": outstanding},
	}


def _ois_mfls(customer: str) -> dict:
	from crm.api.website_redirect import _user_ois_mfls_by_name

	customer_deals = []
	if frappe.db.has_column("CRM Deal", "cx_customer"):
		deal_fields = ["name"] + (["optin_submission"] if frappe.db.has_column("CRM Deal", "optin_submission") else [])
		customer_deals = frappe.get_all(
			"CRM Deal",
			filters={"cx_customer": customer},
			fields=deal_fields,
			ignore_permissions=True,
			limit_page_length=0,
		)
	return _user_ois_mfls_by_name(frappe.session.user, customer_deals)


def _facility_rows(customer: str, mfl_code: str, kind: str) -> tuple[list[dict], bool]:
	"""Authorize, then return this facility's rows of one kind and whether the ceiling was hit."""
	account_mfls = _authorize(frappe.session.user, customer, mfl_code)
	ois_mfls_by_name = _ois_mfls(customer)
	if kind == "order":
		rows = account_orders(customer, account_mfls, ois_mfls_by_name, limit=HISTORY_CEILING)
		return for_facility(rows, mfl_code), len(rows) >= HISTORY_CEILING
	invoices = account_invoices(customer, account_mfls, ois_mfls_by_name, limit=HISTORY_CEILING)
	ceiling_hit = len(invoices) >= HISTORY_CEILING
	if kind == "invoice":
		return for_facility(invoices, mfl_code), ceiling_hit
	payments = _account_payment_rows(customer, {row.get("name"): row for row in invoices}, limit=HISTORY_CEILING)
	return for_facility(payments, mfl_code), ceiling_hit or len(payments) >= HISTORY_CEILING


@frappe.whitelist(methods=["GET", "POST"])
def get_facility_document_counts(customer=None, mfl_code=None):
	"""Totals for the facility page tab labels: orders, invoices (and how many are due), payments."""
	customer = cstr(customer).strip()
	mfl_code = cstr(mfl_code).strip()
	account_mfls = _authorize(frappe.session.user, customer, mfl_code)
	ois_mfls_by_name = _ois_mfls(customer)
	orders = account_orders(customer, account_mfls, ois_mfls_by_name, limit=HISTORY_CEILING)
	invoices = account_invoices(customer, account_mfls, ois_mfls_by_name, limit=HISTORY_CEILING)
	payments = _account_payment_rows(customer, {row.get("name"): row for row in invoices}, limit=HISTORY_CEILING)
	facility_invoices = for_facility(invoices, mfl_code)
	return {
		"order": len(for_facility(orders, mfl_code)),
		"invoice": len(facility_invoices),
		"invoiceDue": sum(1 for row in facility_invoices if flt(row.get("amount")) > 0),
		"payment": len(for_facility(payments, mfl_code)),
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_facility_documents(
	customer=None, mfl_code=None, kind=None, start=0, page_length=DEFAULT_PAGE_LENGTH, status="all", search=""
):
	"""One page of a facility's orders, invoices or payments for the signed-in portal user."""
	customer = cstr(customer).strip()
	mfl_code = cstr(mfl_code).strip()
	kind = cstr(kind).strip()
	status = cstr(status or "all").strip()
	if kind not in KINDS:
		frappe.throw(_("Unknown record type."), frappe.ValidationError)
	if status not in INVOICE_STATUSES:
		status = "all"
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or DEFAULT_PAGE_LENGTH, 1), MAX_PAGE_LENGTH)

	rows, ceiling_hit = _facility_rows(customer, mfl_code, kind)
	result = page_rows(
		rows,
		kind=kind,
		status=status,
		search=search,
		start=start,
		page_length=page_length,
	)
	result["truncated"] = ceiling_hit
	return result
