from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.facility_onboarding import _queue_hmis_provisioning
from crm.api.hfr import (
	_get_provisioning_status,
	_provisioning_journey,
	_reported_setup_details,
	_safe_site_url,
	_typical_setup_minutes,
	provision_onboarded_facility,
)

NOW = datetime(2026, 10, 25, 10, 0, 0)
# Synthetic values on the reserved .test domain (RFC 2606); never real contacts or sites.
SITE_HOST = "site.example.test"
SITE_URL = "https://" + SITE_HOST
ADMIN = "admin@example.test"
PORTAL_USER = "portal-user@example.test"
MFL = "TEST-MFL-1"


def _states(journey):
	return [step["state"] for step in journey["steps"]]


class TestProvisioningJourney(UnitTestCase):
	def test_live_site_shows_https_url_and_sign_in_steps(self):
		journey = _provisioning_journey(
			{"status": "Deployed", "reported": {"site_url": SITE_HOST, "admin_username": ADMIN}},
			now=NOW,
		)
		self.assertEqual(journey["phase"], "live")
		self.assertFalse(journey["poll"])
		self.assertEqual(journey["progress"], 100)
		self.assertEqual(_states(journey), ["done"] * 4)
		self.assertEqual(journey["site"]["url"], SITE_URL)
		self.assertEqual(journey["site"]["admin_email"], ADMIN)
		self.assertIn(SITE_URL, journey["site"]["instructions"][0])
		self.assertIn(ADMIN, journey["site"]["instructions"][1])
		self.assertIsNone(journey["estimate"])

	def test_live_site_without_reported_url_uses_verified_admin_contact(self):
		journey = _provisioning_journey({"status": "live"}, admin_contact={"admin_email": ADMIN}, now=NOW)
		self.assertIsNone(journey["site"]["url"])
		self.assertEqual(journey["site"]["admin_email"], ADMIN)
		self.assertIn("welcome email", journey["site"]["instructions"][0])

	def test_unsafe_site_urls_are_never_shown(self):
		for value in (
			"javascript:alert(1)",
			"http://" + SITE_HOST,
			"https://user:pass@" + SITE_HOST,
			"ftp://" + SITE_HOST,
			"not a url",
			"",
		):
			self.assertIsNone(_safe_site_url(value), value)
		self.assertEqual(_safe_site_url(SITE_URL + "/"), SITE_URL)
		self.assertEqual(_safe_site_url(SITE_HOST + ":8443/app"), SITE_URL + ":8443/app")

	def test_deploying_estimate_extrapolates_from_progress(self):
		journey = _provisioning_journey(
			{"status": "Deploying", "progress": 50, "reported": {"started_at": str(NOW - timedelta(minutes=10))}},
			now=NOW,
		)
		self.assertEqual(journey["phase"], "deploying")
		self.assertTrue(journey["poll"])
		self.assertEqual(_states(journey), ["done", "current", "upcoming", "upcoming"])
		self.assertEqual(journey["estimate"]["source"], "progress")
		self.assertEqual(journey["estimate"]["minutes"], 10)

	def test_service_reported_eta_wins_over_other_estimates(self):
		journey = _provisioning_journey(
			{"status": "In Progress", "progress": 10, "last_attempt": str(NOW - timedelta(minutes=5)), "reported": {"eta_minutes": 7.2}},
			now=NOW,
		)
		self.assertEqual(journey["estimate"]["source"], "service")
		self.assertEqual(journey["estimate"]["minutes"], 8)
		completion = _provisioning_journey(
			{"status": "Deploying", "reported": {"estimated_completion": str(NOW + timedelta(minutes=95))}}, now=NOW
		)
		self.assertEqual(completion["estimate"]["minutes"], 95)
		self.assertIn("1 h 35 min", completion["estimate"]["label"])

	def test_typical_estimate_counts_down_then_reports_overdue(self):
		fresh = _provisioning_journey({"status": "Draft"}, typical_minutes=30, now=NOW)
		self.assertEqual(fresh["phase"], "queued")
		self.assertEqual(fresh["estimate"], {"minutes": 30, "source": "typical", "overdue": False, "label": fresh["estimate"]["label"]})
		started = _provisioning_journey({"status": "Draft", "last_attempt": str(NOW - timedelta(minutes=12))}, typical_minutes=30, now=NOW)
		self.assertEqual(started["estimate"]["minutes"], 18)
		late = _provisioning_journey({"status": "Draft", "last_attempt": str(NOW - timedelta(minutes=45))}, typical_minutes=30, now=NOW)
		self.assertTrue(late["estimate"]["overdue"])
		self.assertIsNone(late["estimate"]["minutes"])
		self.assertIsNone(_provisioning_journey({"status": "Draft"}, typical_minutes=0, now=NOW)["estimate"])

	def test_phases_for_requests_failures_and_identity_problems(self):
		preparing = _provisioning_journey({"status": "not_submitted"}, now=NOW)
		self.assertEqual((preparing["phase"], preparing["poll"]), ("preparing", True))
		self.assertEqual(_states(preparing), ["current", "upcoming", "upcoming", "upcoming"])
		self.assertIsNone(_provisioning_journey({"status": "not_submitted", "progress": 0}, now=NOW)["progress"])

		created = _provisioning_journey({"status": "Draft", "submission": {"state": "created"}}, now=NOW)
		self.assertEqual(created["phase"], "queued")

		# Real setup-service status once a draft has been reviewed.
		approved = _provisioning_journey({"status": "Approved", "progress": 0.0}, now=NOW)
		self.assertEqual(
			(approved["phase"], approved["label"], approved["headline"], approved["progress"]),
			("queued", "Approved", "Approved for deployment", None),
		)

		blocked = _provisioning_journey(
			{"status": "not_submitted", "submission": {"state": "blocked", "message": "Missing licence"}}, now=NOW
		)
		self.assertEqual((blocked["phase"], blocked["poll"], blocked["progress"]), ("blocked", False, None))
		# The missing fields are shown once, in the submission panel, not repeated in the header.
		self.assertNotIn("Missing licence", blocked["detail"])
		self.assertEqual(_states(blocked), ["error", "upcoming", "upcoming", "upcoming"])

		failed = _provisioning_journey({"status": "Error", "has_error": True}, now=NOW)
		self.assertEqual(failed["phase"], "needs_attention")
		self.assertEqual(_states(failed), ["done", "error", "upcoming", "upcoming"])

		configuring = _provisioning_journey({"status": "setting_up"}, now=NOW)
		self.assertEqual(_states(configuring), ["done", "done", "current", "upcoming"])

		for raw, phase in (("not_linked", "not_linked"), ("not_configured", "not_configured"), ("unavailable", "unavailable"), ("route_not_provisioned", "not_configured")):
			journey = _provisioning_journey({"status": raw}, now=NOW)
			self.assertEqual((journey["phase"], journey["steps"], journey["poll"]), (phase, [], False))

	def test_unrecognized_status_on_an_existing_record_is_shown_as_in_progress(self):
		journey = _provisioning_journey({"status": "Building containers"}, now=NOW)
		self.assertEqual(journey["phase"], "deploying")
		self.assertIn("Building containers", journey["detail"])

	def test_reported_details_accept_known_aliases_only(self):
		self.assertEqual(
			_reported_setup_details({"site_name": " %s " % SITE_HOST, "admin_email": ADMIN, "minutes_remaining": 4, "secret": "x", "eta": ""}),
			{"site_url": SITE_HOST, "admin_username": ADMIN, "eta_minutes": 4},
		)

	def test_typical_minutes_defaults_and_never_goes_negative(self):
		self.assertEqual(_typical_setup_minutes(frappe._dict()), 60)
		self.assertIn("1 h", _provisioning_journey({"status": "Draft"}, typical_minutes=60, now=NOW)["estimate"]["label"])
		self.assertEqual(_typical_setup_minutes(frappe._dict(provisioning_typical_minutes=-5)), 0)
		self.assertEqual(_typical_setup_minutes(frappe._dict(provisioning_typical_minutes=45)), 45)

	@patch("crm.api.hfr._typical_setup_minutes", return_value=30)
	@patch("crm.api.hfr._portal_admin_contact", return_value={"admin_email": ADMIN})
	@patch("crm.api.hfr._resolve_provisioning_status", return_value={"status": "Deployed", "reported": {"site_url": SITE_HOST}})
	def test_status_response_carries_journey_and_live_admin(self, mock_resolve, mock_admin, _typical):
		result = _get_provisioning_status(MFL, ensure_missing_draft=True)
		mock_resolve.assert_called_once_with(MFL, True)
		mock_admin.assert_called_once_with(MFL)
		self.assertEqual(result["journey"]["site"]["url"], SITE_URL)
		self.assertEqual(result["journey"]["site"]["admin_email"], ADMIN)

	@patch("crm.api.hfr._typical_setup_minutes", return_value=30)
	@patch("crm.api.hfr._portal_admin_contact")
	@patch("crm.api.hfr._resolve_provisioning_status", return_value={"status": "Draft"})
	def test_admin_lookup_only_runs_for_live_sites(self, _resolve, mock_admin, _typical):
		self.assertEqual(_get_provisioning_status(MFL, ensure_missing_draft=False)["journey"]["phase"], "queued")
		mock_admin.assert_not_called()


class TestProvisioningAfterOnboarding(UnitTestCase):
	@patch("crm.api.hfr.frappe.set_user")
	@patch("crm.api.hfr._get_provisioning_status", return_value={"status": "Draft", "submission": {"state": "created"}, "journey": {"phase": "queued"}})
	def test_job_ensures_as_the_portal_user_and_restores_the_session(self, mock_status, mock_set_user):
		with patch.dict(frappe.session, {"user": "Guest"}):
			self.assertEqual(provision_onboarded_facility(MFL, PORTAL_USER), {"status": "Draft", "phase": "queued"})
		mock_status.assert_called_once_with(MFL, ensure_missing_draft=True)
		self.assertEqual([call.args[0] for call in mock_set_user.call_args_list], [PORTAL_USER, "Guest"])

	@patch("crm.api.hfr.frappe.log_error")
	@patch("crm.api.hfr.frappe.set_user")
	@patch("crm.api.hfr._get_provisioning_status", side_effect=RuntimeError("TA down"))
	def test_job_failure_is_logged_not_raised(self, _status, mock_set_user, mock_log):
		with patch.dict(frappe.session, {"user": "Guest"}):
			self.assertIsNone(provision_onboarded_facility(MFL, PORTAL_USER))
		mock_log.assert_called_once()
		self.assertEqual(mock_set_user.call_args_list[-1].args[0], "Guest")

	@patch("crm.api.facility_onboarding.frappe.enqueue")
	def test_onboarding_queues_one_deduplicated_job_per_facility_after_commit(self, mock_enqueue):
		result = _queue_hmis_provisioning(PORTAL_USER, [MFL, "", MFL, "TEST-MFL-2"])
		self.assertEqual(result, {"state": "started", "facilities": [MFL, "TEST-MFL-2"]})
		self.assertEqual(mock_enqueue.call_count, 2)
		kwargs = mock_enqueue.call_args_list[0].kwargs
		self.assertEqual(mock_enqueue.call_args_list[0].args[0], "crm.api.hfr.provision_onboarded_facility")
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertTrue(kwargs["deduplicate"])
		self.assertEqual(kwargs["job_id"], "crm-hmis-provision:" + MFL)
		self.assertEqual((kwargs["mfl_code"], kwargs["portal_user"]), (MFL, PORTAL_USER))

	@patch("crm.api.facility_onboarding.frappe.log_error")
	@patch("crm.api.facility_onboarding.frappe.enqueue", side_effect=ConnectionError("redis down"))
	def test_enqueue_failure_never_blocks_onboarding(self, _enqueue, mock_log):
		self.assertEqual(_queue_hmis_provisioning(PORTAL_USER, [MFL]), {"state": "deferred", "facilities": []})
		mock_log.assert_called_once()


def _v2_status(status="Deployed", login_status="created", email_sent=False, password=True, error=None):
	"""A setup service v2.1 get_provision_status payload, parsed as CRM stores it."""
	payload = {
		"status": status,
		"progress": 100 if status == "Deployed" else 21,
		"error": error,
		"target": {"instance": "instance", "url": SITE_URL},
		"login": {"email": ADMIN.upper(), "url": SITE_URL, "status": login_status, "email_sent": email_sent},
	}
	if password:
		payload["login"]["password"] = "temporary-secret"
	return {
		"status": status,
		"progress": payload["progress"],
		"has_error": bool(error),
		"owner_user_failed": "[owner user]" in (error or "").casefold(),
		"reported": _reported_setup_details(payload),
	}


class TestOwnerLoginJourney(UnitTestCase):
	def test_status_parsing_keeps_login_summary_but_never_the_password(self):
		reported = _v2_status()["reported"]
		self.assertEqual(reported["site_url"], SITE_URL)
		self.assertEqual(reported["admin_username"], ADMIN)
		self.assertEqual(
			reported["owner_login"],
			{"email": ADMIN, "status": "created", "email_sent": False},
		)
		self.assertNotIn("temporary-secret", frappe.as_json(reported))

	def test_deployed_is_live_only_once_the_owner_login_exists(self):
		for login_status in ("Created", "Activated", "Skipped"):
			journey = _provisioning_journey(_v2_status(login_status=login_status), now=NOW)
			self.assertEqual(journey["phase"], "live", login_status)

	def test_deployed_with_pending_owner_login_keeps_configuring(self):
		journey = _provisioning_journey(_v2_status(login_status=None, password=False), now=NOW)
		self.assertEqual(journey["phase"], "configuring")
		self.assertTrue(journey["poll"])
		self.assertEqual(journey["headline"], "Creating your administrator account")
		self.assertEqual(_states(journey), ["done", "done", "current", "upcoming"])

	def test_failed_owner_login_needs_attention_at_the_configure_step(self):
		journey = _provisioning_journey(_v2_status(login_status="Failed", password=False), now=NOW)
		self.assertEqual(journey["phase"], "needs_attention")
		self.assertEqual(_states(journey), ["done", "done", "error", "upcoming"])
		self.assertEqual(journey["headline"], "Administrator account needs attention")

	def test_failed_owner_user_deploy_step_marks_configure_not_deploy(self):
		status = _v2_status(status="Failed", login_status=None, password=False, error="[Owner User] FAILED: target unreachable")
		journey = _provisioning_journey(status, now=NOW)
		self.assertEqual(_states(journey), ["done", "done", "error", "upcoming"])
		other = _provisioning_journey(_v2_status(status="Failed", login_status=None, password=False, error="Warehouses failed"), now=NOW)
		self.assertEqual(_states(other), ["done", "error", "upcoming", "upcoming"])

	def test_in_progress_owner_retry_step_is_deploying(self):
		journey = _provisioning_journey(_v2_status(status="In Progress", login_status=None, password=False), now=NOW)
		self.assertEqual(journey["phase"], "deploying")

	def test_undelivered_credentials_point_to_forgot_password(self):
		site = _provisioning_journey(_v2_status(), now=NOW)["site"]
		self.assertEqual(site["admin_email"], ADMIN)
		self.assertNotIn("credentials", site)
		self.assertIn("could not be delivered", site["instructions"][2])
		self.assertIn("Forgot password", site["instructions"][2])
		self.assertNotIn("temporary-secret", frappe.as_json(site))

	def test_delivered_and_activated_logins_explain_the_password_source(self):
		sent = _provisioning_journey(_v2_status(email_sent=True, password=False), now=NOW)["site"]
		self.assertIn("credentials email sent to " + ADMIN, sent["instructions"][2])
		activated = _provisioning_journey(_v2_status(login_status="Activated", password=False), now=NOW)["site"]
		self.assertIn("already existed", activated["instructions"][2])

	@patch("crm.api.hfr._typical_setup_minutes", return_value=60)
	@patch("crm.api.hfr._resolve_provisioning_status", side_effect=lambda *args: _v2_status())
	def test_polled_status_never_carries_the_password(self, _resolve, _typical):
		self.assertNotIn("temporary-secret", frappe.as_json(_get_provisioning_status(MFL, False)))
