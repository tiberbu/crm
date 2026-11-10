"""Opt-In billing ledger, paying ahead and quote PDFs (spec P-124 to P-133).

The ledger is read-time: ``CRM Opt-In Submission.billing_schedule_json`` joined
with the native Sales Orders, Sales Invoices and Payment Entries. Paying ahead
issues the next unissued periods through the same ``_create_order_and_invoice``
path the hourly worker uses, so documents are identical whoever issues them.

- Portal methods authorise through the server-side OIS User Permission only.
- Desk methods require Deal read; issuing requires a Sales/Accounts/System Manager.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, now_datetime, nowdate

from crm.utils import optin_ledger as rules

OIS_DOCTYPE = "CRM Opt-In Submission"
STAFF_ISSUER_ROLES = {"Sales Manager", "Accounts Manager", "System Manager"}


def _schedule(submission) -> list[dict]:
	try:
		rows = json.loads(submission.get("billing_schedule_json") or "[]")
	except (TypeError, ValueError):
		return []
	return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _optional(doctype: str, columns) -> list[str]:
	return [col for col in columns if frappe.db.has_column(doctype, col)]


def _documents(submission, rows) -> tuple[dict, dict, dict]:
	"""Orders and invoices of this submission keyed by name and billing key; payments by invoice."""
	orders: dict = {}
	invoices: dict = {}
	if frappe.db.has_column("Sales Order", "crm_optin_submission"):
		for row in frappe.get_all(
			"Sales Order",
			filters={"crm_optin_submission": submission.name, "docstatus": ["!=", 2]},
			fields=["name", "docstatus", "grand_total", "transaction_date", *_optional("Sales Order", ["crm_optin_billing_key"])],
			ignore_permissions=True,  # SYSTEM-INTERNAL: caller authorised the submission
			limit_page_length=0,
		):
			orders[row.name] = row
			if row.get("crm_optin_billing_key"):
				orders.setdefault("key:" + row.crm_optin_billing_key, row)
	if frappe.db.has_column("Sales Invoice", "crm_optin_submission"):
		for row in frappe.get_all(
			"Sales Invoice",
			filters={"crm_optin_submission": submission.name, "docstatus": ["!=", 2]},
			fields=[
				"name",
				"docstatus",
				"grand_total",
				"rounded_total",
				"outstanding_amount",
				"posting_date",
				"due_date",
				"currency",
				*_optional("Sales Invoice", ["crm_optin_billing_key"]),
			],
			ignore_permissions=True,  # SYSTEM-INTERNAL: caller authorised the submission
			limit_page_length=0,
		):
			invoices[row.name] = row
			if row.get("crm_optin_billing_key"):
				invoices.setdefault("key:" + row.crm_optin_billing_key, row)
	payments: dict = {}
	invoice_names = [name for name in invoices if not name.startswith("key:")]
	if invoice_names:
		refs = frappe.get_all(
			"Payment Entry Reference",
			filters={"reference_doctype": "Sales Invoice", "reference_name": ["in", invoice_names], "docstatus": ["!=", 2]},
			fields=["parent", "reference_name", "allocated_amount", "docstatus"],
			ignore_permissions=True,  # SYSTEM-INTERNAL
			limit_page_length=0,
		)
		parents = {
			row.name: row
			for row in frappe.get_all(
				"Payment Entry",
				filters={"name": ["in", list({ref.parent for ref in refs})]} if refs else {"name": ""},
				fields=["name", "posting_date", "mode_of_payment", "docstatus", "reference_no"],
				ignore_permissions=True,  # SYSTEM-INTERNAL
				limit_page_length=0,
			)
		}
		for ref in refs:
			entry = parents.get(ref.parent)
			if not entry:
				continue
			payments.setdefault(ref.reference_name, []).append(
				{
					"name": entry.name,
					"date": cstr(entry.posting_date or ""),
					"amount": flt(ref.allocated_amount),
					"mode": cstr(entry.mode_of_payment or ""),
					"reference_no": cstr(entry.reference_no or ""),
					"status": "Recorded" if cint(entry.docstatus) == 1 else "Pending verification",
				}
			)
	return orders, invoices, payments


def _quotes(submission, contract_status) -> list[dict]:
	try:
		names = json.loads(submission.get("quote_names_json") or "[]")
	except (TypeError, ValueError):
		names = []
	names = [name for name in names if isinstance(name, str) and name]
	if not names:
		return []
	fields = ["name", "docstatus", "grand_total", "currency", *_optional("Quotation", ["crm_optin_year"])]
	by_name = {
		row.name: row
		for row in frappe.get_all(
			"Quotation", filters={"name": ["in", names]}, fields=fields, ignore_permissions=True, limit_page_length=0
		)
	}
	result = []
	for index, name in enumerate(names, start=1):
		row = by_name.get(name)
		if not row or cint(row.docstatus) == 2:
			continue
		result.append(
			{
				"name": name,
				"year": cint(row.get("crm_optin_year")) or index,
				"status_label": rules.quote_status_label(contract_status),
				"amount": flt(row.grand_total),
				"currency": cstr(row.currency or "KES"),
			}
		)
	return sorted(result, key=lambda q: q["year"])


def _invoice_total(invoice) -> float:
	"""What the customer owes in full: ERPNext's outstanding follows the rounded total."""
	return flt(invoice.get("rounded_total")) or flt(invoice.get("grand_total"))


def _unpaid_count(invoices: dict) -> int:
	return sum(
		1
		for name, row in invoices.items()
		if not name.startswith("key:") and cint(row.docstatus) == 1 and flt(row.outstanding_amount) > 0
	)


def build_ledger(submission, staff: bool = False) -> dict:
	from crm.api.website_redirect import _partner_label

	today = getdate(nowdate())
	rows = sorted(_schedule(submission), key=rules.sort_key)
	contract_status = (
		cstr(frappe.db.get_value("CRM Contract", submission.contract, "status") or "") if submission.get("contract") else ""
	)
	orders, invoices, payments = _documents(submission, rows)
	quotes = _quotes(submission, contract_status)
	quote_by_year = {q["year"]: q for q in quotes}
	currency = cstr((quotes[0]["currency"] if quotes else "") or "KES")

	periods = []
	for row in rows:
		key = cstr(row.get("billing_key") or "")
		invoice = invoices.get(cstr(row.get("sales_invoice") or "")) or (invoices.get("key:" + key) if key else None)
		order = orders.get(cstr(row.get("sales_order") or "")) or (orders.get("key:" + key) if key else None)
		effective = dict(row)
		if invoice and not effective.get("sales_invoice"):
			effective["sales_invoice"] = invoice.name
		if order and not effective.get("sales_order"):
			effective["sales_order"] = order.name
		invoice_view = (
			{"outstanding": flt(invoice.outstanding_amount), "due_date": invoice.due_date, "docstatus": invoice.docstatus}
			if invoice
			else None
		)
		state = rules.period_state(effective, invoice_view, today)
		period = {
			"billing_key": key,
			"label": rules.period_label(row),
			"year": cint(row.get("year_number")),
			"quarter": cint(row.get("quarter_number")),
			"scheduled_date": rules.scheduled_date(row),
			"due_date": cstr(invoice.due_date) if invoice else rules.scheduled_due_date(row),
			"amount": flt(row.get("amount_incl_vat")),
			"amount_excl_vat": flt(row.get("amount_excl_vat")),
			"vat": flt(row.get("amount_vat")),
			"state": state,
			"state_label": rules.STATE_LABELS[state],
			"sales_order": order.name if order else cstr(row.get("sales_order") or ""),
			"sales_invoice": invoice.name if invoice else "",
			"invoice_date": cstr(invoice.posting_date) if invoice else "",
			"invoice_total": _invoice_total(invoice) if invoice else 0,
			"outstanding": flt(invoice.outstanding_amount) if invoice else 0,
			"payments": payments.get(invoice.name, []) if invoice else [],
			"issued_early": bool(row.get("issued_early")),
			"issued_by": cstr(row.get("issued_by") or ""),
		}
		if staff:
			period["error"] = cstr(row.get("error") or "")
			period["issued_by_user"] = cstr(row.get("issued_by_user") or "")
			period["issued_on"] = cstr(row.get("issued_on") or "")
		periods.append(period)

	# Invoices on the submission that belong to no schedule period (e.g. a one-off
	# package invoice) stay visible and payable instead of vanishing from the ledger.
	matched = {period["sales_invoice"] for period in periods if period["sales_invoice"]}
	other_invoices = [
		{
			"name": row.name,
			"invoice_date": cstr(row.posting_date or ""),
			"due_date": cstr(row.due_date or ""),
			"amount": _invoice_total(row),
			"outstanding": flt(row.outstanding_amount),
			"currency": cstr(row.currency or currency),
			"payments": payments.get(row.name, []),
		}
		for name, row in invoices.items()
		if not name.startswith("key:") and name not in matched and cint(row.docstatus) == 1
	]
	policy = rules.advance_policy(submission.status, contract_status, rows, _unpaid_count(invoices))
	policy["next"] = [
		{"billing_key": cstr(row.get("billing_key") or ""), "label": rules.period_label(row), "amount": flt(row.get("amount_incl_vat"))}
		for row in rules.issuable_rows(rows)[: rules.MAX_ADVANCE_PERIODS]
	]
	years = []
	for period in periods:
		if not years or years[-1]["year"] != period["year"]:
			years.append({"year": period["year"], "quotation": quote_by_year.get(period["year"]), "periods": []})
		years[-1]["periods"].append(period)

	return {
		"ois": submission.name,
		"network": _partner_label(submission.get("network_slug")),
		"contract": cstr(submission.get("contract") or ""),
		"contract_status": contract_status,
		"status": cstr(submission.status or ""),
		"currency": currency,
		"today": today.isoformat(),
		"summary": rules.ledger_summary(periods, today),
		"advance": policy,
		"years": years,
		"quotes": quotes,
		"other_invoices": sorted(other_invoices, key=lambda row: row["invoice_date"]),
	}


def _portal_submission(ois_number):
	from crm.api.checkout import _portal_submission as authorise

	return authorise(ois_number)


def _deal_submission(deal: str, require_issuer: bool = False):
	deal = cstr(deal).strip()
	if not deal or not frappe.db.exists("CRM Deal", deal):
		frappe.throw(_("Deal not found."), frappe.DoesNotExistError)
	if not frappe.has_permission("CRM Deal", "read", deal):
		frappe.throw(_("You cannot view this Deal."), frappe.PermissionError)
	if require_issuer and not STAFF_ISSUER_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Only a Sales Manager or Accounts Manager can issue invoices early."), frappe.PermissionError)
	names = frappe.get_all(OIS_DOCTYPE, filters={"deal": deal}, pluck="name", order_by="creation desc", limit=1, ignore_permissions=True)
	return frappe.get_doc(OIS_DOCTYPE, names[0]) if names else None


def issue_periods(submission_name: str, count: Any, issued_by: str) -> dict:
	"""Issue the next ``count`` unissued periods now (P-125 to P-128). Shared by portal and Desk."""
	from crm.automation.optin_billing import _create_order_and_invoice, _quote_for_schedule

	# Serialize with the hourly worker and other clicks on the same submission.
	frappe.db.get_value(OIS_DOCTYPE, submission_name, "name", for_update=True)
	submission = frappe.get_doc(OIS_DOCTYPE, submission_name)
	rows = _schedule(submission)
	contract_status = (
		cstr(frappe.db.get_value("CRM Contract", submission.contract, "status") or "") if submission.get("contract") else ""
	)
	invoices = _documents(submission, rows)[1]
	policy = rules.advance_policy(submission.status, contract_status, rows, _unpaid_count(invoices))
	if not policy["allowed"]:
		frappe.throw(_(policy["reason"]), frappe.ValidationError)
	count = cint(count)
	if count < 1 or count > policy["max_periods"]:
		frappe.throw(_("Choose between 1 and {0} periods.").format(policy["max_periods"]), frappe.ValidationError)
	selected = rules.select_next_periods(rows, count)

	today = getdate(nowdate())
	issued, failure = [], ""
	for row in selected:
		key = cstr(row.get("billing_key") or "").strip()
		if not key:
			key = "%s-Y%s-Q%s" % (submission.name, cint(row.get("year_number")), cint(row.get("quarter_number")))
		elif not key.startswith("%s-" % submission.name):
			key = "%s-%s" % (submission.name, key)
		row["billing_key"] = key
		scheduled = rules.scheduled_date(row)
		scheduled_due = rules.scheduled_due_date(row)
		save_point = "optin_ledger_%s" % frappe.generate_hash(length=8)
		frappe.db.savepoint(save_point)
		try:
			quote_name = _quote_for_schedule(submission, cint(row.get("year_number")))
			if not quote_name:
				raise frappe.ValidationError(_("The quotation for {0} is missing.").format(rules.period_label(row)))
			quotation = frappe.get_doc("Quotation", quote_name)
			due = rules.early_due_date(today, scheduled_due)
			order_name, invoice_name = _create_order_and_invoice(row, quotation, submission, today, due_date=due)
			if not order_name or not invoice_name:
				raise frappe.ValidationError(_("ERPNext billing is not available on this site."))
		except Exception as exc:
			frappe.db.rollback(save_point=save_point)
			row["status"] = "Failed"
			row["error"] = cstr(exc)[:500]
			failure = row["error"]
			frappe.log_error(frappe.get_traceback(), "optin ledger: issue %s failed" % key)
			break
		row.setdefault("scheduled_invoice_date", scheduled)
		row.setdefault("scheduled_due_date", scheduled_due)
		row.update(
			{
				"sales_order": order_name,
				"sales_invoice": invoice_name,
				"status": "Invoiced",
				"invoice_date": today.isoformat(),
				"invoice_due_date": due,
				"issued_early": bool(scheduled and today < getdate(scheduled)),
				"issued_on": now_datetime().isoformat(sep=" ", timespec="seconds"),
				"issued_by": issued_by,
				"issued_by_user": frappe.session.user,
			}
		)
		row.pop("error", None)
		issued.append({"billing_key": key, "label": rules.period_label(row), "sales_order": order_name, "sales_invoice": invoice_name, "amount": flt(row.get("amount_incl_vat"))})

	submission.billing_schedule_json = json.dumps(rows, default=str)
	submission.flags.ignore_permissions = True
	submission.save(ignore_permissions=True)  # SYSTEM-INTERNAL: authorised above
	if issued:
		submission.add_comment(
			"Info",
			_("{0} issued {1} early: {2}").format(
				"Customer" if issued_by == "customer" else "Staff",
				len(issued),
				", ".join("%s (%s)" % (item["label"], item["sales_invoice"]) for item in issued),
			),
		)
	frappe.db.commit()
	if failure and not issued:
		frappe.throw(_("The invoice could not be created: {0}").format(failure), frappe.ValidationError)
	return {"issued": issued, "error": failure}


@frappe.whitelist(methods=["GET", "POST"])
def get_optin_ledger(ois_number: Any = None):
	return build_ledger(_portal_submission(ois_number))


@frappe.whitelist(methods=["POST"])
def issue_optin_periods(ois_number: Any = None, count: Any = 1):
	submission = _portal_submission(ois_number)
	result = issue_periods(submission.name, count, "customer")
	result["ledger"] = build_ledger(frappe.get_doc(OIS_DOCTYPE, submission.name))
	return result


@frappe.whitelist(methods=["GET", "POST"])
def get_optin_ledger_for_deal(deal: Any = None):
	submission = _deal_submission(deal)
	if not submission:
		return None
	ledger = build_ledger(submission, staff=True)
	ledger["can_issue"] = bool(STAFF_ISSUER_ROLES.intersection(frappe.get_roles()))
	return ledger


@frappe.whitelist(methods=["POST"])
def issue_optin_periods_for_deal(deal: Any = None, count: Any = 1):
	submission = _deal_submission(deal, require_issuer=True)
	if not submission:
		frappe.throw(_("This Deal has no Opt-In submission."), frappe.DoesNotExistError)
	result = issue_periods(submission.name, count, "staff")
	ledger = build_ledger(frappe.get_doc(OIS_DOCTYPE, submission.name), staff=True)
	ledger["can_issue"] = True
	result["ledger"] = ledger
	return result


def _quote_allowed_for_user(quotation: str, ois_number: str, customer: str) -> bool:
	from crm.api.website_redirect import get_user_customer_names, require_portal_user

	if ois_number:
		if ois_number not in require_portal_user():
			return False
		raw = frappe.db.get_value(OIS_DOCTYPE, ois_number, "quote_names_json") or "[]"
		try:
			return quotation in (json.loads(raw) or [])
		except (TypeError, ValueError):
			return False
	if customer:
		require_portal_user()
		if customer not in (get_user_customer_names(frappe.session.user) or []):
			return False
		return frappe.db.get_value("Quotation", quotation, "party_name") == customer
	return False


@frappe.whitelist(methods=["GET"])
def quotation_pdf(quotation: Any = None, ois_number: Any = None, customer: Any = None):
	"""Stream a quote PDF to a portal user who owns it (P-130)."""
	quotation = cstr(quotation).strip()
	ois_number = cstr(ois_number).strip()
	customer = cstr(customer).strip()
	if not quotation or not frappe.db.exists("Quotation", quotation) or not _quote_allowed_for_user(quotation, ois_number, customer):
		frappe.throw(_("That quotation is not linked to your account."), frappe.PermissionError)
	if cint(frappe.db.get_value("Quotation", quotation, "docstatus")) == 2:
		frappe.throw(_("That quotation was cancelled."), frappe.ValidationError)
	# Ownership was checked above; portal users hold no Quotation print permission.
	previous = frappe.flags.ignore_print_permissions
	frappe.flags.ignore_print_permissions = True
	try:
		pdf = frappe.get_print("Quotation", quotation, "Careverse Quote Standard", as_pdf=True)
	finally:
		frappe.flags.ignore_print_permissions = previous
	frappe.local.response.filename = "%s.pdf" % quotation
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"
