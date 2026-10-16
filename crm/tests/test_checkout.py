import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import ANY, patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from crm.api import checkout
from crm.api import customer_experience as cx
from crm.api.checkout import _send_payment_otp, request_payment_otp
from crm.api.facility_onboarding import _token_packages
from crm.tests.test_customer_experience import OTHER, OWNER, _submission, _website_user


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
		otp_payloads = [json.loads(value) for key, value in cache.values.items() if ":otp:" in key]
		self.assertEqual(len(otp_payloads), 1)
		self.assertEqual(otp_payloads[0]["sent_at"], 1_000_000)


PAYSTACK_SECRET = "sk_test_unit"


class _FakeRequest:
	def __init__(self, body, signature):
		self._body = body
		self.headers = {"x-paystack-signature": signature}

	def get_data(self):
		return self._body


class TestPortalCheckout(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("cx_checkout_test")
		self.addCleanup(frappe.db.rollback, save_point="cx_checkout_test")
		packages = [p for p in _token_packages() if (p.get("price") or 0) > 0]
		if not packages:
			self.skipTest("No enabled token package with a price on this site")
		self.package = packages[0]
		_website_user(OWNER)
		_website_user(OTHER)
		self.ois = _submission(OWNER, "90001")
		self.other_ois = _submission(OTHER, "90002")
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(OWNER)
		order = cx.create_token_order(self.ois, "90001", self.package["item_code"])["data"]["sales_order"]
		self.invoice = cx.start_token_payment(order)["data"]["invoice"]
		self.invoice_doc = frappe.get_doc("Sales Invoice", self.invoice)
		self.amount = round(self.invoice_doc.outstanding_amount * 100)
		self.paystack = patch("crm.api.checkout._paystack_request")
		self.request = self.paystack.start()
		self.addCleanup(self.paystack.stop)
		keys = patch("crm.api.checkout._paystack_settings", return_value=(PAYSTACK_SECRET, "pk_test"))
		keys.start()
		self.addCleanup(keys.stop)

	def _verified(self, reference="ref-1", amount=None, currency=None, ois=None, invoice=None):
		return {
			"status": True,
			"data": {
				"status": "success",
				"amount": self.amount if amount is None else amount,
				"currency": currency or self.invoice_doc.currency,
				"reference": reference,
				"metadata": {"ois_number": ois or self.ois, "invoice": invoice or self.invoice},
			},
		}

	def _payments(self, reference):
		return frappe.get_all("Payment Entry", filters={"crm_checkout_reference": reference}, pluck="name")

	def test_signed_in_owner_sees_the_open_invoice_without_an_otp(self):
		data = checkout.get_portal_checkout(self.ois)
		self.assertEqual([row["name"] for row in data["invoices"]], [self.invoice])
		self.assertEqual(data["ois_number"], self.ois)

	def test_other_customers_guests_and_staff_are_denied(self):
		for user in (OTHER, "Guest", "Administrator"):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError):
				checkout.get_portal_checkout(self.ois)
			with self.assertRaises(frappe.PermissionError):
				checkout.initialize_portal_paystack_payment(self.ois, self.invoice)
			with self.assertRaises(frappe.PermissionError):
				checkout.verify_portal_paystack_payment(self.ois, "ref-1")

	def test_initialize_uses_the_invoice_amount_and_portal_callback(self):
		self.request.return_value = {
			"status": True,
			"data": {"authorization_url": "https://checkout.paystack.test/abc", "reference": "ref-1"},
		}
		result = checkout.initialize_portal_paystack_payment(self.ois, self.invoice)
		payload = self.request.call_args.kwargs["json"]
		self.assertEqual(result["authorization_url"], "https://checkout.paystack.test/abc")
		self.assertEqual(payload["amount"], self.amount)
		self.assertEqual(payload["currency"], self.invoice_doc.currency)
		self.assertEqual(payload["metadata"], {"ois_number": self.ois, "invoice": self.invoice})
		self.assertIn("/cx-portal?reference=OIS-", payload["callback_url"])

	def test_initialize_rejects_an_invoice_that_is_not_the_users(self):
		frappe.set_user("Administrator")
		other_order = None
		frappe.set_user(OTHER)
		other_order = cx.create_token_order(self.other_ois, "90002", self.package["item_code"])["data"][
			"sales_order"
		]
		foreign_invoice = cx.start_token_payment(other_order)["data"]["invoice"]
		frappe.set_user(OWNER)
		with self.assertRaises(frappe.ValidationError):
			checkout.initialize_portal_paystack_payment(self.ois, foreign_invoice)
		self.request.assert_not_called()

	def test_verify_reconciles_once_and_replays_are_idempotent(self):
		self.request.return_value = self._verified()
		first = checkout.verify_portal_paystack_payment(self.ois, "ref-1")
		second = checkout.verify_portal_paystack_payment(self.ois, "ref-1")
		self.assertTrue(first["paid"])
		self.assertEqual(second["payment_entry"], first["payment_entry"])
		self.assertEqual(self._payments("ref-1"), [first["payment_entry"]])
		self.assertEqual(self.request.call_count, 1)
		self.assertEqual(frappe.db.get_value("Sales Invoice", self.invoice, "outstanding_amount"), 0)

	def test_amount_currency_and_ownership_mismatches_create_no_payment(self):
		self.request.return_value = self._verified(amount=self.amount - 100)
		with self.assertRaises(frappe.ValidationError):
			checkout.verify_portal_paystack_payment(self.ois, "ref-1")
		self.request.return_value = self._verified(currency="USD")
		with self.assertRaises(frappe.ValidationError):
			checkout.verify_portal_paystack_payment(self.ois, "ref-1")
		self.request.return_value = self._verified(ois=self.other_ois)
		with self.assertRaises(frappe.PermissionError):
			checkout.verify_portal_paystack_payment(self.ois, "ref-1")
		self.assertEqual(self._payments("ref-1"), [])

	def test_unpaid_transactions_do_not_reconcile(self):
		self.request.return_value = {"status": True, "data": {"status": "abandoned"}}
		self.assertFalse(checkout.verify_portal_paystack_payment(self.ois, "ref-1")["paid"])
		self.assertEqual(self._payments("ref-1"), [])

	def _post_webhook(self, event, signature=None):
		body = json.dumps(event).encode()
		signed = signature or hmac.new(PAYSTACK_SECRET.encode(), body, hashlib.sha512).hexdigest()
		with patch.object(frappe.local, "request", _FakeRequest(body, signed), create=True):
			return checkout.paystack_webhook()

	def test_webhook_requires_a_valid_signature(self):
		event = {"event": "charge.success", "data": self._verified("ref-w")["data"]}
		with self.assertRaises(frappe.PermissionError):
			self._post_webhook(event, signature="bad")
		self.assertEqual(self._payments("ref-w"), [])

	def test_webhook_and_browser_verification_share_one_payment_entry(self):
		event = {"event": "charge.success", "data": self._verified("ref-w")["data"]}
		frappe.set_user("Guest")
		self._post_webhook(event)
		self._post_webhook(event)
		frappe.set_user(OWNER)
		self.request.return_value = self._verified("ref-w")
		result = checkout.verify_portal_paystack_payment(self.ois, "ref-w")
		self.assertTrue(result["paid"])
		self.assertEqual(len(self._payments("ref-w")), 1)

	def test_guest_checkout_payload_matches_the_portal_payload(self):
		submission = checkout._get_submission(self.ois)
		with patch("crm.api.checkout._require_session", return_value=({}, submission)):
			guest = checkout.get_payment_checkout("token")
		self.assertEqual(guest, checkout.get_portal_checkout(self.ois))
