from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.quotes import (
	_facility_signatory_has_signed,
	get_quote_lines,
	list_catalogue_items,
	list_quotes,
	set_quote_price_list,
)
from crm.utils.jinja import get_quotation_tax_summary
from crm.utils.quotation_tax import calculate_vat_totals, quotation_tax_summary


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


class TestConfiguredQuotationVAT(UnitTestCase):
	def setUp(self):
		self.tax_configuration = frappe._dict(
			{
				"template": "Kenya Tax - TB",
				"vat_rate": 16,
				"vat_fraction": 0.16,
				"vat_label": "VAT (16%)",
			}
		)

	def test_preview_totals_use_the_configured_tax_rate(self):
		with patch("crm.utils.quotation_tax.get_vat_tax_configuration", return_value=self.tax_configuration):
			result = calculate_vat_totals(28_425.93)

		self.assertEqual(result.template, "Kenya Tax - TB")
		self.assertEqual(result.vat_amount, 4_548.15)
		self.assertEqual(result.grand_total, 32_974.08)

	def test_legacy_quote_summary_repairs_a_missing_native_grand_total(self):
		quote = frappe._dict(
			{
				"company": "Tiberbu",
				"taxes_and_charges": "",
				"net_total": 100_000,
				"vat_amount": 16_000,
				"grand_total": 100_000,
				"total_taxes_and_charges": 0,
				"taxes": [],
			}
		)
		with patch("crm.utils.quotation_tax.get_vat_tax_configuration", return_value=self.tax_configuration):
			result = quotation_tax_summary(quote)

		self.assertEqual(result.vat_amount, 16_000)
		self.assertEqual(result.grand_total, 116_000)

	def test_quote_lines_expose_the_server_tax_label_and_rate(self):
		quote = SimpleNamespace(
			name="QUO-TEST-0001",
			docstatus=0,
			crm_sent=0,
			crm_deal="DEAL-TEST-0001",
			currency="KES",
			selling_price_list="Negotiated Year 1",
			crm_payment_terms="Annual Upfront",
			valid_till="2026-09-30",
			net_total=100_000,
			items=[
				frappe._dict(
					{
						"item_code": "CV-HIMS-KEPH-3",
						"item_name": "CareverseHIMS - Alpha Clinic",
						"description": "Annual Subscription",
						"qty": 1,
						"rate": 100_000,
						"amount": 100_000,
					}
				),
			],
		)
		quote.get = lambda fieldname, default=None: getattr(quote, fieldname, default)
		tax_summary = frappe._dict(
			{
				"net_total": 100_000,
				"vat_amount": 16_000,
				"grand_total": 116_000,
				"vat_rate": 16,
				"vat_label": "VAT (16%)",
			}
		)
		with (
			patch("crm.api.quotes.frappe.get_doc", return_value=quote),
			patch("crm.api.quotes.frappe.db.get_value", return_value=None),
			patch("crm.api.quotes.quotation_tax_summary", return_value=tax_summary),
		):
			result = get_quote_lines(quote.name)

		self.assertEqual(result["vat_label"], "VAT (16%)")
		self.assertEqual(result["vat_rate"], 16)
		self.assertEqual(result["grand_total"], 116_000)


class TestQuotationPriceListChanges(UnitTestCase):
	def test_facility_signature_is_detected_from_status_or_signature_data(self):
		with patch(
			"crm.api.quotes.frappe.get_list",
			side_effect=[
				[frappe._dict({"name": "CONT-0001"})],
				[frappe._dict({"status": "Pending", "signature_data": "signed-payload"})],
			],
		):
			self.assertTrue(_facility_signatory_has_signed("DEAL-0001"))

	def test_price_list_change_remains_available_after_optin_before_facility_signature(self):
		quote = SimpleNamespace(
			name="QUO-0001",
			docstatus=0,
			crm_deal="DEAL-0001",
			selling_price_list="Negotiated Year 1",
			items=[],
			net_total=0,
			vat_amount=0,
			grand_total=0,
			flags=SimpleNamespace(),
		)
		quote.get = lambda fieldname, default=None: getattr(quote, fieldname, default)
		quote.set_missing_values = lambda: None
		quote.save = lambda **kwargs: None
		with (
			patch("crm.api.quotes._require_manager"),
			patch("crm.api.quotes.frappe.get_doc", return_value=quote),
			# An Opt-In summary may already exist; only the facility signature closes
			# the quotation price-list editing window.
			patch("crm.api.quotes.frappe.db.get_value", return_value="OIS-0001"),
			patch("crm.api.quotes.frappe.db.exists", return_value=True),
			patch("crm.api.quotes.frappe.get_list", return_value=[]),
			patch("crm.api.quotes.apply_quotation_taxes"),
			patch("crm.api.quotes.log_deal_event") as log_event,
		):
			result = set_quote_price_list("QUO-0001", "Negotiated Year 2")

		self.assertEqual(result["price_list"], "Negotiated Year 2")
		log_event.assert_called_once_with(
			"DEAL-0001",
			"Price list changed on quotation QUO-0001: Negotiated Year 1 → Negotiated Year 2 before facility signature",
		)

	def test_price_list_change_is_blocked_after_facility_signature(self):
		quote = frappe._dict(
			{"docstatus": 0, "crm_deal": "DEAL-0001", "selling_price_list": "Negotiated Year 1"}
		)
		with (
			patch("crm.api.quotes._require_manager"),
			patch("crm.api.quotes.frappe.get_doc", return_value=quote),
			patch("crm.api.quotes._facility_signatory_has_signed", return_value=True),
			patch("crm.api.quotes.frappe.db.get_value", return_value=None),
		):
			with self.assertRaises(Exception):
				set_quote_price_list("QUO-0001", "Negotiated Year 2")

	def test_price_list_change_fails_closed_when_signature_status_cannot_be_verified(self):
		quote = frappe._dict(
			{"docstatus": 0, "crm_deal": "DEAL-0001", "selling_price_list": "Negotiated Year 1"}
		)
		with (
			patch("crm.api.quotes._require_manager"),
			patch("crm.api.quotes.frappe.get_doc", return_value=quote),
			patch("crm.api.quotes._facility_signatory_has_signed", return_value=None),
			patch("crm.api.quotes.frappe.db.get_value", return_value=None),
		):
			with self.assertRaises(Exception):
				set_quote_price_list("QUO-0001", "Negotiated Year 2")


class TestQuotationPrintTaxSummary(UnitTestCase):
	def test_print_summary_uses_a_friendly_native_vat_label_when_configuration_is_unavailable(self):
		quote = frappe._dict(
			{
				"net_total": 100_000,
				"vat_amount": 0,
				"total_taxes_and_charges": 16_000,
				"grand_total": 100_000,
				"taxes": [
					frappe._dict(
						{
							"description": "VAT @ 16%",
							"account_head": "VAT - TB",
							"rate": 16,
						}
					)
				],
			}
		)
		with patch(
			"crm.utils.quotation_tax.quotation_tax_summary", side_effect=Exception("missing template")
		):
			result = get_quotation_tax_summary(quote)

		self.assertEqual(result.vat_label, "VAT (16%)")
		self.assertEqual(result.vat_amount, 16_000)
		self.assertEqual(result.grand_total, 116_000)
