from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from crm.finance.email import send_document_copy


class TestFinanceDocumentCopy(TestCase):
	def setUp(self):
		self.document = frappe._dict(name="SINV-0001", company="Careverse HQ")
		self.communication = frappe._dict(
			name="COMM-0001",
			content="<p>Please find the attached copy.</p>",
			insert=MagicMock(),
		)
		self.communication.insert.return_value = self.communication
		self.queue = frappe._dict(name="EMAIL-QUEUE-0001")

	def _patch_delivery(self, *, result=None):
		get_doc = patch(
			"crm.finance.email.frappe.get_doc",
			side_effect=[self.document, self.communication],
		)
		return (
			get_doc,
			patch(
				"crm.finance.email.frappe.sendmail",
				return_value=self.queue if result is None else result,
			),
			patch("crm.finance.email.frappe.has_permission"),
			patch("crm.finance.email.validate_email_address"),
		)

	def test_queues_native_copy_with_print_context_and_email_permission(self):
		get_doc, sendmail, has_permission, validate_email = self._patch_delivery()
		with get_doc, sendmail as queue_send, has_permission as permission, validate_email:
			result = send_document_copy(
				doctype="Sales Invoice",
				name="SINV-0001",
				recipient="accounts@example.com",
				subject="Invoice SINV-0001",
				message="Please find the attached copy.",
				print_format="Standard",
				company="Careverse HQ",
			)

		self.assertEqual(result["email_queue"], "EMAIL-QUEUE-0001")
		self.assertTrue(result["queued"])
		permission.assert_called_once_with(
			"Sales Invoice", doc="SINV-0001", ptype="email", throw=True
		)
		queue_send.assert_called_once()
		self.assertEqual(queue_send.call_args.kwargs["reference_name"], "SINV-0001")
		self.assertEqual(queue_send.call_args.kwargs["communication"], "COMM-0001")
		self.assertEqual(queue_send.call_args.kwargs["attachments"][0]["print_format"], "Standard")
		self.assertTrue(queue_send.call_args.kwargs["print_letterhead"])

	def test_rejects_company_mismatch_before_queueing(self):
		get_doc = patch("crm.finance.email.frappe.get_doc", return_value=self.document)
		with (
			get_doc,
			patch("crm.finance.email.frappe.has_permission"),
			patch("crm.finance.email.frappe.throw", side_effect=ValueError("company mismatch")),
			patch("crm.finance.email.frappe.sendmail") as queue_send,
		):
			with self.assertRaisesRegex(ValueError, "company mismatch"):
				send_document_copy(
					doctype="Sales Invoice",
					name="SINV-0001",
					recipient="accounts@example.com",
					subject="Invoice SINV-0001",
					message="Please find the attached copy.",
					company="Other Company",
				)
		queue_send.assert_not_called()

	def test_reports_queue_creation_failure(self):
		get_doc, sendmail, has_permission, validate_email = self._patch_delivery(result=[])
		with (
			get_doc,
			sendmail,
			has_permission,
			validate_email,
			patch("crm.finance.email.frappe.throw", side_effect=ValueError("queue failure")),
		):
			with self.assertRaisesRegex(ValueError, "queue failure"):
				send_document_copy(
					doctype="Sales Invoice",
					name="SINV-0001",
					recipient="accounts@example.com",
					subject="Invoice SINV-0001",
					message="Please find the attached copy.",
				)

	def test_rejects_email_permission_before_reading_document(self):
		with (
			patch("crm.finance.email.frappe.has_permission", side_effect=frappe.PermissionError),
			patch("crm.finance.email.frappe.get_doc") as get_doc,
		):
			with self.assertRaises(frappe.PermissionError):
				send_document_copy(
					doctype="Sales Invoice",
					name="SINV-0001",
					recipient="accounts@example.com",
					subject="Invoice SINV-0001",
					message="Please find the attached copy.",
				)
		get_doc.assert_not_called()
