"""First-purchase bonus and Partner Coupon tokens replace the Free Trial package.

Adds the two CRM-controlled token quantities, zero-rated bonus lines on token orders and
invoices, and the membership flag for facilities onboarded with a Partner Coupon. The Free
Trial package is disabled and its token quantity becomes the first-purchase bonus.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

BONUS_ITEM = "CV-TOKEN-BONUS"
FREE_PACKAGE = "CV-TOKEN-FREE"


def execute():
	bonus_line_fields = [
		{
			"fieldname": "crm_bonus_type",
			"fieldtype": "Select",
			"label": "Complimentary Token Type",
			"options": "\nWelcome Bonus\nPartner Coupon",
			"read_only": 1,
			"insert_after": "item_name",
		},
		{
			"fieldname": "crm_bonus_tokens",
			"fieldtype": "Int",
			"label": "Complimentary Tokens",
			"read_only": 1,
			"insert_after": "crm_bonus_type",
		},
	]
	create_custom_fields(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "welcome_bonus_tokens",
					"fieldtype": "Int",
					"label": "First-purchase bonus tokens",
					"description": "Complimentary tokens added once per facility to its first paid token order.",
					"default": "400",
					"insert_after": "token_invoice_due_days",
				},
				{
					"fieldname": "partner_coupon_tokens",
					"fieldtype": "Int",
					"label": "Partner Coupon tokens",
					"description": "Complimentary tokens added once per facility onboarded with a Partner Coupon.",
					"default": "0",
					"insert_after": "welcome_bonus_tokens",
				},
			],
			"Sales Order Item": bonus_line_fields,
			"Sales Invoice Item": bonus_line_fields,
			"CRM Facility Membership": [
				{
					"fieldname": "partner_coupon",
					"fieldtype": "Check",
					"label": "Joined with Partner Coupon",
					"read_only": 1,
					"insert_after": "network",
				}
			],
		}
	)
	if "erpnext" in frappe.get_installed_apps():
		_ensure_bonus_item()
	_retire_free_package()


def _ensure_bonus_item():
	if frappe.db.exists("Item", BONUS_ITEM):
		return
	template = frappe.db.get_value(
		"Item", {"item_code": ["like", "CV-TOKEN-%"]}, ["item_group", "stock_uom"], as_dict=True
	) or frappe._dict()
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": BONUS_ITEM,
			"item_name": "Complimentary Care Tokens",
			"description": "Complimentary Care Tokens, at no charge.",
			"item_group": template.item_group
			or frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": template.stock_uom or "Nos",
			"is_stock_item": 0,
			"is_sales_item": 1,
			"include_item_in_manufacturing": 0,
		}
	).insert(ignore_permissions=True)


def _retire_free_package():
	settings = frappe.get_single("CRM Opt-In Settings")
	changed = False
	for row in settings.get("token_packages") or []:
		if row.item_code == FREE_PACKAGE and int(row.enabled or 0):
			if int(row.token_quantity or 0) > 0:
				settings.welcome_bonus_tokens = int(row.token_quantity)
			row.enabled = 0
			changed = True
	if changed:
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
