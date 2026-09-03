"""Retry-safe quarterly billing for multi-year Opt-In subscriptions.

This service is intentionally separate from ``accept_quote``.  That endpoint
continues to serve legacy, one-off quotations; Opt-In bundles are issued only
after the contract is fully executed and each year/quarter has its own stable
idempotency key.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def _json(value, default):
	try:
		result = json.loads(value or "")
	except (TypeError, ValueError, json.JSONDecodeError):
		return default
	return result if isinstance(result, type(default)) else default


def _field(doc, name, value):
	try:
		if doc.meta.has_field(name):
			setattr(doc, name, value)
	except Exception:
		pass


def _quarter_items(quotation, quarter_number):
	"""Copy annual quotation items as one quarter without mutating the quote."""
	items = []
	for row in quotation.items or []:
		annual_amount = float(row.amount or (row.qty or 0) * (row.rate or 0))
		quarter_amount = round(annual_amount / 4, 2)
		# Keep the four quarters exactly reconciled to the annual quotation. Any
		# half-cent rounding remainder is carried by Q4 rather than silently
		# over/under-billing the customer.
		if int(quarter_number or 0) == 4:
			quarter_amount = round(annual_amount - (round(annual_amount / 4, 2) * 3), 2)
		items.append(
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"description": row.description,
				"qty": 1,
				"uom": row.uom or "Nos",
				"rate": quarter_amount,
				"price_list_rate": quarter_amount,
				"discount_percentage": 0,
			}
		)
	return items


def _apply_order_tax_template(order, quotation):
	"""Copy the quotation's exclusive VAT template to a generated order.

	ERPNext's Sales Order → Sales Invoice mapper only carries taxes that are
	actually present on the order.  Keeping the same template prevents quarterly
	invoices from silently becoming net-only when the annual quotation already
	contains the configured VAT charge.
	"""
	tax_template = frappe.utils.cstr(getattr(quotation, "taxes_and_charges", "") or "").strip()
	if not tax_template:
		return
	try:
		from erpnext.controllers.accounts_controller import get_taxes_and_charges

		order.taxes_and_charges = tax_template
		order.set("taxes", get_taxes_and_charges("Sales Taxes and Charges Template", tax_template))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "optin billing: quotation VAT template could not be copied")
		raise


def _find_billing_document(doctype, billing_key, submission=None, year=None, quarter=None):
	"""Find a document created for a schedule row, when additive fields exist.

	The submission link is part of the lookup whenever available.  A bare
	``Y1-Q1`` key is not globally unique, so it must never allow one customer's
	document to satisfy another customer's schedule.
	"""
	if not frappe.db.exists("DocType", doctype):
		return ""
	try:
		has_key = frappe.db.has_column(doctype, "crm_optin_billing_key")
		has_submission = bool(submission) and frappe.db.has_column(doctype, "crm_optin_submission")
		has_year = year is not None and frappe.db.has_column(doctype, "crm_optin_year")
		has_quarter = quarter is not None and frappe.db.has_column(doctype, "crm_optin_quarter")
		if not has_key and not (has_submission and has_year and has_quarter):
			return ""
		filters = {}
		if has_key and billing_key:
			filters["crm_optin_billing_key"] = billing_key
		if has_submission:
			filters["crm_optin_submission"] = submission
		if has_year:
			filters["crm_optin_year"] = year
		if has_quarter:
			filters["crm_optin_quarter"] = quarter
		rows = frappe.get_list(
			doctype,
			filters=filters,
			fields=["name"],
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
		return rows[0].name if rows else ""
	except Exception:
		# Older ERPNext sites may not have the custom field during a rolling
		# migration. The scheduler remains usable; the submission row is still
		# the idempotency source on those sites.
		return ""


def _create_order_and_invoice(schedule, quotation, submission, issue_date):
	"""Create a native SO and SI pair for one billing row."""
	if not frappe.db.exists("DocType", "Sales Order") or not frappe.db.exists("DocType", "Sales Invoice"):
		return "", ""
	billing_key = frappe.utils.cstr(schedule.get("billing_key") or "").strip()
	year = schedule.get("year_number")
	quarter = schedule.get("quarter_number")
	order_name = _find_billing_document(
		"Sales Order", billing_key, submission.name, year, quarter
	)
	invoice_name = _find_billing_document(
		"Sales Invoice", billing_key, submission.name, year, quarter
	)
	if invoice_name:
		return order_name, invoice_name

	if int(quotation.docstatus or 0) != 1:
		quotation.flags.ignore_permissions = True  # SYSTEM-INTERNAL
		quotation.flags.ignore_validate = True
		quotation.submit()

	if order_name:
		order = frappe.get_doc("Sales Order", order_name)
		if int(order.docstatus or 0) != 1:
			order.flags.ignore_permissions = True  # SYSTEM-INTERNAL
			order.flags.ignore_validate = True
			order.flags.ignore_mandatory = True
			order.submit()
	else:
		quarter_items = _quarter_items(quotation, schedule.get("quarter_number"))
		order = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": quotation.party_name,
				"company": quotation.company,
				"transaction_date": issue_date,
				"delivery_date": issue_date,
				"currency": quotation.currency or "KES",
				"selling_price_list": quotation.selling_price_list,
			"items": quarter_items,
		}
		)
		_field(order, "crm_optin_submission", submission.name)
		_field(order, "crm_optin_year", schedule.get("year_number"))
		_field(order, "crm_optin_quarter", schedule.get("quarter_number"))
		_field(order, "crm_optin_quotation", quotation.name)
		_field(order, "crm_optin_billing_key", billing_key)
		_field(order, "quotation", quotation.name)
		order.flags.ignore_permissions = True  # SYSTEM-INTERNAL
		order.flags.ignore_validate = True
		order.flags.ignore_mandatory = True
		order.set_missing_values()
		# set_missing_values may resolve the monthly Item Price. The quarterly
		# amount is authoritative for this schedule row, so restore each rate before
		# calculating taxes and totals.
		for row, source in zip(order.items or [], quarter_items, strict=False):
			row.price_list_rate = source["price_list_rate"]
			row.rate = source["rate"]
			row.discount_percentage = 0
		_apply_order_tax_template(order, quotation)
		order.calculate_taxes_and_totals()
		due_date = frappe.utils.add_days(issue_date, 30)
		order.set("payment_schedule", [])
		order.append(
			"payment_schedule",
			{
				"due_date": due_date,
				"invoice_portion": 100,
				"payment_amount": order.grand_total,
				"base_payment_amount": order.base_grand_total,
			},
		)
		order.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
		order.submit()

	invoice = None
	try:
		from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

		invoice = make_sales_invoice(order.name)
	except Exception:
		# ERPNext v15/v16 mapper names are stable, but keep a clear fallback for a
		# CRM-only or partially-installed site rather than marking a false success.
		frappe.log_error(frappe.get_traceback(), "optin billing: sales invoice mapper failed")
		raise
	invoice.posting_date = issue_date
	invoice.due_date = frappe.utils.add_days(issue_date, 30)
	# The native mapper carries the order's quarter values, but restoring them
	# here protects against ERPNext versions that re-fetch a current list price
	# while preparing the target invoice.
	quarter_items = _quarter_items(quotation, schedule.get("quarter_number"))
	for row, source in zip(invoice.items or [], quarter_items, strict=False):
		row.price_list_rate = source["price_list_rate"]
		row.rate = source["rate"]
		row.discount_percentage = 0
	if getattr(invoice, "taxes", None):
		invoice.calculate_taxes_and_totals()
	for payment in invoice.get("payment_schedule") or []:
		payment.due_date = invoice.due_date
	_field(invoice, "crm_optin_submission", submission.name)
	_field(invoice, "crm_optin_year", schedule.get("year_number"))
	_field(invoice, "crm_optin_quarter", schedule.get("quarter_number"))
	_field(invoice, "crm_optin_quotation", quotation.name)
	_field(invoice, "crm_optin_billing_key", billing_key)
	invoice.flags.ignore_permissions = True  # SYSTEM-INTERNAL
	invoice.flags.ignore_validate = True
	invoice.flags.ignore_mandatory = True
	invoice.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	invoice.submit()
	return order.name, invoice.name


def process_due_optin_billing():
	"""Issue due, fully-executed Opt-In schedule rows; safe to run hourly/daily."""
	if not frappe.db.exists("DocType", "CRM Opt-In Submission"):
		return {"processed": 0, "skipped": 0}
	if not frappe.db.has_column("CRM Opt-In Submission", "billing_schedule_json"):
		return {"processed": 0, "skipped": 0}
	rows = frappe.get_list(
		"CRM Opt-In Submission",
		filters={"status": "Processed"},
		fields=["name", "deal", "contract", "billing_schedule_json"],
		limit_page_length=0,
		ignore_permissions=True,  # SYSTEM-INTERNAL: scheduled system task
	)
	processed = skipped = failed = 0
	for row in rows:
		schedules = _json(row.billing_schedule_json, [])
		if not schedules:
			continue
		if not row.contract or not frappe.db.exists("CRM Contract", row.contract):
			skipped += 1
			continue
		contract_status = frappe.db.get_value("CRM Contract", row.contract, "status")
		if contract_status != "Fully Executed":
			continue
		# Serialize workers per submission before reading/writing the JSON schedule.
		# The stable billing key protects retries, while this row lock prevents two
		# scheduler processes from both observing the same Scheduled row at once.
		if not frappe.db.get_value("CRM Opt-In Submission", row.name, "name", for_update=True):
			continue
		submission = frappe.get_doc("CRM Opt-In Submission", row.name)
		for schedule in schedules:
			if schedule.get("status") != "Scheduled" or schedule.get("sales_invoice"):
				continue
			# Older bundles used ``Y1-Q1`` as the key. Normalize that value at
			# processing time so retries on migrated records cannot collide with
			# another submission's same quarter.
			raw_key = frappe.utils.cstr(schedule.get("billing_key") or "").strip()
			if raw_key and not raw_key.startswith("%s-" % row.name):
				schedule["billing_key"] = "%s-%s" % (row.name, raw_key)
			if getdate(schedule.get("invoice_date") or schedule.get("scheduled_order_date")) > getdate(nowdate()):
				continue
			save_point = "optin_billing_%s_%s" % (
				frappe.utils.cstr(row.name).replace("-", "_"),
				frappe.utils.cstr(schedule.get("billing_key") or "row").replace("-", "_"),
			)
			frappe.db.savepoint(save_point)
			try:
				year = int(schedule.get("year_number") or 0)
				quote_name = _quote_for_schedule(submission, year)
				if not quote_name:
					schedule["status"] = "Failed"
					schedule["error"] = "Yearly quotation is missing"
					failed += 1
					continue
				quotation = frappe.get_doc("Quotation", quote_name)
				issue_date = getdate(schedule.get("invoice_date") or schedule.get("scheduled_order_date"))
				order_name, invoice_name = _create_order_and_invoice(schedule, quotation, submission, issue_date)
				if not order_name or not invoice_name:
					raise frappe.ValidationError(
						_("ERPNext billing is not available on this site; the schedule was not issued.")
					)
				schedule["sales_order"] = order_name
				schedule["sales_invoice"] = invoice_name
				schedule["status"] = "Invoiced"
				schedule["invoice_due_date"] = frappe.utils.add_days(issue_date, 30)
				processed += 1
			except Exception as exc:
				frappe.db.rollback(save_point=save_point)
				schedule["status"] = "Failed"
				schedule["error"] = frappe.utils.cstr(exc)[:500]
				failed += 1
				frappe.log_error(frappe.get_traceback(), "optin billing: %s" % row.name)
		if frappe.db.has_column("CRM Opt-In Submission", "billing_schedule_json"):
			submission.billing_schedule_json = json.dumps(schedules, default=str)
			submission.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	if processed or failed:
		frappe.db.commit()
	return {"processed": processed, "skipped": skipped, "failed": failed}


def _quote_for_schedule(submission, year):
	if frappe.db.has_column("CRM Opt-In Submission", "quote_names_json"):
		quote_names = _json(submission.get("quote_names_json"), [])
		if quote_names:
			plans = _json(submission.get("pricing_plans_json"), [])
			for index, plan in enumerate(plans):
				if int(plan.get("year_number") or index + 1) == year and index < len(quote_names):
					return quote_names[index]
	filters = {"crm_deal": submission.deal}
	if frappe.db.has_column("Quotation", "crm_optin_submission"):
		filters = {"crm_optin_submission": submission.name, "crm_optin_year": year}
	rows = frappe.get_list("Quotation", filters=filters, fields=["name"], limit=1, ignore_permissions=True)
	return rows[0].name if rows else ""
