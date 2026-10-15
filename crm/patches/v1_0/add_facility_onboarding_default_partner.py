"""Add the optional fallback Network Partner ID for public onboarding."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "facility_onboarding_default_partner_id",
					"fieldtype": "Data",
					"label": "Default Network ID",
					"description": "Default six-digit Network ID used when the facility owner leaves the referring partner's Network ID blank during self-onboarding.",
					"insert_after": "facility_onboarding_hie_url",
				}
			]
		}
	)
