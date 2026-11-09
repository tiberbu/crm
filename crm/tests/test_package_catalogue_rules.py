"""Catalogue rules a Sales Manager's changes are checked against before they are published."""

from frappe.tests import UnitTestCase

from crm.utils.value_express import (
	grid_columns,
	monthly_equivalent,
	period_label,
	status_of,
	validate_catalogue,
)


def flex(code, **values):
	return {"item_code": code, "display_name": code, "plan": "Flex", "status": "Active", "token_quantity": 1000, "price": 6000, **values}


def fixed(code, levels, **values):
	return {"item_code": code, "display_name": code, "plan": "Fixed", "status": "Active", "facility_levels": levels, "price": 15000, **values}


class TestPackageCatalogueRules(UnitTestCase):
	def test_a_valid_catalogue_passes(self):
		rows = [flex("STARTER"), fixed("L2", "Level 2"), fixed("L3", "Level 3B\nLevel 3C"), {"item_code": "CUSTOM", "plan": "Custom", "status": "Active", "token_quantity": 1}]
		self.assertEqual(validate_catalogue(rows), [])

	def test_flex_needs_tokens_and_a_price(self):
		errors = validate_catalogue([flex("A", token_quantity=0, price=0)])
		self.assertEqual(len(errors), 2)

	def test_fixed_needs_levels_and_a_price(self):
		errors = validate_catalogue([fixed("L2", "", price=0)])
		self.assertEqual(len(errors), 2)

	def test_one_active_fixed_package_per_level(self):
		errors = validate_catalogue([fixed("M", "Level 2"), fixed("Q", "level  2", billing_period="Quarterly")])
		self.assertIn("already has an active Fixed package", errors[0])
		# A disabled duplicate is fine: only active packages are offered.
		self.assertEqual(validate_catalogue([fixed("M", "Level 2"), fixed("Q", "Level 2", status="Disabled")]), [])

	def test_custom_needs_an_active_flex_and_is_unique(self):
		custom = {"item_code": "C1", "plan": "Custom", "status": "Active", "token_quantity": 1}
		self.assertIn("needs at least one active Flex", validate_catalogue([custom, flex("A", status="Disabled")])[0])
		self.assertIn("Only one Custom", validate_catalogue([custom, {**custom, "item_code": "C2"}, flex("A")])[0])

	def test_items_are_unique_across_all_statuses(self):
		self.assertIn("already used", validate_catalogue([flex("A"), flex("A", status="Discontinued")])[0])

	def test_inactive_packages_are_not_checked_for_completeness(self):
		self.assertEqual(validate_catalogue([flex("A"), flex("B", price=0, status="Discontinued")]), [])

	def test_unknown_period_is_refused(self):
		self.assertIn("Semi-annual", validate_catalogue([flex("A", billing_period="Weekly")])[0])

	def test_status_falls_back_to_enabled(self):
		self.assertEqual(status_of({"enabled": 1}), "Active")
		self.assertEqual(status_of({"enabled": 0}), "Disabled")
		self.assertEqual(status_of({"status": "Discontinued", "enabled": 1}), "Discontinued")

	def test_periods(self):
		self.assertEqual(period_label("Quarterly"), "per quarter")
		self.assertEqual(period_label("Semi-annual"), "per half-year")
		self.assertEqual(period_label(None), "per month")
		self.assertEqual(monthly_equivalent(45000, "Quarterly"), 15000)
		self.assertEqual(monthly_equivalent(180000, "Annual"), 15000)

	def test_grid_columns(self):
		self.assertEqual([grid_columns(n) for n in range(0, 11)], [1, 1, 2, 3, 4, 3, 3, 4, 4, 3, 4])
		self.assertEqual([grid_columns(n, 3) for n in (2, 3, 4, 5)], [2, 3, 2, 3])
