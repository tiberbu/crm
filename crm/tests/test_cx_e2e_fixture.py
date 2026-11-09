from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.patches.v1_0 import seed_cx_e2e_fixture as fixture


def _counts():
	settings = frappe.get_single("CRM Opt-In Settings")
	return {
		"item": frappe.db.count("Item", {"item_code": fixture.ITEM_CODE}),
		"price": frappe.db.count("Item Price", {"item_code": fixture.ITEM_CODE}),
		"network": frappe.db.count("CRM Opt-In Network", {"slug": fixture.NETWORK_SLUG}),
		"rows": [row.item_code for row in settings.token_packages],
	}


class TestCxE2eFixture(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("cx_fixture_test")
		self.addCleanup(frappe.db.rollback, save_point="cx_fixture_test")
		if not frappe.db.get_single_value("CRM Opt-In Settings", "token_price_list"):
			self.skipTest("No token Price List configured on this site")
		self.before = _counts()

	def _run(self, flag=True):
		conf = {fixture.FLAG: 1} if flag else {}
		with patch.dict(frappe.conf, conf, clear=False):
			if not flag:
				frappe.conf.pop(fixture.FLAG, None)
			fixture.execute()

	def test_disabled_by_default_creates_nothing(self):
		self._run(flag=False)
		self.assertEqual(_counts(), self.before)
		self.assertFalse(fixture.enabled())

	def test_opted_in_site_gets_the_synthetic_set(self):
		self._run()
		after = _counts()
		self.assertEqual((after["item"], after["price"], after["network"]), (1, 1, 1))
		self.assertEqual(after["rows"].count(fixture.ITEM_CODE), 1)

	def test_repeat_runs_change_nothing(self):
		self._run()
		first = _counts()
		self._run()
		self._run()
		self.assertEqual(_counts(), first)

	def test_existing_commercial_rows_are_untouched(self):
		self._run()
		after = _counts()
		self.assertEqual(
			[code for code in after["rows"] if code != fixture.ITEM_CODE],
			self.before["rows"],
		)
		self.assertEqual(
			frappe.db.get_single_value("CRM Opt-In Settings", "token_price_list"),
			frappe.get_single("CRM Opt-In Settings").token_price_list,
		)

	def test_fixture_package_is_offered_by_the_catalog_only_when_seeded(self):
		from crm.api.facility_onboarding import _token_packages

		self.assertNotIn(fixture.ITEM_CODE, [p["item_code"] for p in _token_packages()])
		self._run()
		package = next(p for p in _token_packages() if p["item_code"] == fixture.ITEM_CODE)
		self.assertEqual(package["price"], fixture.PRICE)

	def test_patch_is_registered_and_has_no_otp_bypass(self):
		with open(frappe.get_app_path("crm", "patches.txt")) as handle:
			lines = [line.strip() for line in handle]
		self.assertIn("crm.patches.v1_0.seed_cx_e2e_fixture", lines)
		self.assertGreater(
			lines.index("crm.patches.v1_0.seed_cx_e2e_fixture"), lines.index("[post_model_sync]")
		)
		with open(fixture.__file__) as handle:
			source = handle.read().lower()
		self.assertNotIn("otp", source.replace("synthetic", ""))
