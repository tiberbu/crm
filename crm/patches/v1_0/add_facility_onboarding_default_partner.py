"""Add the optional fallback Network Partner ID for public onboarding."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "facility_onboarding_default_partner_id",
					"fieldtype": "Data",
					"label": "Default Partner ID",
					"description": "Six-digit Network Partner ID used when an onboarding link does not provide one.",
					"insert_after": "facility_onboarding_hie_url",
				}
			]
		}
	)
