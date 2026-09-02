"""Repair contract invitation dedupe state and the internal reminder schedule."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from crm.setup.optin import ensure_internal_signatory_reminder_job


def execute():
	"""Create compatibility fields and register the reminder job safely."""
	if frappe.db.table_exists("CRM Contract Signatory"):
		create_custom_fields(
			{
				"CRM Contract Signatory": [
					{
						"fieldname": "crm_last_invitation_sent_at",
						"fieldtype": "Datetime",
						"label": "Last Invitation Sent At",
						"read_only": 1,
						"no_copy": 1,
					}
				]
			},
			ignore_validate=True,
		)
	ensure_internal_signatory_reminder_job()
