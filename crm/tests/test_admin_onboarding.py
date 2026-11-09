"""Alternative admin path: an administrator onboards a facility whose registered contact
holds the onboarding link. The OTP is routed to the registered contact; the resulting
Tiberbu Express account is created on the organization's corporate email.

The existing owner/registrant flow must remain untouched, so these tests exercise only
the additive endpoints and the admin branches of shared helpers.
"""

import copy
import re
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import facility_onboarding as fo


class _Store:
	def __init__(self):
		self.data = {}

	def save(self, token, payload):
		self.data[token] = copy.deepcopy(payload)

	def get(self, token):
		return copy.deepcopy(self.data.get(token))


OWNER_EMAIL = "jane.owner@example.com"
OWNER_PHONE = "+254711000111"
ORG_EMAIL = "billing@adminpathclinic.co.ke"


class TestAdminOnboardingPath(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("admin_onboarding_test")
		self.addCleanup(frappe.db.rollback, save_point="admin_onboarding_test")
		self.store = _Store()
		self.sent = []
		self.sms = []
		self.log_error = Mock()

		def sendmail(**kwargs):
			self.sent.append(kwargs)
			return Mock()

		patches = [
			patch.object(fo, "_session", side_effect=lambda token: self.store.get(token)),
			patch.object(fo, "_save_session", side_effect=self.store.save),
			patch.object(fo, "_rate_limited", return_value=False),
			patch.object(fo, "_password_setting", return_value="test-secret"),
			patch.object(
				fo,
				"_setting",
				side_effect=lambda name, default="": (
					"Email"
					if name == "facility_onboarding_preferred_otp_channel"
					else "Level 3"
					if name == "self_onboarding_allowed_facility_levels"
					else default
				),
			),
			patch.object(fo.frappe, "sendmail", side_effect=sendmail),
			patch.object(fo, "schedule_email_queue_redaction"),
			patch.object(fo.frappe, "log_error", self.log_error),
			patch.object(fo.frappe.db, "commit"),
			patch("crm.api.optin._sms_gateway_configured", side_effect=lambda: False),
			patch("crm.api.optin._send_otp_sms", side_effect=lambda *args: self.sms.append(args)),
		]
		for item in patches:
			item.start()
			self.addCleanup(item.stop)

	def _make_facility(self, mfl="MFL-ADMIN-1", reg="REG-ADMIN-1", level="Level 3", with_contact=True):
		doc = frappe.get_doc(
			{
				"doctype": "CRM Pre-Qualified Facility",
				"mfl_code": mfl,
				"facility_name": "Admin Path Clinic",
				"organization": "Admin Path Clinic Ltd",
				"keph_level": level,
				"registration_number": reg,
			}
		)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True, ignore_links=True)
		if with_contact:
			doc.append(
				"memberships",
				{
					"network": "Test Network",
					"status": "Active",
					"contact_name": "Jane Owner",
					"contact_email": OWNER_EMAIL,
					"contact_phone": OWNER_PHONE,
				},
			)
			doc.save(ignore_permissions=True)
		return doc

	def _start(self, reference="MFL-ADMIN-1"):
		self._make_facility()
		return fo.start_admin_onboarding(reference)["data"]

	def _captured_otp(self):
		return re.search(r">(\d{6})</span>", self.sent[-1]["message"]).group(1)

	def _verified_token(self):
		started = self._start()
		token = started["session_token"]
		fo.verify_otp(token, self._captured_otp())
		return token

	# ---------------------------------------------------------------- start

	def test_start_by_mfl_sends_otp_to_registered_contact_with_masked_preview(self):
		started = self._start()
		token = started["session_token"]
		self.assertTrue(token)
		# Masked owner card: first name + role + masked phone only, never full PII.
		self.assertEqual(started["owner"]["first_name"], "Jane")
		self.assertEqual(started["owner"]["role"], "Registered contact")
		self.assertNotIn(OWNER_EMAIL, str(started))
		self.assertNotIn(OWNER_PHONE, str(started))
		self.assertIn("****", started["owner"]["masked_phone"])
		# Facility resolved from our records, with the organization name for the account.
		self.assertEqual(started["facility"]["mfl_code"], "MFL-ADMIN-1")
		self.assertEqual(started["facility"]["facility_name"], "Admin Path Clinic")
		self.assertEqual(started["organization_name"], "Admin Path Clinic Ltd")
		# Best-known organization inbox: empty without a linked Lead (the contact's own
		# email is the OTP recipient and is never echoed back in clear text).
		self.assertEqual(started["suggested_account_email"], "")
		# Delivery went to the registered contact by the preferred channel (email).
		self.assertEqual(self.sent[0]["recipients"], [OWNER_EMAIL])
		self.assertEqual(started["delivery"]["status"], "sent")
		# Session is pre-bound to the facility so verify_otp needs no HFR lookup.
		session = self.store.get(token)
		self.assertTrue(session["admin_path"])
		self.assertEqual(session["hfr_state"], "ready")
		self.assertEqual(len(session["facilities"]), 1)
		self.assertEqual(session["person"]["email"], OWNER_EMAIL)

	def test_start_by_registration_number(self):
		started = self._start(reference="REG-ADMIN-1")
		self.assertEqual(started["facility"]["mfl_code"], "MFL-ADMIN-1")
		self.assertEqual(self.sent[0]["recipients"], [OWNER_EMAIL])

	def test_unknown_reference_is_rejected_with_generic_message(self):
		self.assertRaisesRegex(frappe.ValidationError, "couldn.t find a facility", lambda: fo.start_admin_onboarding("MFL-DOES-NOT-EXIST-XYZ"))
		self.assertEqual(self.sent, [])

	def test_malformed_reference_is_rejected_before_any_lookup(self):
		self.assertRaisesRegex(frappe.ValidationError, "couldn.t find a facility", lambda: fo.start_admin_onboarding("ab"))
		self.assertRaisesRegex(frappe.ValidationError, "couldn.t find a facility", lambda: fo.start_admin_onboarding("DROP TABLE; --"))

	def test_facility_without_registered_contact_is_rejected(self):
		self._make_facility(with_contact=False)
		self.assertRaisesRegex(frappe.ValidationError, "couldn.t find a facility", lambda: fo.start_admin_onboarding("MFL-ADMIN-1"))
		self.assertEqual(self.sent, [])

	def test_reload_within_resend_window_reuses_code_without_second_send(self):
		self._make_facility()
		first = fo.start_admin_onboarding("MFL-ADMIN-1")["data"]
		second = fo.start_admin_onboarding("MFL-ADMIN-1")["data"]
		# A fresh session token is issued, but the already-sent code moves with it.
		self.assertTrue(second["reused"])
		self.assertEqual(len(self.sent), 1)
		data = fo.verify_otp(second["session_token"], self._captured_otp())["data"]
		self.assertEqual(data["state"], "ready")

	# ---------------------------------------------------------------- verify

	def test_verify_otp_returns_bound_facility_without_hfr_lookup(self):
		hfr = Mock(side_effect=AssertionError("HFR must not be called on the admin path"))
		with patch.object(fo, "_hfr_facilities_for_owner", hfr):
			started = self._start()
			data = fo.verify_otp(started["session_token"], self._captured_otp())["data"]
		self.assertEqual(data["state"], "ready")
		self.assertEqual(data["facilities"][0]["facility_id"], "MFL-ADMIN-1")
		self.assertTrue(data["facilities"][0]["onboarding_eligible"])
		# The verified authority is the registered contact (masked in the preview).
		self.assertEqual(data["identity"]["full_name"], "Jane Owner")

	def test_wrong_tp_is_rejected_and_session_stays_unverified(self):
		started = self._start()
		token = started["session_token"]
		self.assertRaises(frappe.PermissionError, lambda: fo.verify_otp(token, "000000"))
		session = self.store.get(token)
		self.assertFalse(session["verified"])
		self.assertEqual(session["otp_attempts"], 1)

	def test_expired_or_wrong_channel_delivery_still_gated_by_otp(self):
		started = self._start()
		token = started["session_token"]
		session = self.store.get(token)
		session["otp_expires_at"] = 1
		self.store.save(token, session)
		self.assertRaises(frappe.PermissionError, lambda: fo.verify_otp(token, self._captured_otp()))

	# ------------------------------------------------------- corporate email

	def test_set_admin_account_email_binds_corporate_email(self):
		token = self._verified_token()
		data = fo.set_admin_account_email(token, " Billing@AdminPathClinic.Co.Ke ".upper()[:0] + ORG_EMAIL.upper())["data"]
		self.assertEqual(data["email"], ORG_EMAIL)
		session = self.store.get(token)
		self.assertEqual(session["account_email_override"], ORG_EMAIL)

	def test_set_admin_account_email_rejects_invalid_format(self):
		token = self._verified_token()
		self.assertRaises(frappe.ValidationError, lambda: fo.set_admin_account_email(token, "not-an-email"))

	def test_set_admin_account_email_rejects_system_users(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": "internal@tiberbu.example",
				"first_name": "Internal",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		# Frappe demotes new users without system roles to Website User; force the
		# system-user state directly so the guard branch is exercised.
		frappe.db.set_value("User", user.name, "user_type", "System User")
		token = self._verified_token()
		self.assertRaises(frappe.ValidationError, lambda: fo.set_admin_account_email(token, "internal@tiberbu.example"))

	def test_set_admin_account_email_requires_admin_session(self):
		token = "plain-owner-session-token"
		self.store.save(
			token,
			{
				"verified": True,
				"admin_path": False,
				"person": {"first_name": "A", "last_name": "B", "email": OWNER_EMAIL, "phone": OWNER_PHONE},
				"expires_at": 9999999999,
			},
		)
		self.assertRaises(frappe.PermissionError, lambda: fo.set_admin_account_email(token, ORG_EMAIL))

	def test_validate_account_email_admin_branch_accepts_confirmed_corporate_email(self):
		token = self._verified_token()
		fo.set_admin_account_email(token, ORG_EMAIL)
		session = self.store.get(token)
		self.assertEqual(fo._validate_account_email(ORG_EMAIL, session), ORG_EMAIL)

	def test_validate_account_email_admin_branch_rejects_unconfirmed_email(self):
		token = self._verified_token()
		fo.set_admin_account_email(token, ORG_EMAIL)
		session = self.store.get(token)
		self.assertRaises(frappe.ValidationError, lambda: fo._validate_account_email("someone.else@example.com", session))

	def test_validate_account_email_admin_branch_rejects_invalid_format(self):
		session = {"admin_path": True, "account_email_override": ""}
		self.assertRaises(frappe.ValidationError, lambda: fo._validate_account_email("nope", session))

	def test_owner_flow_validation_is_unchanged(self):
		# Regression guard: a non-admin session still requires the registry email.
		session = {
			"admin_path": False,
			"person": {"first_name": "Jane", "last_name": "Owner", "email": OWNER_EMAIL, "phone": OWNER_PHONE},
		}
		self.assertEqual(fo._validate_account_email(OWNER_EMAIL, session), OWNER_EMAIL)
		self.assertRaises(frappe.ValidationError, lambda: fo._validate_account_email(ORG_EMAIL, session))

	# ---------------------------------------------------------- lead fallback

	def test_registered_contact_falls_back_to_linked_lead(self):
		self._make_facility(with_contact=False)
		lead = frappe.get_doc(
			{
				"doctype": "CRM Lead",
				"first_name": "Sam",
				"last_name": "Leaderson",
				"email": "sam.lead@example.com",
				"mobile_no": "+254722000333",
			}
		)
		lead.flags.ignore_permissions = True
		lead.flags.ignore_links = True
		lead.insert(ignore_permissions=True, ignore_links=True)
		link = frappe.get_doc(
			{
				"doctype": "CRM Lead Facility",
				"parent": lead.name,
				"parenttype": "CRM Lead",
				"parentfield": "facilities",
				"mfl_code": "MFL-ADMIN-1",
			}
		)
		link.flags.ignore_permissions = True
		link.flags.ignore_links = True
		link.insert(ignore_permissions=True, ignore_links=True)

		started = fo.start_admin_onboarding("MFL-ADMIN-1")["data"]
		self.assertEqual(started["owner"]["first_name"], "Sam")
		self.assertEqual(self.sent[0]["recipients"], ["sam.lead@example.com"])
		# The Lead's email becomes the suggested corporate inbox.
		self.assertEqual(started["suggested_account_email"], "sam.lead@example.com")
