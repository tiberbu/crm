from contextlib import nullcontext
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api import facility_onboarding as fo

PERSON = {"first_name": "Amina", "last_name": "Otieno", "email": "amina@example.test", "phone": "+254700000001"}


class TestOnboardingSession(UnitTestCase):
	def tearDown(self):
		for key in getattr(self, "_keys", []):
			frappe.cache().delete_value(key)

	def _track(self, key):
		self._keys = [*getattr(self, "_keys", []), key]
		return key

	def test_a_request_reads_its_own_latest_session_save(self):
		# Frappe 15 does not refresh the request-local cache on set_value with an expiry;
		# verify_otp failed with "session expired" because of this stale read.
		token = "session-" + frappe.generate_hash(length=12)
		self._track(fo._session_key(token))
		fo._save_session(token, {"verified": False, "person": PERSON})
		self.assertFalse(fo._session(token)["verified"])

		fo._save_session(token, {**fo._session(token), "verified": True})

		self.assertTrue(fo._session_or_error(token, verified=True)["verified"])

	def _start(self, send_otp, now):
		with (
			patch.object(fo, "_rate_limited", return_value=False),
			patch.object(fo, "_client_registry_person", return_value=dict(PERSON)),
			patch.object(fo, "_send_otp", send_otp),
			patch.object(fo, "_evidence"),
			patch.object(fo, "filelock", side_effect=lambda *a, **k: nullcontext()),
			patch.object(fo.time, "time", return_value=now),
		):
			data = fo.start_identity("National ID", "12345678")["data"]
		self._track(fo._session_key(data["session_token"]))
		return data

	def test_restart_within_resend_window_reuses_the_code_without_sending(self):
		sent = []

		def send_otp(person, otp):
			sent.append(otp)
			return {"channel": "email", "masked_destination": "a***@example.test", "status": "sent"}

		identity_hash = fo.hashlib.sha256(b"national id|12345678").hexdigest()
		self._track(fo._identity_challenge_key(identity_hash))
		now = int(fo.time.time())
		first = self._start(send_otp, now)
		second = self._start(send_otp, now + 20)

		self.assertEqual(len(sent), 1)
		self.assertFalse(first["reused"])
		self.assertTrue(second["reused"])
		self.assertEqual(second["delivery"]["resend_after"], fo.OTP_RESEND_SECONDS - 20)
		self.assertIsNone(fo._session(first["session_token"]))
		self.assertEqual(fo._session(second["session_token"])["otp_hash"], fo._otp_hash(sent[0]))

		third = self._start(send_otp, now + 20 + fo.OTP_RESEND_SECONDS)
		self.assertEqual(len(sent), 2)
		self.assertFalse(third["reused"])

	def test_restart_after_verification_sends_a_new_code_and_keeps_the_verified_session(self):
		sent = []

		def send_otp(person, otp):
			sent.append(otp)
			return {"channel": "email", "masked_destination": "a***@example.test", "status": "sent"}

		identity_hash = fo.hashlib.sha256(b"national id|12345678").hexdigest()
		self._track(fo._identity_challenge_key(identity_hash))
		now = int(fo.time.time())
		first = self._start(send_otp, now)
		with (
			patch.object(fo, "_evidence"),
			patch.object(fo, "filelock", side_effect=lambda *a, **k: nullcontext()),
			patch.object(fo, "_resolve_verified_hfr", return_value={"success": True}),
		):
			fo.verify_otp(first["session_token"], sent[0])

		second = self._start(send_otp, now + 5)

		self.assertEqual(len(sent), 2)
		self.assertFalse(second["reused"])
		self.assertTrue(fo._session_or_error(first["session_token"], verified=True)["verified"])


class TestSubmitWithoutNetwork(UnitTestCase):
	def _submit(self, partner_id, public_network):
		with (
			patch.object(fo, "_session_or_error", return_value={"identity_ref": "ref", "hfr_state": "ready", "facilities": [{"facility_id": "FID-1"}]}),
			patch.object(fo, "_validate_self_onboarding_terms", return_value={"document": "Terms", "hash": "h"}),
			patch.object(fo, "_validate_account_email", return_value="amina@example.test"),
			patch.object(fo, "_public_network", return_value=public_network),
			patch.object(fo, "_packages_for_facilities", return_value={"FID-1": {"item_code": "TOK"}}),
			patch.object(fo, "filelock", side_effect=lambda *a, **k: nullcontext()),
			patch.object(fo, "_check_onboarding_conflicts", return_value={"outcome": "new"}) as conflicts,
			patch.object(fo, "_no_network", return_value={"name": fo.NO_NETWORK_SLUG}) as no_network,
			patch.object(fo, "_evidence") as evidence,
			patch.object(fo, "_submit_selected_facilities", return_value={"success": True}) as submit,
		):
			fo.submit_onboarding("token", partner_id, '["FID-1"]', "TOK", "amina@example.test", 1, "h")
		return conflicts, no_network, evidence, submit

	def test_blank_network_id_is_recorded_as_no_network(self):
		conflicts, no_network, evidence, submit = self._submit("", None)

		no_network.assert_called_once_with()
		self.assertEqual(submit.call_args.args[1], {"name": fo.NO_NETWORK_SLUG})
		self.assertEqual(conflicts.call_args.args[2], fo.NO_NETWORK_SLUG)
		self.assertIn("no Network ID provided", evidence.call_args.kwargs["detail"])

	def test_network_id_uses_that_network(self):
		_conflicts, no_network, _evidence, submit = self._submit("623161", {"name": "net-a"})

		no_network.assert_not_called()
		# A typed Partner ID is a Partner Coupon: the facility earns coupon tokens.
		self.assertEqual(submit.call_args.args[1], {"name": "net-a", "partner_coupon": True})

	def test_unknown_network_id_is_still_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._submit("999999", None)

	def test_no_network_record_is_disabled_so_the_public_lookup_cannot_select_it(self):
		created = not frappe.db.exists("CRM Opt-In Network", fo.NO_NETWORK_SLUG)
		try:
			network = fo._no_network()
			self.assertEqual(network.name, fo.NO_NETWORK_SLUG)
			self.assertEqual(network.display_name, "No Network")
			partner_id = frappe.db.get_value("CRM Opt-In Network", fo.NO_NETWORK_SLUG, "partner_id")
			self.assertEqual(frappe.db.get_value("CRM Opt-In Network", fo.NO_NETWORK_SLUG, "enabled"), 0)
			self.assertIsNone(fo._public_network(partner_id))
		finally:
			if created:
				frappe.db.rollback()


class TestConflictCheckWithoutNetwork(UnitTestCase):
	def _check(self, partner_id, public_network):
		with (
			patch.object(fo, "_session_or_error", return_value={"facilities": [{"facility_id": "FID-1"}]}),
			patch.object(fo, "_public_network", return_value=public_network),
			patch.object(fo, "_check_onboarding_conflicts", return_value={"outcome": "new"}) as conflicts,
			patch.object(fo, "_evidence"),
		):
			result = fo.check_onboarding_conflicts("token", '["FID-1"]', partner_id)
		return result, conflicts

	def test_blank_network_id_is_checked_against_no_network(self):
		# The pre-submit check rejected a blank Network ID with "The configured default
		# Network ID is not available", so the Network-optional submit never ran.
		result, conflicts = self._check("", None)

		self.assertEqual(result["outcome"], "new")
		self.assertEqual(conflicts.call_args.args[2], fo.NO_NETWORK_SLUG)

	def test_network_id_is_checked_against_that_network(self):
		_result, conflicts = self._check("623161", {"name": "net-a"})

		self.assertEqual(conflicts.call_args.args[2], "net-a")

	def test_unknown_network_id_is_still_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._check("999999", None)
