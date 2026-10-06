"""Add provenance fields for facility-scoped token purchases."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	fields = [
		{
			"fieldname": "crm_token_purchase_key",
			"fieldtype": "Data",
			"label": "Token Purchase Key",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "crm_token_facility_mfl",
			"fieldtype": "Data",
			"label": "Token Facility MFL",
			"read_only": 1,
		},
		{
			"fieldname": "crm_token_package_item",
			"fieldtype": "Link",
			"label": "Token Package Item",
			"options": "Item",
			"read_only": 1,
		},
	]
	create_custom_fields({"Quotation": fields, "Sales Order": fields, "Sales Invoice": fields})
