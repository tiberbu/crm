"""Add the single global token catalogue to CRM Opt-In Settings."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "section_token_catalog",
					"fieldtype": "Section Break",
					"label": "Token catalogue",
					"insert_after": "sales_tax_template",
				},
				{
					"fieldname": "token_price_list",
					"fieldtype": "Link",
					"label": "Token selling Price List",
					"options": "Price List",
					"insert_after": "section_token_catalog",
				},
				{
					"fieldname": "token_sales_order_validity_days",
					"fieldtype": "Int",
					"label": "Sales Order validity (days)",
					"default": "30",
					"insert_after": "token_price_list",
				},
				{
					"fieldname": "token_invoice_due_days",
					"fieldtype": "Int",
					"label": "Invoice payment terms (days)",
					"default": "30",
					"insert_after": "token_sales_order_validity_days",
				},
				{
					"fieldname": "token_packages",
					"fieldtype": "Table",
					"label": "Facility-friendly token packages",
					"options": "CRM Token Package",
					"insert_after": "token_invoice_due_days",
				},
			],
		}
	)
