"""Facility owners' low-token email alerts (docs/cx-portal-token-alerts-and-ui-review.md)."""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import token_alerts

USER = "token.alert.owner@example.test"
MFL = "TA-10001"
FID = "FID-00-TA-10001"
FACILITIES = {MFL.lower(): {"mfl_code": MFL, "facility_name": "Alert Test Clinic", "fid": FID}}


def _ok(balance):
	return {FID: {"status": "ok", "balance": balance}}


class TestTokenAlerts(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("User", USER):
			frappe.get_doc({"doctype": "User", "email": USER, "first_name": "Alert", "user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True)

	def setUp(self):
		frappe.db.delete(token_alerts.DOCTYPE, {"user": USER})
		frappe.set_user(USER)
		self.balances = {}
		self.sent = []

	def tearDown(self):
		frappe.set_user("Administrator")

	@contextmanager
	def portal(self, facilities=FACILITIES):
		with patch.object(token_alerts, "require_portal_user", return_value=[]), patch.object(
			token_alerts, "_portal_facilities", return_value=facilities
		), patch.object(token_alerts, "fetch_facility_token_balances", side_effect=lambda fids: dict(self.balances)), patch.object(
			token_alerts.frappe, "sendmail", side_effect=lambda **kw: self.sent.append(kw)
		):
			yield

	def save(self, threshold=500, enabled=1):
		with self.portal():
			return token_alerts.save_token_alert(MFL, enabled=enabled, threshold=threshold)

	def run_check(self):
		with self.portal():
			token_alerts.check_token_alerts()

	def test_rejects_a_facility_outside_the_owners_portal(self):
		with self.portal(facilities={}), self.assertRaises(frappe.PermissionError):
			token_alerts.save_token_alert(MFL, threshold=500)

	def test_requires_an_hfr_facility_id(self):
		no_fid = {MFL.lower(): {**FACILITIES[MFL.lower()], "fid": ""}}
		with self.portal(facilities=no_fid), self.assertRaises(frappe.ValidationError):
			token_alerts.save_token_alert(MFL, threshold=500)

	def test_rejects_a_zero_threshold(self):
		with self.assertRaises(frappe.ValidationError):
			self.save(threshold=0)

	def test_balance_above_threshold_records_without_email(self):
		self.balances = _ok(4000)
		result = self.save(threshold=500)
		self.assertEqual(result["balance_status"], "ok")
		self.assertFalse(result["alert_sent"])
		self.assertEqual(result["alert"]["last_balance"], 4000)
		self.assertEqual(self.sent, [])

	def test_emails_once_per_drop_and_rearms_after_top_up(self):
		self.balances = _ok(300)
		result = self.save(threshold=500)
		self.assertTrue(result["alert_sent"])
		self.assertEqual(len(self.sent), 1)
		self.assertEqual(self.sent[0]["recipients"], [USER])
		self.assertIn("300", self.sent[0]["subject"])

		self.balances = _ok(120)
		self.run_check()
		self.assertEqual(len(self.sent), 1, "still below: no repeat email")

		self.balances = _ok(5000)
		self.run_check()
		self.assertEqual(frappe.db.get_value(token_alerts.DOCTYPE, result["alert"]["name"], "below_threshold"), 0)

		self.balances = _ok(450)
		self.run_check()
		self.assertEqual(len(self.sent), 2, "a new drop after a top-up emails again")

	def test_no_live_balance_never_emails(self):
		for entry in ({}, {FID: {"status": "unavailable"}}, {FID: {"status": "not_metered"}}):
			self.balances = entry
			result = self.save(threshold=500)
			self.assertFalse(result["alert_sent"])
			self.run_check()
		self.assertEqual(self.sent, [])

	def test_changing_the_threshold_rearms(self):
		self.balances = _ok(300)
		self.save(threshold=500)
		self.save(threshold=500)
		self.assertEqual(len(self.sent), 1, "saving the same threshold does not resend")
		self.save(threshold=400)
		self.assertEqual(len(self.sent), 2)

	def test_disabled_alert_is_not_checked(self):
		self.balances = _ok(4000)
		self.save(threshold=500, enabled=0)
		self.balances = _ok(10)
		self.run_check()
		self.assertEqual(self.sent, [])

	def test_one_alert_per_owner_and_facility(self):
		self.balances = _ok(4000)
		self.save(threshold=500)
		self.save(threshold=800)
		self.assertEqual(frappe.db.count(token_alerts.DOCTYPE, {"user": USER}), 1)
		with self.portal():
			alerts = token_alerts.get_token_alerts()["alerts"]
		self.assertEqual(alerts[MFL]["threshold"], 800)
