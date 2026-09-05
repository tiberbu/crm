"""Add network-level invoice timing controls for signature-based billing."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from crm.setup.optin import ensure_default_terms


def execute():
	if not frappe.db.exists("DocType", "CRM Opt-In Network"):
		return
	create_custom_fields(
		{
			"CRM Opt-In Network": [
				{
					"fieldname": "invoice_on_contract_signature",
					"fieldtype": "Check",
					"label": "Issue Invoice on Contract Signature",
					"default": "0",
					"insert_after": "first_invoice_offset_months",
					"description": "When enabled, the first invoice becomes eligible as soon as the contract is fully signed.",
				},
			],
		},
		ignore_validate=True,
	)
	# The system-owned T&C must expose the new timing sentence immediately after
	# migration; administrator-authored active documents remain untouched.
	ensure_default_terms()
