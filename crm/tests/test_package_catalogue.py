"""Settings › Packages API: Sales Managers add, edit, reorder, disable and discontinue packages."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import package_catalogue as pc
from crm.api.optin_admin import update_optin_settings

SALES_USER = "package.catalogue.sales.user@example.test"


def _catalogue():
	return pc.get_package_catalogue()


def _find(catalogue, name):
	return next(p for p in catalogue["packages"] if p["display_name"] == name)


class TestPackageCatalogue(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("package_catalogue_test")
		self.addCleanup(frappe.db.rollback, save_point="package_catalogue_test")
		if "erpnext" not in frappe.get_installed_apps():
			self.skipTest("ERPNext is required for token packages")
		if not frappe.db.get_single_value("CRM Opt-In Settings", "token_price_list"):
			self.skipTest("No token Price List on this site")
		# Start every test from one active Flex package so the rules are predictable.
		settings = frappe.get_single("CRM Opt-In Settings")
		for row in settings.token_packages:
			row.status = "Disabled"
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)

	def _save(self, **values):
		package = {
			"display_name": "Test Flex Pack",
			"description": "A synthetic package",
			"plan": "Flex",
			"token_quantity": 1500,
			"price": 8000,
			"billing_period": "Monthly",
			**values,
		}
		return pc.save_package(package, _catalogue()["version"])

	def test_create_makes_the_item_and_its_price(self):
		package = _find(self._save(popular=1, journeys="40"), "Test Flex Pack")
		self.assertTrue(package["item_code"].startswith("VX-TEST-FLEX-PACK"))
		self.assertEqual(package["price"], 8000)
		self.assertEqual(package["status"], "Active")
		self.assertTrue(package["popular"])
		self.assertEqual(package["journeys"], "40")
		self.assertTrue(frappe.db.get_value("Item", package["item_code"], "is_sales_item"))
		from crm.api.facility_onboarding import _token_packages

		self.assertIn(package["item_code"], [p["item_code"] for p in _token_packages()])

	def test_edit_changes_the_price_and_wording(self):
		package = _find(self._save(), "Test Flex Pack")
		catalogue = pc.save_package({**package, "price": 9000, "description": "New wording", "popular": 0}, _catalogue()["version"])
		edited = _find(catalogue, "Test Flex Pack")
		self.assertEqual(edited["price"], 9000)
		self.assertEqual(edited["description"], "New wording")

	def test_disable_hides_and_enable_restores(self):
		package = _find(self._save(), "Test Flex Pack")
		from crm.api.facility_onboarding import _token_packages

		pc.set_package_status(package["row_name"], "Disabled", _catalogue()["version"])
		self.assertNotIn(package["item_code"], [p["item_code"] for p in _token_packages()])
		pc.set_package_status(package["row_name"], "Active", _catalogue()["version"])
		self.assertIn(package["item_code"], [p["item_code"] for p in _token_packages()])

	def test_discontinue_is_final(self):
		package = _find(self._save(), "Test Flex Pack")
		catalogue = pc.set_package_status(package["row_name"], "Discontinued", _catalogue()["version"])
		self.assertTrue(_find(catalogue, "Test Flex Pack")["discontinued_on"])
		with self.assertRaises(frappe.ValidationError):
			pc.set_package_status(package["row_name"], "Active", _catalogue()["version"])
		with self.assertRaises(frappe.ValidationError):
			pc.save_package({**package, "price": 1}, _catalogue()["version"])

	def test_a_stale_version_is_refused(self):
		version = _catalogue()["version"]
		self._save()
		with self.assertRaises(frappe.TimestampMismatchError):
			pc.save_package({"display_name": "Other", "description": "x", "plan": "Flex", "token_quantity": 1, "price": 1}, version)

	def test_quarterly_fixed_and_one_fixed_per_level(self):
		self._save(display_name="Fixed Q L2", plan="Fixed", price=42000, billing_period="Quarterly", facility_levels=["Level 2"])
		with self.assertRaises(frappe.ValidationError):
			self._save(display_name="Fixed M L2", plan="Fixed", price=15000, facility_levels="Level 2")
		fixed = _find(_catalogue(), "Fixed Q L2")
		self.assertEqual((fixed["billing_period"], fixed["token_quantity"], fixed["facility_levels"]), ("Quarterly", 0, ["Level 2"]))

	def test_custom_needs_an_active_flex(self):
		flex = _find(self._save(), "Test Flex Pack")
		custom = _find(self._save(display_name="Test Custom", plan="Custom", price=0), "Test Custom")
		self.assertEqual(custom["token_quantity"], 1)
		with self.assertRaises(frappe.ValidationError):
			pc.set_package_status(flex["row_name"], "Disabled", _catalogue()["version"])

	def test_sold_package_keeps_its_tokens(self):
		package = _find(self._save(), "Test Flex Pack")
		original = pc._sold_orders
		pc._sold_orders = lambda items: {package["item_code"]: 2}
		self.addCleanup(setattr, pc, "_sold_orders", original)
		with self.assertRaises(frappe.ValidationError):
			pc.save_package({**package, "token_quantity": 2000}, _catalogue()["version"])
		# The price can still change.
		self.assertEqual(_find(pc.save_package({**package, "price": 8500}, _catalogue()["version"]), "Test Flex Pack")["price"], 8500)

	def test_move_reorders_within_the_plan(self):
		self._save(display_name="First Pack")
		second = _find(self._save(display_name="Second Pack"), "Second Pack")
		catalogue = pc.move_package(second["row_name"], "up", _catalogue()["version"])
		names = [p["display_name"] for p in catalogue["packages"] if p["display_name"] in ("First Pack", "Second Pack")]
		self.assertEqual(names, ["Second Pack", "First Pack"])

	def test_move_passes_packages_the_user_cannot_see(self):
		first = _find(self._save(display_name="First Pack"), "First Pack")
		hidden = _find(self._save(display_name="Hidden Pack", status="Disabled"), "Hidden Pack")
		third = _find(self._save(display_name="Third Pack"), "Third Pack")
		catalogue = pc.move_package(third["row_name"], "up", _catalogue()["version"], [first["row_name"], third["row_name"]])
		names = [p["display_name"] for p in catalogue["packages"] if p["row_name"] in (first["row_name"], hidden["row_name"], third["row_name"])]
		self.assertEqual(names, ["Third Pack", "Hidden Pack", "First Pack"])

	def test_opt_in_save_without_packages_leaves_them(self):
		self._save()
		before = len(frappe.get_single("CRM Opt-In Settings").token_packages)
		settings = frappe.call("crm.api.optin_admin.get_optin_settings")
		settings.pop("token_packages")
		# The Opt-In save commits; keep it inside this test's savepoint.
		with patch("frappe.db.commit"):
			update_optin_settings(settings)
		self.assertEqual(len(frappe.get_single("CRM Opt-In Settings").token_packages), before)

	def test_sales_user_is_refused(self):
		if not frappe.db.exists("User", SALES_USER):
			user = frappe.get_doc({"doctype": "User", "email": SALES_USER, "first_name": "Sales", "send_welcome_email": 0})
			user.insert(ignore_permissions=True)
			user.add_roles("Sales User")
		frappe.set_user(SALES_USER)
		self.addCleanup(frappe.set_user, "Administrator")
		with self.assertRaises(frappe.PermissionError):
			pc.get_package_catalogue()
