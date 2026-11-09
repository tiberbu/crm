from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.patches.v1_0.seed_level_6_prices import execute


class TestLevel6PricePatch(UnitTestCase):
	def test_skips_a_crm_only_site(self):
		with (
			patch("crm.patches.v1_0.seed_level_6_prices.frappe.get_installed_apps", return_value=["crm"]),
			patch("crm.patches.v1_0.seed_level_6_prices._ensure_item") as ensure_item,
		):
			execute()

		ensure_item.assert_not_called()

	def test_creates_missing_item_prices_without_overwriting_existing_rates(self):
		created = []

		def get_doc(payload, *args):
			doc = Mock()
			doc.currency = payload.get("currency", "KES") if isinstance(payload, dict) else "KES"
			doc.selling = 1
			doc.enabled = 1
			doc.insert.side_effect = lambda **kwargs: created.append(payload) or doc
			return doc

		with (
			patch("crm.patches.v1_0.seed_level_6_prices.frappe.get_installed_apps", return_value=["erpnext"]),
			patch("crm.patches.v1_0.seed_level_6_prices.frappe.db.exists", return_value=False),
			patch("crm.patches.v1_0.seed_level_6_prices.frappe.db.get_value", return_value="Services"),
			patch("crm.patches.v1_0.seed_level_6_prices.frappe.get_doc", side_effect=get_doc),
		):
			execute()

		self.assertEqual(len(created), 11)  # one item, five lists, five item prices
		prices = [row for row in created if isinstance(row, dict) and row.get("doctype") == "Item Price"]
		self.assertEqual(
			[row["price_list_rate"] for row in prices],
			[386978.91, 386978.91, 305450.49, 320723.01, 336759.16],
		)

	def test_existing_item_price_is_left_untouched(self):
		with (
			patch("crm.patches.v1_0.seed_level_6_prices.frappe.get_installed_apps", return_value=["erpnext"]),
			patch("crm.patches.v1_0.seed_level_6_prices._ensure_item", return_value=True),
			patch(
				"crm.patches.v1_0.seed_level_6_prices._ensure_price_list",
				return_value=frappe._dict({"currency": "KES", "selling": 1, "enabled": 1}),
			),
			patch("crm.patches.v1_0.seed_level_6_prices.frappe.db.exists", return_value=True),
			patch("crm.patches.v1_0.seed_level_6_prices.frappe.get_doc") as get_doc,
		):
			execute()

		get_doc.assert_not_called()
