"""Remove OTP bodies from already-delivered Email Queue records."""

import frappe

from crm.api._email import OTP_QUEUE_REDACTION


def execute():
	"""Redact historical OTP messages without touching emails awaiting delivery."""
	if not frappe.db.table_exists("Email Queue"):
		return

	rows = frappe.get_all(
		"Email Queue",
		filters=[
			["status", "in", ["Sent", "Partially Sent", "Error"]],
			["subject", "like", "%verification code%"],
		],
		fields=["name"],
		limit_page_length=0,
		ignore_permissions=True,  # SYSTEM-INTERNAL: remove historical secrets
	)
	for row in rows:
		frappe.db.set_value(
			"Email Queue",
			row.name,
			"message",
			OTP_QUEUE_REDACTION,
			update_modified=False,
		)
