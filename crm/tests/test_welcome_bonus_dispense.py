"""P-76: the welcome bonus is dispensed once per facility — by button, auto-assign or first payment."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import metering_admin
from crm.utils import token_bonus

FID = "FID-00-TEST-0076"


_real_get_doc = frappe.get_doc


def _orders(order):
	"""frappe.get_doc that returns `order` for Sales Orders only (settings still load)."""
	return patch("frappe.get_doc", side_effect=lambda doctype, *a, **k: order if doctype == "Sales Order" else _real_get_doc(doctype, *a, **k))


def _hooks(status=None, dispense=None):
	"""Stand-ins for the metering app's welcome-bonus hooks."""
	calls = []

	def fake_status(fid):
		return status or {"fid": fid, "dispensed": False, "status": None}

	def fake_dispense(fid, tokens, source_doctype=None, source_name=None):
		calls.append((fid, tokens, source_doctype, source_name))
		return dispense or {"fid": fid, "dispensed": True, "status": "Granted", "changed": True, "tokens": tokens}

	def hook(name):
		return {"crm_welcome_bonus_status": fake_status, "crm_dispense_welcome_bonus": fake_dispense}.get(name)

	return patch.object(token_bonus, "_hook", side_effect=hook), calls


class TestWelcomeBonusDispense(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._settings(welcome_bonus_tokens=400, auto_dispense_welcome_bonus=1)

	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")
		frappe.set_user("Administrator")

	def _settings(self, **values):
		if not frappe.get_meta("CRM Opt-In Settings").has_field("auto_dispense_welcome_bonus"):
			self.skipTest("Run bench migrate: auto_dispense_welcome_bonus is missing")
		frappe.db.set_single_value("CRM Opt-In Settings", values)
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")

	def _order(self, **values):
		return frappe._dict(
			{"name": "SO-TEST-76", "crm_token_package_item": "CV-TOKEN-FLEX", "crm_token_facility_mfl": "90076", **values}
		)

	def test_package_selection_enqueues_once_auto_assign_is_on(self):
		hook, _calls = _hooks()
		with hook, patch.object(token_bonus, "_earns_bonus", return_value=True), patch("frappe.enqueue") as enqueue:
			token_bonus.auto_dispense_on_package_selection(self._order())
		self.assertEqual(enqueue.call_args.kwargs["sales_order"], "SO-TEST-76")
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])

	def test_no_auto_assign_when_off_zero_not_flex_or_no_package(self):
		hook, _calls = _hooks()
		with hook, patch("frappe.enqueue") as enqueue:
			with patch.object(token_bonus, "_earns_bonus", return_value=False):
				token_bonus.auto_dispense_on_package_selection(self._order())
			with patch.object(token_bonus, "_earns_bonus", return_value=True):
				token_bonus.auto_dispense_on_package_selection(self._order(crm_token_package_item=None))
				self._settings(auto_dispense_welcome_bonus=0)
				token_bonus.auto_dispense_on_package_selection(self._order())
				self._settings(auto_dispense_welcome_bonus=1, welcome_bonus_tokens=0)
				token_bonus.auto_dispense_on_package_selection(self._order())
		enqueue.assert_not_called()

	def test_auto_dispense_job_records_the_order_and_skips_when_dispensed(self):
		order = frappe._dict(name="SO-TEST-76", docstatus=1, crm_token_facility_fid=FID, crm_token_facility_mfl="90076")
		with _orders(order):
			hook, calls = _hooks()
			with hook:
				token_bonus.auto_dispense_job("SO-TEST-76")
			self.assertEqual(calls, [(FID, 400, "Sales Order", "SO-TEST-76")])
			hook, calls = _hooks(status={"dispensed": True, "status": "Granted"})
			with hook:
				token_bonus.auto_dispense_job("SO-TEST-76")
			self.assertEqual(calls, [])

	def test_a_failed_auto_assign_is_logged_for_the_admin(self):
		order = frappe._dict(name="SO-TEST-76", docstatus=0, crm_token_facility_fid=FID)
		hook, _calls = _hooks(dispense={"dispensed": False, "status": "Failed", "error": "down"})
		with _orders(order), hook, patch("frappe.log_error") as log:
			token_bonus.auto_dispense_job("SO-TEST-76")
		self.assertIn(FID, log.call_args.kwargs["title"])

	def test_eligible_bonuses_skip_a_dispensed_welcome_bonus(self):
		with patch.object(token_bonus, "_installed", return_value=True), patch.object(
			token_bonus, "_other_confirmed_orders", return_value=[]
		), patch.object(token_bonus, "_coupon_network", return_value=None):
			hook, _calls = _hooks()
			with hook:
				self.assertEqual([b["type"] for b in token_bonus.eligible_bonuses("C", "90076", facility_fid=FID)], ["Welcome Bonus"])
			hook, _calls = _hooks(status={"dispensed": True})
			with hook:
				self.assertEqual(token_bonus.eligible_bonuses("C", "90076", facility_fid=FID), [])

	def test_button_needs_an_openmeter_admin_and_records_who_clicked(self):
		hook, calls = _hooks()
		with hook, patch.object(metering_admin, "get_access", return_value={"can_manage": False}):
			self.assertRaises(frappe.PermissionError, metering_admin.dispense_welcome_bonus, FID)
		self.assertEqual(calls, [])
		with hook, patch.object(metering_admin, "get_access", return_value={"can_manage": True}):
			result = metering_admin.dispense_welcome_bonus(FID)
		self.assertEqual(calls, [(FID, 400, "User", "Administrator")])
		self.assertTrue(result["changed"])
		self.assertTrue(result["auto_dispense"])
		self.assertEqual(result["configured_tokens"], 400)

	def test_button_refuses_zero_tokens_or_no_fid(self):
		hook, calls = _hooks()
		with hook, patch.object(metering_admin, "get_access", return_value={"can_manage": True}):
			self.assertRaises(frappe.ValidationError, metering_admin.dispense_welcome_bonus, " ")
			self._settings(welcome_bonus_tokens=0)
			self.assertRaises(frappe.ValidationError, metering_admin.dispense_welcome_bonus, FID)
		self.assertEqual(calls, [])

	def test_dispensing_drops_the_welcome_line_from_drafts_only(self):
		hook, _calls = _hooks()
		with hook, patch.object(token_bonus, "drop_welcome_lines_from_drafts") as drop:
			token_bonus.dispense_welcome_bonus(FID, "User", "Administrator")
		drop.assert_called_once_with(FID)
		hook, _calls = _hooks(dispense={"dispensed": False, "status": "Failed"})
		with hook, patch.object(token_bonus, "drop_welcome_lines_from_drafts") as drop:
			token_bonus.dispense_welcome_bonus(FID, "User", "Administrator")
		drop.assert_not_called()

	def test_hooks_are_wired_on_sales_order(self):
		events = frappe.get_hooks("doc_events")["Sales Order"]
		for event in ("after_insert", "on_submit"):
			self.assertIn("crm.utils.token_bonus.auto_dispense_on_package_selection", events[event])

	def test_settings_round_trip(self):
		from crm.api import optin_admin

		self.assertTrue(optin_admin.get_optin_settings()["auto_dispense_welcome_bonus"])
