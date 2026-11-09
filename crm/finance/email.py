"""Finance document-copy delivery through Frappe's native Email Queue."""

from __future__ import annotations

from html import escape

import frappe
from frappe import _
from frappe.utils import validate_email_address

from crm.finance.api import _request_flag, _request_text


@frappe.whitelist()
def send_document_copy(
	doctype=None,
	name=None,
	recipient=None,
	subject=None,
	message=None,
	print_format=None,
	print_letterhead=1,
	company=None,
):
	"""Render and queue a Finance document copy without Email Account preflight.

	The `frappe.sendmail` Email Queue path uses CRM's `override_email_send` hook
	when SES is enabled. Check the same document email permission as Frappe's
	native Communication email method before creating the communication record.
	"""
	doctype = _request_text(doctype, "Document type", required=True)
	name = _request_text(name, "Document", required=True)
	recipient = _request_text(recipient, "Recipient", required=True)
	subject = _request_text(subject, "Subject", required=True)
	message = _request_text(message, "Message", required=True)
	print_format = _request_text(print_format, "Print format") or None
	company = _request_text(company, "Company") or None
	print_letterhead = _request_flag(print_letterhead, "Print letterhead", default=1)

	frappe.has_permission(doctype, doc=name, ptype="email", throw=True)
	doc = frappe.get_doc(doctype, name)
	if company and doc.get("company") and doc.company != company:
		frappe.throw(
			_("This document belongs to {0}, not the selected Company {1}.").format(
				doc.company, company
			),
			frappe.PermissionError,
		)
	validate_email_address(recipient, throw=True)

	# This is the native Email Queue attachment descriptor. Frappe renders the
	# selected print format and letterhead while building the queued MIME message.
	attachments = [
		{
			"doctype": doctype,
			"name": name,
			"print_format": print_format,
			"print_format_attachment": 1,
			"lang": frappe.local.lang,
		}
	]
	communication = frappe.get_doc(
		{
			"doctype": "Communication",
			"communication_type": "Communication",
			"communication_medium": "Email",
			"sent_or_received": "Sent",
			"reference_doctype": doctype,
			"reference_name": name,
			"subject": subject,
			"content": "<p>" + "<br>".join(escape(line) for line in message.splitlines()) + "</p>",
			"recipients": recipient,
			"has_attachment": 1,
		}
	).insert(ignore_permissions=True)

	queue = frappe.sendmail(
		recipients=[recipient],
		subject=subject,
		message=communication.content,
		reference_doctype=doctype,
		reference_name=name,
		communication=communication.name,
		attachments=attachments,
		print_letterhead=bool(print_letterhead),
		delayed=True,
	)
	if not queue or not getattr(queue, "name", None):
		frappe.throw(
			_("The copy was not added to the Email Queue. Check the recipient and email settings, then retry."),
			frappe.ValidationError,
		)

	return {
		"queued": True,
		"communication": communication.name,
		"email_queue": queue.name,
	}
