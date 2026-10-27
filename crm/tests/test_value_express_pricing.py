"""Value Express pricing rules: Custom amounts, Flex tiers and the Fixed level match."""

from frappe.tests import UnitTestCase

from crm.utils.value_express import (
	custom_min_amount,
	custom_quote,
	fixed_package_for_level,
	flex_tiers,
	journeys,
	per_token_rate,
)

FLEX_ROWS = [
	{"item_code": "SCALE", "display_name": "Scale", "plan": "Flex", "price_ex_vat": 30000, "token_quantity": 6250},
	{"item_code": "STARTER", "display_name": "Starter", "plan": "Flex", "price_ex_vat": 6000, "token_quantity": 1000},
	{"item_code": "GROWTH", "display_name": "Growth", "plan": "Flex", "price_ex_vat": 15000, "token_quantity": 2800},
	{"item_code": "FREE", "display_name": "Free", "plan": "Flex", "price_ex_vat": 0, "token_quantity": 400},
	{"item_code": "L2", "display_name": "Fixed L2", "plan": "Fixed", "price_ex_vat": 15000, "token_quantity": 0},
]
FIXED_ROWS = [
	{"item_code": "L2", "plan": "Fixed", "facility_levels": "Level 2"},
	{"item_code": "L3", "plan": "Fixed", "facility_levels": "Level 3B\nLevel 3C"},
]


class TestValueExpressPricing(UnitTestCase):
	def setUp(self):
		self.tiers = flex_tiers(FLEX_ROWS)

	def test_tiers_are_paid_flex_packages_cheapest_first(self):
		self.assertEqual([t["name"] for t in self.tiers], ["Starter", "Growth", "Scale"])
		self.assertEqual([t["rate"] for t in self.tiers], [6.0, 5.36, 4.8])

	def test_amount_below_growth_uses_the_starter_rate(self):
		quote = custom_quote(7000, self.tiers)
		self.assertTrue(quote["ok"])
		self.assertEqual((quote["tier"], quote["tokens"], quote["charge"]), ("Starter", 1166, 6996.0))

	def test_amount_reaching_a_tier_uses_its_rate_and_never_overcharges(self):
		growth = custom_quote(20000, self.tiers)
		self.assertEqual((growth["tier"], growth["rate"], growth["tokens"]), ("Growth", 5.36, 3731))
		self.assertLessEqual(growth["charge"], 20000)
		scale = custom_quote("40000", self.tiers)
		self.assertEqual((scale["tier"], scale["tokens"], scale["charge"]), ("Scale", 8333, 39998.4))

	def test_tier_boundary_and_fractions(self):
		self.assertEqual(custom_quote(14999.99, self.tiers)["tier"], "Starter")
		self.assertEqual(custom_quote(15000, self.tiers)["tier"], "Growth")

	def test_below_minimum_is_refused_with_the_minimum_amount(self):
		quote = custom_quote(5999, self.tiers)
		self.assertFalse(quote["ok"])
		self.assertEqual(quote["error"], "below_minimum")
		self.assertEqual(quote["min_amount"], 6000.0)
		self.assertEqual(custom_min_amount(self.tiers), 6000.0)
		self.assertFalse(custom_quote("not a number", self.tiers)["ok"])
		self.assertFalse(custom_quote(-50000, self.tiers)["ok"])

	def test_no_tiers_means_custom_is_unavailable(self):
		self.assertEqual(custom_quote(7000, [])["error"], "unavailable")

	def test_fixed_matches_the_registry_level_exactly_after_normalising(self):
		self.assertEqual(fixed_package_for_level("Level 2", FIXED_ROWS)["item_code"], "L2")
		self.assertEqual(fixed_package_for_level(" level  3c ", FIXED_ROWS)["item_code"], "L3")
		self.assertIsNone(fixed_package_for_level("Level 4", FIXED_ROWS))
		self.assertIsNone(fixed_package_for_level("", FIXED_ROWS))

	def test_card_figures(self):
		self.assertEqual(per_token_rate({"price_ex_vat": 15000, "token_quantity": 2800}), 5.36)
		self.assertEqual([journeys(t) for t in (1000, 2800, 6250)], [25, 70, 156])
