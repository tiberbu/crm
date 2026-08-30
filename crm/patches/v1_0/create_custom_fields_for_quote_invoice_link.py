import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	# Sales Invoice belongs to ERPNext. CRM-only sites do not install that
	# DocType, so there is nothing to extend there.
	if not frappe.db.exists("DocType", "Sales Invoice"):
		return

	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "crm_deal",
					"label": "CRM Deal",
					"fieldtype": "Link",
					"options": "CRM Deal",
					"insert_after": "customer",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "crm_quote",
					"label": "CRM Quote",
					"fieldtype": "Link",
					"options": "CRM Quote",
					"insert_after": "crm_deal",
					"read_only": 1,
					"no_copy": 1,
				},
			]
		},
		ignore_validate=True,
	)
