"""Add the Opt-In Network link that ties an assisted Deal to its OIS workflow."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Deal": [
				{
					"fieldname": "optin_network",
					"fieldtype": "Link",
					"label": "Opt-In Network",
					"options": "CRM Opt-In Network",
					"insert_after": "optin_submission",
					"no_copy": 1,
					"description": "Network for the Deal's assisted or self-service Opt-In process.",
				},
			]
		}
	)
