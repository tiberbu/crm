"""Pure rules of the Opt-In billing ledger (spec P-124 to P-133). No site needed."""

import unittest

from crm.utils import optin_ledger as rules


def _row(year, quarter, **extra):
	row = {
		"year_number": year,
		"quarter_number": quarter,
		"invoice_date": "2027-%02d-30" % (1 + (quarter - 1) * 3),
		"invoice_due_date": "2027-%02d-28" % (2 + (quarter - 1) * 3),
		"amount_incl_vat": 100.0,
		"status": "Scheduled",
		"billing_key": "OIS-1-Y%d-Q%d" % (year, quarter),
	}
	row.update(extra)
	return row


class TestPeriodState(unittest.TestCase):
	def test_labels_name_the_year(self):
		self.assertEqual(rules.period_label(_row(3, 1, period_label="Quarter 1")), "Year 3 · Q1")

	def test_states(self):
		today = "2026-11-10"
		self.assertEqual(rules.period_state(_row(1, 1), None, today), "scheduled")
		self.assertEqual(rules.period_state(_row(1, 1, sales_order="SO-1"), None, today), "order_ready")
		self.assertEqual(rules.period_state(_row(1, 1, status="Failed"), None, today), "needs_attention")
		due = {"docstatus": 1, "outstanding": 50, "due_date": "2026-12-10"}
		self.assertEqual(rules.period_state(_row(1, 1), due, today), "due")
		self.assertEqual(rules.period_state(_row(1, 1), due, "2026-12-11"), "overdue")
		paid = {"docstatus": 1, "outstanding": 0, "due_date": "2026-12-10"}
		self.assertEqual(rules.period_state(_row(1, 1), paid, today), "paid_ahead")
		self.assertEqual(rules.period_state(_row(1, 1), paid, "2027-02-01"), "paid")

	def test_paid_ahead_uses_the_contract_date_after_an_early_issue(self):
		row = _row(1, 2, invoice_date="2026-11-10", scheduled_invoice_date="2027-04-30")
		paid = {"docstatus": 1, "outstanding": 0, "due_date": "2027-05-30"}
		self.assertEqual(rules.period_state(row, paid, "2026-11-11"), "paid_ahead")


class TestPayingAhead(unittest.TestCase):
	def setUp(self):
		self.rows = [_row(2, 1), _row(1, 2), _row(1, 1, sales_invoice="SINV-1"), _row(1, 3)]

	def test_next_periods_are_in_order_and_skip_issued(self):
		picked = rules.select_next_periods(self.rows, 2)
		self.assertEqual([rules.period_label(r) for r in picked], ["Year 1 · Q2", "Year 1 · Q3"])

	def test_count_is_bounded(self):
		with self.assertRaises(ValueError):
			rules.select_next_periods(self.rows, 0)
		with self.assertRaises(ValueError):
			rules.select_next_periods(self.rows, rules.MAX_ADVANCE_PERIODS + 1)

	def test_early_due_date_is_never_sooner_than_the_contract(self):
		self.assertEqual(rules.early_due_date("2026-11-10", "2027-05-30"), "2027-05-30")
		self.assertEqual(rules.early_due_date("2027-06-01", "2027-05-30"), "2027-06-01")
		self.assertEqual(rules.early_due_date("2026-11-10", ""), "2026-11-10")

	def test_policy(self):
		self.assertFalse(rules.advance_policy("Submitted", "Fully Executed", self.rows, 0)["allowed"])
		blocked = rules.advance_policy("Processed", "Awaiting Signatures", self.rows, 0)
		self.assertFalse(blocked["allowed"])
		self.assertIn("signed", blocked["reason"])
		self.assertFalse(rules.advance_policy("Processed", "Fully Executed", self.rows, rules.MAX_UNPAID_INVOICES)["allowed"])
		open_policy = rules.advance_policy("Processed", "Fully Executed", self.rows, 2)
		self.assertTrue(open_policy["allowed"])
		self.assertEqual(open_policy["remaining"], 3)
		self.assertEqual(open_policy["max_periods"], 2)
		done = [_row(1, 1, sales_invoice="S")]
		self.assertFalse(rules.advance_policy("Processed", "Fully Executed", done, 0)["allowed"])


class TestCustomerInvoicesOnlyWhenDue(unittest.TestCase):
	"""P-134: a customer never invoices a period ahead of its contract date."""

	def setUp(self):
		# Q1 on 2027-01-30, Q2 on 2027-04-30, Q3 on 2027-07-30; Q1 already invoiced.
		self.rows = [_row(1, 1, sales_invoice="SINV-1"), _row(1, 2), _row(1, 3)]

	def test_nothing_is_issuable_before_the_date(self):
		policy = rules.advance_policy("Processed", "Fully Executed", self.rows, 0, today="2027-02-01", due_only=True)
		self.assertFalse(policy["allowed"])
		self.assertIn("2027-04-30", policy["reason"])
		self.assertEqual(rules.select_next_periods(self.rows, 1, today="2027-02-01", due_only=True), [])

	def test_only_due_periods_are_issuable(self):
		policy = rules.advance_policy("Processed", "Fully Executed", self.rows, 0, today="2027-05-01", due_only=True)
		self.assertTrue(policy["allowed"])
		self.assertEqual(policy["max_periods"], 1)
		picked = rules.select_next_periods(self.rows, 2, today="2027-05-01", due_only=True)
		self.assertEqual([rules.period_label(r) for r in picked], ["Year 1 · Q2"])

	def test_the_date_itself_counts_as_due(self):
		self.assertTrue(rules.is_due(_row(1, 2), "2027-04-30"))
		self.assertFalse(rules.is_due(_row(1, 2), "2027-04-29"))

	def test_staff_may_still_issue_early(self):
		policy = rules.advance_policy("Processed", "Fully Executed", self.rows, 0, today="2027-02-01")
		self.assertTrue(policy["allowed"])
		self.assertEqual(policy["max_periods"], 2)


class TestSummary(unittest.TestCase):
	def test_totals_and_next_payment(self):
		periods = [
			{"label": "Year 1 · Q1", "amount": 100, "state": "paid_ahead", "sales_invoice": "S1", "invoice_total": 100, "outstanding": 0},
			{"label": "Year 1 · Q2", "amount": 100, "state": "overdue", "sales_invoice": "S2", "invoice_total": 100, "outstanding": 40, "due_date": "2026-11-01"},
			{"label": "Year 1 · Q3", "amount": 100, "state": "scheduled", "scheduled_date": "2027-07-30"},
		]
		summary = rules.ledger_summary(periods, "2026-11-10")
		self.assertEqual(summary["contract_total"], 300)
		self.assertEqual(summary["invoiced_total"], 200)
		self.assertEqual(summary["paid_total"], 160)
		self.assertEqual(summary["outstanding_total"], 40)
		self.assertEqual(summary["overdue_total"], 40)
		self.assertEqual(summary["paid_ahead_total"], 100)
		self.assertEqual(summary["next_payment"]["label"], "Year 1 · Q2")
		self.assertEqual(summary["next_payment"]["amount"], 40)
		self.assertEqual(summary["next_payment"]["date"], "2026-11-01")

	def test_quote_label_follows_the_contract(self):
		self.assertEqual(rules.quote_status_label("Fully Executed"), "Accepted")
		self.assertEqual(rules.quote_status_label("Awaiting Signatures"), "Awaiting signatures")


if __name__ == "__main__":
	unittest.main()
