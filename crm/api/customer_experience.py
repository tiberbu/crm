"""Authenticated Customer Experience token purchase orchestration.

Every mutation is scoped to an OIS User Permission.  Browser-supplied OIS,
facility, order, and package values are treated as selectors only and are
revalidated against the permission and the server-side onboarding snapshot.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Any

import frappe
from frappe import _
from frappe.utils.synchronization import filelock

from crm.api.facility_onboarding import _token_packages
from crm.api.website_redirect import get_user_ois_numbers, require_portal_user
from crm.fcrm.doctype.crm_onboarding_evidence.crm_onboarding_evidence import evidence_ref, record_event


def _text(value):
	return frappe.utils.cstr(value or "").strip()


def _submission(ois_number):
	ois_number = _text(ois_number)
	if ois_number not in require_portal_user():
		frappe.throw(_("That facility record is not linked to your account."), frappe.PermissionError)
	return frappe.get_doc("CRM Opt-In Submission", ois_number)


def _snapshot_facilities(submission):
	try:
		payload = json.loads(submission.raw_json or "{}")
	except (TypeError, ValueError):
		payload = {}
	rows = payload.get("facilities") or payload.get("pricing") or []
	return [row for row in rows if isinstance(row, dict)]


def _package(item_code):
	item_code = _text(item_code)
	return next((row for row in _token_packages() if row["item_code"] == item_code), None)


def _customer(submission):
	organization = ""
	if submission.deal and frappe.db.exists("CRM Deal", submission.deal):
		organization = _text(frappe.db.get_value("CRM Deal", submission.deal, "organization"))
	from crm.api.quotes import _ensure_customer

	return _ensure_customer(
		organization or submission.facility_signatory_name or submission.submitter_email, commit=False
	)


def _company():
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		frappe.throw(_("ERPNext default company is not configured."), frappe.ValidationError)
	return company


def _period_key(package, today=None):
	today = frappe.utils.getdate(today or frappe.utils.today())
	period = _text(package.get("billing_period")) or "Monthly"
	if period == "Annual":
		return "%d" % today.year
	if period == "Quarterly":
		return "%d-Q%d" % (today.year, (today.month - 1) // 3 + 1)
	return "%d-%02d" % (today.year, today.month)


def _purchase_key(submission, facility_mfl, package):
	"""Server-derived identity of one facility's package purchase for one billing period."""
	raw = "|".join((submission.name, facility_mfl, package["item_code"], _period_key(package)))
	return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _existing_document(doctype, key, **filters):
	if not frappe.db.has_column(doctype, "crm_token_purchase_key"):
		return None
	return frappe.db.get_value(
		doctype,
		{"crm_token_purchase_key": key, "docstatus": ["!=", 2], **filters},
		"name",
	)


@contextmanager
def _system_user():
	"""Create ERPNext documents as system; the portal user was already authorised by OIS permission."""
	previous = frappe.session.user
	frappe.flags.crm_cx_actor = previous
	frappe.set_user("Administrator")  # SYSTEM-INTERNAL
	try:
		yield
	finally:
		frappe.set_user(previous)
		frappe.flags.crm_cx_actor = None


def _record_link(doctype, name):
	try:
		record_event(
			"document_linked",
			subject_ref=evidence_ref(frappe.flags.get("crm_cx_actor") or frappe.session.user),
			reference_doctype=doctype,
			reference_name=name,
		)
	except Exception as exc:
		frappe.log_error(
			title="CRM token purchase evidence", message="Evidence write failed (%s)" % type(exc).__name__
		)


def _order_rows(submission):
	if not frappe.db.has_column("Sales Order", "crm_optin_submission"):
		return []
	return frappe.get_list(
		"Sales Order",
		filters={"crm_optin_submission": submission.name, "docstatus": 1, "per_billed": ["<", 100]},
		fields=[
			"name",
			"transaction_date",
			"delivery_date",
			"grand_total",
			"currency",
			"status",
			"crm_token_facility_mfl",
			"crm_token_package_item",
		],
		order_by="creation desc",
		limit_page_length=200,
		ignore_permissions=True,
	)


@frappe.whitelist(methods=["GET"])
def get_purchase_context():
	"""Return scoped package, facility, order, and invoice data for the portal."""
	ois_numbers = require_portal_user()
	rows = []
	from crm.api.checkout import _invoice_rows

	for ois_number in ois_numbers:
		submission = frappe.get_doc("CRM Opt-In Submission", ois_number)
		rows.append(
			{
				"ois": ois_number,
				"facilities": _snapshot_facilities(submission),
				"orders": _order_rows(submission),
				"invoices": _invoice_rows(submission),
			}
		)
	return {"success": True, "data": {"token_packages": _token_packages(), "ois": rows}}


@frappe.whitelist(methods=["POST"])
def create_token_order(ois_number: Any, facility_mfl: Any, package_item_code: Any, purchase_key: Any = None):
	"""Create or resume the one Quotation and submitted Sales Order for a facility, package and period.

	``purchase_key`` is accepted for older clients only; idempotency uses a key the server derives.
	"""
	submission = _submission(ois_number)
	facility_mfl = _text(facility_mfl)
	if not any(_text(row.get("mfl_code")) == facility_mfl for row in _snapshot_facilities(submission)):
		frappe.throw(_("That facility is not part of this Opt-In Request."), frappe.PermissionError)
	package = _package(package_item_code)
	if not package:
		frappe.throw(_("That token package is not available."), frappe.ValidationError)
	key = _purchase_key(submission, facility_mfl, package)
	with filelock("crm_cx_order_%s" % key, timeout=60), _system_user():
		source_quote = _initial_onboarding_quote(submission, facility_mfl, package)
		return _create_or_resume_order(submission, facility_mfl, package, key, source_quote=source_quote)


def create_initial_token_order(submission_name, facility_mfl, package_item_code):
	"""Create the initial self-onboarding Sales Order without requiring a portal login."""
	# This coordinator runs in the Guest request that completed the public wizard.
	# Catalog, OIS, Customer, and source Quotation reads are internal operations.
	with _system_user():
		submission = frappe.get_doc("CRM Opt-In Submission", submission_name)
		if _text(getattr(submission, "onboarding_source", "")) != "token_self_onboarding":
			frappe.throw(
				_("Initial token orders are available only to self-onboarding submissions."),
				frappe.PermissionError,
			)
		facility_mfl = _text(facility_mfl)
		if not any(_text(row.get("mfl_code")) == facility_mfl for row in _snapshot_facilities(submission)):
			frappe.throw(_("That facility is not part of this Opt-In Request."), frappe.PermissionError)
		package = _package(package_item_code)
		if not package:
			frappe.throw(_("That token package is not available."), frappe.ValidationError)
		key = _purchase_key(submission, facility_mfl, package)
		with filelock("crm_cx_order_%s" % key, timeout=60):
			source_quote = _initial_onboarding_quote(submission, facility_mfl, package)
			if not source_quote:
				frappe.throw(
					_("The onboarding quote could not be matched to this facility and token package."),
					frappe.ValidationError,
				)
			return _create_or_resume_order(
				submission, facility_mfl, package, key, source_quote=source_quote
			)


def _initial_onboarding_quote(submission, facility_mfl, package):
	"""Return the exact quote already raised by the self-onboarding OIS, if it matches."""
	if _text(getattr(submission, "onboarding_source", "")) != "token_self_onboarding":
		return None
	try:
		quote_names = json.loads(getattr(submission, "quote_names_json", "[]") or "[]")
	except (TypeError, ValueError):
		quote_names = []
	if not isinstance(quote_names, list):
		return None
	customer = _customer(submission)
	for quote_name in quote_names:
		if not isinstance(quote_name, str) or not frappe.db.exists("Quotation", quote_name):
			continue
		quotation = frappe.get_doc("Quotation", quote_name)
		if quotation.docstatus == 2 or _text(getattr(quotation, "crm_deal", "")) != _text(submission.deal):
			continue
		if _text(getattr(quotation, "party_name", "")) != customer:
			continue
		if _text(getattr(quotation, "currency", "")) != _text(package.get("currency")):
			continue
		if frappe.db.has_column("Quotation", "crm_token_facility_mfl"):
			stamped_facility = _text(getattr(quotation, "crm_token_facility_mfl", ""))
			if stamped_facility and stamped_facility != facility_mfl:
				continue
		if frappe.db.has_column("Quotation", "crm_token_package_item"):
			stamped_package = _text(getattr(quotation, "crm_token_package_item", ""))
			if stamped_package and stamped_package != package["item_code"]:
				continue
		items = [row for row in quotation.items or [] if _text(row.item_code) == package["item_code"]]
		if len(items) != 1 or len(quotation.items or []) != 1:
			continue
		if int(frappe.utils.flt(items[0].qty) or 0) != 1:
			continue
		if abs(float(frappe.utils.flt(items[0].rate)) - float(package["price"])) > 0.01:
			continue
		return quotation.name
	return None


def _create_or_resume_order(submission, facility_mfl, package, key, source_quote=None):
	order_name = _existing_document("Sales Order", key)
	quotation_name = _existing_document("Quotation", key)
	if order_name:
		return {
			"success": True,
			"data": {"quotation": quotation_name, "sales_order": order_name, "idempotent": True},
		}

	from crm.automation.optin_billing import _apply_order_tax_template
	from crm.utils.quotation_tax import apply_quotation_taxes

	settings = frappe.get_single("CRM Opt-In Settings")
	validity = int(settings.get("token_sales_order_validity_days") or 30)
	due_days = int(settings.get("token_invoice_due_days") or 30)
	price = float(package["price"])
	today = frappe.utils.today()
	customer = _customer(submission)
	company = _company()
	provenance = {
		"crm_optin_submission": submission.name,
		"crm_token_purchase_key": key,
		"crm_token_facility_mfl": facility_mfl,
		"crm_token_package_item": package["item_code"],
	}
	item = {
		"item_code": package["item_code"],
		"qty": 1,
		"price_list_rate": price,
		"rate": price,
		"description": package["description"],
	}
	if quotation_name:
		quotation = frappe.get_doc("Quotation", quotation_name)
	elif source_quote:
		quotation = frappe.get_doc("Quotation", source_quote)
		for fieldname, value in (
			("crm_token_purchase_key", key),
			("crm_token_facility_mfl", facility_mfl),
			("crm_token_package_item", package["item_code"]),
		):
			if frappe.db.has_column("Quotation", fieldname):
				setattr(quotation, fieldname, value)
		quotation.save(ignore_permissions=True)  # SYSTEM-INTERNAL: verified onboarding source quote
		_record_link("Quotation", quotation.name)
	else:
		quotation = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": customer,
				"company": company,
				"transaction_date": today,
				"valid_till": frappe.utils.add_days(today, validity),
				"selling_price_list": package["price_list"],
				"currency": package["currency"],
				"order_type": "Sales",
				**provenance,
			}
		)
		quotation.append("items", dict(item))
		quotation.flags.ignore_mandatory = True
		quotation.flags.ignore_permissions = True  # SYSTEM-INTERNAL: server-priced portal purchase
		quotation.set_missing_values()
		_restore_rate(quotation, price)
		apply_quotation_taxes(quotation)
		quotation.insert(ignore_permissions=True, ignore_mandatory=True)  # SYSTEM-INTERNAL
		_record_link("Quotation", quotation.name)

	delivery = frappe.utils.add_days(today, validity)
	sales_order = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": company,
			"transaction_date": today,
			"delivery_date": delivery,
			"selling_price_list": package["price_list"],
			"currency": package["currency"],
			"order_type": "Sales",
			"crm_optin_quotation": quotation.name
			if frappe.db.has_column("Sales Order", "crm_optin_quotation")
			else None,
			**provenance,
		}
	)
	sales_order.append("items", {**item, "delivery_date": delivery})
	sales_order.flags.ignore_mandatory = True
	sales_order.flags.ignore_permissions = True  # SYSTEM-INTERNAL
	sales_order.set_missing_values()
	_restore_rate(sales_order, price)
	_apply_order_tax_template(sales_order, quotation)
	sales_order.calculate_taxes_and_totals()
	sales_order.set("payment_schedule", [])
	sales_order.append(
		"payment_schedule",
		{
			"due_date": frappe.utils.add_days(today, due_days),
			"invoice_portion": 100,
			"payment_amount": sales_order.grand_total,
			"base_payment_amount": sales_order.base_grand_total,
		},
	)
	sales_order.insert(ignore_permissions=True, ignore_mandatory=True)  # SYSTEM-INTERNAL
	sales_order.submit()
	_record_link("Sales Order", sales_order.name)
	return {
		"success": True,
		"data": {"quotation": quotation.name, "sales_order": sales_order.name, "idempotent": False},
	}


def _restore_rate(document, price):
	# set_missing_values can re-resolve a current list price; the catalog price is authoritative.
	for row in document.items or []:
		row.price_list_rate = price
		row.rate = price
		row.discount_percentage = 0


@frappe.whitelist(methods=["POST"])
def start_token_payment(sales_order: Any):
	"""Create and submit the one invoice for a submitted Sales Order, only when the user starts payment."""
	if not frappe.db.has_column("Sales Order", "crm_optin_submission"):
		frappe.throw(_("Token order fields are not installed."), frappe.ValidationError)
	require_portal_user()
	name = _text(sales_order)
	order = (
		frappe.db.get_value(
			"Sales Order",
			name,
			["name", "crm_optin_submission", "crm_token_purchase_key", "docstatus", "status"],
			as_dict=True,
		)
		if name
		else None
	)
	# One error for missing and foreign orders so names cannot be probed.
	if not order or _text(order.crm_optin_submission) not in get_user_ois_numbers():
		frappe.throw(_("That order is not linked to your account."), frappe.PermissionError)
	with (
		filelock("crm_cx_invoice_%s" % hashlib.sha256(order.name.encode()).hexdigest()[:32], timeout=60),
		_system_user(),
	):
		return _start_or_resume_payment(order)


def _start_or_resume_payment(order):
	key = _text(order.crm_token_purchase_key)
	invoice_name = _existing_document("Sales Invoice", key, crm_optin_submission=order.crm_optin_submission)
	idempotent = bool(invoice_name)
	if invoice_name:
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if invoice.docstatus == 0:
			invoice.flags.ignore_permissions = True  # SYSTEM-INTERNAL
			invoice.submit()
	else:
		if order.docstatus != 1 or order.status in ("Closed", "On Hold", "Cancelled"):
			frappe.throw(_("Only an open Sales Order can start payment."), frappe.ValidationError)
		invoice = _make_invoice(order, key)
		_record_link("Sales Invoice", invoice.name)
	return {
		"success": True,
		"data": {
			"invoice": invoice.name,
			"ois": order.crm_optin_submission,
			"idempotent": idempotent,
			"checkout_url": "/payment-checkout?ois=%s" % order.crm_optin_submission,
		},
	}


def _make_invoice(order, key):
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	invoice = make_sales_invoice(order.name, ignore_permissions=True)
	for fieldname, value in (
		("crm_optin_submission", order.crm_optin_submission),
		("crm_token_purchase_key", key),
		("crm_token_facility_mfl", frappe.db.get_value("Sales Order", order.name, "crm_token_facility_mfl")),
		("crm_token_package_item", frappe.db.get_value("Sales Order", order.name, "crm_token_package_item")),
	):
		if frappe.db.has_column("Sales Invoice", fieldname):
			invoice.set(fieldname, value)
	settings = frappe.get_single("CRM Opt-In Settings")
	invoice.due_date = frappe.utils.add_days(
		frappe.utils.today(), int(settings.get("token_invoice_due_days") or 30)
	)
	for payment in invoice.get("payment_schedule") or []:
		payment.due_date = invoice.due_date
	invoice.flags.ignore_mandatory = True
	invoice.flags.ignore_permissions = True  # SYSTEM-INTERNAL
	invoice.insert(ignore_permissions=True, ignore_mandatory=True)  # SYSTEM-INTERNAL
	invoice.submit()
	return invoice
