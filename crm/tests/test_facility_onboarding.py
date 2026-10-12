import copy
import json
import re
from typing import ClassVar
from unittest.mock import Mock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase, UnitTestCase

from crm.api import facility_onboarding as fo
from crm.api.facility_onboarding import _onboarding_config, _session_key
from crm.fcrm.doctype.crm_onboarding_evidence.crm_onboarding_evidence import evidence_ref


class TestFacilityOnboardingRegistryConfig(UnitTestCase):
	def test_session_cache_key_is_keyed_and_does_not_expose_token(self):
		with patch("crm.api.facility_onboarding._password_setting", return_value="test-secret"):
			key = _session_key("opaque-session-token")

		self.assertTrue(key.startswith("crm_facility_onboarding:"))
		self.assertNotIn("opaque-session-token", key)

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
		self.store = _Store()
		self.sent = []
		self.sms = []
		self.channel_setting = "Email"
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
					self.channel_setting if name == "facility_onboarding_preferred_otp_channel" else default
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
			return re.search(r"<strong>(\d{6})</strong>", self.sent[-1]["message"]).group(1)
		return re.search(r"\b(\d{6})\b", self.sms[-1][1]).group(1)

	def test_hfr_is_resolved_before_client_registry(self):
		self._start()
		self.assertEqual([c[0] for c in self.calls.mock_calls], ["hfr", "registry"])
		self.hfr.assert_called_once_with(ID_NUMBER)

	def test_client_registry_is_skipped_when_hfr_has_no_facilities(self):
		self.hfr.return_value = []
		data = self._start()
		self.registry.assert_not_called()
		self.assertEqual(self.sent, [])
		self.assertEqual(data["delivery"]["status"], "sent")

	def test_email_is_the_default_channel(self):
		delivery = self._start()["delivery"]
		self.assertEqual(delivery["channel"], "email")
		self.assertEqual(delivery["masked_destination"], "o***@example.com")
		self.assertEqual(delivery["status"], "sent")
		self.assertEqual(len(self.sent), 1)
		self.assertEqual(self.sms, [])

	def test_sms_is_used_when_preferred(self):
		self.channel_setting = "SMS"
		delivery = self._start()["delivery"]
		self.assertEqual(delivery["channel"], "sms")
		self.assertEqual(delivery["masked_destination"], "254******78")
		self.assertEqual(len(self.sms), 1)
		self.assertEqual(self.sent, [])

	def test_email_failure_falls_back_to_sms(self):
		self.email_fails = True
		delivery = self._start()["delivery"]
		self.assertEqual(delivery["channel"], "sms")
		self.assertEqual(delivery["status"], "sent")

	def test_missing_sms_gateway_falls_back_to_email(self):
		self.channel_setting = "SMS"
		self.gateway = False
		self.assertEqual(self._start()["delivery"]["channel"], "email")

	def test_phone_only_contact_uses_sms(self):
		self.registry.return_value = {**PERSON, "email": ""}
		self.assertEqual(self._start()["delivery"]["channel"], "sms")

	def test_no_deliverable_channel_is_reported_without_leaking_contacts(self):
		self.email_fails = True
		self.gateway = False
		delivery = self._start()["delivery"]
		self.assertEqual(delivery["status"], "unavailable")
		self.assertIsNone(delivery["channel"])
		self.assertNotIn("owner@example.com", repr(self.log_error.call_args_list))

	def test_unknown_id_returns_same_shape_with_stable_decoy(self):
		real = self._start()
		self.hfr.return_value = []
		first = self._start("99999999")
		second = self._start("99999999")
		self.assertEqual(set(first), set(real))
		self.assertEqual(set(first["delivery"]), set(real["delivery"]))
		self.assertEqual(first["delivery"]["channel"], "email")
		self.assertRegex(first["delivery"]["masked_destination"], r"^[a-z]\*\*\*@[a-z.]+$")
		self.assertEqual(first["delivery"]["masked_destination"], second["delivery"]["masked_destination"])

	def test_nothing_sensitive_is_disclosed_before_verification(self):
		body = json.dumps(self._start())
		otp = self._captured_otp()
		for secret in ("owner@example.com", "254712345678", "Alpha Clinic", "Amina", "FID-1", "10001", otp):
			self.assertNotIn(secret, body)

	def test_verified_otp_releases_facilities_and_replay_fails(self):
		token = self._start()["session_token"]
		otp = self._captured_otp()
		data = fo.verify_otp(token, otp)["data"]
		self.assertEqual(data["facilities"][0]["facility_id"], "FID-1")
		with self.assertRaises(frappe.PermissionError):
			fo.verify_otp(token, otp)

	def test_unknown_id_can_never_verify(self):
		self.hfr.return_value = []
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
		self.assertGreater(cooling["delivery"]["resend_after"], 0)
		for _ in range(fo.OTP_MAX_RESENDS):
			self.store.data[token]["otp_sent_at"] = 1
			self.assertEqual(fo.resend_otp(token)["data"]["delivery"]["channel"], "email")
		self.store.data[token]["otp_sent_at"] = 1
		with self.assertRaises(frappe.ValidationError):
			fo.resend_otp(token)

	def test_resend_for_unknown_id_sends_nothing(self):
		self.hfr.return_value = []
		token = self._start("99999999")["session_token"]
		self.store.data[token]["otp_sent_at"] = 1
		self.assertEqual(fo.resend_otp(token)["data"]["delivery"]["status"], "sent")
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
			sorted([("lookup", "ok"), ("otp_sent", "ok"), ("otp_failed", "failed"), ("otp_verified", "ok")]),
		)
		self.assertEqual(
			{row.subject_ref for row in self._evidence_rows(token)}, {evidence_ref(self._subject(token))}
		)

	def _subject(self, token):
		return self.store.data[token]["identity_hash"]

	def test_unknown_id_records_a_failed_lookup_and_no_delivery(self):
		self.hfr.return_value = []
		token = self._start("99999999")["session_token"]
		self.assertEqual(self._events(token), [("lookup", "failed")])

	def test_delivery_failure_and_resend_are_recorded(self):
		self.email_fails = True
		self.gateway = False
		token = self._start()["session_token"]
		self.assertIn(("otp_sent", "failed"), self._events(token))
		self.store.data[token]["otp_sent_at"] = 1
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
		self.ois = {}
		self.processed = []
		self.fail_processing = False
		original = {
			"exists": frappe.db.exists,
			"get_value": frappe.db.get_value,
			"set_value": frappe.db.set_value,
		}

		def create(partner, package, witness, person, facility):
			name = "OIS-T%d" % (len(self.ois) + 1)
			self.ois[name] = {"status": "Pending", "facility": facility["facility_id"]}
			return name

		def exists(doctype, name=None, *args, **kwargs):
			if doctype == "CRM Opt-In Submission":
				return name if name in self.ois else None
			return original["exists"](doctype, name, *args, **kwargs)

		def get_value(doctype, name=None, *args, **kwargs):
			if doctype == "CRM Opt-In Submission":
				return self.ois[name]["status"]
			return original["get_value"](doctype, name, *args, **kwargs)

		def set_value(doctype, name, field, value=None, *args, **kwargs):
			if doctype == "CRM Opt-In Submission":
				self.ois[name][field] = value
				return None
			return original["set_value"](doctype, name, field, value, *args, **kwargs)

		def process(name):
			self.processed.append(name)
			if not self.fail_processing:
				self.ois[name]["status"] = "Processed"

		for item in (
			patch.object(fo, "_public_network", return_value={"name": "net-a"}),
			patch.object(fo, "_token_packages", return_value=[self.PACKAGE]),
			patch.object(fo, "_upsert_facility_membership", return_value=_named("PQF-1")),
			patch.object(fo, "_create_submission", side_effect=create),
			patch.object(fo, "_link_documents"),
			patch.object(fo.frappe.db, "exists", side_effect=exists),
			patch.object(fo.frappe.db, "get_value", side_effect=get_value),
			patch.object(fo.frappe.db, "set_value", side_effect=set_value),
			patch("crm.api.optin._process_submission", side_effect=process),
		):
			item.start()
			self.addCleanup(item.stop)

	def _verified_token(self):
		token = self._start()["session_token"]
		fo.verify_otp(token, self._captured_otp())
		return token

	def _submit(self, token, facility_ids=("FID-1",), package="TOK-1"):
		return fo.submit_onboarding(
			token,
			"123456",
			json.dumps(list(facility_ids)),
			package,
			json.dumps({"name": "Witness", "email": "witness@example.com"}),
			1,
		)["data"]["submissions"]

	def test_submit_records_terms_and_facility_selection(self):
		self._submit_env()
		token = self._verified_token()
		self._submit(token)
		rows = {row.event: row for row in self._evidence_rows(token)}
		self.assertEqual(rows["terms_accepted"].reference_name, "net-a")
		self.assertEqual(rows["facility_selected"].reference_name, "PQF-1")

	def test_repeated_submit_resumes_one_submission_per_facility(self):
		self._submit_env()
		token = self._verified_token()
		first = self._submit(token)
		second = self._submit(token)
		self.assertEqual(first, second)
		self.assertEqual(len(self.ois), 1)
		self.assertEqual(self.processed, ["OIS-T1"])
		self.assertEqual(
			[e for e in self._events(token) if e[0] == "facility_selected"], [("facility_selected", "ok")]
		)

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

	def test_submission_pricing_comes_from_the_server_package(self):
		captured = {}

		def get_doc(data):
			captured.update(data)
			return Mock(**{"insert.return_value": None, "flags": Mock()}, **{"name": "OIS-X"})

		facility = fo._facility_row(FACILITIES[0])
		with (
			patch.object(fo.frappe, "get_doc", side_effect=get_doc),
			patch.object(fo, "_setting", side_effect=lambda name, default="": default),
		):
			fo._create_submission(
				{"name": "net-a"}, self.PACKAGE, {"name": "W", "email": "w@example.com"}, PERSON, facility
			)
		payload = json.loads(captured["raw_json"])
		row = payload["pricing"][0]
		self.assertEqual((row["item_code"], row["annual_kes"], row["price_list"]), ("TOK-1", 1000.0, "PL"))
		self.assertEqual(payload["token_package"]["price"], 1000.0)
		self.assertEqual(row["mfl_code"], "10001")

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
