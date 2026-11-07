"""Add the coupon link to the token bonus lines and deprecate the global coupon setting.

Declares the full existing bonus-line field set (so ``create_custom_fields`` updates the
``crm_bonus_type`` options) plus a new read-only ``crm_coupon`` Link that travels from the order
line to the invoice line. The global ``partner_coupon_tokens`` is relabelled as a deprecated
fallback.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Order Item": _bonus_line_fields(),
			"Sales Invoice Item": _bonus_line_fields(),
			"CRM Opt-In Settings": [
				{
					"fieldname": "partner_coupon_tokens",
					"fieldtype": "Int",
					"label": "Partner Coupon fallback tokens (deprecated)",
					"description": "Used only for a network that has never had a coupon. Set per-network values in Settings > Coupons.",
					"insert_after": "welcome_bonus_tokens",
				}
			],
		}
	)


def _bonus_line_fields():
	return [
		{
			"fieldname": "crm_bonus_type",
			"fieldtype": "Select",
			"label": "Complimentary Token Type",
			"options": "\nWelcome Bonus\nPartner Coupon\nCRM Coupon",
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
		{
			"fieldname": "crm_coupon",
			"fieldtype": "Link",
			"label": "Coupon",
			"options": "CRM Coupon",
			"read_only": 1,
			"insert_after": "crm_bonus_tokens",
		},
	]
