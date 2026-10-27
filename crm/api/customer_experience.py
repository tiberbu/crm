"""Authenticated Customer Experience token purchase orchestration.

Every mutation is scoped to an OIS User Permission.  Browser-supplied OIS,
facility, order, and package values are treated as selectors only and are
revalidated against the permission and the server-side onboarding snapshot.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr, flt, nowdate
from frappe.utils.synchronization import filelock

from crm.api.facility_onboarding import _calculator_config, _hfr_facilities_for_owner, _token_packages
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


def _open_purchase_key(base_key):
	"""The key for this purchase: the period's key, or the next one once that purchase is paid.

	Retrying an unpaid purchase still resumes its order and invoice, but a facility can buy
	the same package again in the same period after paying for the first one.
	"""
	key = base_key
	for attempt in range(2, 102):
		invoice = _existing_document("Sales Invoice", key)
		if not invoice:
			return key
		state = frappe.db.get_value("Sales Invoice", invoice, ["docstatus", "outstanding_amount"], as_dict=True)
		if state.docstatus != 1 or flt(state.outstanding_amount) > 0:
			return key
		key = hashlib.sha256(f"{base_key}|{attempt}".encode()).hexdigest()[:40]
	frappe.throw(_("This package was bought too many times this period. Contact support."), frappe.ValidationError)


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
		base_key = _purchase_key(submission, facility_mfl, package)
		with filelock("crm_cx_order_%s" % base_key, timeout=60), _system_user():
			key = _open_purchase_key(base_key)
			# Only the first purchase in a period can reuse the onboarding quotation.
			source_quote = _initial_onboarding_quote(submission, facility_mfl, package) if key == base_key else None
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
	base_key = hashlib.sha256(raw_key.encode()).hexdigest()[:40]
	with filelock("crm_cx_order_%s" % base_key, timeout=60), _system_user():
		return _create_or_resume_customer_order(cust_name, facility_mfl, package, _open_purchase_key(base_key))


def _create_or_resume_customer_order(customer, facility_mfl, package, key, submit_order=True, source_quote=None):
	"""Create or resume a customer's token order; Express onboarding leaves it as a draft for review.

	``source_quote`` is the onboarding Quotation, reused (and submitted) instead of raising a second one.
	"""
	order_name = _existing_document("Sales Order", key)
	quotation_name = _existing_document("Quotation", key)
	if not order_name and not quotation_name and source_quote:
		for fieldname, value in (
			("crm_token_purchase_key", key),
			("crm_token_facility_mfl", facility_mfl),
			("crm_token_package_item", package["item_code"]),
		):
			if frappe.db.has_column("Quotation", fieldname):
				frappe.db.set_value("Quotation", source_quote, fieldname, value, update_modified=False)
		quotation_name = source_quote
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
		if quotation.docstatus == 0:
			quotation.flags.ignore_permissions = True
			quotation.flags.ignore_mandatory = True
			quotation.submit()
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
		quotation.submit()
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
	_apply_order_tax_template(sales_order, quotation)
	sales_order.insert(ignore_mandatory=True, ignore_permissions=True)
	if submit_order:
		sales_order.submit()
	_record_link("Sales Order", sales_order.name)
	return {
		"success": True,
		"data": {"quotation": quotation.name, "sales_order": sales_order.name, "idempotent": False},
	}


def create_express_draft_order(customer, facility_mfl, package, source_quote=None):
	"""Raise the draft Sales Order for a facility's preselected Express package (no login needed).

	Runs inside the public onboarding submit. The client reviews it in the portal, adds the
	billing details, and confirms it; tokens are granted only once its invoice is paid.
	"""
	raw_key = "|".join((customer, facility_mfl, package["item_code"], _period_key(package)))
	base_key = hashlib.sha256(raw_key.encode()).hexdigest()[:40]
	with filelock("crm_cx_order_%s" % base_key, timeout=60), _system_user():
		return _create_or_resume_customer_order(
			customer,
			facility_mfl,
			package,
			_open_purchase_key(base_key),
			submit_order=False,
			source_quote=source_quote,
		)


KRA_PIN_PATTERN = re.compile(r"^[A-Z]\d{9}[A-Z]$")
ORDER_FREQUENCIES = ("One-time", "Recurring")
RECURRENCE_PERIODS = ("Monthly", "Quarterly", "Yearly")


def _portal_draft_order(sales_order):
	"""The portal user's own draft token order, or a permission error."""
	require_portal_user()
	name = _text(sales_order)
	order = frappe.db.get_value("Sales Order", name, ["name", "customer", "docstatus"], as_dict=True) if name else None
	if not order or _text(order.customer) not in get_user_customer_names():
		frappe.throw(_("That order is not linked to your account."), frappe.PermissionError)
	return order


def _billing_addresses(customer):
	"""Saved addresses linked to the customer, billing ones first."""
	names = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"},
		pluck="parent",
		ignore_permissions=True,
	)
	if not names:
		return []
	rows = frappe.get_all(
		"Address",
		filters={"name": ["in", names], "disabled": 0},
		fields=["name", "address_title", "address_type", "address_line1", "address_line2", "city", "state", "pincode", "country", "email_id", "phone", "is_primary_address"],
		order_by="is_primary_address desc, modified desc",
		ignore_permissions=True,
	)
	rows.sort(key=lambda row: row.address_type != "Billing")
	return rows


@frappe.whitelist(methods=["GET", "POST"])
def get_draft_order(sales_order: Any):
	"""What the client reviews before confirming a token order: lines, totals and billing details."""
	order = _portal_draft_order(sales_order)
	doc = frappe.get_doc("Sales Order", order.name)
	return {
		"success": True,
		"data": {
			"name": doc.name,
			"is_draft": doc.docstatus == 0,
			"status": doc.status,
			"customer": doc.customer,
			"customer_name": doc.customer_name,
			"transaction_date": str(doc.transaction_date or ""),
			"currency": doc.currency,
			"net_total": flt(doc.net_total),
			"total_taxes_and_charges": flt(doc.total_taxes_and_charges),
			"grand_total": flt(doc.grand_total),
			"items": [
				{"item_code": row.item_code, "item_name": row.item_name, "description": row.description, "qty": flt(row.qty), "rate": flt(row.rate), "amount": flt(row.amount)}
				for row in doc.items
			],
			"taxes": [{"description": row.description, "rate": flt(row.rate), "tax_amount": flt(row.tax_amount)} for row in doc.taxes or []],
			"facility_mfl": _text(doc.get("crm_token_facility_mfl")),
			"package_item": _text(doc.get("crm_token_package_item")),
			"billing_address": _text(doc.customer_address),
			"addresses": _billing_addresses(doc.customer),
			"kra_pin": _text(frappe.db.get_value("Customer", doc.customer, "tax_id")),
			"frequency": _text(doc.get("crm_order_frequency")) or "One-time",
			"recurrence_period": _text(doc.get("crm_recurrence_period")),
		},
	}


def _clean_kra_pin(value):
	pin = re.sub(r"\s+", "", _text(value)).upper()
	if not KRA_PIN_PATTERN.match(pin):
		frappe.throw(
			_("Enter a valid KRA PIN: a letter, nine digits and a letter (for example A123456789Z)."),
			frappe.ValidationError,
		)
	return pin


def _billing_address_for(customer, billing_address, new_address):
	"""The chosen saved address, or a new Billing address linked to the customer."""
	billing_address = _text(billing_address)
	if billing_address:
		if billing_address not in {row.name for row in _billing_addresses(customer)}:
			frappe.throw(_("That billing address is not linked to your account."), frappe.PermissionError)
		return billing_address
	if isinstance(new_address, str):
		try:
			new_address = json.loads(new_address or "{}")
		except ValueError:
			new_address = {}
	new_address = new_address if isinstance(new_address, dict) else {}
	line1 = _text(new_address.get("address_line1"))
	city = _text(new_address.get("city"))
	if not line1 or not city:
		frappe.throw(_("Choose a saved billing address, or enter the street address and town."), frappe.ValidationError)
	address = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": _text(new_address.get("address_title")) or frappe.db.get_value("Customer", customer, "customer_name") or customer,
			"address_type": "Billing",
			"address_line1": line1,
			"address_line2": _text(new_address.get("address_line2")),
			"city": city,
			"state": _text(new_address.get("county")),
			"pincode": _text(new_address.get("postal_code")),
			"country": _text(new_address.get("country")) or "Kenya",
			"email_id": _text(new_address.get("email_id")),
			"phone": _text(new_address.get("phone")),
			"is_primary_address": 0 if _billing_addresses(customer) else 1,
			"links": [{"link_doctype": "Customer", "link_name": customer}],
		}
	)
	address.insert(ignore_permissions=True)  # SYSTEM-INTERNAL: linked to the user's own Customer
	_record_link("Address", address.name)
	return address.name


@frappe.whitelist(methods=["POST"])
def confirm_draft_order(
	sales_order: Any,
	kra_pin: Any = None,
	frequency: Any = "One-time",
	recurrence_period: Any = None,
	billing_address: Any = None,
	new_address: Any = None,
):
	"""Confirm a reviewed draft token order: save billing details, submit it and raise its invoice."""
	order = _portal_draft_order(sales_order)
	frequency = _text(frequency) or "One-time"
	recurrence_period = _text(recurrence_period)
	if frequency not in ORDER_FREQUENCIES:
		frappe.throw(_("Choose whether the order is one-time or recurring."), frappe.ValidationError)
	if frequency == "Recurring" and recurrence_period not in RECURRENCE_PERIODS:
		frappe.throw(_("Choose how often a recurring order repeats."), frappe.ValidationError)
	pin = _clean_kra_pin(kra_pin)
	with (
		filelock("crm_cx_invoice_%s" % hashlib.sha256(order.name.encode()).hexdigest()[:32], timeout=60),
		_system_user(),
	):
		doc = frappe.get_doc("Sales Order", order.name)
		if doc.docstatus == 0:
			_confirm_order(doc, pin, frequency, recurrence_period, billing_address, new_address)
		elif doc.docstatus != 1:
			frappe.throw(_("This order was cancelled."), frappe.ValidationError)
		fields = ["name", "crm_token_purchase_key", "docstatus", "status", "customer"]
		if frappe.db.has_column("Sales Order", "crm_optin_submission"):
			fields.append("crm_optin_submission")
		payment = _start_or_resume_payment(frappe.db.get_value("Sales Order", doc.name, fields, as_dict=True))
		payment["data"]["sales_order"] = doc.name
		payment["data"]["auto_repeat"] = _text(frappe.db.get_value("Sales Order", doc.name, "auto_repeat"))
		return payment


def _confirm_order(doc, pin, frequency, recurrence_period, billing_address, new_address):
	from frappe.contacts.doctype.address.address import get_address_display

	if _text(frappe.db.get_value("Customer", doc.customer, "tax_id")) != pin:
		frappe.db.set_value("Customer", doc.customer, "tax_id", pin)
	address = _billing_address_for(doc.customer, billing_address, new_address)
	doc.customer_address = address
	doc.address_display = get_address_display(address)
	doc.tax_id = pin
	doc.crm_order_frequency = frequency
	doc.crm_recurrence_period = recurrence_period if frequency == "Recurring" else ""
	if not _text(doc.get("crm_token_purchase_key")):
		# Auto-repeated orders copy no key (no_copy); invoice idempotency needs one.
		doc.crm_token_purchase_key = hashlib.sha256(("order|" + doc.name).encode()).hexdigest()[:40]
	today = frappe.utils.today()
	if frappe.utils.getdate(doc.transaction_date) < frappe.utils.getdate(today):
		validity = int(frappe.get_single("CRM Opt-In Settings").get("token_sales_order_validity_days") or 30)
		doc.transaction_date = today
		doc.delivery_date = frappe.utils.add_days(today, validity)
		for row in doc.items:
			row.delivery_date = doc.delivery_date
		doc.set("payment_schedule", [])
	doc.flags.ignore_permissions = True  # SYSTEM-INTERNAL: the portal user owns this order
	doc.save()
	doc.submit()
	_record_link("Sales Order", doc.name)
	if frequency == "Recurring":
		_schedule_recurring_order(doc, recurrence_period)


def _schedule_recurring_order(doc, period):
	"""Repeat the order each period as a new draft the client reviews again (never auto-submitted)."""
	months = {"Monthly": 1, "Quarterly": 3, "Yearly": 12}[period]
	auto_repeat = frappe.get_doc(
		{
			"doctype": "Auto Repeat",
			"reference_doctype": "Sales Order",
			"reference_document": doc.name,
			"frequency": period,
			"start_date": frappe.utils.add_months(doc.transaction_date, months),
			"submit_on_creation": 0,
		}
	)
	auto_repeat.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	_record_link("Auto Repeat", auto_repeat.name)
	return auto_repeat.name


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


@frappe.whitelist(methods=["POST"])
def lookup_hfr_facility(query: Any, search_by: str = "mfl_code"):
	"""Search official Health Facility Registry for facility candidates."""
	from crm.api.hfr import search_facility

	query = _text(query)
	if not query:
		return {"success": True, "data": []}
	try:
		results = search_facility(query, search_by=search_by)
		return {"success": True, "data": results}
	except Exception as exc:
		frappe.log_error(f"HFR lookup failed for {query}: {exc}")
		return {"success": False, "error": str(exc), "data": []}


@frappe.whitelist(methods=["POST"])
def add_facility_from_hfr(
	mfl_code: Any,
	fid: Any = None,
	package_item_code: Any = None,
	partner_id: Any = None,
):
	"""Link a verified Health Facility Registry facility to the authenticated user's customer account."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please sign in to link facilities."), frappe.PermissionError)

	from crm.api.website_redirect import get_user_customer_names

	customer_names = get_user_customer_names(user)
	if not customer_names:
		frappe.throw(_("No customer account found for your profile."), frappe.ValidationError)
	customer = customer_names[0]
	from crm.api.facility_onboarding import _public_network

	partner = _public_network(_text(partner_id))
	if not partner:
		frappe.throw(
			_("Enter a valid six-digit Partner ID, or leave it blank to use the configured default."),
			frappe.ValidationError,
		)

	mfl_code = _text(mfl_code)
	fid = _text(fid)
	if not mfl_code and not fid:
		frappe.throw(_("MFL code or HFR Facility ID is required."), frappe.ValidationError)

	from crm.api.hfr import get_facility_detail, search_facility

	facility_data = {}
	if fid:
		facility_data = get_facility_detail(fid) or {}

	if not facility_data and mfl_code:
		candidates = search_facility(mfl_code, search_by="mfl_code")
		if candidates:
			candidate_fid = candidates[0].get("facility_fid")
			if candidate_fid:
				facility_data = get_facility_detail(candidate_fid) or {}
	if not facility_data:
		frappe.throw(
			_("Full Health Facility Registry details could not be loaded. The facility was not linked; try again when the registry is available."),
			frappe.ValidationError,
		)
	resolved_fid = _text(facility_data.get("hfr_facility_id")).strip()
	if not re.fullmatch(r"FID-\d{2}-[\w-]+", resolved_fid, flags=re.IGNORECASE):
		frappe.throw(
			_("The Health Facility Registry record has no valid Facility ID (FID) for deployment lookup, so it was not linked."),
			frappe.ValidationError,
		)
	if fid and resolved_fid.casefold() != fid.casefold():
		frappe.throw(
			_("The Health Facility Registry returned a different Facility ID than the one requested. The facility was not linked."),
			frappe.ValidationError,
		)

	facility_name = facility_data.get("organization_name") or mfl_code
	keph_level = facility_data.get("facility_level") or "Level 2"
	resolved_mfl = facility_data.get("mfl_code") or mfl_code
	if not resolved_mfl:
		frappe.throw(
			_("This registry record has no MFL code, so it cannot be added to the facility portfolio yet."),
			frappe.ValidationError,
		)

	with _system_user():
		row = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": resolved_mfl}, "name")
		if row:
			fac_doc = frappe.get_doc("CRM Pre-Qualified Facility", row)
			if facility_name:
				fac_doc.facility_name = facility_name
			if keph_level:
				fac_doc.keph_level = keph_level
		else:
			fac_doc = frappe.get_doc(
				{
					"doctype": "CRM Pre-Qualified Facility",
					"mfl_code": resolved_mfl,
					"facility_name": facility_name,
					"organization": facility_name,
					"keph_level": keph_level,
				}
			)
		fac_doc.hfr_facility_id = resolved_fid
		for fieldname in (
			"facility_type",
			"facility_category",
			"facility_owner",
			"facility_owner_type",
			"regulatory_body",
			"board_registration_number",
			"kra_pin",
			"operational_status",
			"hfr_county",
			"hfr_sub_county",
			"hfr_constituency",
			"hfr_ward",
			"latitude",
			"longitude",
			"license_number",
			"license_type",
			"license_expiry",
			"facility_standing",
			"number_of_beds",
			"number_of_cots",
			"open_whole_day",
			"open_weekends",
			"open_public_holidays",
			"open_late_night",
		):
			value = facility_data.get(fieldname)
			if value not in (None, ""):
				fac_doc.set(fieldname, value)
		if facility_data.get("registration_number"):
			fac_doc.registration_number = facility_data["registration_number"]
		fac_doc.hfr_sync_status = "HFR Verified"
		fac_doc.hfr_last_synced = frappe.utils.now_datetime()

		fac_doc.flags.skip_invitation = True
		if hasattr(fac_doc, "is_self_onboarded"):
			fac_doc.is_self_onboarded = 1

		membership_exists = False
		for m in fac_doc.memberships or []:
			if m.customer == customer:
				membership_exists = True
				break

		if not membership_exists:
			user_doc = frappe.db.get_value("User", user, ["full_name", "mobile_no"], as_dict=True) or {}
			fac_doc.append(
				"memberships",
				{
					"network": partner.get("name"),
					"customer": customer,
					"status": "Active",
					"go_live": 1,
					"contact_name": user_doc.get("full_name") or user,
					"contact_email": user,
					"contact_phone": user_doc.get("mobile_no") or "Not provided",
				},
			)

		fac_doc.save(ignore_permissions=True)

		deals = frappe.get_all("CRM Deal", filters={"cx_customer": customer}, fields=["name"], limit=1)
		if deals:
			deal_doc = frappe.get_doc("CRM Deal", deals[0].name)
			deal_fac_row = next(
				(
					df
					for df in deal_doc.facilities or []
					if frappe.utils.cstr(df.mfl_code).strip() == resolved_mfl
				),
				None,
			)
			deal_fac = {
				"facility_name": facility_name,
				"mfl_code": resolved_mfl,
				"facility_level": keph_level,
				"hfr_facility_id": facility_data.get("hfr_facility_id") or "",
				"hfr_sync_status": "HFR Verified",
			}
			for fieldname in (
				"facility_type",
				"facility_category",
				"facility_owner",
				"facility_owner_type",
				"regulatory_body",
				"board_registration_number",
				"kra_pin",
				"operational_status",
				"hfr_county",
				"hfr_sub_county",
				"hfr_constituency",
				"hfr_ward",
				"latitude",
				"longitude",
				"license_number",
				"license_type",
				"license_expiry",
				"facility_standing",
				"number_of_beds",
				"number_of_cots",
				"open_whole_day",
				"open_weekends",
				"open_public_holidays",
				"open_late_night",
				"registration_number",
			):
				value = facility_data.get(fieldname)
				if value not in (None, ""):
					deal_fac[fieldname] = value
			if deal_fac_row:
				for fieldname, value in deal_fac.items():
					deal_fac_row.set(fieldname, value)
			else:
				if package_item_code:
					pkg = _package(package_item_code)
					if pkg:
						deal_fac["cx_token_package_item"] = pkg["item_code"]
						deal_fac["cx_token_package_quantity"] = pkg.get("token_quantity") or 0
						deal_fac["cx_token_package_price"] = pkg.get("price") or 0
						deal_fac["cx_token_package_vat"] = pkg.get("vat_amount") or 0
						deal_fac["cx_token_package_gross_total"] = pkg.get("gross_total") or 0
						deal_fac["cx_token_package_currency"] = pkg.get("currency") or "KES"
				deal_doc.append("facilities", deal_fac)
			deal_doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"success": True,
			"data": {
				"mfl_code": resolved_mfl,
				"facility_name": facility_name,
				"keph_level": keph_level,
				"customer": customer,
			},
		}


def _mask_national_id(national_id: str) -> str:
	raw = _text(national_id).strip()
	if not raw:
		return ""
	if len(raw) <= 4:
		return "•" * len(raw)
	prefix = raw[:2]
	suffix = raw[-2:]
	bullets = "•" * (len(raw) - 4)
	return f"{prefix}{bullets}{suffix}"


@frappe.whitelist(methods=["GET", "POST"])
def get_user_profile():
	"""Return the authenticated user's profile, masked National ID, organization, and linked facilities."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to view your profile."), frappe.PermissionError)

	user_doc = frappe.get_doc("User", user)
	national_id = _text(user_doc.get("national_id") or "").strip()
	identification_type = _text(user_doc.get("identification_type") or "National ID").strip()
	national_id_verified = bool(
		user_doc.get("national_id_verified")
		if frappe.db.has_column("User", "national_id_verified")
		else False
	)
	hfr_owner_licence = _text(user_doc.get("hfr_owner_licence") or "").strip()
	hfr_registration_number = _text(user_doc.get("hfr_registration_number") or "").strip()

	from crm.api.website_redirect import get_user_customer_names
	customer_names = get_user_customer_names(user)
	customer = customer_names[0] if customer_names else None

	# If National ID or KYC details are not on the User doc, check linked Deal/Lead
	if not national_id:
		deal_filters = {}
		if customer:
			deal_filters["cx_customer"] = customer
		else:
			from crm.api.website_redirect import get_user_deal_names
			deal_names = get_user_deal_names(user)
			if deal_names:
				deal_filters["name"] = ["in", deal_names]
		if deal_filters and frappe.db.has_column("CRM Deal", "cx_onboarding_identity_ref"):
			identity_ref = frappe.db.get_value(
				"CRM Deal",
				deal_filters,
				"cx_onboarding_identity_ref",
			)
			if identity_ref and ":" in identity_ref:
				raw_parts = identity_ref.split(":", 1)
				raw_type = raw_parts[0]
				raw_num = raw_parts[1]
				national_id = raw_num.strip()
				identification_type = raw_type.replace("_", " ").title() or "National ID"
				national_id_verified = True
				if frappe.db.has_column("User", "national_id"):
					user_doc.db_set("national_id", national_id, update_modified=False)
				if frappe.db.has_column("User", "national_id_verified"):
					user_doc.db_set("national_id_verified", 1, update_modified=False)
				if frappe.db.has_column("User", "identification_type"):
					user_doc.db_set("identification_type", identification_type, update_modified=False)

	org_name = ""
	network_name = "CareVerse Partner Network"
	facility_count = 0

	if customer:
		customer_doc = frappe.db.get_value("Customer", customer, ["customer_name", "customer_type", "mobile_no"], as_dict=True) or {}
		org_name = customer_doc.get("customer_name") or customer

		deals = frappe.get_all("CRM Deal", filters={"cx_customer": customer}, fields=["name", "organization", "optin_network"], limit=5)
		if deals:
			if deals[0].get("optin_network"):
				network_name = deals[0].get("optin_network")
			if not org_name:
				org_name = deals[0].get("organization") or customer

		if frappe.db.has_column("CRM Facility Membership", "customer"):
			facility_count = frappe.db.count("CRM Facility Membership", {"customer": customer})
		if facility_count == 0 and deals:
			facility_count = frappe.db.count("CRM Deal Facility", {"parent": ["in", [d["name"] for d in deals]]})
	else:
		from crm.api.website_redirect import get_user_deal_names, get_user_lead_names
		deal_names = get_user_deal_names(user)
		if deal_names:
			deal_doc = frappe.db.get_value("CRM Deal", deal_names[0], ["organization", "optin_network"], as_dict=True) or {}
			org_name = deal_doc.get("organization") or ""
			if deal_doc.get("optin_network"):
				network_name = deal_doc.get("optin_network")
			facility_count = frappe.db.count("CRM Deal Facility", {"parent": ["in", deal_names]})
		else:
			lead_names = get_user_lead_names(user)
			if lead_names:
				lead_doc = frappe.db.get_value("CRM Lead", lead_names[0], ["organization", "optin_network"], as_dict=True) or {}
				org_name = lead_doc.get("organization") or ""
				if lead_doc.get("optin_network"):
					network_name = lead_doc.get("optin_network")
				facility_count = frappe.db.count("CRM Lead Facility", {"parent": ["in", lead_names]})

	full_name = user_doc.full_name or f"{user_doc.first_name} {user_doc.last_name or ''}".strip()
	mobile_no = user_doc.mobile_no or user_doc.phone or ""
	if not mobile_no and customer:
		cust_phone = frappe.db.get_value("Customer", customer, "mobile_no")
		if cust_phone:
			mobile_no = cust_phone
			user_doc.db_set("mobile_no", mobile_no, update_modified=False)

	return {
		"success": True,
		"data": {
			"user_id": user_doc.name,
			"full_name": full_name or user_doc.email,
			"email": user_doc.email,
			"mobile_no": mobile_no,
			"national_id": national_id,
			"masked_national_id": _mask_national_id(national_id) if national_id else "",
			"national_id_verified": national_id_verified,
			"identification_type": identification_type or "National ID",
			"hfr_owner_licence": hfr_owner_licence,
			"hfr_registration_number": hfr_registration_number,
			"organization": org_name or full_name or "Healthcare Practice",
			"customer_name": org_name or full_name,
			"customer_id": customer or "",
			"primary_network": network_name,
			"facility_count": facility_count,
		},
	}


@frappe.whitelist(methods=["POST"])
def update_user_profile(
	national_id: Any = None,
	mobile_no: Any = None,
	full_name: Any = None,
	organization: Any = None,
	identification_type: Any = None,
):
	"""Update user contact, KYC, and linked Customer name on file."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to update your profile."), frappe.PermissionError)

	user_doc = frappe.get_doc("User", user)
	updates = {}

	if national_id is not None:
		raw_id = _text(national_id).strip()
		cleaned_id = re.sub(r"[^\d]", "", raw_id)
		if raw_id and (not cleaned_id or len(cleaned_id) < 6 or len(cleaned_id) > 10):
			frappe.throw(_("Kenyan National ID must be between 6 and 10 digits."), frappe.ValidationError)
		if not frappe.db.has_column("User", "national_id"):
			from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
			create_custom_fields({
				"User": [{
					"fieldname": "national_id",
					"label": "National ID",
					"fieldtype": "Data",
					"insert_after": "phone",
				}]
			})
		updates["national_id"] = cleaned_id
		if frappe.db.has_column("User", "national_id_verified"):
			updates["national_id_verified"] = 1 if cleaned_id else 0

	if identification_type is not None and frappe.db.has_column("User", "identification_type"):
		updates["identification_type"] = _text(identification_type).strip() or "National ID"

	if mobile_no is not None:
		cleaned_phone = _text(mobile_no).strip()
		updates["mobile_no"] = cleaned_phone
		updates["phone"] = cleaned_phone

	raw_name = ""
	if full_name is not None and _text(full_name).strip():
		raw_name = _text(full_name).strip()
		parts = raw_name.split(None, 1)
		updates["first_name"] = parts[0]
		updates["last_name"] = parts[1] if len(parts) > 1 else ""
		updates["full_name"] = raw_name

	if updates:
		user_doc.db_set(updates)

	# Update linked Customer records
	from crm.api.website_redirect import get_user_customer_names
	customer_names = get_user_customer_names(user)
	new_org_name = _text(organization).strip() if organization is not None else ""
	target_customer_name = new_org_name or raw_name

	for cust_name in customer_names:
		if frappe.db.exists("Customer", cust_name):
			cust_doc = frappe.get_doc("Customer", cust_name)
			cust_modified = False
			if target_customer_name and target_customer_name != cust_doc.customer_name:
				cust_doc.customer_name = target_customer_name
				cust_modified = True
			if mobile_no is not None and _text(mobile_no).strip() != (cust_doc.mobile_no or ""):
				cust_doc.mobile_no = _text(mobile_no).strip()
				cust_modified = True
			if cust_modified:
				cust_doc.save(ignore_permissions=True)

	if not getattr(frappe.flags, "in_test", False):
		frappe.db.commit()

	return get_user_profile()


@frappe.whitelist(methods=["POST"])
def lookup_facilities_by_owner_id(national_id: Any = None):
	"""Search official Health Facility Registry (HFR) using the owner's National ID on file."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to discover facilities."), frappe.PermissionError)

	user_doc = frappe.get_doc("User", user)
	id_number = _text(national_id).strip() or _text(user_doc.get("national_id") or "").strip()

	if not id_number:
		frappe.throw(
			_("No National ID on file. Please enter and save your National ID in My Profile before discovering facilities."),
			frappe.ValidationError,
		)

	try:
		raw_facilities = _hfr_facilities_for_owner(id_number)
	except Exception as exc:
		frappe.log_error(f"HFR lookup by owner ID failed: {exc}")
		return {
			"success": False,
			"error": _("Unable to query Health Facility Registry at this time. Please try again or search by MFL code."),
			"data": [],
			"national_id": id_number,
			"masked_national_id": _mask_national_id(id_number),
		}

	from crm.api.website_redirect import get_user_customer_names, get_user_ois_numbers
	customer_names = get_user_customer_names(user)
	existing_mfls = set()
	if customer_names:
		memberships = frappe.get_all("CRM Facility Membership", filters={"customer": ["in", customer_names]}, fields=["parent"])
		parent_facilities = [m.parent for m in memberships if m.parent]
		if parent_facilities:
			fac_rows = frappe.get_all("CRM Pre-Qualified Facility", filters={"name": ["in", parent_facilities]}, fields=["mfl_code"])
			for fr in fac_rows:
				if fr.mfl_code:
					existing_mfls.add(cstr(fr.mfl_code).strip().casefold())

	ois_numbers = get_user_ois_numbers(user)
	if ois_numbers:
		for ois_name in ois_numbers:
			raw_json = frappe.db.get_value("CRM Opt-In Submission", ois_name, "raw_json")
			if raw_json:
				try:
					payload = json.loads(raw_json)
					fac_list = payload.get("facilities") or payload.get("pricing") or []
					for f in fac_list:
						if isinstance(f, dict) and f.get("mfl_code"):
							existing_mfls.add(cstr(f.get("mfl_code")).strip().casefold())
				except Exception:
					pass

	results = []
	for fac in raw_facilities:
		fid = _text(fac.get("facility_fid") or fac.get("facility_id") or fac.get("fid") or "")
		mfl = _text(fac.get("mfl_code") or fac.get("facility_code") or fac.get("code") or fid)
		name = _text(fac.get("facility_name") or fac.get("name") or "Healthcare Facility")
		level = _text(fac.get("facility_level") or fac.get("keph_level") or fac.get("level") or "Level 2 Dispensary")
		county = _text(fac.get("county") or "")
		subcounty = _text(fac.get("subcounty") or fac.get("sub_county") or "")
		owner_type = _text(fac.get("facility_owner_type") or fac.get("owner_type") or fac.get("ownership") or "Private Practice")

		is_linked = (mfl and mfl.casefold() in existing_mfls) or (fid and fid.casefold() in existing_mfls)

		results.append({
			"mfl_code": mfl,
			"fid": fid,
			"name": name,
			"level": level,
			"county": county,
			"subcounty": subcounty,
			"owner_type": owner_type,
			"already_linked": is_linked,
		})

	return {
		"success": True,
		"data": results,
		"national_id": id_number,
		"masked_national_id": _mask_national_id(id_number),
	}


@frappe.whitelist(methods=["POST"])
def report_mpesa_payment(invoice_name: Any, mpesa_code: Any, amount: Any = None, phone: Any = None):
	"""Record a customer M-Pesa transaction reference for finance reconciliation against an invoice."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to report payment."), frappe.PermissionError)

	invoice_name = _text(invoice_name).strip()
	mpesa_code = _text(mpesa_code).strip().upper()

	if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
		frappe.throw(_("Invoice not found or invalid."), frappe.ValidationError)

	if not mpesa_code or len(mpesa_code) < 6:
		frappe.throw(_("Please enter a valid M-Pesa transaction confirmation code (e.g. SB65A1TU7X)."), frappe.ValidationError)

	from crm.api.website_redirect import get_user_customer_names
	customer_names = get_user_customer_names(user)

	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice.customer not in customer_names:
		frappe.throw(_("You are not permitted to manage this invoice."), frappe.PermissionError)

	existing_pe = frappe.get_all(
		"Payment Entry",
		filters={"reference_no": mpesa_code, "docstatus": ["!=", 2]},
		fields=["name", "docstatus"],
		limit=1,
	)
	if existing_pe:
		return {
			"success": True,
			"status": "already_submitted",
			"payment_entry": existing_pe[0].name,
			"message": _("This M-Pesa reference is already recorded and is awaiting reconciliation."),
		}

	from crm.api.checkout import _pending_mpesa_report_for_invoice
	pending_payment = _pending_mpesa_report_for_invoice(invoice.name)
	if pending_payment:
		return {
			"success": True,
			"status": "payment_already_pending",
			"payment_entry": pending_payment,
			"message": _("A payment report for this invoice is already being verified. Please wait for confirmation before paying again."),
		}

	from crm.api.checkout import _payment_entry_for_invoice
	pay_amount = flt(amount or invoice.outstanding_amount)

	current_user = frappe.session.user
	try:
		frappe.set_user("Administrator")
		pe = _payment_entry_for_invoice(
			invoice.name,
			pay_amount,
			mode_of_payment="Bank Transfer",
			reference_no=mpesa_code,
			reference_date=nowdate(),
		)
		pe.remarks = f"M-Pesa Paybill payment {mpesa_code} reported by {current_user} for {invoice.name}. Phone: {_text(phone)}"
		pe.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.commit()
		pe_name = pe.name
	finally:
		frappe.set_user(current_user)

	return {
		"success": True,
		"status": "submitted_for_reconciliation",
		"payment_entry": pe_name,
		"mpesa_code": mpesa_code,
		"message": _("M-Pesa payment {0} received. Your invoice will update as soon as reconciliation completes.").format(mpesa_code),
	}

