import copy
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import ClassVar
from unittest.mock import Mock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase, UnitTestCase

from crm.api import facility_onboarding as fo
from crm.api.facility_onboarding import _onboarding_config, _session_key
from crm.fcrm.doctype.crm_onboarding_evidence.crm_onboarding_evidence import evidence_ref
from crm.patches.v1_0 import seed_self_onboarding_facility_level_whitelist as whitelist_patch


class TestFacilityOnboardingLevelWhitelistPatch(UnitTestCase):
	def test_patch_adds_required_levels_once_and_preserves_existing_configuration(self):
		class Settings:
			def __init__(self):
				self.allowed_levels = "Level 3\nCustom Level\nlevel 3b\nLevel 3"

			def get(self, fieldname):
				return self.allowed_levels if fieldname == whitelist_patch.SETTING_FIELD else None

			def set(self, fieldname, value):
				if fieldname == whitelist_patch.SETTING_FIELD:
					self.allowed_levels = value

			def save(self, **kwargs):
				return None

		settings = Settings()
		with (
			patch.object(whitelist_patch.frappe.db, "exists", return_value=True),
			patch.object(whitelist_patch.frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(whitelist_patch.frappe, "get_single", return_value=settings),
			patch.object(whitelist_patch.frappe, "clear_cache"),
		):
			whitelist_patch.execute()
			first_result = settings.allowed_levels
			whitelist_patch.execute()

		self.assertEqual(
			first_result.splitlines(),
			["Level 3", "Custom Level", "Level 3B", "Level 2", "Level 3C"],
		)
		self.assertEqual(settings.allowed_levels, first_result)

	def test_patch_seeds_levels_when_setting_is_blank(self):
		class Settings:
			allowed_levels = ""

			def get(self, fieldname):
				return self.allowed_levels if fieldname == whitelist_patch.SETTING_FIELD else None

			def set(self, fieldname, value):
				if fieldname == whitelist_patch.SETTING_FIELD:
					self.allowed_levels = value

			save = Mock()

		settings = Settings()
		with (
			patch.object(whitelist_patch.frappe.db, "exists", return_value=True),
			patch.object(whitelist_patch.frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(whitelist_patch.frappe, "get_single", return_value=settings),
			patch.object(whitelist_patch.frappe, "clear_cache"),
		):
			whitelist_patch.execute()

		self.assertEqual(settings.allowed_levels.splitlines(), ["Level 2", "Level 3B", "Level 3C"])
		settings.save.assert_called_once_with(ignore_permissions=True)

	def test_patch_fails_if_settings_field_is_missing(self):
		with (
			patch.object(whitelist_patch.frappe.db, "exists", return_value=True),
			patch.object(whitelist_patch.frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=False))),
			patch.object(whitelist_patch.frappe, "throw", side_effect=RuntimeError("missing field")) as throw,
		):
			with self.assertRaisesRegex(RuntimeError, "missing field"):
				whitelist_patch.execute()

		throw.assert_called_once()

	def test_patch_is_registered_after_model_sync(self):
		with open(frappe.get_app_path("crm", "patches.txt")) as handle:
			lines = [line.strip() for line in handle]
		patch_name = "crm.patches.v1_0.seed_self_onboarding_facility_level_whitelist"
		self.assertIn(patch_name, lines)
		self.assertGreater(lines.index(patch_name), lines.index("[post_model_sync]"))


class TestFacilityOnboardingRegistryConfig(UnitTestCase):
	def test_blank_referring_network_id_resolves_the_configured_default(self):
		network = {"name": "network-a", "partner_id": "654321"}
		with (
			patch.object(fo, "_setting", return_value="654321"),
			patch.object(fo.frappe, "get_list", return_value=[network]) as get_networks,
		):
			self.assertEqual(fo._public_network(""), network)

		self.assertEqual(get_networks.call_args.kwargs["filters"], {"partner_id": "654321", "enabled": 1})

	def test_facility_membership_links_existing_network_and_verified_contact(self):
		facility_doc = Mock()
		facility_doc.memberships = []
		facility = {
			"mfl_code": "10001",
			"facility_name": "Alpha Clinic",
			"classification": "Level 2",
		}
		with (
			patch.object(fo.frappe.db, "get_value", return_value=None),
			patch.object(fo.frappe, "get_doc", return_value=facility_doc),
			patch.object(fo.frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
		):
			fo._upsert_facility_membership(facility, "network-a", PERSON, customer="customer-a")

		self.assertEqual(
			facility_doc.append.call_args.args,
			(
				"memberships",
				{
					"network": "network-a",
					"customer": "customer-a",
					"status": "Active",
					"contact_name": "Amina Otieno",
					"contact_email": "owner@example.com",
					"contact_phone": "254712345678",
				},
			),
		)

	def test_identity_reference_uses_normalized_identity_with_the_keyed_helper(self):
		with patch.object(fo, "evidence_ref", side_effect=lambda value: "keyed:" + value) as keyed:
			first = fo._identity_reference("National ID", "AbC 123")
			second = fo._identity_reference("national_id", "aBc 123")

		self.assertEqual(first, "keyed:nationalid|abc 123")
		self.assertEqual(second, first)
		self.assertEqual(keyed.call_count, 2)

	def test_session_cache_key_is_keyed_and_does_not_expose_token(self):
		with patch("crm.api.facility_onboarding._password_setting", return_value="test-secret"):
			key = _session_key("opaque-session-token")

		self.assertTrue(key.startswith("crm_facility_onboarding:"))
		self.assertNotIn("opaque-session-token", key)

	def test_identity_number_is_encrypted_in_cached_session(self):
		cache = Mock()
		with patch.object(fo.frappe, "cache", return_value=cache):
			fo._save_session("opaque-session-token", {"identity_number": ID_NUMBER})
			stored = cache.set_value.call_args.args[1]
			self.assertNotIn(ID_NUMBER, stored)
			cache.get_value.return_value = stored
			session = fo._session("opaque-session-token")

		self.assertEqual(session["identity_number"], ID_NUMBER)

	def test_onboarding_reuses_crm_hfr_credentials(self):
		hfr = Mock(
			hfr_enabled=1,
			hfr_url="https://registry.example.test",
			hfr_username="canonical-user",
			hfr_jwt_expiry=3600,
		)
		hfr.get_password.return_value = "canonical-password"
		optin = {
			"facility_onboarding_hie_url": "https://legacy.example.test",
			"facility_onboarding_hie_username": "legacy-user",
			"facility_onboarding_hfr_owner_path": "/owner-facilities",
			"facility_onboarding_hfr_facility_path": "/facility",
			"facility_onboarding_client_registry_path": "/client",
		}

		def get_single(doctype):
			return hfr if doctype == "CRM HFR Settings" else optin

		with patch("crm.api.facility_onboarding.frappe.get_single", side_effect=get_single):
			config = _onboarding_config()

		self.assertEqual(config["base_url"], "https://registry.example.test")
		self.assertEqual(config["username"], "canonical-user")
		self.assertEqual(config["password"], "canonical-password")
		self.assertEqual(config["jwt_expiry"], 3600)
		self.assertEqual(config["owner_path"], "/owner-facilities")
		self.assertEqual(config["client_path"], "/client")

	def test_client_registry_selects_the_unique_exact_id_and_type_match(self):
		person = {
			"identification_number": ID_NUMBER,
			"identification_type": "National ID",
			"email": "owner@example.com",
		}
		response = {
			"message": {
				"total": 2,
				"result": [
					{"identification_number": "87654321", "identification_type": "National ID"},
					person,
				],
			}
		}
		with (
			patch.object(fo, "_onboarding_config", return_value={"client_path": "/client"}),
			patch.object(fo, "_request", return_value=response),
		):
			self.assertEqual(fo._client_registry_person("national_id", ID_NUMBER), person)

	def test_client_registry_rejects_ambiguous_exact_rows(self):
		person = {"identification_number": ID_NUMBER, "identification_type": "National ID"}
		response = {"message": {"total": 2, "result": [person, dict(person)]}}
		with (
			patch.object(fo, "_onboarding_config", return_value={"client_path": "/client"}),
			patch.object(fo, "_request", return_value=response),
		):
			self.assertIsNone(fo._client_registry_person("national_id", ID_NUMBER))

	def test_client_registry_rejects_matching_number_with_wrong_id_type(self):
		response = {
			"message": {
				"total": 1,
				"result": [{"identification_number": ID_NUMBER, "identification_type": "Passport"}],
			}
		}
		with (
			patch.object(fo, "_onboarding_config", return_value={"client_path": "/client"}),
			patch.object(fo, "_request", return_value=response),
		):
			self.assertIsNone(fo._client_registry_person("national_id", ID_NUMBER))

	def test_hfr_no_facilities_response_normalizes_to_empty_list(self):
		response = {
			"message": {
				"data": None,
				"message": "No facilities found for this owner",
				"status": "error",
			}
		}
		with (
			patch.object(fo, "_onboarding_config", return_value={"owner_path": "/owners"}),
			patch.object(fo, "_request", return_value=response) as request,
		):
			self.assertEqual(fo._hfr_facilities_for_owner(ID_NUMBER), [])
		request.assert_called_once_with(
			{"owner_path": "/owners"},
			"/owners",
			{"owner_id_number": ID_NUMBER},
			allow_no_facilities=True,
		)

	def test_hfr_explicit_empty_facility_list_is_valid(self):
		for response in (
			{"message": {"data": {"facilities": []}}},
			{"message": {"facilities": []}},
			{"data": {"facilities": []}},
			{"facilities": []},
		):
			with (
				patch.object(fo, "_onboarding_config", return_value={"owner_path": "/owners"}),
				patch.object(fo, "_request", return_value=response),
			):
				self.assertEqual(fo._hfr_facilities_for_owner(ID_NUMBER), [])

	def test_hfr_unrecognized_or_malformed_response_is_retryable_error(self):
		for response in (
			{"message": {"data": None, "status": "success"}},
			{"message": {"data": {"facilities": {"unexpected": True}}}},
			{"facilities": ["not-a-facility-row"]},
		):
			with (
				patch.object(fo, "_onboarding_config", return_value={"owner_path": "/owners"}),
				patch.object(fo, "_request", return_value=response),
			):
				with self.assertRaises(frappe.ValidationError):
					fo._hfr_facilities_for_owner(ID_NUMBER)


ID_NUMBER = "12345678"
PERSON = {
	"first_name": "Amina",
	"last_name": "Otieno",
	"email": "owner@example.com",
	"phone": "254712345678",
}
FACILITIES = [
	{
		"facility_id": "FID-1",
		"facility_code": "10001",
		"facility_name": "Alpha Clinic",
		"facility_level": "Level 3",
	}
]


def _named(name):
	mock = Mock()
	mock.name = name
	return mock


class _Store:
	def __init__(self):
		self.data = {}

	def save(self, token, payload):
		self.data[token] = copy.deepcopy(payload)

	def get(self, token):
		return copy.deepcopy(self.data.get(token))


class TestFacilityOnboardingOtpFlow(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("facility_onboarding_test")
		self.addCleanup(frappe.db.rollback, save_point="facility_onboarding_test")
		self.store = _Store()
		self.sent = []
		self.sms = []
		self.channel_setting = "Email"
		self.allowed_facility_levels = "Level 3"
		self.gateway = True
		self.email_fails = False
		self.hfr = Mock(return_value=FACILITIES)
		self.registry = Mock(return_value=dict(PERSON))
		self.calls = Mock()
		self.calls.attach_mock(self.hfr, "hfr")
		self.calls.attach_mock(self.registry, "registry")
		self.log_error = Mock()

		def sendmail(**kwargs):
			if self.email_fails:
				raise RuntimeError("smtp down for " + kwargs["recipients"][0])
			self.sent.append(kwargs)
			return Mock()

		patches = [
			patch.object(fo, "_hfr_facilities_for_owner", self.hfr),
			patch.object(fo, "_client_registry_person", self.registry),
			patch.object(fo, "_session", side_effect=lambda token: self.store.get(token)),
			patch.object(fo, "_save_session", side_effect=self.store.save),
			patch.object(fo, "_rate_limited", return_value=False),
			patch.object(fo, "_password_setting", return_value="test-secret"),
			patch.object(
				fo,
				"_setting",
				side_effect=lambda name, default="": (
					self.channel_setting
					if name == "facility_onboarding_preferred_otp_channel"
					else self.allowed_facility_levels
					if name == "self_onboarding_allowed_facility_levels"
					else default
				),
			),
			patch.object(fo.frappe, "sendmail", side_effect=sendmail),
			patch.object(fo, "schedule_email_queue_redaction"),
			patch.object(fo.frappe, "log_error", self.log_error),
			patch.object(fo.frappe.db, "commit"),
			patch("crm.api.optin._sms_gateway_configured", side_effect=lambda: self.gateway),
			patch("crm.api.optin._send_otp_sms", side_effect=lambda *args: self.sms.append(args)),
		]
		for item in patches:
			item.start()
			self.addCleanup(item.stop)

	def _start(self, number=ID_NUMBER):
		return fo.start_identity("national_id", number)["data"]

	def _captured_otp(self):
		if self.sent:
			return re.search(r">(\d{6})</span>", self.sent[-1]["message"]).group(1)
		return re.search(r"\b(\d{6})\b", self.sms[-1][1]).group(1)

	def test_cr_lookup_and_otp_precede_hfr_ownership_lookup(self):
		started = self._start()
		token = started["session_token"]
		self.assertNotIn(PERSON["email"], str(started))
		self.assertEqual([c[0] for c in self.calls.mock_calls], ["registry"])
		self.assertEqual(self.sent[0]["recipients"], [PERSON["email"]])
		data = fo.verify_otp(token, self._captured_otp())["data"]
		self.assertEqual(data["account_email"], PERSON["email"])
		self.assertEqual(data["facilities"][0]["facility_id"], "FID-1")
		self.assertEqual([c[0] for c in self.calls.mock_calls], ["registry", "hfr"])
		self.hfr.assert_called_once_with(ID_NUMBER)

	def test_hfr_facilities_keep_category_separate_and_refresh_eligibility(self):
		self.hfr.return_value = [
			{**FACILITIES[0], "facility_level": " Level 3 ", "category": "Clinic"},
			{"facility_id": "FID-2", "facility_name": "No level", "category": "Level 3"},
		]
		token = self._start()["session_token"]
		data = fo.verify_otp(token, self._captured_otp())["data"]

		self.assertEqual(data["facilities"][0]["facility_level"], "Level 3")
		self.assertEqual(data["facilities"][0]["facility_category"], "Clinic")
		self.assertTrue(data["facilities"][0]["onboarding_eligible"])
		self.assertFalse(data["facilities"][1]["onboarding_eligible"])
		self.assertEqual(data["facilities"][1]["facility_eligibility_reason"], "missing_level")

		self.allowed_facility_levels = "Level 30"
		refreshed = fo.retry_hfr(token)["data"]["facilities"]
		self.assertFalse(refreshed[0]["onboarding_eligible"])
		self.assertEqual(refreshed[0]["facility_eligibility_reason"], "level_not_allowed")

	def test_facility_level_whitelist_uses_trimmed_case_insensitive_exact_matches(self):
		facility = fo._facility_row({**FACILITIES[0], "facility_level": "  LEVEL 3  "})

		self.assertTrue(fo._facility_level_eligibility(facility, {"level 3"})["onboarding_eligible"])
		self.assertFalse(fo._facility_level_eligibility(facility, {"level 30"})["onboarding_eligible"])
		self.assertFalse(fo._facility_level_eligibility(facility, set())["onboarding_eligible"])
		category_only = fo._facility_row({"facility_id": "FID-CATEGORY", "category": "Level 3"})
		self.assertFalse(category_only["facility_level"])
		self.assertFalse(fo._facility_level_eligibility(category_only, {"level 3"})["onboarding_eligible"])
		fallback_level = fo._facility_row(
			{**FACILITIES[0], "facility_level": "  ", "kephl_level": " Level 3 "}
		)
		self.assertEqual(fallback_level["facility_level"], "Level 3")
		self.assertTrue(
			fo._facility_level_eligibility(fallback_level, {"level 3"})["onboarding_eligible"]
		)
		primary_level = fo._facility_row(
			{**FACILITIES[0], "facility_level": "Level 4", "kephl_level": "Level 3"}
		)
		self.assertEqual(primary_level["facility_level"], "Level 4")

	def test_hfr_no_facilities_is_resolved_only_after_otp(self):
		self.hfr.return_value = []
		data = self._start()
		self.registry.assert_called_once_with("national_id", ID_NUMBER)
		self.assertEqual(len(self.sent), 1)
		self.assertEqual(data["delivery"]["status"], "sent")
		self.assertEqual(fo.verify_otp(data["session_token"], self._captured_otp())["data"]["facilities"], [])
		self.hfr.assert_called_once_with(ID_NUMBER)

	def test_hfr_is_not_checked_when_client_registry_has_no_exact_match(self):
		self.registry.return_value = None
		data = self._start()
		self.hfr.assert_not_called()
		self.assertEqual(self.sent, [])
		self.assertIn("CR/Afyangu: no exact match", self._evidence_rows(data["session_token"])[0].detail)

	def test_hfr_failure_after_otp_is_recoverable_without_a_second_otp(self):
		self.hfr.side_effect = RuntimeError("HFR unavailable")
		token = self._start()["session_token"]
		self.registry.assert_called_once_with("national_id", ID_NUMBER)
		self.hfr.assert_not_called()
		result = fo.verify_otp(token, self._captured_otp())["data"]
		self.assertEqual(result, {"state": "hfr_pending", "retryable": True})
		with self.assertRaises(frappe.PermissionError):
			fo.verify_otp(token, self._captured_otp())
		self.assertEqual(len(self.sent), 1)
		self.hfr.side_effect = None
		result = fo.retry_hfr(token)["data"]
		self.assertEqual(result["facilities"][0]["facility_id"], "FID-1")
		self.assertEqual(len(self.sent), 1)
		self.assertEqual(self._events(token).count(("otp_verified", "ok")), 1)
		self.assertEqual(self._events(token).count(("lookup", "failed")), 1)
		self.assertEqual(self._events(token).count(("lookup", "ok")), 2)

	def test_hfr_retry_requires_verified_session_and_has_a_lookup_limit(self):
		token = self._start()["session_token"]
		with self.assertRaises(frappe.PermissionError):
			fo.retry_hfr(token)
		self.hfr.side_effect = RuntimeError("HFR unavailable")
		first = fo.verify_otp(token, self._captured_otp())["data"]
		self.assertTrue(first["retryable"])
		for _ in range(fo.HFR_MAX_LOOKUPS - 1):
			result = fo.retry_hfr(token)["data"]
		self.assertEqual(result, {"state": "hfr_pending", "retryable": False})
		self.assertEqual(self.hfr.call_count, fo.HFR_MAX_LOOKUPS)

	def test_concurrent_hfr_retries_share_one_session_lookup(self):
		self.hfr.side_effect = RuntimeError("HFR unavailable")
		token = self._start()["session_token"]
		fo.verify_otp(token, self._captured_otp())
		self.log_error.reset_mock()

		self.hfr.reset_mock()

		def slow_lookup(number):
			time.sleep(0.1)
			return FACILITIES

		self.hfr.side_effect = slow_lookup
		locks = {}
		locks_guard = threading.Lock()

		@contextmanager
		def synchronized(lock_name, timeout=30):
			with locks_guard:
				lock = locks.setdefault(lock_name, threading.Lock())
			if not lock.acquire(timeout=timeout):
				raise TimeoutError("test file lock timed out")
			try:
				yield
			finally:
				lock.release()

		with patch.object(fo, "filelock", synchronized), patch.object(fo, "_evidence"):
			with ThreadPoolExecutor(max_workers=2) as pool:
				first = pool.submit(fo.retry_hfr, token)
				second = pool.submit(fo.retry_hfr, token)
				first_result = first.result(timeout=5)["data"]
				second_result = second.result(timeout=5)["data"]

		self.assertFalse(self.log_error.call_args_list, repr(self.log_error.call_args_list))
		self.assertEqual(first_result["state"], "ready")
		self.assertEqual(second_result["state"], "ready")
		self.hfr.assert_called_once_with(ID_NUMBER)

	def test_client_registry_failure_does_not_call_hfr_or_send_otp(self):
		self.registry.side_effect = RuntimeError("CR unavailable")
		data = self._start()
		self.hfr.assert_not_called()
		self.assertEqual(self.sent, [])
		self.assertIn("CR/Afyangu: lookup failed", self._evidence_rows(data["session_token"])[0].detail)

	def test_client_registry_without_a_deliverable_contact_fails_its_gate(self):
		self.registry.return_value = {**PERSON, "email": "", "phone": ""}
		data = self._start()
		self.assertEqual(self.sent, [])
		self.assertIn("CR/Afyangu: no usable contact", self._evidence_rows(data["session_token"])[0].detail)

	def test_both_failed_gates_are_recorded_without_public_disclosure(self):
		valid = self._start()
		self.registry.return_value = None
		failed = self._start("87654321")
		self.assertEqual(set(failed), set(valid))
		self.assertEqual(set(failed["delivery"]), set(valid["delivery"]))
		self.assertEqual(len(self.sent), 1)
		self.assertNotIn("CR/Afyangu", json.dumps(failed))
		self.assertNotIn("facilities", json.dumps(failed))
		rows = self._evidence_rows(failed["session_token"])
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].detail, "CR/Afyangu: no exact match")

	def test_email_is_the_default_channel(self):
		delivery = self._start()["delivery"]
		self.assertEqual(delivery["channel"], "email")
		self.assertEqual(delivery["masked_destination"], "o***@example.com")
		self.assertNotIn("owner@example.com", delivery["masked_destination"])
		self.assertEqual(delivery["status"], "sent")
		self.assertEqual(len(self.sent), 1)
		self.assertEqual(self.sms, [])

	def test_email_uses_careverse_transactional_layout_and_unique_safe_subject(self):
		self._start()
		message = self.sent[0]["message"]
		subject = self.sent[0]["subject"]

		self.assertIn("CareverseHIMS", message)
		self.assertIn('role="presentation"', message)
		self.assertIn("Your CareverseHIMS verification code", message)
		self.assertIn("One-time passcode", message)
		self.assertIn("This code expires in 10 minutes", message)
		self.assertIn("Never share it", message)
		self.assertIn("One-time passcode", message)
		self.assertIn("max-width:560px", message)
		self.assertIn("align=\"left\"", message)
		self.assertIn("font-family:InterVar,Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif", message)
		self.assertIn("background:#f5f7fa", message)
		self.assertIn("background:#bc1823", message)
		self.assertNotIn("max-width:480px", message)
		self.assertRegex(subject, r"CareverseHIMS.*\b\d{6}\b.*OTP ID [A-F0-9]{12}")
		self.assertIn(self._captured_otp(), subject)

	def test_sms_is_used_when_preferred(self):
		self.channel_setting = "SMS"
		delivery = self._start()["delivery"]
		self.assertEqual(delivery["channel"], "sms")
		self.assertEqual(delivery["masked_destination"], "254******78")
		self.assertNotIn("254712345678", delivery["masked_destination"])
		self.assertEqual(len(self.sms), 1)
		self.assertEqual(self.sent, [])

	def test_email_failure_falls_back_to_sms(self):
		self.email_fails = True
		started = self._start()
		delivery = started["delivery"]
		self.assertEqual(delivery["channel"], "sms")
		self.assertEqual(delivery["masked_destination"], "254******78")
		self.assertEqual(self.store.get(started["session_token"])["delivery"]["channel"], "sms")
		self.assertEqual(delivery["status"], "sent")

	def test_missing_sms_gateway_falls_back_to_email(self):
		self.channel_setting = "SMS"
		self.gateway = False
		started = self._start()
		self.assertEqual(started["delivery"]["channel"], "email")
		self.assertEqual(self.store.get(started["session_token"])["delivery"]["channel"], "email")

	def test_phone_only_contact_uses_sms(self):
		self.registry.return_value = {**PERSON, "email": ""}
		started = self._start()
		self.assertEqual(started["delivery"]["channel"], "sms")
		self.assertEqual(started["delivery"]["masked_destination"], "254******78")
		self.assertEqual(self.store.get(started["session_token"])["delivery"]["channel"], "sms")

	def test_no_deliverable_channel_is_reported_without_leaking_contacts(self):
		self.email_fails = True
		self.gateway = False
		started = self._start()
		delivery = started["delivery"]
		self.assertEqual(delivery["status"], "unavailable")
		self.assertEqual(delivery["channel"], "email")
		self.assertRegex(delivery["masked_destination"], r"^[a-z]\*\*\*@[a-z.]+$")
		self.assertNotIn("owner@example.com", repr(self.log_error.call_args_list))
		unknown = self._start("87654321")["delivery"]
		for field in ("channel", "status", "resend_after"):
			self.assertEqual(delivery[field], unknown[field])
		self.assertRegex(unknown["masked_destination"], r"^[a-z]\*\*\*@[a-z.]+$")
		token = started["session_token"]
		self.email_fails = False
		self.assertEqual(fo.resend_otp(token)["data"]["delivery"]["status"], "sent")

	def test_unknown_id_returns_same_shape_with_stable_decoy(self):
		real = self._start()
		self.registry.return_value = None
		first = self._start("99999999")
		second = self._start("99999999")
		self.assertEqual(set(first), set(real))
		self.assertEqual(set(first["delivery"]), set(real["delivery"]))
		self.assertEqual(first["delivery"]["channel"], "email")
		self.assertEqual(first["delivery"]["status"], "unavailable")
		self.assertRegex(first["delivery"]["masked_destination"], r"^[a-z]\*\*\*@[a-z.]+$")
		self.assertEqual(first["delivery"]["masked_destination"], second["delivery"]["masked_destination"])
		self.assertEqual(first["delivery"]["channel"], real["delivery"]["channel"])
		self.assertEqual(real["delivery"]["status"], "sent")
		self.assertEqual(real["delivery"]["masked_destination"], "o***@example.com")

	def test_nothing_sensitive_is_disclosed_before_verification(self):
		data = self._start()
		body = json.dumps(data)
		otp = self._captured_otp()
		for secret in ("owner@example.com", "254712345678", "Alpha Clinic", "Amina", "FID-1", "10001", otp):
			self.assertNotIn(secret, body)
		self.assertNotIn("identity", data)
		self.assertNotIn("facilities", self.store.data[data["session_token"]])
		self.assertNotIn("Alpha Clinic", json.dumps(self._evidence_rows(data["session_token"]), default=str))

	def test_verified_otp_releases_facilities_and_replay_fails(self):
		token = self._start()["session_token"]
		otp = self._captured_otp()
		data = fo.verify_otp(token, otp)["data"]
		self.assertEqual(data["facilities"][0]["facility_id"], "FID-1")
		with self.assertRaises(frappe.PermissionError):
			fo.resend_otp(token)
		self.assertEqual(len(self.sent), 1)
		with self.assertRaises(frappe.PermissionError):
			fo.verify_otp(token, otp)

	def test_concurrent_resend_cannot_overwrite_verified_session(self):
		token = self._start()["session_token"]
		otp = self._captured_otp()
		hfr_started = threading.Event()
		release_hfr = threading.Event()

		def slow_hfr(_identity):
			hfr_started.set()
			self.assertTrue(release_hfr.wait(timeout=5))
			return FACILITIES

		self.hfr.side_effect = slow_hfr
		locks = {}
		locks_guard = threading.Lock()

		@contextmanager
		def synchronized(lock_name, timeout=30):
			with locks_guard:
				lock = locks.setdefault(lock_name, threading.Lock())
			if not lock.acquire(timeout=timeout):
				raise TimeoutError("test file lock timed out")
			try:
				yield
			finally:
				lock.release()

		def throw(_message, exception):
			raise exception

		with (
			patch.object(fo, "filelock", synchronized),
			patch.object(fo, "_client_ip", return_value="127.0.0.1"),
			patch.object(fo, "_evidence"),
			patch.object(fo.frappe, "throw", side_effect=throw),
			ThreadPoolExecutor(max_workers=2) as pool,
		):
			verification = pool.submit(fo.verify_otp, token, otp)
			if not hfr_started.wait(timeout=5):
				verification.result(timeout=1)
			resend = pool.submit(fo.resend_otp, token)
			release_hfr.set()
			self.assertEqual(verification.result(timeout=5)["data"]["state"], "ready")
			with self.assertRaises(frappe.PermissionError):
				resend.result(timeout=5)
		self.assertTrue(self.store.get(token)["verified"])
		self.assertEqual(len(self.sent), 1)

	def test_unknown_id_can_never_verify(self):
		self.registry.return_value = None
		token = self._start("99999999")["session_token"]
		for code in ("000000", "123456"):
			with self.assertRaises(frappe.PermissionError):
				fo.verify_otp(token, code)

	def test_attempt_limit_blocks_the_correct_code(self):
		token = self._start()["session_token"]
		otp = self._captured_otp()
		wrong = "000000" if otp != "000000" else "111111"
		for _ in range(fo.OTP_MAX_ATTEMPTS):
			with self.assertRaises(frappe.PermissionError):
				fo.verify_otp(token, wrong)
		with self.assertRaises(frappe.PermissionError):
			fo.verify_otp(token, otp)

	def test_expired_code_is_rejected(self):
		token = self._start()["session_token"]
		otp = self._captured_otp()
		self.store.data[token]["otp_expires_at"] = 1
		with self.assertRaises(frappe.PermissionError):
			fo.verify_otp(token, otp)

	def test_resend_has_cooldown_and_a_hard_limit(self):
		token = self._start()["session_token"]
		cooling = fo.resend_otp(token)["data"]
		self.assertEqual(len(self.sent), 1)
		self.assertGreaterEqual(cooling["delivery"]["resend_after"], 1)
		self.assertLessEqual(cooling["delivery"]["resend_after"], fo.OTP_RESEND_SECONDS)
		self.assertEqual(self.store.data[token]["resend_count"], 0)
		for _ in range(fo.OTP_MAX_RESENDS):
			self.store.data[token]["otp_sent_at"] = 1
			self.assertEqual(fo.resend_otp(token)["data"]["delivery"]["channel"], "email")
		self.store.data[token]["otp_sent_at"] = 1
		with self.assertRaises(frappe.ValidationError):
			fo.resend_otp(token)

	def test_resend_for_unknown_id_sends_nothing(self):
		self.registry.return_value = None
		token = self._start("99999999")["session_token"]
		self.store.data[token]["otp_sent_at"] = 1
		self.assertEqual(fo.resend_otp(token)["data"]["delivery"]["status"], "unavailable")
		self.assertEqual(self.sent, [])

	def _evidence_rows(self, token):
		return frappe.get_all(
			"CRM Onboarding Evidence",
			filters={"session_ref": evidence_ref(token)},
			fields="*",
			order_by="creation asc, name asc",
		)

	def _events(self, token):
		return sorted((row.event, row.outcome) for row in self._evidence_rows(token))

	def test_evidence_is_written_for_lookup_delivery_failure_and_verification(self):
		token = self._start()["session_token"]
		with self.assertRaises(frappe.PermissionError):
			fo.verify_otp(token, "000000" if self._captured_otp() != "000000" else "111111")
		fo.verify_otp(token, self._captured_otp())
		self.assertEqual(
			self._events(token),
			sorted(
				[
					("lookup", "ok"),
					("lookup", "ok"),
					("otp_sent", "ok"),
					("otp_failed", "failed"),
					("otp_verified", "ok"),
				]
			),
		)
		self.assertEqual(
			{row.subject_ref for row in self._evidence_rows(token)}, {evidence_ref(self._subject(token))}
		)

	def _subject(self, token):
		return self.store.data[token]["identity_hash"]

	def test_unknown_id_records_a_failed_lookup_and_no_delivery(self):
		self.registry.return_value = None
		token = self._start("99999999")["session_token"]
		self.assertEqual(self._events(token), [("lookup", "failed")])

	def test_delivery_failure_and_resend_are_recorded(self):
		self.email_fails = True
		self.gateway = False
		token = self._start()["session_token"]
		self.assertIn(("otp_sent", "failed"), self._events(token))
		fo.resend_otp(token)
		self.assertEqual(self._events(token).count(("otp_sent", "failed")), 2)

	def test_attempt_limit_is_recorded_as_blocked_and_bounded(self):
		token = self._start()["session_token"]
		for _ in range(fo.OTP_MAX_ATTEMPTS + 3):
			with self.assertRaises(frappe.PermissionError):
				fo.verify_otp(token, "000000")
		events = self._events(token)
		self.assertEqual(events.count(("otp_failed", "failed")), fo.OTP_MAX_ATTEMPTS)
		self.assertEqual(events.count(("otp_failed", "blocked")), 1)

	def test_failure_evidence_is_committed_before_the_error_response(self):
		token = self._start()["session_token"]
		fo.frappe.db.commit.reset_mock()
		with self.assertRaises(frappe.PermissionError):
			fo.verify_otp(token, "000000")
		fo.frappe.db.commit.assert_called_once()

	def test_no_evidence_row_contains_identity_contacts_code_or_token(self):
		token = self._start()["session_token"]
		otp = self._captured_otp()
		with self.assertRaises(frappe.PermissionError):
			fo.verify_otp(token, "000000" if otp != "000000" else "111111")
		fo.verify_otp(token, otp)
		dump = json.dumps(self._evidence_rows(token), default=str)
		for secret in (ID_NUMBER, "owner@example.com", "254712345678", "Amina", "Alpha Clinic", otp, token):
			self.assertNotIn(secret, dump)

	def test_evidence_failure_does_not_block_onboarding(self):
		with patch.object(fo, "record_event", side_effect=RuntimeError("db down")):
			data = self._start()
		self.assertEqual(data["delivery"]["status"], "sent")
		self.assertTrue(self.log_error.called)

	PACKAGE: ClassVar[dict] = {
		"item_code": "TOK-1",
		"display_name": "Starter",
		"description": "",
		"token_quantity": 10,
		"price": 1000.0,
		"price_list": "PL",
	}

	def _submit_env(self):
		"""Fake the OIS store and processing so submit_onboarding runs without real CRM records."""
		self._terms_environment(
			"Self-Onboarding Terms",
			"Legacy Terms",
			{
				"Self-Onboarding Terms": {"name": "Self-Onboarding Terms", "terms": "<p>Current terms.</p>"},
				"Legacy Terms": {"name": "Legacy Terms", "terms": "<p>Legacy terms.</p>"},
			},
		)
		self.ois = {}
		self.processed = []
		self.fail_processing = False
		original = {
			"exists": frappe.db.exists,
			"get_value": frappe.db.get_value,
			"set_value": frappe.db.set_value,
			"get_all": frappe.get_all,
		}

		def create(partner, package, account_email, person, facility, terms_snapshot, identity_ref):
			name = "OIS-T%d" % (len(self.ois) + 1)
			self.ois[name] = {
				"status": "Pending",
				"network_slug": partner["name"],
				"onboarding_source": "token_self_onboarding",
				"onboarding_identity_ref": identity_ref,
				"cx_account_email": account_email,
				"raw_json": json.dumps({"facilities": [facility]}),
				"self_onboarding_tc_document": terms_snapshot["document"],
				"self_onboarding_tc_hash": terms_snapshot["hash"],
				"self_onboarding_tc_accepted_at": terms_snapshot["accepted_at"],
			}
			return name

		def exists(doctype, name=None, *args, **kwargs):
			if doctype == "CRM Opt-In Submission":
				return name if name in self.ois else None
			return original["exists"](doctype, name, *args, **kwargs)

		def get_value(doctype, name=None, *args, **kwargs):
			if name is None and "filters" in kwargs:
				return original["get_value"](doctype, **kwargs)
			if doctype == "CRM Opt-In Submission":
				field = args[0] if args else "status"
				return self.ois[name].get(field)
			if doctype == "CRM Pre-Qualified Facility":
				return None
			return original["get_value"](doctype, name, *args, **kwargs)

		def set_value(doctype, name, field, value=None, *args, **kwargs):
			if doctype == "CRM Opt-In Submission":
				self.ois[name][field] = value
				return None
			return original["set_value"](doctype, name, field, value, *args, **kwargs)

		def get_all(doctype, filters=None, fields=None, *args, **kwargs):
			if doctype != "CRM Opt-In Submission":
				return original["get_all"](doctype, filters, fields, *args, **kwargs)
			filters = filters or {}
			rows = []
			for name, values in self.ois.items():
				if any(values.get(key) != value for key, value in filters.items()):
					continue
				rows.append({"name": name, **values})
			return rows

		def process(name):
			self.processed.append(name)
			if not self.fail_processing:
				self.ois[name]["status"] = "Processed"

		for item in (
			patch.object(fo, "_public_network", return_value={"name": "net-a"}),
			patch.object(fo, "_token_packages", return_value=[self.PACKAGE]),
			patch.object(fo, "_upsert_facility_membership", return_value=_named("PQF-1")),
			patch.object(fo, "_create_submission", side_effect=create),
			patch.object(fo, "_ensure_customer_experience_access", return_value={"status": "sent"}),
			patch.object(fo, "_link_documents"),
			patch(
				"crm.api.customer_experience.create_initial_token_order",
				return_value={"success": True, "data": {"quotation": "QTN-X", "sales_order": "SO-X"}},
			),
			patch.object(fo.frappe.db, "exists", side_effect=exists),
			patch.object(fo.frappe.db, "get_value", side_effect=get_value),
			patch.object(fo.frappe.db, "set_value", side_effect=set_value),
			patch.object(fo.frappe.db, "has_column", return_value=True),
			patch.object(fo.frappe, "get_all", side_effect=get_all),
			patch("crm.api.optin._process_submission", side_effect=process),
		):
			item.start()
			self.addCleanup(item.stop)

	def _verified_token(self):
		token = self._start()["session_token"]
		fo.verify_otp(token, self._captured_otp())
		return token

	def _terms_environment(self, dedicated, legacy, documents):
		"""Install configurable Terms fixtures for endpoint and submission tests."""
		settings = {
			"self_onboarding_tc_document": dedicated,
			"active_tc_document": legacy,
			"self_onboarding_allowed_facility_levels": self.allowed_facility_levels,
		}
		self.terms_settings = settings
		original_exists = fo.frappe.db.exists
		original_get_doc = fo.frappe.get_doc

		def exists(doctype, name=None, *args, **kwargs):
			if doctype == "Terms and Conditions":
				return name if name in documents else None
			return original_exists(doctype, name, *args, **kwargs)

		def get_doc(doctype, name=None, *args, **kwargs):
			if doctype == "Terms and Conditions":
				return documents[name]
			if name is None:
				return original_get_doc(doctype, *args, **kwargs)
			return original_get_doc(doctype, name, *args, **kwargs)

		for item in (
			patch.object(
				fo,
				"_setting",
				side_effect=lambda name, default="": settings.get(
					name,
					self.channel_setting if name == "facility_onboarding_preferred_otp_channel" else default,
				),
			),
			patch.object(fo.frappe.db, "exists", side_effect=exists),
			patch.object(fo.frappe, "get_doc", side_effect=get_doc),
			patch("crm.utils.jinja.render_terms_template", side_effect=lambda template, context: template),
		):
			item.start()
			self.addCleanup(item.stop)
		self.terms_documents = documents

	def _accepted_terms(self, token):
		return fo.get_self_onboarding_terms(token)

	def _submit(self, token, facility_ids=("FID-1",), package="TOK-1"):
		terms = self._accepted_terms(token)
		return fo.submit_onboarding(
			token,
			"123456",
			json.dumps(list(facility_ids)),
			package,
			"owner@example.com",
			1,
			terms["content_hash"],
		)["data"]["submissions"]

	def test_self_onboarding_terms_uses_dedicated_setting_and_returns_rendered_hash(self):
		self._terms_environment(
			"Self-Onboarding Terms",
			"Legacy Terms",
			{
				"Self-Onboarding Terms": {"name": "Self-Onboarding Terms", "terms": "<p>Dedicated terms.</p>"},
				"Legacy Terms": {"name": "Legacy Terms", "terms": "<p>Legacy.</p>"},
			},
		)
		token = self._verified_token()

		result = self._accepted_terms(token)

		self.assertEqual(set(result), {"document", "rendered_html", "content_hash"})
		self.assertEqual(result["document"], "Self-Onboarding Terms")
		self.assertEqual(result["rendered_html"], "<p>Dedicated terms.</p>")
		self.assertEqual(result["content_hash"], fo.hashlib.sha256(result["rendered_html"].encode()).hexdigest())
		self.assertEqual(self.store.get(token)["accepted_terms_document"], result["document"])
		self.assertEqual(self.store.get(token)["accepted_terms_hash"], result["content_hash"])

	def test_self_onboarding_terms_falls_back_to_active_legacy_setting(self):
		self._terms_environment(
			"",
			"Legacy Terms",
			{"Legacy Terms": {"name": "Legacy Terms", "terms": "<p>Legacy terms.</p>"}},
		)
		token = self._verified_token()

		result = self._accepted_terms(token)

		self.assertEqual(result["document"], "Legacy Terms")
		self.assertEqual(result["rendered_html"], "<p>Legacy terms.</p>")

	def test_submit_rejects_terms_changed_after_customer_review(self):
		self._submit_env()
		token = self._verified_token()
		terms = self._accepted_terms(token)
		self.terms_documents["Self-Onboarding Terms"]["terms"] = "<p>Changed terms.</p>"

		with self.assertRaises(frappe.ValidationError):
			fo.submit_onboarding(
				token,
				"123456",
				'["FID-1"]',
				"TOK-1",
				"owner@example.com",
				1,
				terms["content_hash"],
			)

		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_submit_rejects_invalid_account_email_before_creating_records(self):
		self._submit_env()
		token = self._verified_token()
		terms = self._accepted_terms(token)

		with self.assertRaisesRegex(frappe.ValidationError, "verified registry profile"):
			fo.submit_onboarding(
				token,
				"123456",
				'["FID-1"]',
				"TOK-1",
				"not-an-email",
				1,
				terms["content_hash"],
			)

		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_submit_uses_verified_registry_email_and_rejects_browser_override(self):
		self._submit_env()
		token = self._verified_token()
		terms = self._accepted_terms(token)

		with self.assertRaisesRegex(frappe.ValidationError, "verified registry profile"):
			fo.submit_onboarding(
				token,
				"123456",
				'["FID-1"]',
				"TOK-1",
				"attacker@example.com",
				1,
				terms["content_hash"],
			)

		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_submit_rejects_internal_account_email_before_creating_records(self):
		self._submit_env()
		token = self._verified_token()
		session = self.store.get(token)
		session["person"]["email"] = "staff@example.com"
		self.store.save(token, session)
		terms = self._accepted_terms(token)

		def user_lookup(doctype, name=None, *args, **kwargs):
			if doctype == "User" and isinstance(name, dict):
				return "staff@example.com"
			if doctype == "User":
				return frappe._dict(user_type="System User", enabled=1)
			return None

		with patch.object(fo.frappe.db, "get_value", side_effect=user_lookup):
			with self.assertRaisesRegex(frappe.ValidationError, "cannot be used"):
				fo.submit_onboarding(
					token,
					"123456",
					'["FID-1"]',
					"TOK-1",
					"staff@example.com",
					1,
					terms["content_hash"],
				)

		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_submit_rejects_disabled_website_account_before_creating_records(self):
		self._submit_env()
		token = self._verified_token()
		session = self.store.get(token)
		session["person"]["email"] = "disabled@example.com"
		self.store.save(token, session)
		terms = self._accepted_terms(token)

		def user_lookup(doctype, name=None, *args, **kwargs):
			if doctype == "User" and isinstance(name, dict):
				return "disabled@example.com"
			if doctype == "User":
				return frappe._dict(user_type="Website User", enabled=0)
			return None

		with patch.object(fo.frappe.db, "get_value", side_effect=user_lookup):
			with self.assertRaisesRegex(frappe.ValidationError, "cannot be used"):
				fo.submit_onboarding(
					token,
					"123456",
					'["FID-1"]',
					"TOK-1",
					"disabled@example.com",
					1,
					terms["content_hash"],
				)

		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_submit_rejects_non_ascii_or_malformed_terms_hash(self):
		self._submit_env()
		token = self._verified_token()
		self._accepted_terms(token)

		for bad_hash in ("é" + "a" * 63, "A" * 64, "a" * 63, " " + "a" * 64):
			with self.subTest(bad_hash=bad_hash), self.assertRaises(frappe.ValidationError):
				fo.submit_onboarding(
					token,
					"123456",
					'["FID-1"]',
					"TOK-1",
					"owner@example.com",
					1,
					bad_hash,
				)
		self.assertEqual(self.ois, {})

	def test_submit_pending_hfr_session_returns_controlled_retry_error(self):
		self._submit_env()
		token = self._start()["session_token"]
		self.hfr.side_effect = RuntimeError("HFR unavailable")
		self.assertEqual(
			fo.verify_otp(token, self._captured_otp())["data"],
			{"state": "hfr_pending", "retryable": True},
		)
		self._accepted_terms(token)
		with self.assertRaisesRegex(frappe.ValidationError, "Facility details are not ready"):
			self._submit(token)
		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_submit_revalidates_terms_inside_lock_before_creating_records(self):
		self._submit_env()
		token = self._verified_token()
		terms = self._accepted_terms(token)
		original_filelock = fo.filelock

		@contextmanager
		def change_terms_after_lock(lock_name, timeout=60):
			with original_filelock(lock_name, timeout=timeout):
				if lock_name.startswith("crm_onboarding_submit_"):
					self.terms_documents["Self-Onboarding Terms"]["terms"] = "<p>Changed under lock.</p>"
				yield

		with patch.object(fo, "filelock", change_terms_after_lock):
			with self.assertRaisesRegex(frappe.ValidationError, "Terms and Conditions have changed"):
				fo.submit_onboarding(
					token,
					"123456",
					'["FID-1"]',
					"TOK-1",
					"owner@example.com",
					1,
					terms["content_hash"],
				)

		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_submit_rejects_document_switch_even_when_rendered_content_matches(self):
		self._submit_env()
		token = self._verified_token()
		terms = self._accepted_terms(token)
		self.terms_documents["Legacy Terms"]["terms"] = "<p>Current terms.</p>"
		self.terms_settings["self_onboarding_tc_document"] = "Legacy Terms"

		with self.assertRaises(frappe.ValidationError):
			fo.submit_onboarding(
				token,
				"123456",
				'["FID-1"]',
				"TOK-1",
				"owner@example.com",
				1,
				terms["content_hash"],
			)

		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_missing_self_onboarding_terms_blocks_request_and_submit_before_records(self):
		self._submit_env()
		# Both configuration fields are blank and no usable Terms document exists.
		self._terms_environment("", "", {})
		token = self._verified_token()

		with self.assertRaises(frappe.ValidationError):
			self._accepted_terms(token)
		with self.assertRaises(frappe.ValidationError):
			fo.submit_onboarding(
				token,
				"123456",
				'["FID-1"]',
				"TOK-1",
				"owner@example.com",
				1,
				"a" * 64,
			)

		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_submit_records_terms_and_facility_selection(self):
		self._submit_env()
		token = self._verified_token()
		self._submit(token)
		rows = {row.event: row for row in self._evidence_rows(token)}
		self.assertEqual(rows["terms_accepted"].reference_name, "net-a")
		self.assertEqual(rows["facility_selected"].reference_name, "PQF-1")
		stored_terms = self.ois["OIS-T1"]
		self.assertEqual(stored_terms["self_onboarding_tc_document"], "Self-Onboarding Terms")
		self.assertEqual(len(stored_terms["self_onboarding_tc_hash"]), 64)
		self.assertTrue(stored_terms["self_onboarding_tc_accepted_at"])

	def test_repeated_submit_resumes_one_submission_per_facility(self):
		self._submit_env()
		token = self._verified_token()
		first = self._submit(token)
		second = self._submit(token)
		self.assertEqual(first, second)
		self.assertEqual(len(self.ois), 1)
		self.assertEqual(self.processed, ["OIS-T1"])
		self.assertIn(
			"replay: staged submission resumed",
			[row.detail for row in self._evidence_rows(token)],
		)
		self.assertEqual(
			[e for e in self._events(token) if e[0] == "facility_selected"], [("facility_selected", "ok")]
		)

	def test_conflict_preflight_requires_otp_and_limits_ids_to_the_verified_session(self):
		token = self._start()["session_token"]
		with self.assertRaises(frappe.PermissionError):
			fo.check_onboarding_conflicts(token, '["FID-1"]')

		fo.verify_otp(token, self._captured_otp())
		with patch.object(fo, "_public_network", return_value={"name": "net-a"}):
			with self.assertRaises(frappe.ValidationError):
				fo.check_onboarding_conflicts(token, '["FID-TAMPERED"]')
			self.assertEqual(
				fo.check_onboarding_conflicts(token, '["FID-1"]'),
				{"outcome": "new", "allowed_facility_ids": ["FID-1"]},
			)

	def test_conflict_preflight_reports_invalid_referring_network_id(self):
		token = self._verified_token()
		with patch.object(fo, "_public_network", return_value=None):
			with self.assertRaisesRegex(frappe.ValidationError, "That Network ID"):
				fo.check_onboarding_conflicts(token, '["FID-1"]', "123456")

	def test_conflict_preflight_rechecks_current_facility_level_whitelist(self):
		token = self._verified_token()
		self.allowed_facility_levels = " Level 3 "
		with patch.object(fo, "_public_network", return_value={"name": "net-a"}):
			self.assertEqual(
				fo.check_onboarding_conflicts(token, '["FID-1"]'),
				{"outcome": "new", "allowed_facility_ids": ["FID-1"]},
			)
			self.allowed_facility_levels = "Level 30"
			self.assertEqual(
				fo.check_onboarding_conflicts(token, '["FID-1"]'),
				{
					"outcome": "facility_level_ineligible",
					"allowed_facility_ids": [],
					"ineligible_facility_ids": ["FID-1"],
					"facility_eligibility": [
						{
							"facility_id": "FID-1",
							"onboarding_eligible": False,
							"facility_eligibility_reason": "level_not_allowed",
						}
					],
				},
			)

	def test_submit_rechecks_current_facility_level_whitelist_before_side_effects(self):
		self._submit_env()
		token = self._verified_token()
		terms = self._accepted_terms(token)
		self.terms_settings["self_onboarding_allowed_facility_levels"] = "Level 30"

		result = fo.submit_onboarding(
			token, "123456", '["FID-1"]', "TOK-1", "owner@example.com", 1, terms["content_hash"]
		)

		self.assertEqual(result["data"]["outcome"], "facility_level_ineligible")
		self.assertEqual(self.ois, {})
		fo._upsert_facility_membership.assert_not_called()

	def test_duplicate_identity_preflight_returns_only_allow_listed_state(self):
		self._submit_env()
		first_token = self._verified_token()
		self._submit(first_token)
		second_token = self._verified_token()

		result = fo.check_onboarding_conflicts(second_token, '["FID-1"]', "123456")

		self.assertEqual(result["outcome"], "facility_review")
		self.assertEqual(result["allowed_facility_ids"], [])
		self.assertEqual(result["already_onboarded_facility_ids"], ["FID-1"])
		self.assertTrue(result.get("is_existing_identity"))
		self.assertNotIn("owner@example.com", json.dumps(result))
		self.assertNotIn("OIS-T1", json.dumps(result))
		self.assertNotIn(ID_NUMBER, json.dumps(result))

	def test_existing_identity_can_onboard_new_facility_and_links_account(self):
		self._submit_env()
		self.hfr.return_value = [
			FACILITIES[0],
			{**FACILITIES[0], "facility_id": "FID-2", "facility_name": "Beta Clinic", "facility_code": "10002"},
		]
		first_token = self._verified_token()
		self._submit(first_token, facility_ids=("FID-1",))
		second_token = self._verified_token()

		preflight = fo.check_onboarding_conflicts(second_token, '["FID-2"]', "123456")
		self.assertEqual(preflight["outcome"], "new")
		self.assertEqual(preflight["allowed_facility_ids"], ["FID-2"])
		self.assertTrue(preflight.get("is_existing_identity"))

		terms = self._accepted_terms(second_token)
		submit_result = fo.submit_onboarding(
			second_token,
			"123456",
			'["FID-2"]',
			"TOK-1",
			"owner@example.com",
			1,
			terms["content_hash"],
		)
		self.assertTrue(submit_result["success"])
		self.assertEqual(submit_result["data"]["outcome"], "new")
		self.assertEqual(submit_result["data"]["portal_status"], "linked")
		self.assertTrue(submit_result["data"].get("is_existing_identity"))

	def test_legacy_identity_without_reference_is_not_claimed_but_facility_conflict_blocks(self):
		self._submit_env()
		self.ois["OIS-LEGACY"] = {
			"status": "Processed",
			"network_slug": "net-a",
			"raw_json": json.dumps({"facilities": [{"mfl_code": "10001"}]}),
		}
		token = self._verified_token()

		result = fo.submit_onboarding(
			token,
			"123456",
			'["FID-1"]',
			"TOK-1",
			"owner@example.com",
			1,
			self._accepted_terms(token)["content_hash"],
		)

		self.assertEqual(result["data"], {"outcome": "facility_review", "allowed_facility_ids": []})
		self.assertEqual(set(self.ois), {"OIS-LEGACY"})
		fo._upsert_facility_membership.assert_not_called()

	def test_concurrent_sessions_share_identity_lock_and_create_one_record_set(self):
		self._submit_env()
		tokens = [self._verified_token(), self._verified_token()]
		args = []
		for token in tokens:
			terms = self._accepted_terms(token)
			args.append(
				(
					token,
					"123456",
					'["FID-1"]',
					"TOK-1",
					"owner@example.com",
					1,
					terms["content_hash"],
				)
			)
		locks = {}
		guard = threading.Lock()
		created = []

		@contextmanager
		def synchronized(lock_name, timeout=60):
			with guard:
				lock = locks.setdefault(lock_name, threading.Lock())
			if not lock.acquire(timeout=timeout):
				raise TimeoutError("submit lock timed out")
			try:
				yield
			finally:
				lock.release()

		def check(session, selected, network):
			# Model the database recheck under the lock; the waiter sees the first
			# submission after the lock holder creates it.
			time.sleep(0.05)
			if created:
				return {"outcome": "existing_identity", "allowed_facility_ids": []}
			return {"outcome": "new", "allowed_facility_ids": sorted(selected)}

		def create(*args):
			created.append("OIS-T1")
			return {"success": True, "data": {"submissions": [{"submission": "OIS-T1"}]}}

		with (
			patch.object(fo, "filelock", synchronized),
			patch.object(fo, "evidence_ref", side_effect=lambda value: "keyed:" + value),
			patch.object(fo, "_session_or_error", side_effect=lambda token, verified=False: self.store.get(token)),
			patch.object(fo, "_validate_self_onboarding_terms", return_value={"hash": "a" * 64}),
			patch.object(fo, "_validate_account_email", return_value="owner@example.com"),
			patch.object(fo, "_public_network", return_value={"name": "net-a"}),
			patch.object(fo, "_token_packages", return_value=[self.PACKAGE]),
			patch.object(fo, "_catalog_packages", return_value=[self.PACKAGE]),
			patch.object(fo, "_check_onboarding_conflicts", side_effect=check),
			patch.object(fo, "_submit_selected_facilities", side_effect=create),
		):
			with ThreadPoolExecutor(max_workers=2) as pool:
				results = [pool.submit(fo.submit_onboarding, *submit_args) for submit_args in args]
				data = [result.result(timeout=5)["data"] for result in results]

		self.assertEqual(len(locks), 1)
		self.assertEqual(len(created), 1)
		self.assertCountEqual([row.get("outcome", "new") for row in data], ["new", "existing_identity"])

	def test_retry_after_processing_failure_reuses_the_staged_submission(self):
		self._submit_env()
		token = self._verified_token()
		self.fail_processing = True
		with self.assertRaises(frappe.ValidationError):
			self._submit(token)
		self.fail_processing = False
		result = self._submit(token)
		self.assertEqual(len(self.ois), 1)
		self.assertEqual(result[0]["submission"], "OIS-T1")
		self.assertEqual(self.ois["OIS-T1"]["status"], "Processed")

	def test_failed_submission_is_reset_before_reprocessing(self):
		self._submit_env()
		token = self._verified_token()
		self.fail_processing = True
		with self.assertRaises(frappe.ValidationError):
			self._submit(token)
		self.ois["OIS-T1"]["status"] = "Failed"
		self.fail_processing = False
		self._submit(token)
		self.assertEqual(self.processed, ["OIS-T1", "OIS-T1"])
		self.assertEqual(len(self.ois), 1)

	def test_facility_selected_in_another_session_is_rejected(self):
		self._submit_env()
		other = [{**FACILITIES[0], "facility_id": "FID-2"}]
		self.hfr.return_value = other
		token = self._verified_token()
		with self.assertRaises(frappe.ValidationError):
			self._submit(token, facility_ids=("FID-1",))
		self.assertEqual(self.ois, {})

	def test_each_selected_facility_gets_its_own_submission(self):
		self._submit_env()
		self.hfr.return_value = [
			*FACILITIES,
			{**FACILITIES[0], "facility_id": "FID-2", "facility_code": "10002"},
		]
		token = self._verified_token()
		result = self._submit(token, facility_ids=("FID-1", "FID-2"))
		self.assertEqual(len({row["submission"] for row in result}), 2)
		self.assertEqual(len(self._submit(token, facility_ids=("FID-1", "FID-2"))), 2)
		self.assertEqual(len(self.ois), 2)

	def test_password_setup_failure_is_retryable_after_records_are_saved(self):
		self._submit_env()
		token = self._verified_token()
		with patch.object(fo, "_ensure_customer_experience_access", return_value={"status": "failed"}):
			with self.assertRaises(frappe.ValidationError):
				self._submit(token)

		self.assertEqual(len(self.ois), 1)
		self.assertEqual(self.processed, ["OIS-T1"])
		result = self._submit(token)
		self.assertEqual(len(result), 1)
		self.assertEqual(len(self.ois), 1)

	def test_submission_pricing_comes_from_the_server_package(self):
		captured = {}

		def get_doc(data):
			captured.update(data)
			return Mock(**{"insert.return_value": None, "flags": Mock()}, **{"name": "OIS-X"})

		facility = fo._facility_row(FACILITIES[0])
		with (
			patch.object(fo.frappe, "get_doc", side_effect=get_doc),
			patch.object(fo.frappe.db, "has_column", return_value=True),
			patch.object(fo, "_setting", side_effect=lambda name, default="": default),
		):
			fo._create_submission(
				{"name": "net-a"},
				self.PACKAGE,
				"owner@example.com",
				PERSON,
				facility,
				{"document": "Terms", "hash": "a" * 64, "accepted_at": "2026-10-13 12:00:00"},
				"keyed-identity-reference",
			)
		payload = json.loads(captured["raw_json"])
		row = payload["pricing"][0]
		self.assertEqual((row["item_code"], row["annual_kes"], row["price_list"]), ("TOK-1", 1000.0, "PL"))
		self.assertEqual(payload["token_package"]["price"], 1000.0)
		self.assertEqual(row["mfl_code"], "10001")
		self.assertEqual(captured["self_onboarding_tc_document"], "Terms")
		self.assertEqual(captured["self_onboarding_tc_hash"], "a" * 64)
		self.assertEqual(captured["self_onboarding_tc_accepted_at"], "2026-10-13 12:00:00")
		self.assertEqual(captured["onboarding_source"], "token_self_onboarding")
		self.assertEqual(captured["onboarding_identity_ref"], "keyed-identity-reference")
		self.assertEqual(captured["cx_account_email"], "owner@example.com")
		self.assertNotIn("witness", payload)
		self.assertEqual(payload["tc_doc_name"], "Terms")
		self.assertEqual(payload["tc_doc_hash"], "a" * 64)

	def test_link_documents_stamps_package_and_records_each_quotation(self):
		token = self._start()["session_token"]
		facility = fo._facility_row(FACILITIES[0])
		with (
			patch.object(fo.frappe.db, "has_column", return_value=True),
			patch.object(fo.frappe.db, "get_value", return_value='["QTN-1","QTN-2"]'),
			patch.object(fo.frappe.db, "exists", return_value=True),
			patch.object(fo.frappe.db, "set_value") as set_value,
		):
			fo._link_documents(token, self.store.get(token), "OIS-T1", facility, self.PACKAGE)
		stamped = {(c.args[1], c.args[2], c.args[3]) for c in set_value.call_args_list}
		self.assertIn(("QTN-1", "crm_token_package_item", "TOK-1"), stamped)
		self.assertIn(("QTN-2", "crm_token_facility_mfl", "10001"), stamped)
		linked = {row.reference_name for row in self._evidence_rows(token) if row.event == "document_linked"}
		self.assertEqual(linked, {"OIS-T1", "QTN-1", "QTN-2"})


class TestFacilityOnboardingLogging(UnitTestCase):
	def test_registry_failure_log_does_not_contain_the_identity_number(self):
		config = {"base_url": "https://registry.example.test"}
		error = requests.exceptions.ConnectionError("failed for url ?owner_id_number=%s" % ID_NUMBER)
		with (
			patch.object(fo, "_jwt_token", return_value="jwt"),
			patch.object(fo.requests, "get", side_effect=error),
			patch.object(fo.frappe, "log_error") as log_error,
		):
			with self.assertRaises(frappe.ValidationError):
				fo._request(config, "/owners", {"owner_id_number": ID_NUMBER})
		self.assertNotIn(ID_NUMBER, repr(log_error.call_args_list))

	def test_hfr_not_found_no_facilities_response_is_returned_for_gate_diagnosis(self):
		response = Mock(status_code=404)
		response.json.return_value = {
			"message": {"message": "No facilities found for this owner", "status": "error"},
			"status": "error",
			"status_code": 404,
		}
		with (
			patch.object(fo, "_jwt_token", return_value="jwt"),
			patch.object(fo.requests, "get", return_value=response),
		):
			body = fo._request(
				{"base_url": "https://registry.example.test"},
				"/owners",
				{"owner_id_number": ID_NUMBER},
				allow_no_facilities=True,
			)
		self.assertEqual(body["message"]["message"], "No facilities found for this owner")
		response.raise_for_status.assert_not_called()

	def test_other_hfr_404_responses_remain_upstream_errors(self):
		response = Mock(status_code=404)
		response.json.return_value = {"message": {"message": "Route not found"}}
		response.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
		with (
			patch.object(fo, "_jwt_token", return_value="jwt"),
			patch.object(fo.requests, "get", return_value=response),
			patch.object(fo.frappe, "log_error"),
		):
			with self.assertRaises(frappe.ValidationError):
				fo._request(
					{"base_url": "https://registry.example.test"},
					"/owners",
					{"owner_id_number": ID_NUMBER},
					allow_no_facilities=True,
				)


class TestFacilityOnboardingCatalog(UnitTestCase):
	@staticmethod
	def _vat(net_total, *args, **kwargs):
		vat = round(net_total * 0.16, 2)
		return frappe._dict(
			net_total=net_total,
			vat_amount=vat,
			grand_total=round(net_total + vat, 2),
			vat_rate=16.0,
			vat_label="VAT (16%)",
		)

	def test_catalog_reports_server_resolved_vat_and_hides_the_price_list(self):
		package = {
			"item_code": "TOK-1",
			"display_name": "Starter",
			"price": 1000.0,
			"price_list": "Internal PL",
		}
		with (
			patch.object(fo, "_public_network", return_value={"name": "net-a"}),
			patch.object(fo, "_token_packages", return_value=[package]),
			patch("crm.utils.quotation_tax.calculate_vat_totals", side_effect=self._vat),
		):
			data = fo.get_catalog("123456")["data"]
		row = data["packages"][0]
		self.assertEqual(
			(row["price_ex_vat"], row["vat_amount"], row["gross_total"]), (1000.0, 160.0, 1160.0)
		)
		self.assertEqual(row["vat_label"], "VAT (16%)")
		self.assertNotIn("price_list", row)
		self.assertEqual(row["price"], 1000.0)

	def test_catalog_loads_global_packages_without_partner_id_and_keeps_default_network_optional(self):
		with (
			patch.object(fo, "_public_network", return_value=None) as public_network,
			patch.object(fo, "_token_packages", return_value=[]),
			patch("crm.utils.quotation_tax.calculate_vat_totals"),
		):
			data = fo.get_catalog()["data"]

		self.assertEqual(data["network"], {})
		self.assertEqual(data["packages"], [])
		self.assertIn("calculator_config", data)
		public_network.assert_called_once_with("")

	def test_invalid_nonblank_partner_id_never_falls_back_to_default_network(self):
		with patch.object(fo, "_public_network", return_value=None):
			with self.assertRaisesRegex(frappe.ValidationError, "Network ID"):
				fo.get_catalog("12345x")

	def test_invalid_vat_configuration_is_reported_generically(self):
		with (
			patch.object(fo, "_public_network", return_value={"name": "net-a"}),
			patch.object(fo, "_token_packages", return_value=[{"item_code": "TOK-1", "price": 1.0}]),
			patch(
				"crm.utils.quotation_tax.calculate_vat_totals",
				side_effect=RuntimeError("Kenya Tax - TB"),
			),
			patch.object(fo.frappe, "log_error"),
		):
			with self.assertRaises(frappe.ValidationError) as caught:
				fo.get_catalog("123456")
		self.assertNotIn("Kenya Tax", str(caught.exception))

	def test_disabled_and_unpriced_packages_are_not_offered(self):
		rows = [
			{"item_code": "ON", "enabled": 1, "display_name": "On", "token_quantity": 5},
			{"item_code": "OFF", "enabled": 0, "display_name": "Off"},
			{"item_code": "NOPRICE", "enabled": 1, "display_name": "No price"},
		]
		settings = Mock()
		settings.get.side_effect = lambda name: "PL" if name == "token_price_list" else rows

		def get_value(doctype, filters, fields, as_dict=False):
			if filters["item_code"] == "ON":
				return frappe._dict(price_list_rate=500, currency="KES")
			return None

		with (
			patch.object(fo.frappe, "get_single", return_value=settings),
			patch.object(fo.frappe.db, "get_value", side_effect=get_value),
		):
			packages = fo._token_packages()
		self.assertEqual([p["item_code"] for p in packages], ["ON"])
