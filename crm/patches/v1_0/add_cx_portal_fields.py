"""Add the OIS fields used to reconcile Customer Experience access."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Opt-In Submission": [
				{
					"fieldname": "section_cx_portal",
					"fieldtype": "Section Break",
					"label": "Customer Experience Portal",
					"insert_after": "contract_invitation_queued_at",
				},
				{
					"fieldname": "portal_user",
					"fieldtype": "Link",
					"label": "Customer Experience User",
					"options": "User",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "section_cx_portal",
				},
				{
					"fieldname": "portal_invitation_status",
					"fieldtype": "Select",
					"label": "Portal Invitation Status",
					"options": "Pending\nSent\nAlready active\nBlocked\nFailed",
					"default": "Pending",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "portal_user",
				},
				{
					"fieldname": "portal_invitation_sent_at",
					"fieldtype": "Datetime",
					"label": "Portal Invitation Sent At",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "portal_invitation_status",
				},
				{
					"fieldname": "portal_invitation_error",
					"fieldtype": "Small Text",
					"label": "Portal Invitation Error",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "portal_invitation_sent_at",
				},
			],
		}
	)
