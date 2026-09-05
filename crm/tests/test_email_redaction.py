from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import CallbackManager

from crm.api._email import OTP_QUEUE_REDACTION, schedule_email_queue_redaction


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
