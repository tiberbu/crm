"""Make the token-based terms setting a selectable Terms and Conditions link."""

import frappe


def execute():
	"""Upgrade sites where the earlier Data custom field has already been created."""
	field_name = frappe.db.get_value(
		"Custom Field",
		{"dt": "CRM Opt-In Settings", "fieldname": "self_onboarding_tc_document"},
		"name",
	)
	if not field_name:
		return

	frappe.db.set_value(
		"Custom Field",
		field_name,
		{
			"fieldtype": "Link",
			"options": "Terms and Conditions",
			"label": "Token-Based Self-Onboarding Terms Document",
			"description": (
				"Terms shown in token-based facility onboarding. Leave blank to use the configured "
				"Default Terms and Conditions above."
			),
		},
		update_modified=False,
	)
	frappe.clear_cache(doctype="CRM Opt-In Settings")
