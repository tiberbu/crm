"""Add the `Awaiting signature` option to the OIS portal invitation status field.

Contract-journey submissions now defer the platform-access email to the facility's
first signature. While the user and permission exist but the email is still to be
sent, the OIS shows `Awaiting signature`. The field is created by
`add_cx_portal_fields`; this patch only extends its Select options.
"""

import frappe

PORTAL_STATUS_FIELDNAME = "portal_invitation_status"
NEW_OPTIONS = "Pending\nAwaiting signature\nSent\nAlready active\nBlocked\nFailed"


def execute():
	field_name = "CRM Opt-In Submission-%s" % PORTAL_STATUS_FIELDNAME
	if not frappe.db.exists("Custom Field", field_name):
		return
	frappe.db.set_value("Custom Field", field_name, "options", NEW_OPTIONS)
	frappe.clear_cache(doctype="CRM Opt-In Submission")
