from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from crm.utils.price_list_history import append_change, snapshot


class TestPriceListHistory(UnitTestCase):
	def test_history_keeps_initial_and_each_negotiated_switch(self):
		quote = SimpleNamespace(
			selling_price_list="Negotiated Year 1",
			crm_initial_price_list="",
			crm_price_list_history="",
			creation="2026-09-01 09:00:00",
			owner="sales@example.com",
		)

		with patch("crm.utils.price_list_history._has_field", return_value=True):
			append_change(quote, "Negotiated Year 1", "Negotiated Year 2")
			quote.selling_price_list = "Negotiated Year 3"
			append_change(quote, "Negotiated Year 2", "Negotiated Year 3")
			result = snapshot(quote)

		self.assertEqual(result["initial"], "Negotiated Year 1")
		self.assertEqual(result["negotiated"], "Negotiated Year 3")
		self.assertEqual(
			[(event["from"], event["to"]) for event in result["history"]],
			[
				("", "Negotiated Year 1"),
				("Negotiated Year 1", "Negotiated Year 2"),
				("Negotiated Year 2", "Negotiated Year 3"),
			],
		)

	def test_snapshot_is_truthful_for_legacy_quote_without_history(self):
		quote = SimpleNamespace(selling_price_list="Negotiated Year 4")
		with patch("crm.utils.price_list_history._has_field", return_value=False):
			result = snapshot(quote)

		self.assertEqual(result["initial"], "Negotiated Year 4")
		self.assertEqual(result["negotiated"], "Negotiated Year 4")
		self.assertEqual(result["history"][0]["to"], "Negotiated Year 4")
