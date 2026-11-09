from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import CallbackManager

from crm.api._email import OTP_QUEUE_REDACTION, schedule_email_queue_redaction
from crm.email.queue_patch import apply_queue_builder_patches
from crm.email.ses_runtime import AwsSesRuntimeConfig


class _Queue:
	name = "Email Queue-TEST-OTP"

	def __init__(self, events):
		self.events = events

	def send(self):
		self.events.append("send")


class TestEmailQueueRedaction(UnitTestCase):
	def test_redaction_wraps_queue_send_after_delivery(self):
		events = []
		queue = _Queue(events)
		callbacks = CallbackManager()
		callbacks.add(queue.send)

		with (
			patch.object(frappe.db, "after_commit", callbacks),
			patch.object(frappe.db, "exists", return_value=True),
			# Frappe 16 defers a now=True send to after commit, so the row is still unsent.
			patch.object(frappe.db, "get_value", return_value="Not Sent"),
			patch.object(frappe, "get_doc", return_value=queue),
			patch.object(
				frappe.db,
				"set_value",
				side_effect=lambda *args, **kwargs: events.append("redact"),
			),
			patch.object(frappe.db, "commit"),
		):
			schedule_email_queue_redaction(queue)
			callbacks.run()

		self.assertEqual(events, ["send", "redact"])
		self.assertEqual(OTP_QUEUE_REDACTION, "OTP email content redacted after delivery.")


class TestOtpEmailIsSentOnce(UnitTestCase):
	def setUp(self):
		apply_queue_builder_patches()

	def tearDown(self):
		for name in getattr(self, "_queues", []):
			frappe.db.delete("Email Queue Recipient", {"parent": name})
			frappe.db.delete("Email Queue", name)
		frappe.db.commit()

	def test_send_now_email_with_redaction_reaches_the_transport_once(self):
		# Frappe 15 sends a now=True email immediately and records "Sent" only in the
		# database; the after-commit send must not deliver the same queue row again.
		sent = []
		ses = AwsSesRuntimeConfig(enabled=True, default_sender_email="noreply@example.test")
		with (
			patch("crm.email.queue_patch.get_ses_runtime_config", return_value=ses),
			patch("crm.email.email_queue.get_ses_runtime_config", return_value=ses),
			patch("crm.email.ses_send.send", side_effect=lambda queue, sender, recipient, message: sent.append(recipient)),
			patch.object(frappe, "are_emails_muted", return_value=False),
		):
			queue = frappe.sendmail(
				recipients=["otp-once@example.test"],
				subject="Verification code test",
				message="<p>code</p>",
				now=True,
			)
			self._queues = [queue.name]
			schedule_email_queue_redaction(queue)
			frappe.db.commit()

		self.assertEqual(sent, ["otp-once@example.test"])
		self.assertEqual(frappe.db.get_value("Email Queue", queue.name, "status"), "Sent")
		self.assertEqual(frappe.db.get_value("Email Queue", queue.name, "message"), OTP_QUEUE_REDACTION)
