"""Add Customer/Deal links and idempotency fields for no-OIS facility enrollment."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Facility Membership": [
				{
					"fieldname": "customer",
					"fieldtype": "Link",
					"options": "Customer",
					"label": "Customer Account",
					"description": "ERPNext Customer that owns this self-enrolled facility membership. Blank on legacy memberships.",
					"insert_after": "network",
				}
			],
			"CRM Lead": [
				{
					"fieldname": "cx_onboarding_source",
					"fieldtype": "Data",
					"label": "Customer Experience Onboarding Source",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "status",
				},
				{
					"fieldname": "cx_onboarding_identity_ref",
					"fieldtype": "Data",
					"label": "Customer Experience Identity Reference",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "cx_onboarding_source",
				},
				{
					"fieldname": "cx_onboarding_network",
					"fieldtype": "Link",
					"options": "CRM Opt-In Network",
					"label": "Customer Experience Network",
					"read_only": 1,
					"insert_after": "cx_onboarding_identity_ref",
				},
				{
					"fieldname": "cx_onboarding_package_item",
					"fieldtype": "Link",
					"options": "Item",
					"label": "Selected Token Package",
					"read_only": 1,
					"insert_after": "cx_onboarding_network",
				},
			],
			"CRM Deal": [
				{
					"fieldname": "cx_customer",
					"fieldtype": "Link",
					"options": "Customer",
					"label": "Customer Account",
					"read_only": 1,
					"insert_after": "organization",
				},
				{
					"fieldname": "cx_onboarding_source",
					"fieldtype": "Data",
					"label": "Customer Experience Onboarding Source",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "erpnext_customer",
				},
				{
					"fieldname": "cx_onboarding_identity_ref",
					"fieldtype": "Data",
					"label": "Customer Experience Identity Reference",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "cx_onboarding_source",
				},
				{
					"fieldname": "cx_onboarding_package_item",
					"fieldtype": "Link",
					"options": "Item",
					"label": "Customer Experience Token Package",
					"read_only": 1,
					"insert_after": "cx_onboarding_identity_ref",
				},
			],
		}
	)
