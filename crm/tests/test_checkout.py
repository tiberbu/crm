import json
from types import SimpleNamespace
from unittest.mock import ANY, patch

from frappe.tests import UnitTestCase

from crm.api.checkout import _send_payment_otp, request_payment_otp


class _Cache:
	def __init__(self):
		self.values = {}

	def get_value(self, key):
		return self.values.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.values[key] = value


class TestCheckoutOtp(UnitTestCase):
	def test_payment_otp_uses_branded_email_and_unique_subject(self):
		submission = SimpleNamespace(
			name="OIS-2026-00001",
			deal="DEAL-00001",
			facility_signatory_email="signatory@example.com",
		)
		queue = SimpleNamespace(name="EMAIL-QUEUE-00001")
		network = {
			"display_name": "Example Health Network",
			"primary_colour": "#0f766e",
		}

		with (
			patch("crm.api.checkout._network_for_submission", return_value=network),
			patch("crm.api.checkout.create_transactional_communication", return_value="COMM-00001"),
			patch("crm.api.checkout.frappe.sendmail", return_value=queue) as sendmail,
			patch("crm.api.checkout.schedule_email_queue_redaction") as redact,
		):
			self.assertTrue(_send_payment_otp(submission, "123456", request_id="CHECKOUT-A1B2"))

		payload = sendmail.call_args.kwargs
		self.assertEqual(payload["recipients"], ["signatory@example.com"])
		self.assertEqual(
			payload["subject"],
			"Example Health Network — secure payment code · OIS-2026-00001 · CHECKOUT-A1B2",
		)
		self.assertIn("Your secure payment code", payload["message"])
		self.assertIn("123456", payload["message"])
		self.assertIn("For your security, do not share this code.", payload["message"])
		redact.assert_called_once_with(queue, ANY)

	def test_duplicate_otp_request_reuses_the_existing_code_without_resending(self):
		cache = _Cache()
		submission = SimpleNamespace(
			name="OIS-2026-00001",
			status="Processed",
			facility_signatory_email="signatory@example.com",
		)

		with (
			patch("crm.api.checkout.frappe.cache", return_value=cache),
			patch("crm.api.checkout.frappe.parse_json", side_effect=json.loads),
			patch("crm.api.checkout._get_submission", return_value=submission),
			patch("crm.api.checkout._hash_otp", return_value="hash"),
			patch("crm.api.checkout._send_payment_otp") as send_otp,
			patch("crm.api.checkout.time.time", return_value=1_000_000),
		):
			first = request_payment_otp(submission.name)
			second = request_payment_otp(submission.name)

		self.assertTrue(first["sent"])
		self.assertTrue(second["sent"])
		send_otp.assert_called_once()
		otp_payloads = [
			json.loads(value)
			for key, value in cache.values.items()
			if ":otp:" in key
		]
		self.assertEqual(len(otp_payloads), 1)
		self.assertEqual(otp_payloads[0]["sent_at"], 1_000_000)
