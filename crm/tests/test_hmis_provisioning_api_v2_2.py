"""HMIS setup service provisioning API v2.2: idempotent re-posts and the FID format.

Decisions V22-A to V22-E: _bmad-output/hmis-provisioning/implementation-artifacts/
party-review-provisioning-api-v2-2-2026-11-01.md
"""

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.hfr import (
	_build_external_provisioning_payload,
	_deploy_not_queued_key,
	_get_external_provisioning_status,
	_is_valid_fid,
	_provisioning_journey,
)
from crm.tests.test_hmis_provisioning_api_v2_0 import FID, NOW, TestProvisioningApiV20Submit, _untranslated


@patch("crm.api.hfr.frappe.get_hooks", return_value=[])
@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
@patch("crm.api.hfr.frappe.cache")
@patch("crm.api.hfr._get_external_provisioning_status")
@patch("crm.api.hfr.requests.post")
class TestIdempotentRepost(TestProvisioningApiV20Submit):
	"""V22-B: a re-post never starts deployment (v2.2 §4.5)."""

	# The v2.0 cases already run in their own module.
	for _name in [name for name in dir(TestProvisioningApiV20Submit) if name.startswith("test_")]:
		locals()[_name] = None
	del _name

	def test_idempotent_draft_with_auto_deploy_waits_for_the_team(self, mock_post, mock_status, mock_cache, *_):
		body = {"message": {"accepted": True, "idempotent": True, "facility_setup": "SETUP-0001", "status": "Draft"}}
		result, cache = self._submit(mock_post, mock_status, mock_cache, body)
		self.assertEqual(result["submission"]["state"], "already_exists")
		self.assertIs(result["submission"]["deploy_queued"], False)
		self.assertTrue(result["deploy_not_queued"])
		cache.set_value.assert_called_once_with(_deploy_not_queued_key(FID), 1, expires_in_sec=7 * 24 * 3600)
		cache.delete_value.assert_not_called()
		with patch("crm.api.hfr._", new=_untranslated):
			journey = _provisioning_journey({**result, "auto_deploy": True}, now=NOW)
		self.assertIn("did not start automatically", journey["detail"])
		self.assertNotIn("Deployment starts automatically", journey["detail"])

	def test_idempotent_draft_under_manual_review_is_not_flagged(self, mock_post, mock_status, mock_cache, *_):
		body = {"message": {"accepted": True, "idempotent": True, "facility_setup": "SETUP-0001", "status": "Draft"}}
		result, cache = self._submit(mock_post, mock_status, mock_cache, body, auto_deploy=False)
		self.assertIsNone(result["submission"]["deploy_queued"])
		self.assertNotIn("deploy_not_queued", result)
		cache.set_value.assert_not_called()

	def test_idempotent_record_already_deploying_is_not_flagged(self, mock_post, mock_status, mock_cache, *_):
		body = {"message": {"accepted": True, "idempotent": True, "facility_setup": "SETUP-0001", "status": "In Progress"}}
		result, cache = self._submit(mock_post, mock_status, mock_cache, body)
		self.assertIsNone(result["submission"]["deploy_queued"])
		cache.set_value.assert_not_called()


class TestFidFormat(UnitTestCase):
	"""V22-C: the service's FR code format is checked before any call."""

	def test_fid_pattern_matches_the_service(self):
		for fid in ("FID-98-123456-7", "fid-01-ABC_1", " FID-99-TEST-1 "):
			self.assertTrue(_is_valid_fid(fid), fid)
		for fid in ("", None, "FID-1-2", "MFL-12345", "FID-29-", "FID-29-12 34", "XFID-29-1"):
			self.assertFalse(_is_valid_fid(fid), fid)

	@patch("crm.api.hfr.requests.get")
	def test_malformed_fid_is_not_sent_to_the_status_api(self, mock_get):
		with patch("crm.api.hfr._", new=_untranslated):
			result = _get_external_provisioning_status("https://deploy.example.test", "key", "secret", "12345")
		mock_get.assert_not_called()
		self.assertEqual(result["status"], "unavailable")
		self.assertEqual(result["error_code"], "invalid_fid")
		self.assertFalse(result["retryable"])

	@patch("crm.api.hfr.requests.get")
	def test_valid_fid_still_calls_the_status_api(self, mock_get):
		response = MagicMock(status_code=200, headers={})
		response.json.return_value = {"message": {"status": "Draft", "progress": 0}}
		mock_get.return_value = response
		with patch("crm.api.hfr.frappe.cache") as mock_cache:
			mock_cache.return_value.get_value.return_value = None
			_get_external_provisioning_status("https://deploy.example.test", "key", "secret", FID)
		mock_get.assert_called_once()

	def test_payload_keeps_the_same_fid_rule(self):
		source = {
			"fid": "FID-1",
			"licence": "LIC-TEST-1",
			"admin_email": "admin@example.test",
			"admin_name": "Facility Admin",
			"admin_mobile": "+254700000001",
		}
		_, missing = _build_external_provisioning_payload(source)
		self.assertEqual(missing, ["valid fid"])
		_, missing = _build_external_provisioning_payload({**source, "fid": FID})
		self.assertEqual(missing, [])

	def test_payload_never_carries_v2_1_billing_fields(self):
		"""V22-A / v2.1: billing metering is not part of the setup request."""
		payload, _ = _build_external_provisioning_payload(
			{
				"fid": FID,
				"licence": "LIC-TEST-1",
				"admin_email": "Admin@Example.test",
				"admin_name": "Facility Admin",
				"admin_mobile": "+254700000001",
				"tokens_awarded": 100,
				"billing_model": "Token",
				"token_expiry_date": "2027-01-01",
				"license_expiry_date": "2027-01-01",
			}
		)
		for field in ("tokens_awarded", "billing_model", "token_expiry_date", "license_expiry_date"):
			self.assertNotIn(field, payload)
		self.assertEqual(payload["admin_email"], "admin@example.test")
