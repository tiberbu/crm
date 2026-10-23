from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase
from frappe.utils.file_lock import LockTimeoutError

from crm.api.hfr import (
	_auto_submit_external_provisioning,
	_build_external_provisioning_payload,
	_get_external_provisioning_status,
	get_provisioning_status,
	ensure_provisioning_draft,
	_hfr_request,
	_merge_facility_hfr_fallback,
	_map_facility_to_org_fields,
	_external_submit_error,
	_external_error_details,
	_token_expiry_from_onboarding_date,
	_unique_facility_projection,
	search_facility,
)


class TestExternalProvisioningStatus(UnitTestCase):
	def _not_submitted(self):
		return {
			"configured": True,
			"status": "not_submitted",
			"progress": 0,
			"source": "external_setup",
		}

	def _valid_payload(self):
		return {
			"fid": "FID-99-TEST-1",
			"licence": "LIC-TEST-1",
			"tokens_awarded": 500,
			"token_expiry_date": "2027-10-21",
			"admin_email": "facility@example.test",
			"admin_name": "Facility Admin",
			"billing_model": "Token",
			"admin_mobile": "+254700000001",
		}

	@patch("crm.api.hfr._get_provisioning_status", return_value={"status": "not_submitted"})
	def test_status_query_is_read_only(self, mock_status):
		self.assertEqual(get_provisioning_status("88776"), {"status": "not_submitted"})
		mock_status.assert_called_once_with("88776", ensure_missing_draft=False)

	@patch("crm.api.hfr._get_provisioning_status", return_value={"status": "Draft"})
	def test_ensure_draft_is_a_separate_command(self, mock_status):
		self.assertEqual(ensure_provisioning_draft("88776"), {"status": "Draft"})
		mock_status.assert_called_once_with("88776", ensure_missing_draft=True)

	@patch("crm.api.hfr._hfr_request", return_value={"data": [
		{"hie_id": "HIE-ONLY", "facility_code": "12345"},
		{"hie_id": "HIE-2", "facility_fid": "FID-29-116804-5", "facility_code": "116804"},
	]})
	@patch("crm.api.hfr._build_hfr_url", return_value="https://hfr.example.test/facilities")
	@patch("crm.api.hfr._get_settings")
	def test_search_never_exposes_generic_hie_id_as_deployment_fid(self, _settings, _url, _request):
		rows = search_facility("12345")
		self.assertIsNone(rows[0]["fid"])
		self.assertEqual(rows[0]["hie_id"], "HIE-ONLY")
		self.assertEqual(rows[1]["fid"], "FID-29-116804-5")

	def test_status_facility_uses_deal_fid_when_prequalified_copy_is_blank(self):
		facility = _merge_facility_hfr_fallback(
			{"mfl_code": "116804", "hfr_facility_id": None, "facility_name": "Registry name"},
			{"hfr_facility_id": "FID-29-116804-5", "facility_name": "Deal copy", "license_number": "LIC-1"},
		)
		self.assertEqual(facility.hfr_facility_id, "FID-29-116804-5")
		self.assertEqual(facility.facility_name, "Registry name")
		self.assertEqual(facility.license_number, "LIC-1")

	def test_facility_projection_drops_conflicting_values_instead_of_picking_a_row(self):
		projection = _unique_facility_projection(
			[
				{"hfr_facility_id": "FID-29-111-1", "facility_name": "Same facility"},
				{"hfr_facility_id": "FID-29-222-1", "facility_name": "Same facility"},
			],
			["hfr_facility_id", "facility_name"],
		)
		self.assertNotIn("hfr_facility_id", projection)
		self.assertEqual(projection["facility_name"], "Same facility")

	def test_ta_validation_message_is_visible_to_facility_operator(self):
		message = _external_submit_error(
			400, {"message": "Missing required field(s): licence, token_expiry_date."}
		)
		self.assertIn("licence, token_expiry_date", message)

	def test_token_expiry_is_30_days_after_facility_onboarding_date(self):
		self.assertEqual(_token_expiry_from_onboarding_date("2026-10-21"), "2026-11-20")

	def test_raw_service_error_details_redact_credentials(self):
		details = _external_error_details(
			400,
			{
				"message": "Missing licence",
				"api_key": "key",
				"error": {"token": "token-value", "trace": "failed"},
				"response_text": "api_key=raw-key",
			},
		)
		self.assertIn('"http_status": 400', details)
		self.assertIn("Missing licence", details)
		self.assertEqual(details.count("[REDACTED]"), 3)
		self.assertNotIn("token-value", details)
		self.assertNotIn("raw-key", details)

	@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
	@patch("crm.api.hfr.frappe.cache")
	@patch("crm.api.hfr._get_external_provisioning_status")
	@patch("crm.api.hfr.requests.post")
	def test_auto_submit_posts_basic_auth_then_reloads_status(self, mock_post, mock_status, mock_cache, _mock_lock):
		cache = MagicMock()
		cache.get_value.return_value = None
		mock_cache.return_value = cache
		accepted = MagicMock()
		accepted.status_code = 200
		accepted.headers = {"X-Correlation-Id": "corr-123"}
		accepted.json.return_value = {
			"message": {
				"accepted": True,
				"facility_setup": "SETUP-0001",
				"status": "Draft",
				"message": "Draft created",
			}
		}
		mock_post.return_value = accepted
		mock_status.side_effect = [self._not_submitted(), {"configured": True, "status": "Draft", "progress": 0}]

		result = _auto_submit_external_provisioning(
			"https://deploy.example.test", "key", "secret", "FID-99-TEST-1",
			self._not_submitted(), self._valid_payload(), [],
		)

		self.assertEqual(result["status"], "Draft")
		self.assertEqual(result["submission"]["state"], "created")
		self.assertEqual(result["submission"]["facility_setup"], "SETUP-0001")
		mock_status.assert_any_call("https://deploy.example.test", "key", "secret", "FID-99-TEST-1")
		self.assertEqual(mock_status.call_count, 2)  # authoritative GET before POST, then refresh GET
		mock_post.assert_called_once_with(
			"https://deploy.example.test/api/method/hmis_setup.api.external_provisioning.provision_facility",
			auth=("key", "secret"),
			json=self._valid_payload(),
			headers={"Accept": "application/json", "Content-Type": "application/json", "X-Correlation-Id": mock_post.call_args.kwargs["headers"]["X-Correlation-Id"]},
			timeout=60,
		)

	@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
	@patch("crm.api.hfr.frappe.cache")
	@patch("crm.api.hfr._get_external_provisioning_status")
	@patch("crm.api.hfr.requests.post")
	def test_authoritative_no_draft_retries_after_prior_ambiguous_post(
		self, mock_post, mock_status, mock_cache, _mock_lock
	):
		cache = MagicMock()
		cache.get_value.return_value = "unknown"
		mock_cache.return_value = cache
		accepted = MagicMock()
		accepted.status_code = 200
		accepted.headers = {"X-Correlation-Id": "corr-retry"}
		accepted.json.return_value = {"message": {"accepted": True, "facility_setup": "SETUP-0002"}}
		mock_post.return_value = accepted
		mock_status.side_effect = [
			self._not_submitted(),
			{"configured": True, "status": "Draft", "progress": 0},
		]

		result = _auto_submit_external_provisioning(
			"https://deploy.example.test", "key", "secret", "FID-99-TEST-1",
			self._not_submitted(), self._valid_payload(), [],
		)

		self.assertEqual(result["submission"]["state"], "created")
		mock_post.assert_called_once()

	@patch("crm.api.hfr.requests.post")
	def test_missing_ta_fields_block_submission(self, mock_post):
		payload, missing = _build_external_provisioning_payload({"fid": "FID-99-TEST-1"})
		result = _auto_submit_external_provisioning(
			"https://deploy.example.test", "key", "secret", "FID-99-TEST-1",
			self._not_submitted(), payload, missing,
		)
		self.assertEqual(result["submission"]["state"], "blocked")
		self.assertIn("licence", result["submission"]["missing_fields"])
		self.assertIn("token_expiry_date", result["submission"]["missing_fields"])
		mock_post.assert_not_called()

	def test_payload_builder_accepts_complete_policy_verified_data(self):
		source = {
			**self._valid_payload(),
			"facility_name": "Example Health Centre",
			"facility_level": "LEVEL 3",
		}
		payload, missing = _build_external_provisioning_payload(source)
		self.assertEqual(missing, [])
		self.assertEqual(payload["tokens_awarded"], 500)
		self.assertEqual(payload["facility_name"], "Example Health Centre")

	@patch("crm.api.hfr.filelock", side_effect=LockTimeoutError("locked"))
	@patch("crm.api.hfr.requests.post")
	def test_lock_timeout_returns_status_check_retry_without_post(self, mock_post, _mock_lock):
		result = _auto_submit_external_provisioning(
			"https://deploy.example.test", "key", "secret", "FID-99-TEST-1",
			self._not_submitted(), self._valid_payload(), [],
		)
		self.assertEqual(result["submission"]["state"], "unknown")
		self.assertEqual(result["submission"]["retry_mode"], "status_check")
		mock_post.assert_not_called()

	@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
	@patch("crm.api.hfr.frappe.cache")
	@patch("crm.api.hfr._get_external_provisioning_status", side_effect=lambda *args: {"status": "not_submitted"})
	@patch("crm.api.hfr.requests.post", side_effect=__import__("requests").exceptions.Timeout)
	def test_uncertain_post_retries_only_after_fresh_status_confirms_no_draft(self, mock_post, _mock_status, mock_cache, _mock_lock):
		cache = MagicMock()
		state = {}
		cache.get_value.side_effect = lambda key: state.get(key)
		cache.set_value.side_effect = lambda key, value, **kwargs: state.__setitem__(key, value)
		mock_cache.return_value = cache

		first = _auto_submit_external_provisioning(
			"https://deploy.example.test", "key", "secret", "FID-99-TEST-1",
			self._not_submitted(), self._valid_payload(), [],
		)
		second = _auto_submit_external_provisioning(
			"https://deploy.example.test", "key", "secret", "FID-99-TEST-1",
			self._not_submitted(), self._valid_payload(), [],
		)

		self.assertEqual(first["submission"]["state"], "unknown")
		self.assertEqual(second["submission"]["state"], "unknown")
		# Every explicit ensure performs a fresh GET; a confirmed absence permits
		# another POST even when the previous response was ambiguous.
		self.assertEqual(mock_post.call_count, 2)

	@patch.dict("crm.api.hfr.frappe.conf", {"encryption_key": "test-site-encryption-key"})
	@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
	@patch("crm.api.hfr.frappe.cache")
	@patch("crm.api.hfr._get_external_provisioning_status", side_effect=lambda *args: {"status": "not_submitted"})
	@patch("crm.api.hfr.frappe.log_error")
	@patch("crm.api.hfr.requests.post")
	def test_rejected_payload_fingerprint_is_keyed_and_does_not_repost_same_payload(
		self, mock_post, _mock_log_error, _mock_status, mock_cache, _mock_lock
	):
		cache = MagicMock()
		state = {}
		cache.get_value.side_effect = lambda key: state.get(key)
		cache.set_value.side_effect = lambda key, value, **kwargs: state.__setitem__(key, value)
		mock_cache.return_value = cache
		rejected = MagicMock()
		rejected.status_code = 400
		rejected.headers = {}
		rejected.json.return_value = {"message": "Missing required field"}
		mock_post.return_value = rejected

		first = _auto_submit_external_provisioning(
			"https://deploy.example.test", "key", "secret", "FID-99-TEST-1",
			self._not_submitted(), self._valid_payload(), [],
		)
		second = _auto_submit_external_provisioning(
			"https://deploy.example.test", "key", "secret", "FID-99-TEST-1",
			self._not_submitted(), self._valid_payload(), [],
		)

		self.assertEqual(first["submission"]["state"], "error")
		self.assertEqual(second["submission"]["state"], "error")
		mock_post.assert_called_once()
		stored_attempt = next(value for value in state.values() if str(value).startswith("rejected:"))
		self.assertNotIn("facility@example.test", stored_attempt)

	@patch("crm.api.hfr._generate_jwt", return_value="hfr-token")
	@patch("crm.api.hfr._get_settings")
	@patch("crm.api.hfr.requests.get")
	def test_hfr_search_values_are_sent_as_get_query_params(self, mock_get, _mock_settings, _mock_jwt):
		response = MagicMock()
		response.json.return_value = {"data": []}
		mock_get.return_value = response

		self.assertEqual(_hfr_request("https://hfr.example.test/lookup", {"facility-code": "12345"}), {"data": []})
		mock_get.assert_called_once_with(
			"https://hfr.example.test/lookup",
			params={"facility-code": "12345"},
			headers={
				"Authorization": "Bearer hfr-token",
				"Content-Type": "application/json",
				"Accept": "application/json",
			},
			timeout=30,
		)

	def test_hfr_facility_id_uses_deployment_fid_not_generic_hie_id(self):
		mapped = _map_facility_to_org_fields(
			{"facility_fid": "FID-29-116804-5", "hie_id": "HIE-123", "facility_code": "12345"}
		)
		self.assertEqual(mapped["hfr_facility_id"], "FID-29-116804-5")
		self.assertEqual(mapped["mfl_code"], "12345")

		without_fid = _map_facility_to_org_fields({"hie_id": "HIE-123", "facility_code": "12345"})
		self.assertIsNone(without_fid["hfr_facility_id"])

	@patch("crm.api.hfr._generate_jwt", return_value="hfr-token")
	@patch("crm.api.hfr._get_settings")
	@patch("crm.api.hfr.requests.get")
	def test_hfr_not_found_response_is_an_empty_search_result(self, mock_get, _mock_settings, _mock_jwt):
		response = MagicMock()
		response.status_code = 400
		response.json.return_value = {"status": "error", "message": "Organization with the facility-code 12345 not found"}
		mock_get.return_value = response

		self.assertEqual(_hfr_request("https://hfr.example.test/lookup", {"facility-code": "12345"}), {"message": []})
		response.raise_for_status.assert_not_called()

	@patch("crm.api.hfr.requests.get")
	def test_frappe_validation_error_for_missing_setup_maps_to_not_submitted(self, mock_get):
		response = MagicMock()
		response.status_code = 417
		response.json.return_value = {
			"exc_type": "ValidationError",
			"exception": "frappe.exceptions.ValidationError: No Facility Setup found for FID 'FID-99-TEST-1'.",
		}
		mock_get.return_value = response

		result = _get_external_provisioning_status(
			"https://deploy.example.test", "service-key", "service-secret", "FID-99-TEST-1"
		)

		self.assertEqual(result["status"], "not_submitted")
		self.assertEqual(result["source"], "external_setup")
		self.assertEqual(result["progress"], 0)
		mock_get.assert_called_once_with(
			"https://deploy.example.test/api/method/hmis_setup.api.external_provisioning.get_provision_status",
			params={"fid": "FID-99-TEST-1"},
			auth=("service-key", "service-secret"),
			headers={
				"Accept": "application/json",
				"X-Correlation-Id": mock_get.call_args.kwargs["headers"]["X-Correlation-Id"],
			},
			timeout=15,
		)

	@patch("crm.api.hfr.requests.get")
	def test_duplicate_setup_validation_error_maps_to_support(self, mock_get):
		response = MagicMock()
		response.status_code = 417
		response.json.return_value = {
			"exc_type": "ValidationError",
			"exception": "frappe.exceptions.ValidationError: Multiple Facility Setup documents found for FID 'FID-99-TEST-1'.",
		}
		mock_get.return_value = response

		result = _get_external_provisioning_status(
			"https://deploy.example.test", "service-key", "service-secret", "FID-99-TEST-1"
		)

		self.assertEqual(result["status"], "needs_support")
		self.assertEqual(result["source"], "external_setup")

	@patch("crm.api.hfr.requests.get")
	def test_unexpected_http_error_is_not_reported_as_network_failure(self, mock_get):
		response = MagicMock()
		response.status_code = 503
		mock_get.return_value = response

		result = _get_external_provisioning_status(
			"https://deploy.example.test", "service-key", "service-secret", "FID-99-TEST-1"
		)

		self.assertEqual(result["status"], "unavailable")
		self.assertEqual(result["error_code"], "service_error")
		self.assertTrue(result["retryable"])

	@patch("crm.api.hfr.requests.get")
	def test_setup_error_details_are_limited_to_system_managers(self, mock_get):
		response = MagicMock()
		response.status_code = 200
		response.headers = {}
		response.json.return_value = {
			"message": {"status": "Error", "progress": 40, "error": "Deploy failed", "log": "Traceback ..."}
		}
		mock_get.return_value = response

		for roles, expect_details in ((["System Manager"], True), (["Customer"], False)):
			with self.subTest(roles=roles), patch("crm.api.hfr.frappe.get_roles", return_value=roles):
				result = _get_external_provisioning_status(
					"https://deploy.example.test", "service-key", "service-secret", "FID-99-TEST-1"
				)
				self.assertEqual(result["status"], "Error")
				self.assertEqual("error_details" in result, expect_details)
