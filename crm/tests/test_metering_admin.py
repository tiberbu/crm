from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.api import metering_admin

HOOKS = {
	"crm_metering_admin_access": ["metering.access"],
	"crm_metering_admin_facility": ["metering.facility"],
	"crm_metering_admin_action": ["metering.action"],
	"crm_metering_admin_reveal_key": ["metering.reveal_key"],
}


def _with_metering_app(handlers):
	"""Patch the hooks as if a metering app answered them with `handlers` (name -> callable)."""
	return (
		patch("frappe.get_hooks", side_effect=lambda name: HOOKS.get(name, [])),
		patch("frappe.get_attr", side_effect=lambda path: handlers[path.split(".", 1)[1]]),
	)


class TestMeteringAdmin(UnitTestCase):
	def test_no_metering_app_hides_the_tab(self):
		with patch("frappe.get_hooks", return_value=[]):
			self.assertEqual(metering_admin.get_access(), metering_admin.NO_ACCESS)
			self.assertRaises(frappe.ValidationError, metering_admin.get_facility, "FID-00-TEST-0001")
			self.assertRaises(frappe.ValidationError, metering_admin.run_action, "sync", "FID-00-TEST-0001")

	def test_access_comes_from_the_metering_app(self):
		hooks, attr = _with_metering_app({"access": lambda: {"can_manage": True, "can_reveal": False}})
		with hooks, attr:
			self.assertEqual(
				metering_admin.get_access(), {"enabled": True, "can_manage": True, "can_reveal": False}
			)

	def test_a_failing_access_hook_hides_the_tab(self):
		def broken():
			raise RuntimeError("boom")

		hooks, attr = _with_metering_app({"access": broken})
		with hooks, attr, patch("frappe.log_error") as log:
			self.assertEqual(metering_admin.get_access(), metering_admin.NO_ACCESS)
		log.assert_called_once()

	def test_actions_and_reveal_are_passed_through(self):
		action, reveal = MagicMock(return_value={"requeued": 0}), MagicMock(return_value={"key": "k"})
		hooks, attr = _with_metering_app({"action": action, "reveal_key": reveal})
		with hooks, attr:
			self.assertEqual(
				metering_admin.run_action("verify_probe", "FID-00-TEST-0001", '{"event": "e1"}'), {"requeued": 0}
			)
			self.assertEqual(metering_admin.reveal_key("FID-00-TEST-0001", "pw"), {"key": "k"})
		action.assert_called_once_with("verify_probe", fid="FID-00-TEST-0001", params={"event": "e1"})
		reveal.assert_called_once_with("FID-00-TEST-0001", "pw")

	def test_facilities_need_metering_access(self):
		with (
			patch("frappe.has_permission", return_value=True),
			patch.object(metering_admin, "get_access", return_value=metering_admin.NO_ACCESS),
		):
			self.assertRaises(frappe.PermissionError, metering_admin.get_deal_facilities, "CRM-DEAL-0001")

	def test_facilities_are_listed_by_facility_id(self):
		rows = [frappe._dict(hfr_facility_id=" FID-00-TEST-0001 ", facility_name="Test", mfl_code="1")]
		with (
			patch("frappe.has_permission", return_value=True),
			patch.object(metering_admin, "get_access", return_value={"can_manage": True}),
			patch("frappe.get_all", return_value=rows),
		):
			self.assertEqual(
				metering_admin.get_deal_facilities("CRM-DEAL-0001"),
				[{"fid": "FID-00-TEST-0001", "facility_name": "Test", "mfl_code": "1"}],
			)

	def test_reveal_is_post_only_and_rate_limited(self):
		self.assertIn(metering_admin.reveal_key, frappe.whitelisted)
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[metering_admin.reveal_key], ["POST"])
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[metering_admin.run_action], ["POST"])
