"""Add the preferred OTP channel for public facility onboarding."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "facility_onboarding_preferred_otp_channel",
					"fieldtype": "Select",
					"label": "Preferred OTP channel",
					"options": "Email\nSMS",
					"default": "Email",
					"description": "Tried first; the other verified channel is used if it is unavailable or delivery fails.",
					"insert_after": "facility_onboarding_default_partner_id",
				}
			]
		}
	)
