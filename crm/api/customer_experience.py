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

from crm.api.facility_onboarding import _calculator_config, _token_packages
from crm.api.website_redirect import get_user_customer_names, get_user_ois_numbers, require_portal_user
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
	orders = frappe.get_list(
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
	for order in orders:
		order["can_create_invoice"] = _invoice_status_allows(order.get("status"))
	return orders


def _invoice_status_allows(status):
	"""Keep the portal's invoice action aligned with the server-side status guard."""
	return _text(status).casefold() not in {"closed", "on hold", "cancelled"}


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
	return {
		"success": True,
		"data": {
			"token_packages": _token_packages(),
			"calculator_config": _calculator_config(),
			"ois": rows,
		},
	}


@frappe.whitelist(methods=["POST"])
def create_token_order(
	ois_number: Any = None,
	facility_mfl: Any = None,
	package_item_code: Any = None,
	purchase_key: Any = None,
	customer: Any = None,
):
	"""Create or resume the one Quotation and submitted Sales Order for a facility, package and period.

	``purchase_key`` is accepted for older clients only; idempotency uses a key the server derives.
	"""
	facility_mfl = _text(facility_mfl)
	package = _package(package_item_code)
	if not package:
		frappe.throw(_("That token package is not available."), frappe.ValidationError)

	customer = _text(customer)
	ois_number = _text(ois_number)
	if not ois_number and not customer:
		frappe.throw(_("Missing account reference."), frappe.ValidationError)

	if ois_number and ois_number in get_user_ois_numbers():
		submission = _submission(ois_number)
		if not any(_text(row.get("mfl_code")) == facility_mfl for row in _snapshot_facilities(submission)):
			frappe.throw(_("That facility is not part of this Opt-In Request."), frappe.PermissionError)
		key = _purchase_key(submission, facility_mfl, package)
		with filelock("crm_cx_order_%s" % key, timeout=60), _system_user():
			source_quote = _initial_onboarding_quote(submission, facility_mfl, package)
			return _create_or_resume_order(submission, facility_mfl, package, key, source_quote=source_quote)

	cust_name = customer or ois_number
	if cust_name not in get_user_customer_names():
		frappe.throw(_("That facility record is not linked to your account."), frappe.PermissionError)

	facility_parents = frappe.get_all(
		"CRM Pre-Qualified Facility",
		filters={"mfl_code": facility_mfl},
		fields=["name"],
		ignore_permissions=True,
		limit_page_length=1,
	)
	if not facility_parents:
		frappe.throw(_("Facility not found."), frappe.ValidationError)
	has_membership = frappe.db.exists(
		"CRM Facility Membership",
		{"parent": facility_parents[0]["name"], "customer": cust_name},
	)
	if not has_membership:
		frappe.throw(_("That facility is not part of your account."), frappe.PermissionError)

	raw_key = "|".join((cust_name, facility_mfl, package["item_code"], _period_key(package)))
	key = hashlib.sha256(raw_key.encode()).hexdigest()[:40]
	with filelock("crm_cx_order_%s" % key, timeout=60), _system_user():
		return _create_or_resume_customer_order(cust_name, facility_mfl, package, key)


def _create_or_resume_customer_order(customer, facility_mfl, package, key):
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
	price = float(package["price"])
	today = frappe.utils.today()
	company = _company()
	provenance = {
		"customer": customer,
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
	else:
		price_list = package.get("price_list")
		if not price_list or not frappe.db.exists("Price List", price_list):
			price_list = (
				frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
			)
		quotation = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": customer,
				"company": company,
				"transaction_date": today,
				"valid_till": frappe.utils.add_days(today, validity),
				"selling_price_list": price_list,
				"currency": package.get("currency") or "KES",
				"order_type": "Sales",
				**provenance,
			}
		)
		quotation.append("items", dict(item))
		quotation.flags.ignore_mandatory = True
		quotation.flags.ignore_permissions = True
		quotation.set_missing_values()
		_restore_rate(quotation, price)
		apply_quotation_taxes(quotation)
		quotation.insert(ignore_mandatory=True, ignore_permissions=True)
		quotation_name = quotation.name
		_record_link("Quotation", quotation_name)

	from erpnext.selling.doctype.quotation.quotation import _make_sales_order

	sales_order = _make_sales_order(quotation_name, ignore_permissions=True)
	sales_order.flags.ignore_mandatory = True
	sales_order.flags.ignore_permissions = True
	sales_order.delivery_date = frappe.utils.add_days(today, validity)
	for fieldname, value in provenance.items():
		if frappe.db.has_column("Sales Order", fieldname):
			setattr(sales_order, fieldname, value)
	sales_order.set_missing_values()
	_restore_rate(sales_order, price)
	_apply_order_tax_template(sales_order)
	sales_order.insert(ignore_mandatory=True, ignore_permissions=True)
	sales_order.submit()
	_record_link("Sales Order", sales_order.name)
	return {
		"success": True,
		"data": {"quotation": quotation.name, "sales_order": sales_order.name, "idempotent": False},
	}


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
	tokens = int(package.get("token_quantity") or 400)
	description = package.get("description") or package.get("display_name") or package["item_code"]
	if package.get("item_code") == "CV-TOKEN-FREE" or price == 0:
		liability_val = float(tokens * 6.0)
		description = (
			f"{package.get('display_name', 'Free Trial')}: {tokens} Care Tokens granted with zero customer financial commitment. "
			f"Promotional Service Delivery Liability: KES {liability_val:,.2f} (evaluated at KES 6.00/token baseline). "
			"Customer Net Payable: KES 0.00."
		)
	item = {
		"item_code": package["item_code"],
		"qty": 1,
		"price_list_rate": price,
		"rate": price,
		"description": description,
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
	require_portal_user()
	name = _text(sales_order)
	fields = ["name", "crm_token_purchase_key", "docstatus", "status", "customer"]
	if frappe.db.has_column("Sales Order", "crm_optin_submission"):
		fields.append("crm_optin_submission")
	order = (
		frappe.db.get_value(
			"Sales Order",
			name,
			fields,
			as_dict=True,
		)
		if name
		else None
	)
	permitted_ois = get_user_ois_numbers()
	permitted_customers = get_user_customer_names()
	is_permitted = False
	if order:
		if _text(order.get("crm_optin_submission")) and _text(order.crm_optin_submission) in permitted_ois:
			is_permitted = True
		elif _text(order.get("customer")) and _text(order.customer) in permitted_customers:
			is_permitted = True
	if not order or not is_permitted:
		frappe.throw(_("That order is not linked to your account."), frappe.PermissionError)
	with (
		filelock("crm_cx_invoice_%s" % hashlib.sha256(order.name.encode()).hexdigest()[:32], timeout=60),
		_system_user(),
	):
		return _start_or_resume_payment(order)


def _start_or_resume_payment(order):
	key = _text(order.crm_token_purchase_key)
	existing_filters = {}
	if _text(order.get("crm_optin_submission")):
		existing_filters["crm_optin_submission"] = order.crm_optin_submission
	elif _text(order.get("customer")):
		existing_filters["customer"] = order.customer
	invoice_name = _existing_document("Sales Invoice", key, **existing_filters)
	idempotent = bool(invoice_name)
	if invoice_name:
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if invoice.docstatus == 0:
			invoice.flags.ignore_permissions = True  # SYSTEM-INTERNAL
			invoice.submit()
	else:
		if order.docstatus != 1 or not _invoice_status_allows(order.status):
			frappe.throw(_("Only an open Sales Order can start payment."), frappe.ValidationError)
		invoice = _make_invoice(order, key)
		_record_link("Sales Invoice", invoice.name)
	checkout_url = (
		"/payment-checkout?ois=%s" % order.crm_optin_submission
		if _text(order.get("crm_optin_submission"))
		else "/cx-portal?invoice=%s" % invoice.name
	)
	return {
		"success": True,
		"data": {
			"invoice": invoice.name,
			"ois": order.get("crm_optin_submission") or "",
			"customer": order.get("customer") or "",
			"idempotent": idempotent,
			"checkout_url": checkout_url,
		},
	}


def _make_invoice(order, key):
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	invoice = make_sales_invoice(order.name, ignore_permissions=True)
	for fieldname, value in (
		("crm_optin_submission", order.get("crm_optin_submission")),
		("crm_token_purchase_key", key),
		("crm_token_facility_mfl", frappe.db.get_value("Sales Order", order.name, "crm_token_facility_mfl") if frappe.db.has_column("Sales Order", "crm_token_facility_mfl") else None),
		("crm_token_package_item", frappe.db.get_value("Sales Order", order.name, "crm_token_package_item") if frappe.db.has_column("Sales Order", "crm_token_package_item") else None),
	):
		if value is not None and frappe.db.has_column("Sales Invoice", fieldname):
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
