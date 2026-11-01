"""HMIS setup service provisioning API v2.0: completion, steps, auto-deploy and status display.

Decisions D-A to D-L: _bmad-output/hmis-provisioning/implementation-artifacts/
party-review-provisioning-api-v2-0-2026-11-01.md
"""

from contextlib import nullcontext
from datetime import datetime
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.hfr import (
	_auto_deploy_enabled,
	_auto_submit_external_provisioning,
	_deploy_not_queued_key,
	_get_external_provisioning_status,
	_owner_user_failed,
	_provisioning_journey,
	_reported_setup_details,
	get_hfr_settings,
)

NOW = datetime(2026, 11, 1, 10, 0, 0)
# Synthetic values on the reserved .test domain (RFC 2606); never real contacts or sites.
FID = "FID-99-TEST-1"
ADMIN = "admin@example.test"
BACKEND_URL = "https://backend.example.test"
FRONTEND_URL = "https://facility.example.test"
PASSWORD = "temporary-secret"
STEP_NAMES = (
	"Role Profiles",
	"Company",
	"Owner User (retry)",
	"Warehouses",
	"Practitioners",
	"Service Units",
	"Laboratories",
	"Service Unit Access",
	"Company Settings",
	"Final Configuration",
	"API Gateway Credentials",
	"Verification Pass",
)


def _steps(done=0, current=None, current_status="Running"):
	"""Twelve v2.0 steps: the first `done` are Done, then `current_status` at `current`, the rest Pending."""
	steps = []
	for index, name in enumerate(STEP_NAMES):
		status = "Done" if index < done else current_status if index == current else "Pending"
		error = "internal step failure detail" if status == "Failed" else None
		steps.append(
			{"name": name, "status": status, "started_on": None, "finished_on": None, "error": error}
		)
	return steps


def _payload(
	status="Provisioning",
	deployment=False,
	owner=False,
	steps=None,
	login_status="Created",
	email_sent=False,
	error=None,
	login_url=FRONTEND_URL,
	deployed_on=None,
):
	"""A v2.0 get_provision_status message."""
	return {
		"status": status,
		"progress": 100 if deployment else 45,
		"log": "Step 1/12 Role Profiles: Done",
		"error": error,
		"last_attempt": "2026-11-01 09:40:00",
		"fid": FID,
		"facility_name": "Example Health Centre",
		"facility_setup": "SETUP-0001",
		"deployed_on": deployed_on,
		"hmis_instance": "Example Instance",
		"target": {"instance": "Example Instance", "url": BACKEND_URL, "frontend_url": FRONTEND_URL},
		"login": {
			"email": ADMIN,
			"url": login_url,
			"status": login_status,
			"email_sent": email_sent,
			"password": PASSWORD,
		},
		"steps": steps
		if steps is not None
		else _steps(done=12 if deployment else 5, current=None if deployment else 5),
		"workflow": {"provision_source": "Auto-Provision API"},
		"completion": {
			"deployment_complete": deployment,
			"owner_user_complete": owner,
			"fully_provisioned": deployment and owner,
		},
	}


def _status(payload, **extra):
	"""The payload parsed the way _get_external_provisioning_status stores it."""
	reported = _reported_setup_details(payload)
	return {
		"status": payload["status"],
		"progress": payload["progress"],
		"has_error": bool(payload.get("error")),
		"owner_user_failed": _owner_user_failed(payload, reported),
		"reported": reported,
		**extra,
	}


def _untranslated(text, *args, **kwargs):
	return text


def _states(journey):
	return [step["state"] for step in journey["steps"]]


class TestProvisioningApiV20Parsing(UnitTestCase):
	def test_site_url_prefers_the_public_frontend_over_the_backend(self):
		"""D-C: target.url is the Frappe backend; users get target.frontend_url."""
		self.assertEqual(_reported_setup_details(_payload())["site_url"], FRONTEND_URL)
		self.assertEqual(_reported_setup_details(_payload(login_url=None))["site_url"], FRONTEND_URL)
		backend_only = _payload(login_url=None)
		backend_only["target"].pop("frontend_url")
		self.assertEqual(_reported_setup_details(backend_only)["site_url"], BACKEND_URL)

	def test_completion_and_steps_are_kept_without_step_errors_or_password(self):
		"""D-G, D-L: names and states only; the password and step error text never leave parsing."""
		payload = _payload(steps=_steps(done=6, current=6, current_status="Failed"))
		reported = _reported_setup_details(payload)
		self.assertEqual(
			reported["completion"],
			{"deployment_complete": False, "owner_user_complete": False, "fully_provisioned": False},
		)
		self.assertEqual(len(reported["deploy_steps"]), 12)
		self.assertEqual(reported["deploy_steps"][6], {"name": "Laboratories", "status": "failed"})
		serialized = frappe.as_json(_provisioning_journey(_status(payload), now=NOW)) + frappe.as_json(
			reported
		)
		self.assertNotIn(PASSWORD, serialized)
		self.assertNotIn("internal step failure detail", serialized)

	def test_owner_user_failure_is_detected_from_completion_or_the_owner_step(self):
		"""D-H."""
		after_deploy = _payload(
			status="Failed", deployment=True, owner=False, error="Owner user retries exhausted"
		)
		self.assertTrue(_owner_user_failed(after_deploy, _reported_setup_details(after_deploy)))
		owner_step = _payload(
			status="Failed", steps=_steps(done=2, current=2, current_status="Failed"), error="failed"
		)
		self.assertTrue(_owner_user_failed(owner_step, _reported_setup_details(owner_step)))
		other_step = _payload(
			status="Failed", steps=_steps(done=3, current=3, current_status="Failed"), error="failed"
		)
		self.assertFalse(_owner_user_failed(other_step, _reported_setup_details(other_step)))


class TestProvisioningApiV20Journey(UnitTestCase):
	def test_live_only_when_fully_provisioned(self):
		"""D-A: Deployed or progress 100 alone is not ready."""
		live = _provisioning_journey(
			_status(_payload(status="Deployed", deployment=True, owner=True)), now=NOW
		)
		self.assertEqual(live["phase"], "live")
		self.assertEqual(live["site"]["url"], FRONTEND_URL)
		self.assertIsNone(live["poll_after_seconds"])
		not_ready = _provisioning_journey(
			_status(_payload(status="Deployed", deployment=True, owner=False)), now=NOW
		)
		self.assertEqual(not_ready["phase"], "configuring")
		self.assertIsNone(not_ready["site"])

	def test_provisioning_after_deployment_is_creating_the_administrator(self):
		"""D-B."""
		journey = _provisioning_journey(
			_status(_payload(status="Provisioning", deployment=True, owner=False)), now=NOW
		)
		self.assertEqual(journey["phase"], "configuring")
		self.assertEqual(journey["headline"], "Creating your administrator account")
		self.assertEqual(_states(journey), ["done", "done", "current", "upcoming"])
		self.assertIsNone(journey["deploy_step"])  # every deployment step is done

	def test_running_step_is_named_in_plain_words(self):
		"""D-G, D-J."""
		journey = _provisioning_journey(_status(_payload(status="In Progress")), now=NOW)
		self.assertEqual(journey["phase"], "deploying")
		self.assertEqual(journey["deploy_step"]["text"], "Step 6 of 12 · Creating service units")
		self.assertEqual(journey["deploy_step"]["name"], "Service Units")
		self.assertEqual(journey["poll_after_seconds"], 60)

	def test_unknown_step_names_pass_through(self):
		steps = _steps(done=1, current=1)
		steps[1]["name"] = "Brand New Step"
		journey = _provisioning_journey(_status(_payload(status="In Progress", steps=steps)), now=NOW)
		self.assertEqual(journey["deploy_step"]["text"], "Step 2 of 12 · Brand New Step")

	def test_failed_step_says_where_deployment_stopped(self):
		payload = _payload(
			status="Failed", steps=_steps(done=6, current=6, current_status="Failed"), error="failed"
		)
		journey = _provisioning_journey(_status(payload), now=NOW)
		self.assertEqual(journey["phase"], "needs_attention")
		self.assertEqual(journey["deploy_step"]["text"], "Stopped at step 7 of 12 · Setting up laboratories")
		self.assertEqual(_states(journey), ["done", "error", "upcoming", "upcoming"])

	def test_failed_owner_step_marks_the_configure_step(self):
		payload = _payload(
			status="Failed", steps=_steps(done=2, current=2, current_status="Failed"), error="failed"
		)
		# Without the fetch-time flag too: the step alone decides the copy and the stepper.
		journey = _provisioning_journey(_status(payload, owner_user_failed=False), now=NOW)
		self.assertEqual(journey["headline"], "Administrator account needs attention")
		self.assertEqual(_states(journey), ["done", "done", "error", "upcoming"])

	def test_live_card_shows_live_since(self):
		"""D-I."""
		payload = _payload(status="Deployed", deployment=True, owner=True, deployed_on="2026-10-31 11:42:03")
		self.assertEqual(
			_provisioning_journey(_status(payload), now=NOW)["site"]["live_since"], "Live since 31 Oct 2026"
		)

	def test_waiting_phases_poll_slower(self):
		"""D-J."""
		self.assertEqual(_provisioning_journey({"status": "Draft"}, now=NOW)["poll_after_seconds"], 300)
		self.assertEqual(
			_provisioning_journey({"status": "not_submitted"}, now=NOW)["poll_after_seconds"], 300
		)

	def test_queued_copy_follows_auto_deploy(self):
		"""D-D, D-E."""
		auto = _provisioning_journey({"status": "Draft", "auto_deploy": True}, now=NOW)
		self.assertIn("starts automatically", auto["detail"])
		manual = _provisioning_journey({"status": "Draft", "auto_deploy": False}, now=NOW)
		self.assertIn("implementation team releases it", manual["detail"])
		not_queued = _provisioning_journey(
			{"status": "Draft", "auto_deploy": True, "deploy_not_queued": True}, now=NOW
		)
		self.assertIn("did not start automatically", not_queued["detail"])
		submitted = _provisioning_journey(
			{
				"status": "Draft",
				"auto_deploy": True,
				"submission": {"state": "created", "deploy_queued": False},
			},
			now=NOW,
		)
		self.assertIn("did not start automatically", submitted["detail"])

	def test_cancelled_and_paused_instance_have_their_own_copy(self):
		"""D-K."""
		cancelled = _provisioning_journey({"status": "Cancelled"}, now=NOW)
		self.assertEqual(cancelled["phase"], "needs_attention")
		self.assertEqual(cancelled["label"], "Cancelled")
		self.assertEqual(cancelled["headline"], "Setup was cancelled")
		paused = _provisioning_journey(
			{"status": "Failed", "has_error": True, "instance_blocked": True}, now=NOW
		)
		self.assertEqual(paused["headline"], "HMIS server paused")


class TestProvisioningApiV20Service(UnitTestCase):
	@patch("crm.api.hfr.frappe.cache")
	@patch("crm.api.hfr.requests.get")
	def test_status_read_flags_owner_failure_and_paused_instance(self, mock_get, mock_cache):
		mock_cache.return_value.get_value.return_value = None
		blocked = _payload(
			status="Failed",
			error="HMIS Instance 'Example Instance' is Inactive. Deployment is blocked until the instance is set to Active.",
		)
		response = MagicMock(status_code=200, headers={})
		response.json.return_value = {"message": blocked}
		mock_get.return_value = response
		result = _get_external_provisioning_status("https://deploy.example.test", "key", "secret", FID)
		self.assertTrue(result["instance_blocked"])
		self.assertFalse(result["owner_user_failed"])
		self.assertNotIn(PASSWORD, frappe.as_json(result))

	@patch("crm.api.hfr.frappe.cache")
	@patch("crm.api.hfr.requests.get")
	def test_draft_remembers_an_auto_deploy_that_was_not_queued(self, mock_get, mock_cache):
		mock_cache.return_value.get_value.return_value = 1
		response = MagicMock(status_code=200, headers={})
		response.json.return_value = {"message": _payload(status="Draft", steps=_steps())}
		mock_get.return_value = response
		result = _get_external_provisioning_status("https://deploy.example.test", "key", "secret", FID)
		self.assertTrue(result["deploy_not_queued"])
		mock_cache.return_value.get_value.assert_called_with(_deploy_not_queued_key(FID))

	def test_auto_deploy_is_on_unless_manual_review_is_switched_on(self):
		"""D-D: a missing value (existing Single record before migrate) means auto-deploy."""
		self.assertTrue(_auto_deploy_enabled(frappe._dict()))
		self.assertTrue(_auto_deploy_enabled(frappe._dict(external_provisioning_manual_review=0)))
		self.assertFalse(_auto_deploy_enabled(frappe._dict(external_provisioning_manual_review=1)))

	@patch("crm.api.hfr.frappe.has_permission", return_value=True)
	@patch("crm.api.hfr.frappe.get_single")
	def test_settings_api_returns_manual_review(self, mock_single, _perm):
		settings = MagicMock()
		settings.get.side_effect = lambda key, default=None: {"external_provisioning_manual_review": 1}.get(
			key, default
		)
		settings.get_password.return_value = None
		mock_single.return_value = settings
		self.assertEqual(get_hfr_settings()["external_provisioning_manual_review"], 1)


@patch("crm.api.hfr.frappe.get_hooks", return_value=[])
@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
@patch("crm.api.hfr.frappe.cache")
@patch("crm.api.hfr._get_external_provisioning_status")
@patch("crm.api.hfr.requests.post")
class TestProvisioningApiV20Submit(UnitTestCase):
	def _request(self, auto_deploy=True):
		return {
			"fid": FID,
			"licence": "LIC-TEST-1",
			"admin_email": ADMIN,
			"admin_name": "Facility Admin",
			"admin_mobile": "+254700000001",
			"auto_deploy": auto_deploy,
		}

	def _submit(self, mock_post, mock_status, mock_cache, body, status_code=200, auto_deploy=True):
		cache = MagicMock()
		cache.get_value.return_value = None
		mock_cache.return_value = cache
		response = MagicMock(status_code=status_code, headers={"X-Correlation-Id": "corr-v2"})
		response.json.return_value = body
		mock_post.return_value = response
		not_submitted = {"configured": True, "status": "not_submitted", "progress": 0}
		mock_status.side_effect = [not_submitted, {"configured": True, "status": "Draft", "progress": 0}]
		# Translation reads through frappe.cache, which is mocked here.
		with patch("crm.api.hfr._", new=_untranslated):
			result = _auto_submit_external_provisioning(
				"https://deploy.example.test",
				"key",
				"secret",
				FID,
				dict(not_submitted),
				self._request(auto_deploy),
				[],
			)
		return result, cache

	def test_auto_deploy_is_sent_and_a_queued_deploy_is_recorded(
		self, mock_post, mock_status, mock_cache, *_
	):
		body = {
			"message": {
				"accepted": True,
				"facility_setup": "SETUP-0001",
				"status": "Draft",
				"auto_deploy_queued": True,
				"owner_user_queued": True,
				"message": "Deployment queued (auto_deploy).",
			}
		}
		result, cache = self._submit(mock_post, mock_status, mock_cache, body)
		self.assertIs(mock_post.call_args.kwargs["json"]["auto_deploy"], True)
		self.assertEqual(result["submission"]["state"], "created")
		self.assertIs(result["submission"]["deploy_queued"], True)
		self.assertIn("starts automatically", result["submission"]["message"])
		cache.set_value.assert_not_called()
		cache.delete_value.assert_called_once_with(_deploy_not_queued_key(FID))

	def test_enqueue_warning_is_recorded_and_never_shown_raw(self, mock_post, mock_status, mock_cache, *_):
		"""D-E."""
		body = {
			"message": {
				"accepted": True,
				"facility_setup": "SETUP-0001",
				"status": "Draft",
				"auto_deploy_queued": False,
				"owner_user_queued": True,
				"message": "WARNING: auto_deploy requested but deployment could not be queued: worker down",
			}
		}
		with patch("crm.api.hfr.frappe.log_error") as mock_log:
			result, cache = self._submit(mock_post, mock_status, mock_cache, body)
		self.assertIs(result["submission"]["deploy_queued"], False)
		self.assertTrue(result["deploy_not_queued"])
		self.assertNotIn("WARNING", frappe.as_json(result))
		cache.set_value.assert_called_once_with(_deploy_not_queued_key(FID), 1, expires_in_sec=7 * 24 * 3600)
		cache.delete_value.assert_not_called()
		mock_log.assert_called_once()
		with patch("crm.api.hfr._", new=_untranslated):
			journey = _provisioning_journey({**result, "auto_deploy": True}, now=NOW)
		self.assertIn("did not start automatically", journey["detail"])

	def test_manual_review_sends_auto_deploy_false(self, mock_post, mock_status, mock_cache, *_):
		body = {
			"message": {
				"accepted": True,
				"facility_setup": "SETUP-0001",
				"status": "Draft",
				"auto_deploy_queued": False,
				"message": "Facility Setup document created (Draft). Review and deploy it from the Setup app UI.",
			}
		}
		result, cache = self._submit(mock_post, mock_status, mock_cache, body, auto_deploy=False)
		self.assertIs(mock_post.call_args.kwargs["json"]["auto_deploy"], False)
		self.assertIsNone(result["submission"]["deploy_queued"])
		self.assertNotIn("Setup app UI", result["submission"]["message"])
		cache.set_value.assert_not_called()

	def test_idempotent_response_is_already_exists(self, mock_post, mock_status, mock_cache, *_):
		body = {
			"message": {
				"accepted": True,
				"idempotent": True,
				"facility_setup": "SETUP-0001",
				"status": "Provisioning",
			}
		}
		result, cache = self._submit(mock_post, mock_status, mock_cache, body)
		self.assertEqual(result["submission"]["state"], "already_exists")
		self.assertIsNone(result["submission"]["deploy_queued"])
		cache.set_value.assert_not_called()

	def test_registry_outage_is_retryable_not_a_cached_rejection(
		self, mock_post, mock_status, mock_cache, *_
	):
		"""D-F."""
		body = {
			"exc_type": "ValidationError",
			"exception": "frappe.exceptions.ValidationError: Facility registry lookup failed (HTTP 503): upstream unavailable",
		}
		with patch("crm.api.hfr.frappe.log_error"):
			result, cache = self._submit(mock_post, mock_status, mock_cache, body, status_code=417)
		self.assertEqual(result["submission"]["state"], "unknown")
		self.assertTrue(result["submission"]["retryable"])
		self.assertIn("Health Facility Registry", result["submission"]["message"])
		cache.set_value.assert_not_called()

	def test_registry_miss_is_still_a_rejection(self, mock_post, mock_status, mock_cache, *_):
		body = {
			"exc_type": "ValidationError",
			"exception": "frappe.exceptions.ValidationError: No facility found in the registry for FR code 'FID-99-TEST-1'.",
		}
		with patch("crm.api.hfr.frappe.log_error"):
			result, cache = self._submit(mock_post, mock_status, mock_cache, body, status_code=417)
		self.assertEqual(result["submission"]["state"], "error")
		self.assertFalse(result["submission"]["retryable"])
		self.assertTrue(cache.set_value.called)


def _live_status(**login_overrides):
	"""A fully provisioned v2.0 status whose owner email was not delivered, as CRM resolves it."""
	payload = _payload(status="Deployed", deployment=True, owner=True)
	payload["login"].update(login_overrides)
	return {**_status(payload), "fid": FID, "configured": True, "source": "external_setup"}


@patch("crm.api.hfr.frappe.db.commit")
@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
@patch("crm.api.hfr._typical_setup_minutes", return_value=60)
class TestOwnerPasswordOneTimeView(UnitTestCase):
	"""P-1 to P-9: the temporary password is shown once, to the HMIS owner only, and never polled."""

	def setUp(self):
		frappe.db.delete("CRM HMIS Credential View", {"fid": FID})

	def tearDown(self):
		frappe.db.delete("CRM HMIS Credential View", {"fid": FID})

	def _status_for(self, session_email, status=None):
		with (
			patch("crm.api.hfr._resolve_provisioning_status", return_value=status or _live_status()),
			patch("crm.api.hfr._session_email", return_value=session_email),
		):
			from crm.api.hfr import _get_provisioning_status

			return _get_provisioning_status("TEST-MFL-1", False)

	def _reveal(self, session_email, login=None, status=None):
		fetched = {"email": ADMIN, "status": "Created", "email_sent": False, "password": PASSWORD}
		with (
			patch("crm.api.hfr._resolve_provisioning_status", return_value=status or _live_status()),
			patch("crm.api.hfr._session_email", return_value=session_email),
			patch(
				"crm.api.hfr._fetch_owner_login", return_value=fetched if login is None else login
			) as fetch,
		):
			from crm.api.hfr import reveal_hmis_owner_password

			return reveal_hmis_owner_password("TEST-MFL-1"), fetch

	def test_polled_status_offers_the_view_to_the_owner_without_the_password(self, *_):
		result = self._status_for(ADMIN)
		credentials = result["journey"]["site"]["credentials"]
		self.assertTrue(credentials["password_available"])
		self.assertTrue(credentials["can_view"])
		self.assertEqual(credentials["owner_email_masked"], "a***@e***.test")
		self.assertNotIn(PASSWORD, frappe.as_json(result))

	def test_other_portal_users_cannot_view(self, *_):
		credentials = self._status_for("partner@example.test")["journey"]["site"]["credentials"]
		self.assertTrue(credentials["password_available"])
		self.assertFalse(credentials["can_view"])
		with self.assertRaises(frappe.PermissionError):
			self._reveal("partner@example.test")
		self.assertFalse(frappe.db.exists("CRM HMIS Credential View", {"fid": FID}))

	def test_owner_sees_the_password_once_and_the_view_is_recorded(self, *_):
		result, fetch = self._reveal(ADMIN)
		self.assertEqual(result["password"], PASSWORD)
		self.assertEqual(result["email"], ADMIN)
		fetch.assert_called_once_with(FID)
		view = frappe.get_all(
			"CRM HMIS Credential View",
			filters={"fid": FID},
			fields=["status", "owner_email", "viewed_by", "facility_setup"],
		)
		self.assertEqual(
			view,
			[
				{
					"status": "Viewed",
					"owner_email": ADMIN,
					"viewed_by": frappe.session.user,
					"facility_setup": "SETUP-0001",
				}
			],
		)
		self.assertNotIn(
			PASSWORD,
			frappe.as_json(frappe.get_all("CRM HMIS Credential View", fields=["*"], filters={"fid": FID})),
		)
		with self.assertRaisesRegex(frappe.ValidationError, "already viewed"):
			self._reveal(ADMIN)
		credentials = self._status_for(ADMIN)["journey"]["site"]["credentials"]
		self.assertFalse(credentials["can_view"])
		self.assertTrue(credentials["viewed_on"])
		self.assertTrue(credentials["viewed_by_you"])

	def test_support_can_re_arm_one_more_view(self, *_):
		self._reveal(ADMIN)
		name = frappe.db.get_value("CRM HMIS Credential View", {"fid": FID}, "name")
		frappe.db.set_value("CRM HMIS Credential View", name, "status", "Re-armed")
		result, _fetch = self._reveal(ADMIN)
		self.assertEqual(result["password"], PASSWORD)
		self.assertEqual(frappe.db.count("CRM HMIS Credential View", {"fid": FID}), 2)

	def test_nothing_is_recorded_when_the_password_cannot_be_fetched(self, *_):
		for login in (
			{},
			{"email": ADMIN, "email_sent": True, "password": PASSWORD},
			{"email": "other@example.test", "password": PASSWORD},
		):
			with (
				self.subTest(login=login),
				self.assertRaisesRegex(frappe.ValidationError, "not available right now"),
			):
				self._reveal(ADMIN, login=login)
		self.assertFalse(frappe.db.exists("CRM HMIS Credential View", {"fid": FID}))

	def test_no_view_before_the_site_is_live_or_once_the_email_was_sent(self, *_):
		configuring = _payload(status="Provisioning", deployment=True, owner=False)
		not_live = {**_status(configuring), "fid": FID}
		with self.assertRaisesRegex(frappe.ValidationError, "No temporary password"):
			self._reveal(ADMIN, status=not_live)
		sent = _live_status(email_sent=True)
		self.assertFalse(self._status_for(ADMIN, sent)["journey"]["site"]["credentials"]["can_view"])
		with self.assertRaisesRegex(frappe.ValidationError, "No temporary password"):
			self._reveal(ADMIN, status=sent)
