"""Server-side helpers for the customer portal's commercial projection.

The pure decision logic lives in :mod:`crm.utils.portal_commercial` (no frappe
imports). This module does the querying and calls those helpers so that the
customer's orders and invoices are attributed to the right facilities and the
plan-aware data reaches the browser through ``get_portal_context``.

Attribution happens at read time: we never stamp ``crm_token_*`` fields onto
opt-in documents, because the OpenMeter grant path reads those fields and a
subscription document must not look like a token purchase (invariant I6).
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cstr, flt, getdate

from crm.utils import value_express
from crm.utils.portal_commercial import (
	JOURNEY_NETWORK,
	PLAN_TIME_BOUND,
	PLAN_TOKEN,
	apply_live_balance,
	attribute_facilities,
	can_create_invoice,
	cycle_label,
	decide_commercial,
	empty_commercial,
	fixed_plan_status,
	_empty_plan as empty_plan,
	is_schedule_governed,
	next_invoice,
	network_plan_status,
	order_doc_kind,
	order_display_status,
	order_display_title,
	period_label,
	quote_status_label,
	schedule_rows,
	term_label,
)


def _is_pending_mpesa_report(payment_entry) -> bool:
	"""Only portal M-Pesa reports are pending customer-visible Payment Entries."""
	if isinstance(payment_entry, dict):
		remarks = cstr(payment_entry.get("remarks") or "")
		docstatus = payment_entry.get("docstatus")
	else:
		remarks = cstr(getattr(payment_entry, "remarks", "") or "")
		docstatus = getattr(payment_entry, "docstatus", 0)
	return int(docstatus or 0) == 0 and remarks.startswith("M-Pesa Paybill payment ")


def _append_mfl(bucket: list, mfl) -> None:
	text = cstr(mfl or "").strip()
	if not text or any(existing.casefold() == text.casefold() for existing in bucket):
		return
	bucket.append(text)


def package_lookup(item_codes) -> dict:
	"""Read ``CRM Token Package`` rows directly, including disabled ones.

	Keyed by the casefolded item code. A code not found in the catalogue counts
	as ``Flex`` with the Item name, matching ``value_express.plan_of`` (SPEC 4.2).
	"""
	wanted = {cstr(code).strip().casefold(): cstr(code).strip() for code in (item_codes or []) if cstr(code).strip()}
	if not wanted:
		return {}
	result: dict[str, dict] = {}
	try:
		settings = frappe.get_single("CRM Opt-In Settings")
		for row in settings.get("token_packages") or []:
			code = cstr(row.get("item_code") or "").strip()
			key = code.casefold()
			if key in wanted:
				result[key] = {
					"item_code": code,
					"display_name": cstr(row.get("display_name") or ""),
					"plan": value_express.plan_of(row),
					"billing_period": cstr(row.get("billing_period") or ""),
					"token_quantity": int(row.get("token_quantity") or 0),
				}
	except Exception:
		frappe.log_error(
			title="CRM portal package lookup", message=frappe.get_traceback()
		)
	missing = [code for key, code in wanted.items() if key not in result]
	if missing:
		try:
			items = frappe.get_all(
				"Item",
				filters={"name": ["in", missing]},
				fields=["name", "item_name"],
				ignore_permissions=True,
				limit_page_length=0,
			)
			for item in items:
				key = cstr(item.get("name")).strip().casefold()
				result[key] = {
					"item_code": cstr(item.get("name")),
					"display_name": cstr(item.get("item_name") or item.get("name")),
					"plan": value_express.FLEX,
					"billing_period": "",
					"token_quantity": 0,
				}
		except Exception:
			frappe.log_error(
				title="CRM portal item fallback", message=frappe.get_traceback()
			)
	return result


def _order_item_rows(order_names) -> dict:
	"""One batched read of each order's item MFLs and first source quotation."""
	names = [name for name in (order_names or []) if name]
	result = {name: {"mfls": [], "prevdoc": ""} for name in names}
	if not names:
		return result
	fields = ["parent", "prevdoc_docname"]
	if frappe.db.has_column("Sales Order Item", "crm_optin_facility_mfl_code"):
		fields.append("crm_optin_facility_mfl_code")
	try:
		rows = frappe.get_all(
			"Sales Order Item",
			filters={"parent": ["in", names], "parenttype": "Sales Order"},
			fields=fields,
			ignore_permissions=True,
			limit_page_length=0,
		)
	except Exception:
		return result
	for row in rows:
		entry = result.get(row.parent)
		if not entry:
			continue
		_append_mfl(entry["mfls"], row.get("crm_optin_facility_mfl_code"))
		if not entry["prevdoc"] and row.get("prevdoc_docname"):
			entry["prevdoc"] = cstr(row.prevdoc_docname)
	return result


def _invoice_item_mfls(invoice_names) -> dict:
	"""Map each invoice to the MFLs on its item rows, one batched read."""
	names = [name for name in (invoice_names or []) if name]
	result: dict[str, list] = {name: [] for name in names}
	if not names or not frappe.db.has_column("Sales Invoice Item", "crm_optin_facility_mfl_code"):
		return result
	try:
		rows = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": ["in", names], "parenttype": "Sales Invoice"},
			fields=["parent", "crm_optin_facility_mfl_code"],
			ignore_permissions=True,
			limit_page_length=0,
		)
	except Exception:
		return result
	for row in rows:
		_append_mfl(result.get(row.parent, []), row.get("crm_optin_facility_mfl_code"))
	return result


def order_invoice_links(order_names) -> tuple[dict, dict]:
	"""Map orders to invoices and invoices to orders (submitted invoices only)."""
	names = [name for name in (order_names or []) if name]
	order_to_invoices = {name: [] for name in names}
	invoice_to_orders: dict[str, list] = {}
	if not names:
		return order_to_invoices, invoice_to_orders
	try:
		links = frappe.get_all(
			"Sales Invoice Item",
			filters={"parenttype": "Sales Invoice", "sales_order": ["in", names]},
			fields=["parent", "sales_order"],
			ignore_permissions=True,
			limit_page_length=0,
		)
	except Exception:
		return order_to_invoices, invoice_to_orders
	invoice_names = sorted({link.parent for link in links if link.parent})
	if not invoice_names:
		return order_to_invoices, invoice_to_orders
	try:
		submitted = {
			row.name
			for row in frappe.get_all(
				"Sales Invoice",
				filters={"name": ["in", invoice_names], "docstatus": 1},
				fields=["name"],
				ignore_permissions=True,
				limit_page_length=0,
			)
		}
	except Exception:
		submitted = set()
	for link in links:
		if link.parent not in submitted or not link.sales_order:
			continue
		if link.parent not in order_to_invoices.get(link.sales_order, []):
			order_to_invoices.setdefault(link.sales_order, []).append(link.parent)
		bucket = invoice_to_orders.setdefault(link.parent, [])
		if link.sales_order not in bucket:
			bucket.append(link.sales_order)
	return order_to_invoices, invoice_to_orders


def _enrich_order_fields(rows, ois_mfls_by_name, account_mfls, packages, prevdocs):
	for row in rows:
		header = cstr(row.get("crm_token_facility_mfl") or "")
		mfls = row.get("_item_mfls") or []
		ois_mfls = ois_mfls_by_name.get(cstr(row.get("crm_optin_submission") or ""), [])
		row["facility_mfls"] = attribute_facilities(header, mfls, ois_mfls, account_mfls)
		code = cstr(row.get("crm_token_package_item") or "")
		package = packages.get(code.strip().casefold()) if code else None
		package_plan = package["plan"] if package else None
		governed = is_schedule_governed(row.get("crm_optin_billing_key"), row.get("crm_optin_year"))
		doc_kind = order_doc_kind(governed, package_plan)
		period = period_label(row.get("crm_optin_year"), row.get("crm_optin_quarter"))
		package_name = package["display_name"] if package else ""
		docstatus = int(row.get("docstatus") or 0)
		status = cstr(row.get("status") or "")
		per_billed = flt(row.get("per_billed"))
		row["doc_kind"] = doc_kind
		row["display_title"] = order_display_title(doc_kind, governed, period, package_name)
		row["display_status"] = order_display_status(docstatus, status, per_billed, governed)
		row["schedule_governed"] = bool(governed)
		row["period_label"] = period
		row["quotation"] = cstr(row.get("crm_optin_quotation") or prevdocs.get(row.get("name"), "") or "")
		row["is_draft"] = docstatus == 0
		row["can_create_invoice"] = can_create_invoice(row["is_draft"], status, governed)
		row.pop("crm_optin_billing_key", None)
		row.pop("_item_mfls", None)
	return rows


def enrich_orders(rows, ois_mfls_by_name, account_mfls, packages) -> list:
	"""Add facility and display fields to customer/OIS order rows (SPEC 5.1)."""
	if not rows:
		return rows
	item_info = _order_item_rows([row.get("name") for row in rows])
	for row in rows:
		info = item_info.get(row.get("name"), {"mfls": [], "prevdoc": ""})
		row["_item_mfls"] = info["mfls"]
		if not row.get("crm_optin_quotation") and info["prevdoc"]:
			row["crm_optin_quotation"] = info["prevdoc"]
	return _enrich_order_fields(rows, ois_mfls_by_name, account_mfls, packages, {})


def _invoice_to_orders(invoice_names) -> dict:
	"""Collect the orders these invoices were raised from, one batched read."""
	names = sorted({name for name in invoice_names if name})
	result = {name: [] for name in names}
	if not names:
		return result
	try:
		rows = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": ["in", names], "parenttype": "Sales Invoice"},
			fields=["parent", "sales_order"],
			ignore_permissions=True,
			limit_page_length=0,
		)
	except Exception:
		return result
	for row in rows:
		if not row.sales_order:
			continue
		bucket = result.setdefault(row.parent, [])
		if row.sales_order not in bucket:
			bucket.append(row.sales_order)
	return result


def enrich_invoices(rows, ois_mfls_by_name, account_mfls) -> list:
	"""Normalize and add facility and display fields to invoice rows (SPEC 5.2)."""
	if not rows:
		return rows
	mfls_by_invoice = _invoice_item_mfls([row.get("name") for row in rows])
	invoice_to_orders = _invoice_to_orders([row.get("name") for row in rows])
	packages = package_lookup([row.get("crm_token_package_item") for row in rows])
	for row in rows:
		amount = flt(row.get("outstanding_amount"))
		row["invoice_number"] = row.get("name")
		row["posting_date"] = str(row.get("posting_date") or "")
		row["due_date"] = str(row.get("due_date") or "")
		row["amount"] = amount
		row["grand_total"] = flt(row.get("grand_total"))
		row["currency"] = cstr(row.get("currency") or "KES")
		row["status"] = "Outstanding" if amount > 0 else "Paid"
		header = cstr(row.get("crm_token_facility_mfl") or "")
		ois_mfls = ois_mfls_by_name.get(cstr(row.get("crm_optin_submission") or ""), [])
		row["facility_mfls"] = attribute_facilities(header, mfls_by_invoice.get(row.get("name"), []), ois_mfls, account_mfls)
		code = cstr(row.get("crm_token_package_item") or "")
		package = packages.get(code.strip().casefold()) if code else None
		governed = is_schedule_governed(row.get("crm_optin_billing_key"), row.get("crm_optin_year"))
		period = period_label(row.get("crm_optin_year"), row.get("crm_optin_quarter"))
		row["doc_kind"] = order_doc_kind(governed, package["plan"] if package else None)
		row["period_label"] = period
		row["sales_orders"] = invoice_to_orders.get(row.get("name"), [])
		row.pop("crm_optin_billing_key", None)
	return rows


def _account_payment_rows(customer, invoices_by_name) -> list:
	"""All customer payments, with the facility MFLs of the invoices they settle."""
	if not customer or not frappe.db.exists("DocType", "Payment Entry"):
		return []
	fields = [
		"name",
		"posting_date",
		"paid_amount",
		"received_amount",
		"mode_of_payment",
		"reference_no",
		"status",
		"docstatus",
		"remarks",
	]
	try:
		rows = frappe.get_list(
			"Payment Entry",
			filters={"party": customer, "party_type": "Customer", "docstatus": ["in", [0, 1]]},
			fields=fields,
			order_by="posting_date desc, creation desc",
			limit_page_length=200,
			ignore_permissions=True,
		)
	except Exception:
		return []
	payment_names = [row.name for row in rows]
	refs_by_payment: dict[str, list] = {}
	if payment_names and frappe.db.exists("DocType", "Payment Entry Reference"):
		try:
			refs = frappe.get_all(
				"Payment Entry Reference",
				filters={"parent": ["in", payment_names], "reference_doctype": "Sales Invoice"},
				fields=["parent", "reference_name", "allocated_amount"],
				limit_page_length=0,
				ignore_permissions=True,
			)
			for ref in refs:
				refs_by_payment.setdefault(ref.parent, []).append(ref)
		except Exception:
			refs_by_payment = {}
	result = []
	for row in rows:
		if row.docstatus != 1 and not _is_pending_mpesa_report(row):
			continue
		pending = _is_pending_mpesa_report(row)
		ref_list = refs_by_payment.get(row.name, [])
		invoice_names = [ref.reference_name for ref in ref_list if ref.reference_name]
		mfls: list[str] = []
		for invoice_name in invoice_names:
			for mfl in (invoices_by_name.get(invoice_name) or {}).get("facility_mfls", []):
				_append_mfl(mfls, mfl)
		result.append(
			{
				"name": row.name,
				"posting_date": str(row.posting_date or ""),
				"amount": float(row.paid_amount or row.received_amount or 0),
				"mode_of_payment": "M-Pesa Paybill" if pending else (row.mode_of_payment or "M-Pesa / Bank"),
				"reference_no": row.reference_no or "",
				"status": "Pending Verification" if pending else "Recorded",
				"invoice_names": invoice_names,
				"invoice": (invoice_names or [None])[0],
				"facility_mfls": mfls,
				"customer": customer,
			}
		)
	return result


def account_billing(customer, account_mfls, ois_mfls_by_name) -> dict:
	"""Full history for one customer: orders, invoices, payments (SPEC S2)."""
	if not customer or not frappe.db.exists("Customer", customer):
		return {"orders": [], "invoices": [], "payments": []}

	order_fields = [
		"name",
		"transaction_date",
		"delivery_date",
		"grand_total",
		"currency",
		"status",
		"docstatus",
		"per_billed",
	]
	for col in (
		"crm_token_facility_mfl",
		"crm_token_package_item",
		"crm_optin_submission",
		"crm_optin_year",
		"crm_optin_quarter",
		"crm_optin_billing_key",
		"crm_optin_quotation",
	):
		if frappe.db.has_column("Sales Order", col):
			order_fields.append(col)
	try:
		orders = frappe.get_list(
			"Sales Order",
			filters={"customer": customer, "docstatus": ["in", [0, 1]]},
			fields=order_fields,
			order_by="creation desc",
			limit_page_length=200,
			ignore_permissions=True,
		)
	except Exception:
		orders = []
	orders = enrich_orders(
		orders, ois_mfls_by_name, account_mfls, package_lookup([o.get("crm_token_package_item") for o in orders])
	)

	invoice_fields = [
		"name",
		"posting_date",
		"due_date",
		"grand_total",
		"outstanding_amount",
		"currency",
	]
	for col in (
		"crm_token_facility_mfl",
		"crm_token_package_item",
		"crm_optin_submission",
		"crm_optin_year",
		"crm_optin_quarter",
		"crm_optin_billing_key",
	):
		if frappe.db.has_column("Sales Invoice", col):
			invoice_fields.append(col)
	try:
		invoices = frappe.get_list(
			"Sales Invoice",
			filters={"customer": customer, "docstatus": 1},
			fields=invoice_fields,
			order_by="due_date asc, posting_date asc",
			limit_page_length=200,
			ignore_permissions=True,
		)
	except Exception:
		invoices = []
	invoices = enrich_invoices(invoices, ois_mfls_by_name, account_mfls)
	invoices_by_name = {row.get("name"): row for row in invoices}
	payments = _account_payment_rows(customer, invoices_by_name)
	return {"orders": orders, "invoices": invoices, "payments": payments}


def for_facility(rows, mfl) -> list:
	"""Keep only the rows attributed to this facility (case-insensitive)."""
	key = cstr(mfl or "").strip().casefold()
	if not key:
		return []
	return [row for row in (rows or []) if any(m.casefold() == key for m in row.get("facility_mfls") or [])]


# ---------------------------------------------------------------------------
# Plan projection (SPEC 4.3, 4.5, 4.6, 5.3)
# ---------------------------------------------------------------------------


def _parse_list(value):
	if isinstance(value, list):
		return value
	try:
		parsed = json.loads(value or "[]")
	except (TypeError, ValueError):
		return []
	return parsed if isinstance(parsed, list) else []


def network_plans_by_mfl(ois_names) -> dict:
	"""Map each facility MFL (casefolded) to its Network Opt-In context (SPEC S4).

	One read per OIS; only Network Opt-In rows qualify (``token_self_onboarding``
	is excluded, ``NULL`` counts as Network).
	"""
	from crm.api.website_redirect import OIS_DOCTYPE, _contract_progress, _submission_facilities

	result: dict[str, dict] = {}
	for ois_name in ois_names or []:
		if not ois_name:
			continue
		row = frappe.db.get_value(
			OIS_DOCTYPE,
			ois_name,
			[
				"name",
				"status",
				"onboarding_source",
				"contract",
				"pricing_plans_json",
				"billing_schedule_json",
				"quote_names_json",
				"raw_json",
			],
			as_dict=True,
		)
		if not row:
			continue
		if cstr(row.get("onboarding_source") or "").strip() == "token_self_onboarding":
			continue
		plans = _parse_list(row.get("pricing_plans_json"))
		schedule = _parse_list(row.get("billing_schedule_json"))
		quotes = _parse_list(row.get("quote_names_json"))
		try:
			contract_complete = bool(_contract_progress(row.get("contract"))["complete"])
		except Exception:
			contract_complete = False
		ctx = {
			"ois": row.get("name"),
			"status": cstr(row.get("status") or ""),
			"contract": row.get("contract"),
			"contract_complete": contract_complete,
			"plans": plans,
			"schedule": schedule,
			"quote_names": quotes,
		}
		mfls: set[str] = set()
		for plan in plans:
			if isinstance(plan, dict):
				for fac in plan.get("facilities") or []:
					if isinstance(fac, dict):
						code = cstr(fac.get("mfl_code") or "").strip().casefold()
						if code:
							mfls.add(code)
		if not mfls:
			for snapshot in _submission_facilities(row):
				code = cstr(snapshot.get("mfl_code") or "").strip().casefold()
				if code:
					mfls.add(code)
		for code in mfls:
			result.setdefault(code, ctx)
	return result


def facility_quotes(customer, mfl, network_ctx, quote_cache: dict | None = None) -> list:
	"""The facility's quotes (SPEC 5.3): Network from the OIS, else self-onboarding."""
	key = cstr(mfl or "").strip().casefold()
	if network_ctx:
		quote_names = network_ctx.get("quote_names") or []
		quote_names = [name for name in quote_names if isinstance(name, str) and name]
		if not quote_names:
			return []
		cache = quote_cache if quote_cache is not None else {}
		cache_key = tuple(quote_names)
		if cache_key not in cache:
			fields = ["name", "docstatus", "grand_total", "currency"]
			if frappe.db.has_column("Quotation", "crm_optin_year"):
				fields.append("crm_optin_year")
			try:
				cache[cache_key] = frappe.get_all(
					"Quotation",
					filters={"name": ["in", quote_names]},
					fields=fields,
					ignore_permissions=True,
					limit_page_length=0,
				)
			except Exception:
				cache[cache_key] = []
		quotes_by_name = {q.name: q for q in cache[cache_key]}
		if frappe.db.has_column("Quotation Item", "crm_optin_facility_mfl_code"):
			try:
				items = frappe.get_all(
					"Quotation Item",
					filters={"parent": ["in", quote_names], "parenttype": "Quotation"},
					fields=["parent", "crm_optin_facility_mfl_code"],
					ignore_permissions=True,
					limit_page_length=0,
				)
			except Exception:
				items = []
		else:
			items = []
		mfls_by_quote: dict[str, list[str]] = {}
		for item in items:
			code = cstr(item.get("crm_optin_facility_mfl_code") or "").strip()
			if code:
				mfls_by_quote.setdefault(item.parent, []).append(code)
		result = []
		for index, quote_name in enumerate(quote_names, start=1):
			quote = quotes_by_name.get(quote_name)
			if not quote:
				continue
			if int(quote.docstatus or 0) == 2:
				continue
			quote_mfls = mfls_by_quote.get(quote_name, [])
			if quote_mfls and key not in [m.casefold() for m in quote_mfls]:
				continue
			year = quote.get("crm_optin_year") if "crm_optin_year" in quote else None
			result.append(
				{
					"name": quote.name,
					"label": "Year %s" % (quote.get("crm_optin_year") or index) if quote.get("crm_optin_year") else "Year %d" % index,
					"status_label": quote_status_label(quote.docstatus),
					"amount": flt(quote.grand_total),
					"currency": cstr(quote.currency or "KES"),
				}
			)
		return result
	if not customer or not frappe.db.has_column("Quotation", "crm_token_facility_mfl"):
		return []
	try:
		rows = frappe.get_all(
			"Quotation",
			filters={"party_name": customer, "crm_token_facility_mfl": mfl, "docstatus": ["!=", 2]},
			fields=["name", "docstatus", "grand_total", "currency"],
			ignore_permissions=True,
			limit_page_length=0,
		)
	except Exception:
		return []
	return [
		{
			"name": row.name,
			"label": "Quote",
			"status_label": quote_status_label(row.docstatus),
			"amount": flt(row.grand_total),
			"currency": cstr(row.currency or "KES"),
		}
		for row in rows
	]


def _facility_in_plan(plan, mfl):
	key = cstr(mfl or "").strip().casefold()
	for fac in (plan or {}).get("facilities") or []:
		if isinstance(fac, dict) and cstr(fac.get("mfl_code") or "").strip().casefold() == key:
			return fac
	return {}


def _raw_schedule_state(row) -> str:
	if row.get("sales_invoice") or cstr(row.get("status") or "").strip().casefold() == "invoiced":
		return "invoiced"
	return "open"


def _next_raw_schedule_year(raw_schedule) -> int:
	for row in raw_schedule or []:
		if not isinstance(row, dict) or _raw_schedule_state(row) != "invoiced":
			year = int(flt(row.get("year_number"))) if row else 0
			return year or 1
	return 1


def _fill_network_plan(plan: dict, mfl, network_ctx, quotes) -> None:
	plans = [p for p in (network_ctx.get("plans") or []) if isinstance(p, dict)]
	raw_schedule = network_ctx.get("schedule") or []
	schedule = schedule_rows(raw_schedule, network_ctx.get("contract_complete"))
	next_inv = next_invoice(schedule)
	next_year = 1
	if next_inv:
		for row in raw_schedule:
			if isinstance(row, dict) and cstr(row.get("period_label") or "") == cstr(next_inv.get("label")) and _raw_schedule_state(row) != "invoiced":
				next_year = int(flt(row.get("year_number"))) or 1
				break
		else:
			next_year = _next_raw_schedule_year(raw_schedule)
	years = [int(flt(p.get("year_number"))) for p in plans if flt(p.get("year_number")) > 0]
	plan_by_year = {int(flt(p.get("year_number"))): p for p in plans if flt(p.get("year_number")) > 0}
	relevant = plan_by_year.get(next_year) or plan_by_year.get(1) or (plans[0] if plans else {})
	fac = _facility_in_plan(relevant, mfl)
	seen = set()
	for p in plans:
		for f in p.get("facilities") or []:
			if isinstance(f, dict):
				code = cstr(f.get("mfl_code") or "").strip().casefold()
				if code:
					seen.add(code)
	cycle = cstr(relevant.get("invoice_schedule_frequency") or "")
	plan.update(
		{
			"name": "Network subscription",
			"source": "optin_contract",
			"status": network_plan_status(network_ctx.get("status"), network_ctx.get("contract_complete")),
			"cycle": cycle,
			"cycle_label": cycle_label(cycle),
			"term_years": max(years) if years else None,
			"term_label": term_label(max(years)) if years else "",
			"currency": cstr((quotes[0].get("currency") if quotes else "") or "KES"),
			"facilities_on_plan": len(seen) or None,
			"facility_monthly_excl_vat": flt(fac.get("monthly_kes")) if fac else None,
			"facility_annual_excl_vat": flt(fac.get("annual_kes")) if fac else None,
			"cycle_amount_incl_vat": flt(next_inv.get("amount_incl_vat")) if next_inv else 0,
			"current_period": None,
			"next_invoice": (
				{
					"label": next_inv.get("label"),
					"date": next_inv.get("invoice_date"),
					"amount_incl_vat": flt(next_inv.get("amount_incl_vat")),
					"projected": bool(next_inv.get("projected")),
				}
				if next_inv
				else None
			),
			"schedule": schedule,
		}
	)


def _fill_fixed_plan(plan: dict, package_row, facility_orders, facility_invoices, facility_row) -> None:
	paid = [inv for inv in (facility_invoices or []) if flt(inv.get("amount")) <= 0]
	has_paid = bool(paid)
	cycle = cstr(package_row.get("billing_period") or "")
	currency = cstr(facility_row.get("package_currency") or "") or "KES"
	amount = flt(facility_row.get("package_gross_total"))
	latest = facility_orders[0] if facility_orders else {}
	if amount <= 0:
		amount = flt(latest.get("grand_total"))
	current_period = None
	if has_paid:
		newest = sorted(paid, key=lambda inv: cstr(inv.get("posting_date") or ""), reverse=True)[0]
		start = cstr(newest.get("posting_date") or "").strip()
		if start:
			end = add_days(add_months(getdate(start), value_express.period_months(cycle)), -1)
			current_period = {"start": str(getdate(start)), "end": str(end)}
	next_inv = None
	latest_name = latest.get("name") if latest else None
	if latest_name and frappe.db.exists("DocType", "Auto Repeat"):
		try:
			auto_repeats = frappe.get_all(
				"Auto Repeat",
				filters={"reference_doctype": "Sales Order", "reference_name": latest_name, "docstatus": 1},
				fields=["next_schedule_date"],
				order_by="creation desc",
				limit_page_length=1,
				ignore_permissions=True,
			)
		except Exception:
			auto_repeats = []
		if auto_repeats and auto_repeats[0].get("next_schedule_date"):
			next_inv = {
				"label": "Next renewal",
				"date": str(auto_repeats[0].get("next_schedule_date")),
				"amount_incl_vat": flt(latest.get("grand_total")),
				"projected": True,
			}
	plan.update(
		{
			"name": cstr(package_row.get("display_name") or ""),
			"source": "fixed_package",
			"status": fixed_plan_status(has_paid),
			"cycle": cycle,
			"cycle_label": cycle_label(cycle),
			"term_years": None,
			"term_label": "",
			"currency": currency,
			"facilities_on_plan": None,
			"facility_monthly_excl_vat": None,
			"facility_annual_excl_vat": None,
			"cycle_amount_incl_vat": amount or None,
			"current_period": current_period,
			"next_invoice": next_inv,
			"schedule": [],
		}
	)


def _fill_token_plan(plan: dict, package_row, facility_row) -> None:
	has_package = bool(
		package_row.get("item_code")
		or cstr(facility_row.get("token_package_item_code") or "").strip()
		or cstr(facility_row.get("token_package") or "").strip()
	)
	plan.update(
		{
			"name": cstr(package_row.get("display_name") or facility_row.get("token_package") or ""),
			"source": "token_package",
			"status": "Active" if has_package else "Ordered",
			"currency": cstr(facility_row.get("package_currency") or "") or "KES",
		}
	)


def build_commercial(mfl, network_ctx, package_row, facility_orders, facility_invoices, quotes, is_self_onboarding, facility_row=None) -> dict:
	"""Project the facility's journey and plan for the portal (SPEC 5.3).

	Failures never break the portal: any error logs and returns the unknown
	shape with ``unavailable: true``.
	"""
	facility_row = facility_row or {}
	package_row = package_row or {}
	try:
		token_order_count = sum(1 for order in (facility_orders or []) if order.get("doc_kind") == "token")
		decision = decide_commercial(
			network_ctx is not None,
			package_row.get("plan"),
			bool(is_self_onboarding),
			token_order_count,
		)
		commercial = {
			"journey": decision["journey"],
			"journey_label": decision["journey_label"],
			"plan_type": decision["plan_type"],
			"has_tokens": decision["has_tokens"],
			"unavailable": False,
			"plan": empty_plan(),
			"quotes": list(quotes or []),
		}
		if decision["plan_type"] == PLAN_TIME_BOUND and network_ctx is not None:
			_fill_network_plan(commercial["plan"], mfl, network_ctx, quotes or [])
		elif decision["plan_type"] == PLAN_TIME_BOUND:
			_fill_fixed_plan(commercial["plan"], package_row, facility_orders or [], facility_invoices or [], facility_row)
		elif decision["plan_type"] == PLAN_TOKEN:
			_fill_token_plan(commercial["plan"], package_row, facility_row)
		return commercial
	except Exception as exc:
		frappe.log_error(
			title="CRM portal commercial projection",
			message="Build failed (%s): %s" % (type(exc).__name__, frappe.get_traceback()),
		)
		return empty_commercial(unavailable=True)
