from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from crm.automation.optin_billing import _find_billing_document, _quarter_items


class TestOptInBillingHelpers(UnitTestCase):
	def test_quarter_items_reconcile_rounded_annual_amount_on_q4(self):
		quotation = SimpleNamespace(
			items=[
				SimpleNamespace(
					amount=100.01,
					qty=1,
					rate=100.01,
					item_code="ITEM-1",
					item_name="Subscription",
					description="Annual subscription",
					uom="Nos",
				)
			]
		)

		self.assertEqual(_quarter_items(quotation, 1)[0]["rate"], 25.0)
		self.assertEqual(_quarter_items(quotation, 4)[0]["rate"], 25.01)

	def test_billing_document_lookup_is_safe_when_custom_field_is_missing(self):
		with patch("crm.automation.optin_billing.frappe.db.exists", return_value=True), patch(
			"crm.automation.optin_billing.frappe.db.has_column", return_value=False
		):
			self.assertEqual(_find_billing_document("Sales Invoice", "SUB-1-Y1-Q1"), "")
