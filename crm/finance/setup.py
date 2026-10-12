"""Finance-specific metadata that depends on ERPNext doctypes."""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def ensure_network_payout_mappings():
	"""Add Network rebate and Supplier mappings when their doctypes exist.

	The fields use permission level 1 so Accounts Managers can maintain payout
	configuration without gaining write access to the rest of Network setup.
	"""
	if not frappe.db.exists("DocType", "CRM Opt-In Network"):
		return False

	fields = []
	if frappe.db.exists("DocType", "CRM Rebate Structure"):
		fields.append(
			{
				"fieldname": "finance_rebate_structure",
				"fieldtype": "Link",
				"label": "Finance Rebate Structure",
				"options": "CRM Rebate Structure",
				"insert_after": "partner_id",
				"permlevel": 1,
				"in_list_view": 0,
				"description": "Rate source used to accrue rebates for this Opt-In Network.",
			}
		)
	if frappe.db.exists("DocType", "Supplier"):
		fields.append(
			{
				"fieldname": "finance_supplier",
				"fieldtype": "Link",
				"label": "Rebate Payee Supplier",
				"options": "Supplier",
				"insert_after": "finance_rebate_structure",
				"permlevel": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"description": "ERPNext Supplier used for approved Network rebate payables.",
			}
		)
	if not fields:
		return False
	if not any(field["fieldname"] == "finance_rebate_structure" for field in fields):
		fields[0].pop("insert_after", None)
	create_custom_fields({"CRM Opt-In Network": fields}, ignore_validate=True)

	# Grant Finance Managers access to this field alone. Keep the standard
	# Network edit permissions unchanged for every other field.
	if frappe.db.exists("Role", "Accounts Manager"):
		for permlevel, read, write in ((0, 1, 0), (1, 1, 1)):
			permission = frappe.db.get_value(
				"DocPerm",
				{
					"parent": "CRM Opt-In Network",
					"role": "Accounts Manager",
					"permlevel": permlevel,
				},
				"name",
			)
			if not permission:
				frappe.get_doc(
					{
					"doctype": "DocPerm",
					"parent": "CRM Opt-In Network",
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": "Accounts Manager",
					"permlevel": permlevel,
					"read": read,
					"write": write,
				}
				).insert(ignore_permissions=True)

	return all(frappe.db.has_column("CRM Opt-In Network", field["fieldname"]) for field in fields)
