"""Store the onboarding token package and price snapshot on each Deal Facility."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Deal Facility": [
				{
					"fieldname": "cx_token_package_item",
					"fieldtype": "Link",
					"options": "Item",
					"label": "Customer Experience Token Package",
					"read_only": 1,
					"insert_after": "facility_level",
				},
				{
					"fieldname": "cx_token_package_quantity",
					"fieldtype": "Int",
					"label": "Customer Experience Token Quantity",
					"read_only": 1,
					"insert_after": "cx_token_package_item",
				},
				{
					"fieldname": "cx_token_package_price",
					"fieldtype": "Currency",
					"label": "Package Price Excl. VAT",
					"read_only": 1,
					"insert_after": "cx_token_package_quantity",
				},
				{
					"fieldname": "cx_token_package_vat",
					"fieldtype": "Currency",
					"label": "Package VAT",
					"read_only": 1,
					"insert_after": "cx_token_package_price",
				},
				{
					"fieldname": "cx_token_package_gross_total",
					"fieldtype": "Currency",
					"label": "Package Total Incl. VAT",
					"read_only": 1,
					"insert_after": "cx_token_package_vat",
				},
				{
					"fieldname": "cx_token_package_currency",
					"fieldtype": "Data",
					"label": "Package Currency",
					"read_only": 1,
					"insert_after": "cx_token_package_gross_total",
				},
			]
		}
	)
