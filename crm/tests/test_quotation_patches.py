from unittest.mock import patch

from frappe.tests import UnitTestCase

from crm.patches.v1_0.add_quotation_crm_fields import execute as add_quotation_crm_fields
from crm.patches.v1_0.create_custom_fields_for_quote_invoice_link import (
	execute as add_sales_invoice_quote_link,
)


class TestQuotationPatches(UnitTestCase):
	def test_quotation_patch_skips_a_crm_only_site(self):
		with (
			patch(
				"crm.patches.v1_0.add_quotation_crm_fields.frappe.db.exists",
				return_value=False,
			) as exists,
			patch("crm.patches.v1_0.add_quotation_crm_fields.create_custom_fields") as create_custom_fields,
		):
			add_quotation_crm_fields()

		exists.assert_called_once_with("DocType", "Quotation")
		create_custom_fields.assert_not_called()

	def test_quotation_patch_skips_only_the_absent_sales_invoice(self):
		def doctype_exists(doctype, name):
			return doctype == "DocType" and name in {"Quotation", "Quotation Item"}

		with (
			patch(
				"crm.patches.v1_0.add_quotation_crm_fields.frappe.db.exists",
				side_effect=doctype_exists,
			),
			patch("crm.patches.v1_0.add_quotation_crm_fields.create_custom_fields") as create_custom_fields,
			patch("crm.patches.v1_0.add_quotation_crm_fields.frappe.clear_cache") as clear_cache,
			patch("crm.patches.v1_0.add_quotation_crm_fields.frappe.db.sql") as sql,
		):
			add_quotation_crm_fields()

		create_custom_fields.assert_called_once()
		clear_cache.assert_called_once_with()
		sql.assert_not_called()

	def test_sales_invoice_link_patch_skips_a_crm_only_site(self):
		with (
			patch(
				"crm.patches.v1_0.create_custom_fields_for_quote_invoice_link.frappe.db.exists",
				return_value=False,
			),
			patch(
				"crm.patches.v1_0.create_custom_fields_for_quote_invoice_link.create_custom_fields"
			) as create_custom_fields,
		):
			add_sales_invoice_quote_link()

		create_custom_fields.assert_not_called()
