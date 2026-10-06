"""Authenticated Customer Experience token purchase orchestration.

Every mutation is scoped to an OIS User Permission.  Browser-supplied OIS,
facility, order, and package values are treated as selectors only and are
revalidated against the permission and the server-side onboarding snapshot.
"""

from __future__ import annotations

import json
import secrets

import frappe
from frappe import _

from crm.api.facility_onboarding import _token_packages
from crm.api.website_redirect import get_user_ois_numbers, require_portal_user


def _text(value):
	return frappe.utils.cstr(value or "").strip()


def _submission(ois_number):
	ois_number = _text(ois_number)
	if ois_number not in get_user_ois_numbers():
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

	return _ensure_customer(organization or submission.facility_signatory_name or submission.submitter_email, commit=False)


def _company():
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		frappe.throw(_("ERPNext default company is not configured."), frappe.ConfigurationError)
	return company


def _existing_purchase(key):
	for doctype in ("Sales Order", "Quotation"):
		if not frappe.db.has_column(doctype, "crm_token_purchase_key"):
			continue
		name = frappe.db.get_value(doctype, {"crm_token_purchase_key": key}, "name")
		if name:
			return doctype, name
	return None


def _order_rows(submission):
	if not frappe.db.has_column("Sales Order", "crm_optin_submission"):
		return []
	return frappe.get_list(
		"Sales Order",
		filters={"crm_optin_submission": submission.name, "docstatus": 0},
		fields=["name", "transaction_date", "valid_till", "grand_total", "currency", "status", "crm_token_facility_mfl", "crm_token_package_item"],
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
def create_token_order(ois_number, facility_mfl, package_item_code, purchase_key=None):
	"""Create one draft next-period quotation and Sales Order for one facility."""
	submission = _submission(ois_number)
	facility_mfl = _text(facility_mfl)
	if not any(_text(row.get("mfl_code")) == facility_mfl for row in _snapshot_facilities(submission)):
		frappe.throw(_("That facility is not part of this Opt-In Request."), frappe.PermissionError)
	package = _package(package_item_code)
	if not package:
		frappe.throw(_("That token package is not available."), frappe.ValidationError)
	key = _text(purchase_key) or secrets.token_urlsafe(18)
	existing = _existing_purchase(key)
	if existing:
		return {"success": True, "data": {"quotation": existing[1] if existing[0] == "Quotation" else None, "sales_order": existing[1] if existing[0] == "Sales Order" else None, "idempotent": True}}
	settings = frappe.get_single("CRM Opt-In Settings")
	validity = int(settings.get("token_sales_order_validity_days") or 30)
	price = float(package["price"])
	customer = _customer(submission)
	company = _company()
	common = {
		"quotation_to": "Customer",
		"party_name": customer,
		"company": company,
		"transaction_date": frappe.utils.today(),
		"valid_till": frappe.utils.add_days(frappe.utils.today(), validity),
		"selling_price_list": package["price_list"],
		"currency": package["currency"],
		"order_type": "Sales",
		"crm_optin_submission": submission.name,
		"crm_token_purchase_key": key,
		"crm_token_facility_mfl": facility_mfl,
		"crm_token_package_item": package["item_code"],
	}
	quotation = frappe.get_doc({"doctype": "Quotation", **common})
	quotation.append("items", {"item_code": package["item_code"], "qty": 1, "price_list_rate": price, "rate": price, "description": package["description"]})
	quotation.flags.ignore_mandatory = True
	quotation.flags.ignore_permissions = True
	quotation.set_missing_values()
	quotation.insert(ignore_permissions=True, ignore_mandatory=True)
	sales_order = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": company,
			"transaction_date": frappe.utils.today(),
			"delivery_date": frappe.utils.add_days(frappe.utils.today(), validity),
			"selling_price_list": package["price_list"],
			"currency": package["currency"],
			"order_type": "Sales",
			"crm_optin_submission": submission.name,
			"crm_optin_quotation": quotation.name if frappe.db.has_column("Sales Order", "crm_optin_quotation") else None,
			"crm_token_purchase_key": key,
			"crm_token_facility_mfl": facility_mfl,
			"crm_token_package_item": package["item_code"],
		}
	)
	sales_order.append("items", {"item_code": package["item_code"], "qty": 1, "price_list_rate": price, "rate": price, "description": package["description"], "delivery_date": frappe.utils.add_days(frappe.utils.today(), validity)})
	sales_order.flags.ignore_mandatory = True
	sales_order.flags.ignore_permissions = True
	sales_order.set_missing_values()
	sales_order.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.commit()
	return {"success": True, "data": {"quotation": quotation.name, "sales_order": sales_order.name, "idempotent": False}}


@frappe.whitelist(methods=["POST"])
def start_token_payment(sales_order):
	"""Create and submit the invoice only when the user starts payment."""
	if not frappe.db.has_column("Sales Order", "crm_optin_submission"):
		frappe.throw(_("Token order fields are not installed."), frappe.ConfigurationError)
	name = _text(sales_order)
	order = frappe.get_doc("Sales Order", name) if name else None
	if not order or _text(order.crm_optin_submission) not in get_user_ois_numbers():
		frappe.throw(_("That order is not linked to your account."), frappe.PermissionError)
	if order.docstatus != 0:
		frappe.throw(_("Only an open Sales Order can start payment."), frappe.ValidationError)
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	invoice = make_sales_invoice(order.name, ignore_permissions=True)
	if frappe.db.has_column("Sales Invoice", "crm_optin_submission"):
		invoice.crm_optin_submission = order.crm_optin_submission
	if frappe.db.has_column("Sales Invoice", "crm_token_purchase_key"):
		invoice.crm_token_purchase_key = order.crm_token_purchase_key
		invoice.crm_token_facility_mfl = order.crm_token_facility_mfl
		invoice.crm_token_package_item = order.crm_token_package_item
	settings = frappe.get_single("CRM Opt-In Settings")
	invoice.due_date = frappe.utils.add_days(frappe.utils.today(), int(settings.get("token_invoice_due_days") or 30))
	invoice.flags.ignore_mandatory = True
	invoice.insert(ignore_permissions=True, ignore_mandatory=True)
	invoice.submit()
	frappe.db.commit()
	return {"success": True, "data": {"invoice": invoice.name, "ois": order.crm_optin_submission, "checkout_url": "/payment-checkout?ois=%s" % order.crm_optin_submission}}
