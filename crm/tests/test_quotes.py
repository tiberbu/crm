from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.quotes import list_catalogue_items, list_quotes


class TestQuoteLoadBatching(UnitTestCase):
	def test_list_quotes_fetches_invoice_links_in_one_query(self):
		quotes = [
			frappe._dict({"name": "QUO-0001", "docstatus": 0, "crm_sent": 1}),
			frappe._dict({"name": "QUO-0002", "docstatus": 1, "crm_sent": 1}),
		]
		invoices = [
			frappe._dict({"name": "SINV-0002", "crm_quotation": "QUO-0002"}),
			frappe._dict({"name": "SINV-0001", "crm_quotation": "QUO-0001"}),
		]

		with patch("crm.api.quotes.frappe.get_list", side_effect=[quotes, invoices]) as get_list:
			result = list_quotes("DEAL-0001")

		self.assertEqual(get_list.call_count, 2)
		self.assertEqual(result[0]["erpnext_sales_invoice"], "SINV-0001")
		self.assertEqual(result[1]["erpnext_sales_invoice"], "SINV-0002")
		self.assertEqual(result[0]["status"], "Sent")
		self.assertEqual(result[1]["status"], "Accepted")

	def test_catalogue_item_prices_are_batched(self):
		items = [
			frappe._dict({"item_code": "ITEM-001", "item_name": "Item One", "stock_uom": "Nos"}),
			frappe._dict({"item_code": "ITEM-002", "item_name": "Item Two", "stock_uom": "Nos"}),
		]
		prices = [
			frappe._dict(
				{
					"item_code": "ITEM-001",
					"price_list": "Negotiated Year 1",
					"price_list_rate": 1500,
					"valid_from": None,
					"valid_upto": None,
				}
			),
			frappe._dict(
				{
					"item_code": "ITEM-002",
					"price_list": "Standard Selling",
					"price_list_rate": 900,
					"valid_from": None,
					"valid_upto": None,
				}
			),
		]

		with (
			patch("crm.api.quotes.frappe.get_list", side_effect=[items, prices]) as get_list,
			patch("crm.api.quotes.nowdate", return_value="2026-08-29"),
		):
			result = list_catalogue_items(price_list="Negotiated Year 1")

		self.assertEqual(get_list.call_count, 2)
		self.assertEqual(
			result,
			[
				{"item_code": "ITEM-001", "label": "Item One", "uom": "Nos", "rate": 1500},
				{"item_code": "ITEM-002", "label": "Item Two", "uom": "Nos", "rate": 900},
			],
		)
