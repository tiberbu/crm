"""Add CRM-owned credentials and paths for public facility onboarding."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	if not frappe.db.exists("DocType", "CRM Opt-In Settings"):
		return

	create_custom_fields(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "section_facility_onboarding_registry",
					"fieldtype": "Section Break",
					"label": "Facility onboarding registry",
					"insert_after": "token_packages",
				},
				{
					"fieldname": "facility_onboarding_hie_url",
					"fieldtype": "Data",
					"label": "Registry base URL",
					"insert_after": "section_facility_onboarding_registry",
				},
				{
					"fieldname": "facility_onboarding_hie_username",
					"fieldtype": "Data",
					"label": "Registry username",
					"insert_after": "facility_onboarding_hie_url",
				},
				{
					"fieldname": "facility_onboarding_hie_password",
					"fieldtype": "Password",
					"label": "Registry password",
					"insert_after": "facility_onboarding_hie_username",
				},
				{
					"fieldname": "facility_onboarding_hfr_owner_path",
					"fieldtype": "Data",
					"label": "HFR owner lookup path",
					"default": "/v1/hfr/fetch-facilities-by-owner",
					"insert_after": "facility_onboarding_hie_password",
				},
				{
					"fieldname": "facility_onboarding_hfr_facility_path",
					"fieldtype": "Data",
					"label": "HFR facility lookup path",
					"default": "/v1/hfr/fetch-facility",
					"insert_after": "facility_onboarding_hfr_owner_path",
				},
				{
					"fieldname": "facility_onboarding_client_registry_path",
					"fieldtype": "Data",
					"label": "Client Registry lookup path",
					"default": "/client-registry/fetch-client",
					"insert_after": "facility_onboarding_hfr_facility_path",
				},
				{
					"fieldname": "facility_onboarding_jwt_expiry",
					"fieldtype": "Int",
					"label": "Registry JWT expiry (seconds)",
					"default": "20000",
					"insert_after": "facility_onboarding_client_registry_path",
				},
			],
		}
	)
