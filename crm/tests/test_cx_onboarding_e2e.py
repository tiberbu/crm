"""Mocked-upstream end-to-end proof: identity to authorised checkout.

HFR, Client Registry, mail and Paystack are mocked, so nothing is delivered or
charged. OIS pipeline processing (lead/deal/quotation creation) is stood in by a
status flip because it commits; its own suite covers it. Everything else is real:
sessions, OTP, evidence, OIS, Network membership, Website User and permission,
Quotation, Sales Order, Sales Invoice, Payment Entry.
"""

import json
import re
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import checkout
from crm.api import customer_experience as cx
from crm.api import facility_onboarding as fo
from crm.api.website_redirect import ensure_website_user_for_ois
from crm.fcrm.doctype.crm_onboarding_evidence.crm_onboarding_evidence import evidence_ref
from crm.tests.test_customer_experience import OTHER, _submission, _website_user

OWNER_EMAIL = "cx-e2e-owner@example.com"
ID_NUMBER = "87654321"
MFL = "90077"
PERSON = {"first_name": "Amina", "last_name": "Otieno", "email": OWNER_EMAIL, "phone": "254712345678"}
FACILITY = {
	"facility_id": "FID-E2E",
	"facility_code": MFL,
	"facility_name": "E2E Clinic",
	"facility_level": "Level 3",
}


class TestOnboardingToCheckout(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("cx_e2e_test")
		self.addCleanup(frappe.db.rollback, save_point="cx_e2e_test")
		self.addCleanup(frappe.set_user, "Administrator")
		self.network = frappe.db.get_value(
			"CRM Opt-In Network",
			{"enabled": 1, "partner_id": ["!=", ""]},
			["name", "partner_id"],
			as_dict=True,
		)
		if not self.network or not fo._token_packages():
			self.skipTest("Needs an enabled Network and a priced token package")
		self.package = fo._token_packages()[0]
		self.mail = []
		self.order = Mock()
		self.order.attach_mock(Mock(return_value=[FACILITY]), "hfr")
		self.order.attach_mock(Mock(return_value=dict(PERSON)), "registry")
		self.paystack = Mock()

		def process(name):
			frappe.db.set_value("CRM Opt-In Submission", name, "status", "Processed")

		cache = {}
		patches = [
			patch.object(fo, "_hfr_facilities_for_owner", self.order.hfr),
			patch.object(fo, "_client_registry_person", self.order.registry),
			patch.object(fo, "_session", side_effect=lambda token: cache.get(token)),
			patch.object(
				fo,
				"_save_session",
				side_effect=lambda token, payload: cache.__setitem__(token, json.loads(json.dumps(payload))),
			),
			patch.object(fo, "_rate_limited", return_value=False),
			patch.object(fo.frappe, "sendmail", side_effect=lambda **kw: self.mail.append(kw) or Mock()),
			patch.object(fo, "schedule_email_queue_redaction"),
			patch.object(fo.frappe.db, "commit"),
			patch("crm.api.optin._process_submission", side_effect=process),
			patch("frappe.core.doctype.user.user.User.send_welcome_mail_to_user"),
			patch("crm.api.checkout._paystack_request", self.paystack),
			patch("crm.api.checkout._paystack_settings", return_value=("sk_test_e2e", "pk_test")),
		]
		for item in patches:
			item.start()
			self.addCleanup(item.stop)

	def _otp(self):
		return re.search(r"<strong>(\d{6})</strong>", self.mail[-1]["message"]).group(1)

	def _onboard(self):
		frappe.set_user("Guest")
		start = fo.start_identity("national_id", ID_NUMBER)["data"]
		token = start["session_token"]
		self.otp = self._otp()
		verified = fo.verify_otp(token, self.otp)["data"]
		catalog = fo.get_catalog(self.network.partner_id)["data"]
		witness = json.dumps({"name": "Witness", "email": "cx-e2e-witness@example.com"})
		args = (
			token,
			self.network.partner_id,
			json.dumps(["FID-E2E"]),
			self.package["item_code"],
			witness,
			1,
		)
		first = fo.submit_onboarding(*args)["data"]["submissions"]
		second = fo.submit_onboarding(*args)["data"]["submissions"]
		frappe.set_user("Administrator")
		return start, verified, catalog, first, second, token

	def test_identity_to_paid_invoice_with_retries_and_isolation(self):
		start, verified, catalog, first, second, token = self._onboard()

		# Identity: HFR first, masked delivery, nothing disclosed before the code.
		self.assertEqual([c[0] for c in self.order.mock_calls], ["hfr", "registry"])
		self.assertEqual(start["delivery"]["masked_destination"], "c***@example.com")
		self.assertNotIn(OWNER_EMAIL, json.dumps(start))
		self.assertEqual(verified["facilities"][0]["facility_id"], "FID-E2E")

		# Catalog carries server-resolved VAT; submission is idempotent and server-priced.
		priced = next(p for p in catalog["packages"] if p["item_code"] == self.package["item_code"])
		self.assertEqual(priced["gross_total"], round(priced["price_ex_vat"] + priced["vat_amount"], 2))
		self.assertEqual(first, second)
		self.assertEqual(len(first), 1)
		ois = first[0]["submission"]
		payload = json.loads(frappe.db.get_value("CRM Opt-In Submission", ois, "raw_json"))
		self.assertEqual(payload["pricing"][0]["annual_kes"], self.package["price"])
		self.assertEqual(frappe.db.count("CRM Opt-In Submission", {"submitter_email": OWNER_EMAIL}), 1)

		# Network membership for the selected facility.
		facility = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": MFL}, "name")
		memberships = frappe.get_all(
			"CRM Facility Membership",
			filters={"parent": facility, "network": self.network.name},
			pluck="status",
		)
		self.assertTrue(memberships)

		# Website User access, then the purchase chain with retries.
		ensure_website_user_for_ois(frappe.get_doc("CRM Opt-In Submission", ois), email=OWNER_EMAIL)
		frappe.set_user(OWNER_EMAIL)
		order = cx.create_token_order(ois, MFL, self.package["item_code"])["data"]
		again = cx.create_token_order(ois, MFL, self.package["item_code"])["data"]
		self.assertEqual(order["sales_order"], again["sales_order"])
		self.assertTrue(again["idempotent"])
		self.assertEqual(frappe.db.get_value("Sales Order", order["sales_order"], "docstatus"), 1)
		self.assertEqual(frappe.db.count("Sales Invoice", {"crm_optin_submission": ois}), 0)

		invoice = cx.start_token_payment(order["sales_order"])["data"]["invoice"]
		self.assertEqual(cx.start_token_payment(order["sales_order"])["data"]["invoice"], invoice)
		self.assertEqual(frappe.db.count("Sales Invoice", {"crm_optin_submission": ois, "docstatus": 1}), 1)

		# Authorised checkout: amount from the invoice, replay-safe reconciliation.
		amount = round(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount") * 100)
		self.paystack.return_value = {
			"status": True,
			"data": {"authorization_url": "https://checkout.test/x"},
		}
		checkout.initialize_portal_paystack_payment(ois, invoice)
		self.assertEqual(self.paystack.call_args.kwargs["json"]["amount"], amount)
		self.paystack.return_value = {
			"status": True,
			"data": {
				"status": "success",
				"amount": amount,
				"currency": frappe.db.get_value("Sales Invoice", invoice, "currency"),
				"metadata": {"ois_number": ois, "invoice": invoice},
			},
		}
		paid = checkout.verify_portal_paystack_payment(ois, "e2e-ref-1")
		replay = checkout.verify_portal_paystack_payment(ois, "e2e-ref-1")
		self.assertTrue(paid["paid"])
		self.assertEqual(replay["payment_entry"], paid["payment_entry"])
		self.assertEqual(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount"), 0)

		# Another customer cannot see or act on any of it.
		frappe.set_user("Administrator")
		_website_user(OTHER)
		_submission(OTHER, "90099")
		frappe.set_user(OTHER)
		for call in (
			lambda: cx.create_token_order(ois, MFL, self.package["item_code"]),
			lambda: cx.start_token_payment(order["sales_order"]),
			lambda: checkout.get_portal_checkout(ois),
			lambda: checkout.initialize_portal_paystack_payment(ois, invoice),
			lambda: checkout.verify_portal_paystack_payment(ois, "e2e-ref-1"),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

		# Append-only evidence covers the journey without personal data.
		frappe.set_user("Administrator")
		rows = frappe.get_all(
			"CRM Onboarding Evidence",
			filters={"session_ref": evidence_ref(token)},
			fields=["event", "outcome", "reference_name", "detail"],
		)
		events = {row.event for row in rows}
		self.assertTrue(
			{"lookup", "otp_sent", "otp_verified", "terms_accepted", "facility_selected"} <= events
		)
		linked = {
			r.reference_name
			for r in frappe.get_all(
				"CRM Onboarding Evidence", filters={"event": "document_linked"}, fields=["reference_name"]
			)
		}
		self.assertTrue({order["sales_order"], invoice} <= linked)
		dump = json.dumps(rows, default=str)
		for secret in (ID_NUMBER, OWNER_EMAIL, "254712345678", self.otp):
			self.assertNotIn(secret, dump)
