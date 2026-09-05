"""Seed checkout configuration and the Tiberbu bank transfer destination.

The patch is safe on CRM-only sites: ERPNext accounting records are created only
when their native doctypes are installed.  Secrets are intentionally left blank;
an administrator supplies Paystack keys in CRM Finance Settings.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


BANK_NAME = "Gulf African Bank"
BANK_ACCOUNT_NUMBER = "0300163301"
BANK_BRANCH = "UpperHill"
LEGAL_ACCOUNT_NAME = "TIBERBU HEALTHNET LIMITED"


def _add_fields():
	available = {}
	if frappe.db.exists("DocType", "CRM Finance Settings"):
		available["CRM Finance Settings"] = [
			{
				"fieldname": "paystack_enabled",
				"fieldtype": "Check",
				"label": "Enable Paystack Checkout",
				"default": "0",
				"insert_after": "default_sales_manager",
			},
			{
				"fieldname": "paystack_public_key",
				"fieldtype": "Data",
				"label": "Paystack Public Key",
				"insert_after": "paystack_enabled",
			},
			{
				"fieldname": "paystack_secret_key",
				"fieldtype": "Password",
				"label": "Paystack Secret Key",
				"insert_after": "paystack_public_key",
			},
			{
				"fieldname": "bank_account",
				"fieldtype": "Link",
				"label": "Checkout Bank Account",
				"options": "Bank Account",
				"insert_after": "paystack_secret_key",
			},
			{
				"fieldname": "bank_name",
				"fieldtype": "Data",
				"label": "Checkout Bank",
				"read_only": 1,
				"insert_after": "bank_account",
			},
			{
				"fieldname": "bank_branch",
				"fieldtype": "Data",
				"label": "Checkout Bank Branch",
				"read_only": 1,
				"insert_after": "bank_name",
			},
			{
				"fieldname": "bank_account_number",
				"fieldtype": "Data",
				"label": "Checkout Bank Account Number",
				"read_only": 1,
				"insert_after": "bank_branch",
			},
		]
	if frappe.db.exists("DocType", "Payment Entry"):
		available["Payment Entry"] = [
			{
				"fieldname": "crm_checkout_provider",
				"fieldtype": "Select",
				"label": "Checkout Provider",
				"options": "\nPaystack\nBank Transfer",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "reference_no",
			},
			{
				"fieldname": "crm_checkout_reference",
				"fieldtype": "Data",
				"label": "Checkout Reference",
				"read_only": 1,
				"no_copy": 1,
				"unique": 0,
				"insert_after": "crm_checkout_provider",
			},
			{
				"fieldname": "crm_optin_submission",
				"fieldtype": "Link",
				"label": "Opt-In Submission",
				"options": "CRM Opt-In Submission",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "crm_checkout_reference",
			},
			{
				"fieldname": "crm_checkout_notes",
				"fieldtype": "Small Text",
				"label": "Checkout Notes",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "crm_optin_submission",
			},
		]
	if frappe.db.exists("DocType", "CRM Opt-In Submission"):
		available["CRM Opt-In Submission"] = [
			{
				"fieldname": "payment_link_email_queue",
				"fieldtype": "Link",
				"label": "Payment Link Email Queue",
				"options": "Email Queue",
				"read_only": 1,
				"no_copy": 1,
			},
			{
				"fieldname": "payment_link_email_queued_at",
				"fieldtype": "Datetime",
				"label": "Payment Link Email Queued At",
				"read_only": 1,
				"no_copy": 1,
			},
		]
	if available:
		create_custom_fields(available, ignore_validate=True)


def _company():
	if not frappe.db.exists("DocType", "Company"):
		return ""
	rows = frappe.get_list("Company", fields=["name"], limit_page_length=0, ignore_permissions=True)
	for row in rows:
		if "tiberbu" in row.name.casefold():
			return row.name
	return rows[0].name if rows else ""


def _ensure_bank():
	if not frappe.db.exists("DocType", "Bank"):
		return ""
	if not frappe.db.exists("Bank", BANK_NAME):
		frappe.get_doc({"doctype": "Bank", "bank_name": BANK_NAME}).insert(ignore_permissions=True)
	return BANK_NAME


def _ensure_account(company):
	if not company or not frappe.db.exists("DocType", "Account"):
		return ""
	rows = frappe.get_list(
		"Account",
		filters={"company": company, "is_group": 1, "root_type": "Asset"},
		fields=["name", "account_name"],
		order_by="name asc",
		limit_page_length=0,
		ignore_permissions=True,
	)
	parent = next((row.name for row in rows if "bank" in (row.account_name or row.name).casefold()), None)
	parent = parent or (rows[0].name if rows else "")
	if not parent:
		return ""
	account_name = "%s - KES" % BANK_NAME
	existing = frappe.get_list(
		"Account",
		filters={"company": company, "account_name": account_name},
		fields=["name"],
		limit_page_length=1,
		ignore_permissions=True,
	)
	if existing:
		return existing[0].name
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": account_name,
				"company": company,
				"parent_account": parent,
				"is_group": 0,
				"account_type": "Bank",
				"account_currency": "KES",
			}
		).insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), "CRM checkout bank account seed failed")
		return ""


def _ensure_bank_account(company, bank, account):
	if not bank or not frappe.db.exists("DocType", "Bank Account"):
		return ""
	existing = frappe.get_list(
		"Bank Account",
		filters={"bank_account_no": BANK_ACCOUNT_NUMBER, "company": company, "is_company_account": 1},
		fields=["name"],
		limit_page_length=1,
		ignore_permissions=True,
	)
	if existing:
		return existing[0].name
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": LEGAL_ACCOUNT_NAME,
				"bank": bank,
				"bank_account_no": BANK_ACCOUNT_NUMBER,
				"branch_code": BANK_BRANCH,
				"company": company,
				"is_company_account": 1,
				"is_default": 1,
				"account": account,
			}
		).insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), "CRM checkout bank account record seed failed")
		return ""


def _ensure_mode_of_payment(account, name):
	if not account or not frappe.db.exists("DocType", "Mode of Payment"):
		return
	if frappe.db.exists("Mode of Payment", name):
		doc = frappe.get_doc("Mode of Payment", name)
	else:
		doc = frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": name, "type": "Bank", "enabled": 1})
	doc.set("accounts", [row for row in (doc.get("accounts") or []) if row.company != _company()])
	doc.append("accounts", {"company": _company(), "default_account": account})
	doc.save(ignore_permissions=True)


def execute():
	_add_fields()
	company = _company()
	bank = _ensure_bank()
	account = _ensure_account(company)
	bank_account = _ensure_bank_account(company, bank, account)
	_ensure_mode_of_payment(account, "Bank Transfer")
	_ensure_mode_of_payment(account, "Paystack")
	if frappe.db.exists("DocType", "CRM Finance Settings"):
		settings = frappe.get_single("CRM Finance Settings")
		for field, value in {
			"bank_account": bank_account,
			"bank_name": BANK_NAME,
			"bank_branch": BANK_BRANCH,
			"bank_account_number": BANK_ACCOUNT_NUMBER,
		}.items():
			if settings.meta.has_field(field):
				settings.set(field, value)
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
