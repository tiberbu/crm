"""OpenMeter as the HMIS token source (openmeter_mediator ADR-003) and FID-stamped token purchases."""

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.hfr import (
	_apply_token_source,
	_auto_submit_external_provisioning,
	_deliver_existing_site_key,
	_external_error_details,
	run_hmis_provisioning_submitted_hooks,
)
from crm.utils.token_facility import facility_fid_for_mfl, stamp_facility_fid

FID = "FID-99-TEST-1"
SITE_KEY = "omk2." + FID + "." + "s" * 43


def _payload():
	return {
		"fid": FID,
		"licence": "LIC-TEST-1",
		"tokens_awarded": 400,
		"token_expiry_date": "2027-10-21",
		"admin_email": "facility@example.test",
		"admin_name": "Facility Admin",
		"billing_model": "Token",
		"admin_mobile": "+254700000001",
	}


def _not_submitted():
	return {"configured": True, "status": "not_submitted", "progress": 0, "source": "external_setup"}


def _accepted():
	response = MagicMock()
	response.status_code = 200
	response.headers = {"X-Correlation-Id": "corr-om"}
	response.json.return_value = {
		"message": {"accepted": True, "facility_setup": "SETUP-0001", "status": "Draft"}
	}
	return response


def _hooks(key_hook=None, submitted_hook=None):
	hooks = {
		"crm_issue_hmis_metering_site_key": [key_hook] if key_hook else [],
		"crm_on_hmis_provisioning_submitted": [submitted_hook] if submitted_hook else [],
	}
	return lambda name, *args, **kwargs: hooks.get(name, [])


class TestApplyTokenSource(UnitTestCase):
	def test_off_by_default_leaves_the_payload_unchanged(self):
		payload = _payload()
		context = _apply_token_source(frappe._dict(), payload)
		self.assertEqual(payload, _payload())
		self.assertEqual(
			context, {"fid": FID, "package_tokens": 400, "token_source": "crm", "defer_package_grant": True}
		)

	def test_paid_packages_defer_their_grant_to_the_invoice(self):
		catalog = [
			{"item_code": "CV-TOKEN-FREE", "price": 0},
			{"item_code": "CV-TOKEN-STARTER", "price": 6000},
		]
		with patch("crm.api.facility_onboarding._token_packages", return_value=catalog):
			free = _apply_token_source(frappe._dict(), _payload(), package_item="CV-TOKEN-FREE")
			paid = _apply_token_source(frappe._dict(), _payload(), package_item="CV-TOKEN-STARTER")
			unknown = _apply_token_source(frappe._dict(), _payload(), package_item="CV-TOKEN-RETIRED")
		self.assertFalse(free["defer_package_grant"])
		self.assertTrue(paid["defer_package_grant"])
		self.assertTrue(unknown["defer_package_grant"])

	def test_openmeter_awards_no_tokens_in_the_payload(self):
		payload = _payload()
		with patch("crm.api.hfr.frappe.utils.get_url", return_value="https://crm.example.test/cx-portal"):
			context = _apply_token_source(frappe._dict(hmis_token_source_openmeter=1), payload)
		self.assertEqual(payload["tokens_awarded"], 0)
		self.assertEqual(payload["token_source"], "openmeter")
		self.assertEqual(payload["token_purchase_url"], "https://crm.example.test/cx-portal")
		self.assertEqual(context["package_tokens"], 400)
		self.assertEqual(context["token_source"], "openmeter")

	def test_configured_purchase_url_wins(self):
		payload = _payload()
		_apply_token_source(
			frappe._dict(
				hmis_token_source_openmeter=1, token_purchase_url=" https://shop.example.test/tokens "
			),
			payload,
		)
		self.assertEqual(payload["token_purchase_url"], "https://shop.example.test/tokens")


@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
@patch("crm.api.hfr.frappe.cache")
@patch("crm.api.hfr._get_external_provisioning_status")
@patch("crm.api.hfr.requests.post")
class TestOpenMeterProvisioningSubmit(UnitTestCase):
	def _submit(self, mock_cache, metering):
		cache = MagicMock()
		cache.get_value.return_value = None
		mock_cache.return_value = cache
		payload = _payload()
		payload.update(tokens_awarded=0, token_source="openmeter")
		return payload, _auto_submit_external_provisioning(
			"https://deploy.example.test",
			"key",
			"secret",
			FID,
			_not_submitted(),
			payload,
			[],
			metering=metering,
		)

	def test_site_key_travels_only_in_the_request(self, mock_post, mock_status, mock_cache, _lock):
		mock_post.return_value = _accepted()
		mock_status.side_effect = [_not_submitted(), {"configured": True, "status": "Draft", "progress": 0}]
		key_hook = MagicMock(return_value=SITE_KEY)
		metering = {"fid": FID, "package_tokens": 400, "token_source": "openmeter"}
		with (
			patch("crm.api.hfr.frappe.get_hooks", side_effect=_hooks("app.key_hook")),
			patch("crm.api.hfr.frappe.get_attr", return_value=key_hook),
		):
			payload, result = self._submit(mock_cache, metering)

		key_hook.assert_called_once_with(fid=FID, context=metering)
		sent = mock_post.call_args.kwargs["json"]
		self.assertEqual(sent["metering_site_key"], SITE_KEY)
		self.assertEqual(sent["tokens_awarded"], 0)
		self.assertNotIn("metering_site_key", payload)
		self.assertNotIn(SITE_KEY, frappe.as_json(result))
		self.assertEqual(result["submission"]["state"], "created")

	def test_no_site_key_blocks_submission(self, mock_post, mock_status, mock_cache, _lock):
		mock_status.return_value = _not_submitted()
		with patch("crm.api.hfr.frappe.get_hooks", side_effect=_hooks()):
			_payload_sent, result = self._submit(mock_cache, {"fid": FID, "token_source": "openmeter"})
		self.assertEqual(result["submission"]["state"], "blocked")
		self.assertEqual(result["submission"]["missing_fields"], ["metering_site_key"])
		mock_post.assert_not_called()

	def test_crm_token_source_issues_no_key(self, mock_post, mock_status, mock_cache, _lock):
		mock_post.return_value = _accepted()
		mock_status.side_effect = [_not_submitted(), {"configured": True, "status": "Draft", "progress": 0}]
		key_hook = MagicMock(return_value=SITE_KEY)
		with (
			patch("crm.api.hfr.frappe.get_hooks", side_effect=_hooks("app.key_hook")),
			patch("crm.api.hfr.frappe.get_attr", return_value=key_hook),
		):
			self._submit(mock_cache, {"fid": FID, "token_source": "crm"})
		key_hook.assert_not_called()
		self.assertNotIn("metering_site_key", mock_post.call_args.kwargs["json"])

	def test_accepted_submission_enqueues_the_submitted_hooks(
		self, mock_post, mock_status, mock_cache, _lock
	):
		mock_post.return_value = _accepted()
		mock_status.side_effect = [_not_submitted(), {"configured": True, "status": "Draft", "progress": 0}]
		metering = {"fid": FID, "package_tokens": 400, "token_source": "crm"}
		with (
			patch("crm.api.hfr.frappe.get_hooks", side_effect=_hooks(submitted_hook="app.on_submitted")),
			patch("crm.api.hfr.frappe.enqueue") as enqueue,
		):
			self._submit(mock_cache, metering)
		enqueue.assert_called_once_with(
			"crm.api.hfr.run_hmis_provisioning_submitted_hooks",
			queue="short",
			enqueue_after_commit=True,
			fid=FID,
			context=metering,
		)


def _existing_site_hooks(key_hook, delivered_hook):
	attrs = {"app.key_hook": key_hook, "app.on_delivered": delivered_hook}
	hooks = _hooks("app.key_hook")
	return (
		lambda name, *args, **kwargs: ["app.on_delivered"] if name == "crm_on_hmis_metering_site_key_delivered" else hooks(name),
		lambda method: attrs[method],
	)


@patch("crm.api.hfr.filelock", side_effect=lambda *args, **kwargs: nullcontext())
@patch("crm.api.hfr._get_external_provisioning_status")
@patch("crm.api.hfr.requests.post")
class TestExistingSiteKeyDelivery(UnitTestCase):
	def _deliver(self, key_hook, delivered_hook):
		get_hooks, get_attr = _existing_site_hooks(key_hook, delivered_hook)
		with (
			patch("crm.api.hfr.frappe.get_hooks", side_effect=get_hooks),
			patch("crm.api.hfr.frappe.get_attr", side_effect=get_attr),
		):
			return _deliver_existing_site_key("https://deploy.example.test", "key", "secret", FID)

	def test_live_site_gets_its_key_through_the_setup_service(self, mock_post, mock_status, _lock):
		mock_status.return_value = {"configured": True, "status": "Completed", "progress": 100}
		mock_post.return_value = _accepted()
		key_hook, delivered_hook = MagicMock(return_value=SITE_KEY), MagicMock()
		result = self._deliver(key_hook, delivered_hook)

		self.assertEqual(result, {"state": "delivered"})
		key_hook.assert_called_once_with(fid=FID, context={"fid": FID, "purpose": "existing_site", "token_source": "openmeter"})
		self.assertTrue(mock_post.call_args.args[0].endswith("external_provisioning.update_metering_site_key"))
		self.assertEqual(mock_post.call_args.kwargs["json"], {"fid": FID, "metering_site_key": SITE_KEY})
		delivered_hook.assert_called_once_with(fid=FID, context={"fid": FID})
		self.assertNotIn(SITE_KEY, frappe.as_json(result))

	def test_facility_without_a_site_is_left_to_provisioning(self, mock_post, mock_status, _lock):
		mock_status.return_value = _not_submitted()
		key_hook = MagicMock(return_value=SITE_KEY)
		self.assertEqual(self._deliver(key_hook, MagicMock())["state"], "skipped")
		key_hook.assert_not_called()
		mock_post.assert_not_called()

	def test_unavailable_status_issues_no_key(self, mock_post, mock_status, _lock):
		mock_status.return_value = {"configured": True, "status": "unavailable"}
		key_hook = MagicMock(return_value=SITE_KEY)
		self.assertEqual(self._deliver(key_hook, MagicMock())["state"], "failed")
		key_hook.assert_not_called()

	def test_refused_push_is_not_marked_delivered(self, mock_post, mock_status, _lock):
		mock_status.return_value = {"configured": True, "status": "Completed", "progress": 100}
		refused = MagicMock(status_code=404, headers={})
		refused.json.return_value = {"exc_type": "DoesNotExistError", "echo": SITE_KEY}
		mock_post.return_value = refused
		delivered_hook = MagicMock()
		result = self._deliver(MagicMock(return_value=SITE_KEY), delivered_hook)

		self.assertEqual(result["state"], "failed")
		self.assertIn("update_metering_site_key", result["reason"])
		self.assertNotIn(SITE_KEY, frappe.as_json(result))
		delivered_hook.assert_not_called()


class TestSubmittedHooks(UnitTestCase):
	def test_a_failing_hook_is_logged_and_the_rest_still_run(self):
		good = MagicMock()
		hooks = {"crm_on_hmis_provisioning_submitted": ["app.bad", "app.good"]}
		attrs = {"app.bad": MagicMock(side_effect=RuntimeError("boom")), "app.good": good}
		with (
			patch("crm.api.hfr.frappe.get_hooks", side_effect=lambda name, *a, **k: hooks.get(name, [])),
			patch("crm.api.hfr.frappe.get_attr", side_effect=attrs.get),
			patch("crm.api.hfr.frappe.log_error") as log_error,
		):
			run_hmis_provisioning_submitted_hooks(FID, {"fid": FID})
		good.assert_called_once_with(fid=FID, context={"fid": FID})
		log_error.assert_called_once()

	def test_site_keys_are_redacted_from_error_details(self):
		details = _external_error_details(
			400, {"metering_site_key": SITE_KEY, "message": "rejected " + SITE_KEY}
		)
		self.assertNotIn(SITE_KEY, details)
		self.assertNotIn("s" * 43, details)


class TestTokenFacilityFid(UnitTestCase):
	def _rows(self, by_doctype):
		return lambda doctype, **kwargs: by_doctype.get(doctype, [])

	def test_one_fid_across_facility_records_is_used(self):
		rows = {"CRM Deal Facility": [FID, FID.lower()], "CRM Pre-Qualified Facility": [FID]}
		with patch("crm.utils.token_facility.frappe.get_all", side_effect=self._rows(rows)):
			self.assertEqual(facility_fid_for_mfl(" 12345 "), FID)

	def test_ambiguous_or_missing_fid_is_left_blank(self):
		rows = {"CRM Deal Facility": [FID], "CRM Pre-Qualified Facility": ["FID-99-TEST-2"]}
		with patch("crm.utils.token_facility.frappe.get_all", side_effect=self._rows(rows)):
			self.assertEqual(facility_fid_for_mfl("12345"), "")
		with patch("crm.utils.token_facility.frappe.get_all", return_value=[]):
			self.assertEqual(facility_fid_for_mfl("12345"), "")
		self.assertEqual(facility_fid_for_mfl(""), "")

	def _doc(self, **values):
		doc = frappe._dict(values)
		doc.meta = MagicMock()
		doc.meta.has_field.return_value = True
		doc.set = lambda field, value: doc.__setitem__(field, value)
		return doc

	def test_stamp_fills_fid_from_mfl(self):
		doc = self._doc(crm_token_facility_mfl="12345")
		with patch("crm.utils.token_facility.facility_fid_for_mfl", return_value=FID):
			stamp_facility_fid(doc)
		self.assertEqual(doc.crm_token_facility_fid, FID)

	def test_stamp_keeps_an_existing_fid(self):
		doc = self._doc(crm_token_facility_mfl="12345", crm_token_facility_fid="FID-99-TEST-2")
		with patch("crm.utils.token_facility.facility_fid_for_mfl", return_value=FID) as lookup:
			stamp_facility_fid(doc)
		self.assertEqual(doc.crm_token_facility_fid, "FID-99-TEST-2")
		lookup.assert_not_called()
