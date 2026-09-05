from datetime import date

from frappe.tests import UnitTestCase

from crm.utils.optin_bundles import (
	add_months,
	billing_schedule,
	effective_year_price_list,
	invoice_issue_timing,
	normalize_price_lists,
	split_period_amount,
)


class TestOptInBundleHelpers(UnitTestCase):
	def test_normalize_price_lists_preserves_explicit_order_and_legacy_fallback(self):
		self.assertEqual(
			normalize_price_lists(
				[
					{"year_number": 2, "price_list": "Year Two"},
					{"year_number": 1, "price_list": "Year One"},
					{"year_number": 3, "price_list": "Disabled", "enabled": False},
				],
				"Legacy",
			),
			[
				{"year_number": 1, "price_list": "Year One", "label": "Year 1", "enabled": True},
				{"year_number": 2, "price_list": "Year Two", "label": "Year 2", "enabled": True},
			],
		)
		self.assertEqual(
			normalize_price_lists([], "Legacy"),
			[{"year_number": 1, "price_list": "Legacy", "label": "Year 1", "enabled": True}],
		)

	def test_facility_override_wins_over_network_year_plan(self):
		plans = [
			{"year_number": 1, "price_list": "Network Year One"},
			{"year_number": 2, "price_list": "Network Year Two"},
		]
		self.assertEqual(
			effective_year_price_list(2, plans, '{"2": "Facility Year Two"}'),
			"Facility Year Two",
		)
		self.assertEqual(effective_year_price_list(1, plans, "{}", ""), "Network Year One")

	def test_billing_schedule_uses_calendar_months_and_thirty_day_due_dates(self):
		rows = billing_schedule(date(2026, 1, 31), [1, 2], 3)
		self.assertEqual(len(rows), 8)
		self.assertEqual(rows[0]["invoice_date"], "2026-04-30")
		self.assertEqual(rows[0]["invoice_due_date"], "2026-05-30")
		self.assertEqual(rows[4]["invoice_date"], "2027-04-30")
		self.assertEqual(rows[-1]["billing_key"], "Y2-Q4")
		prefixed = billing_schedule(date(2026, 1, 31), [1], 3, key_prefix="OIS-1")
		self.assertEqual(prefixed[0]["billing_key"], "OIS-1-Y1-Q1")
		self.assertEqual(add_months(date(2028, 2, 29), 12), date(2029, 2, 28))

	def test_invoice_issue_timing_prefers_signature_rule_and_keeps_legacy_fallback(self):
		self.assertEqual(
			invoice_issue_timing({"invoice_on_contract_signature": 1}),
			{
				"mode": "contract_signature",
				"label": "on contract signature",
			},
		)
		self.assertEqual(
			invoice_issue_timing({"first_invoice_offset_months": 2})["label"],
			"2 months after Opt-In submission",
		)

	def test_split_period_amount_carries_rounding_remainder_to_last_period(self):
		self.assertEqual([split_period_amount(100.01, quarter) for quarter in range(1, 5)], [25, 25, 25, 25.01])
