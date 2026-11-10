"""Pure-logic tests for crm.utils.portal_commercial (no site, no frappe runtime)."""

import unittest

from crm.utils.portal_commercial import (
	apply_live_balance,
	attribute_facilities,
	can_create_invoice,
	cycle_label,
	decide_commercial,
	empty_commercial,
	fixed_plan_status,
	is_schedule_governed,
	next_invoice,
	network_plan_status,
	order_display_status,
	order_display_title,
	order_doc_kind,
	period_label,
	quote_status_label,
	schedule_rows,
	term_label,
)


class AttributeFacilitiesTests(unittest.TestCase):
	def test_header_wins(self):
		self.assertEqual(attribute_facilities("MFL-A", ["MFL-B"], ["MFL-C"], ["MFL-D"]), ["MFL-A"])

	def test_item_mfls_when_header_empty(self):
		self.assertEqual(attribute_facilities("", ["MFL-B"], ["MFL-C"], ["MFL-D"]), ["MFL-B"])

	def test_ois_snapshot_when_no_header_or_items(self):
		self.assertEqual(attribute_facilities(None, [], ["MFL-C", "MFL-C2"], ["MFL-D"]), ["MFL-C", "MFL-C2"])

	def test_single_account_facility_fallback(self):
		self.assertEqual(attribute_facilities(None, [], [], ["MFL-D"]), ["MFL-D"])

	def test_multi_facility_account_is_account_level(self):
		self.assertEqual(attribute_facilities(None, [], [], ["MFL-A", "MFL-B"]), [])

	def test_empty_lists_are_account_level(self):
		self.assertEqual(attribute_facilities(None, None, None, None), [])

	def test_mixed_case_duplicates_deduped_first_wins(self):
		self.assertEqual(
			attribute_facilities(None, ["mfl-a", "MFL-A", "Mfl-A", "MFL-B"], [], []),
			["mfl-a", "MFL-B"],
		)

	def test_three_item_mfls_preserve_order(self):
		self.assertEqual(attribute_facilities(None, ["C", "A", "B"], [], []), ["C", "A", "B"])

	def test_whitespace_values_ignored(self):
		self.assertEqual(attribute_facilities("  ", ["  ", "X"], [], []), ["X"])


class ScheduleGovernedTests(unittest.TestCase):
	def test_billing_key_governs(self):
		self.assertTrue(is_schedule_governed("Y1-Q1", 0))

	def test_year_governs(self):
		self.assertTrue(is_schedule_governed(None, 1))

	def test_token_order_year_zero_not_governed(self):
		self.assertFalse(is_schedule_governed(None, 0))

	def test_non_numeric_year_not_governed(self):
		self.assertFalse(is_schedule_governed("", "abc"))

	def test_blank_key_zero_year(self):
		self.assertFalse(is_schedule_governed("   ", 0))


class PeriodLabelTests(unittest.TestCase):
	def test_standard(self):
		self.assertEqual(period_label(1, 2), "Year 1 · Quarter 2")

	def test_year_zero_empty(self):
		self.assertEqual(period_label(0, 1), "")

	def test_non_numeric_year_empty(self):
		self.assertEqual(period_label("x", 1), "")

	def test_missing_year_empty(self):
		self.assertEqual(period_label(None, 1), "")


class OrderDocKindTests(unittest.TestCase):
	def test_governed_is_subscription(self):
		self.assertEqual(order_doc_kind(True, None), "subscription")

	def test_fixed_is_subscription(self):
		self.assertEqual(order_doc_kind(False, "Fixed"), "subscription")

	def test_flex_is_token(self):
		self.assertEqual(order_doc_kind(False, "Flex"), "token")

	def test_custom_is_token(self):
		self.assertEqual(order_doc_kind(False, "Custom"), "token")

	def test_no_package_is_other(self):
		self.assertEqual(order_doc_kind(False, None), "other")

	def test_governed_wins_over_package(self):
		self.assertEqual(order_doc_kind(True, "Flex"), "subscription")


class OrderDisplayTitleTests(unittest.TestCase):
	def test_governed_with_period(self):
		self.assertEqual(
			order_display_title("subscription", True, "Year 1 · Quarter 1", None),
			"Year 1 · Quarter 1 subscription",
		)

	def test_governed_without_period(self):
		self.assertEqual(order_display_title("subscription", True, "", "Nope"), "Subscription order")

	def test_fixed_uses_package_name(self):
		self.assertEqual(order_display_title("subscription", False, "", "Quarterly Essentials"), "Quarterly Essentials")

	def test_token_uses_package_name(self):
		self.assertEqual(order_display_title("token", False, "", "Flex 10k"), "Flex 10k")

	def test_token_fallback(self):
		self.assertEqual(order_display_title("token", False, "", ""), "Token order")

	def test_other_is_plain_order(self):
		self.assertEqual(order_display_title("other", False, "", "Item-123"), "Order")


class OrderDisplayStatusTests(unittest.TestCase):
	def test_draft_needs_review(self):
		self.assertEqual(order_display_status(0, "Draft", 0, True), "Needs your review")

	def test_closed(self):
		self.assertEqual(order_display_status(1, "Closed", 0, False), "Closed")

	def test_on_hold(self):
		self.assertEqual(order_display_status(1, "On Hold", 0, False), "On hold")

	def test_completed(self):
		self.assertEqual(order_display_status(1, "Completed", 0, False), "Complete")

	def test_fully_billed_is_invoiced(self):
		# A billed order keeps a non-terminal ERPNext status (often still "Draft").
		self.assertEqual(order_display_status(1, "Draft", 100, False), "Invoiced")

	def test_completed_beats_invoiced(self):
		self.assertEqual(order_display_status(1, "Completed", 100, False), "Complete")

	def test_governed_draft_status_confirmed(self):
		self.assertEqual(order_display_status(1, "Draft", 0, True), "Confirmed")

	def test_ungoverned_draft_status_awaiting_invoice(self):
		self.assertEqual(order_display_status(1, "Draft", 0, False), "Awaiting invoice")

	def test_invoiced_beats_governed(self):
		self.assertEqual(order_display_status(1, "Draft", 100, True), "Invoiced")

	def test_draft_never_returned(self):
		self.assertNotEqual(order_display_status(1, "Draft", 5, True), "Draft")


class CanCreateInvoiceTests(unittest.TestCase):
	def test_draft_blocked(self):
		self.assertFalse(can_create_invoice(True, "Draft", False))

	def test_governed_blocked(self):
		self.assertFalse(can_create_invoice(False, "Draft", True))

	def test_closed_blocked(self):
		self.assertFalse(can_create_invoice(False, "Closed", False))

	def test_on_hold_blocked(self):
		self.assertFalse(can_create_invoice(False, "On Hold", False))

	def test_cancelled_blocked(self):
		self.assertFalse(can_create_invoice(False, "Cancelled", False))

	def test_normal_allowed(self):
		self.assertTrue(can_create_invoice(False, "Draft", False))


class DecideCommercialTests(unittest.TestCase):
	def test_network_wins(self):
		row = decide_commercial(True, "Flex", False, 1)
		self.assertEqual(row["journey"], "network_optin")
		self.assertEqual(row["journey_label"], "Network Opt-In")
		self.assertEqual(row["plan_type"], "time_bound")
		self.assertTrue(row["has_tokens"])

	def test_fixed_self_onboarding_time_bound(self):
		row = decide_commercial(False, "Fixed", True, 0)
		self.assertEqual(row["journey"], "self_onboarding")
		self.assertEqual(row["journey_label"], "Self-Onboarding")
		self.assertEqual(row["plan_type"], "time_bound")
		self.assertFalse(row["has_tokens"])

	def test_flex_token_even_with_recurring_order(self):
		# Recurrence is not an input; token_order_count covers the purchase.
		row = decide_commercial(False, "Flex", True, 3)
		self.assertEqual(row["plan_type"], "token")
		self.assertTrue(row["has_tokens"])

	def test_custom_token(self):
		self.assertEqual(decide_commercial(False, "Custom", False, 0)["plan_type"], "token")

	def test_token_orders_without_package(self):
		# Journey only keys on the network plan, self-onboarding or a package (SPEC 4.3).
		row = decide_commercial(False, None, False, 2)
		self.assertEqual(row["journey"], "unknown")
		self.assertEqual(row["plan_type"], "token")
		self.assertTrue(row["has_tokens"])

	def test_token_orders_self_onboarding(self):
		row = decide_commercial(False, "Flex", True, 2)
		self.assertEqual(row["journey"], "self_onboarding")
		self.assertEqual(row["plan_type"], "token")

	def test_unknown(self):
		row = decide_commercial(False, None, False, 0)
		self.assertEqual(row["journey"], "unknown")
		self.assertEqual(row["journey_label"], "")
		self.assertEqual(row["plan_type"], "unknown")
		self.assertFalse(row["has_tokens"])

	def test_balance_makes_has_tokens(self):
		row = decide_commercial(False, None, False, 0, balance_status="ok", balance=10)
		self.assertTrue(row["has_tokens"])

	def test_not_metered_balance_ignored(self):
		row = decide_commercial(False, None, False, 0, balance_status="not_metered", balance=10)
		self.assertFalse(row["has_tokens"])

	def test_time_bound_with_token_orders(self):
		row = decide_commercial(False, "Fixed", True, 1)
		self.assertEqual(row["plan_type"], "time_bound")
		self.assertTrue(row["has_tokens"])


class ApplyLiveBalanceTests(unittest.TestCase):
	def test_positive_ok_balance_sets_has_tokens(self):
		row = apply_live_balance({"plan_type": "unknown", "has_tokens": False}, {"status": "ok", "balance": 5})
		self.assertTrue(row["has_tokens"])

	def test_non_ok_balance_ignored(self):
		row = apply_live_balance({"has_tokens": False}, {"status": "unavailable"})
		self.assertFalse(row["has_tokens"])

	def test_existing_has_tokens_kept(self):
		row = apply_live_balance({"has_tokens": True}, {"status": "not_metered"})
		self.assertTrue(row["has_tokens"])

	def test_empty_entry(self):
		self.assertFalse(apply_live_balance({"has_tokens": False}, None)["has_tokens"])


class ScheduleRowsTests(unittest.TestCase):
	def test_allow_list_only(self):
		rows = schedule_rows(
			[
				{
					"period_label": "Year 1 · Quarter 1",
					"invoice_date": "2027-01-30",
					"invoice_due_date": "2027-03-01",
					"amount_incl_vat": 6960,
					"status": "Pending",
					"preview": True,
					"error": "boom",
					"handoff_note": "internal",
				}
			],
			contract_complete=False,
		)
		self.assertEqual(
			rows[0],
			{
				"label": "Year 1 · Quarter 1",
				"invoice_date": "2027-01-30",
				"due_date": "2027-03-01",
				"amount_incl_vat": 6960,
				"state": "upcoming",
				"projected": True,
			},
		)
		self.assertNotIn("error", rows[0])
		self.assertNotIn("handoff_note", rows[0])

	def test_failed_row_is_preparing(self):
		rows = schedule_rows([{"status": "Failed", "preview": False}], contract_complete=True)
		self.assertEqual(rows[0]["state"], "preparing")

	def test_invoiced_by_status(self):
		rows = schedule_rows([{"status": "Invoiced"}], contract_complete=True)
		self.assertEqual(rows[0]["state"], "invoiced")

	def test_invoiced_by_sales_invoice(self):
		rows = schedule_rows([{"status": "Failed", "sales_invoice": "ACC-SINV-1"}], contract_complete=True)
		self.assertEqual(rows[0]["state"], "invoiced")

	def test_label_falls_back_to_year_quarter(self):
		rows = schedule_rows([{"year_number": 2, "quarter_number": 3}], contract_complete=True)
		self.assertEqual(rows[0]["label"], "Year 2 · Quarter 3")

	def test_year_and_quarter_beat_the_repeating_stored_label(self):
		rows = schedule_rows([{"year_number": 3, "quarter_number": 1, "period_label": "Quarter 1"}], contract_complete=True)
		self.assertEqual(rows[0]["label"], "Year 3 · Quarter 1")

	def test_non_dict_rows_skipped(self):
		self.assertEqual(schedule_rows(["junk", None], contract_complete=True), [])


class NextInvoiceTests(unittest.TestCase):
	def test_earliest_not_invoiced(self):
		schedule = schedule_rows(
			[
				{"period_label": "Q1", "invoice_date": "2027-01-30", "sales_invoice": "X"},
				{"period_label": "Q2", "invoice_date": "2026-12-31"},
				{"period_label": "Q3", "invoice_date": "2027-04-30"},
			],
			contract_complete=True,
		)
		self.assertEqual(next_invoice(schedule)["label"], "Q2")

	def test_all_invoiced_is_none(self):
		schedule = schedule_rows([{"sales_invoice": "X"}, {"status": "Invoiced"}], contract_complete=True)
		self.assertIsNone(next_invoice(schedule))

	def test_empty_is_none(self):
		self.assertIsNone(next_invoice([]))


class PlanStatusTests(unittest.TestCase):
	def test_network_being_set_up(self):
		self.assertEqual(network_plan_status("Draft", True), "Being set up")

	def test_network_awaiting_signatures(self):
		self.assertEqual(network_plan_status("Processed", False), "Awaiting signatures")

	def test_network_active(self):
		self.assertEqual(network_plan_status("Processed", True), "Active")

	def test_fixed_active(self):
		self.assertEqual(fixed_plan_status(True), "Active")

	def test_fixed_awaiting_first_payment(self):
		self.assertEqual(fixed_plan_status(False), "Awaiting first payment")


class LabelTests(unittest.TestCase):
	def test_cycle_labels(self):
		self.assertEqual(cycle_label("Monthly"), "Billed monthly")
		self.assertEqual(cycle_label("Quarterly"), "Billed quarterly")
		self.assertEqual(cycle_label("Semi-annual"), "Billed every six months")
		self.assertEqual(cycle_label("Annual"), "Billed annually")
		self.assertEqual(cycle_label(""), "")
		self.assertEqual(cycle_label(None), "")

	def test_term_labels(self):
		self.assertEqual(term_label(1), "1 year")
		self.assertEqual(term_label(3), "3 years")
		self.assertEqual(term_label(0), "")
		self.assertEqual(term_label("x"), "")

	def test_quote_status_labels(self):
		self.assertEqual(quote_status_label(1), "Accepted")
		self.assertEqual(quote_status_label(0), "Planned")
		self.assertEqual(quote_status_label(2), "")


class EmptyCommercialTests(unittest.TestCase):
	def test_unknown_shape(self):
		row = empty_commercial()
		self.assertEqual(row["journey"], "unknown")
		self.assertEqual(row["plan_type"], "unknown")
		self.assertFalse(row["has_tokens"])
		self.assertFalse(row["unavailable"])
		self.assertEqual(row["plan"]["source"], "none")
		self.assertEqual(row["quotes"], [])

	def test_unavailable_flag(self):
		self.assertTrue(empty_commercial(unavailable=True)["unavailable"])


if __name__ == "__main__":
	unittest.main()
