"""Add persistence fields for CRM self-onboarding submissions."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Opt-In Submission": [
				{
					"fieldname": "section_self_onboarding",
					"fieldtype": "Section Break",
					"label": "Self-Onboarding",
					"insert_after": "contract_invitation_queued_at",
				},
				{
					"fieldname": "onboarding_source",
					"fieldtype": "Data",
					"label": "Onboarding Source",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "section_self_onboarding",
				},
				{
					"fieldname": "onboarding_identity_ref",
					"fieldtype": "Data",
					"label": "Onboarding Identity Reference",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "onboarding_source",
				},
				{
					"fieldname": "cx_account_email",
					"fieldtype": "Data",
					"label": "Customer Experience Account Email",
					"options": "Email",
					"insert_after": "onboarding_identity_ref",
				},
				{
					"fieldname": "self_onboarding_tc_document",
					"fieldtype": "Data",
					"label": "Self-Onboarding T&C Document",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "cx_account_email",
				},
				{
					"fieldname": "self_onboarding_tc_hash",
					"fieldtype": "Data",
					"label": "Self-Onboarding T&C Hash (SHA-256)",
					"length": 64,
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "self_onboarding_tc_document",
				},
				{
					"fieldname": "self_onboarding_tc_accepted_at",
					"fieldtype": "Datetime",
					"label": "Self-Onboarding T&C Accepted At",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "self_onboarding_tc_hash",
				},
			],
			"CRM Opt-In Settings": [
				{
					"fieldname": "self_onboarding_tc_document",
					"fieldtype": "Data",
					"label": "Self-Onboarding T&C Document",
					"insert_after": "active_tc_document",
				}
			],
		}
	)
