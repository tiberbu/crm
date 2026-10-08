from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from crm.automation.optin_billing import (
	_facility_handoff_schedule,
	_find_billing_document,
	_invoice_at_facility_handoff,
	_quarter_items,
)


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
		with (
			patch("crm.automation.optin_billing.frappe.db.exists", return_value=True),
			patch("crm.automation.optin_billing.frappe.db.has_column", return_value=False),
		):
			self.assertEqual(_find_billing_document("Sales Invoice", "SUB-1-Y1-Q1"), "")

	def test_facility_handoff_creates_traceable_q1_row_without_invoice_schedule(self):
		submission = SimpleNamespace(name="SUB-1", billing_schedule_json="[]")
		schedules, row, persisted = _facility_handoff_schedule(submission, "2026-10-08")

		self.assertEqual(schedules, [])
		self.assertFalse(persisted)
		self.assertEqual(row["year_number"], 1)
		self.assertEqual(row["quarter_number"], 1)
		self.assertFalse(row["invoice_schedule_configured"])
		self.assertIn("no Sales Invoice was generated", row["error"])

	def test_facility_handoff_invoice_requires_native_signature_timing_rule(self):
		self.assertTrue(
			_invoice_at_facility_handoff(
				{"invoice_issue_timing": "contract_signature"}, True
			)
		)
		self.assertFalse(
			_invoice_at_facility_handoff(
				{"invoice_issue_timing": "submission_offset"}, True
			)
		)
		self.assertFalse(
			_invoice_at_facility_handoff(
				{"invoice_issue_timing": "contract_signature"}, False
			)
		)
