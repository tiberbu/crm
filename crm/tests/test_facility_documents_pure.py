"""Pure-logic tests for the paged facility documents endpoint (no site needed)."""

import unittest

from crm.api.facility_documents import page_rows, sort_invoices
from crm.api.portal_commercial import slim_facility_records


def _invoice(name, amount, due="", posted=""):
	return {"name": name, "amount": amount, "due_date": due, "posting_date": posted}


class SortInvoicesTests(unittest.TestCase):
	def test_open_first_by_due_date_then_paid_newest_first(self):
		rows = [
			_invoice("PAID-OLD", 0, posted="2026-01-01"),
			_invoice("OPEN-LATE", 50, due="2026-03-01"),
			_invoice("PAID-NEW", 0, posted="2026-05-01"),
			_invoice("OPEN-SOON", 20, due="2026-02-01"),
		]
		self.assertEqual(
			[row["name"] for row in sort_invoices(rows)],
			["OPEN-SOON", "OPEN-LATE", "PAID-NEW", "PAID-OLD"],
		)


class PageRowsTests(unittest.TestCase):
	def setUp(self):
		self.orders = [
			{"name": "SO-%03d" % i, "transaction_date": "2026-01-%02d" % (i % 28 + 1)} for i in range(100)
		]

	def test_slices_one_page_and_reports_total(self):
		page = page_rows(self.orders, kind="order", status="all", search="", start=0, page_length=20)
		self.assertEqual(len(page["rows"]), 20)
		self.assertEqual(page["total"], 100)
		self.assertEqual(page["counts"]["all"], 100)

	def test_last_page_is_partial(self):
		page = page_rows(self.orders, kind="order", status="all", search="", start=90, page_length=20)
		self.assertEqual(len(page["rows"]), 10)

	def test_orders_newest_first(self):
		page = page_rows(self.orders, kind="order", status="all", search="", start=0, page_length=100)
		dates = [row["transaction_date"] for row in page["rows"]]
		self.assertEqual(dates, sorted(dates, reverse=True))

	def test_search_matches_name_case_insensitively(self):
		page = page_rows(self.orders, kind="order", status="all", search="so-04", start=0, page_length=20)
		self.assertEqual(sorted(row["name"] for row in page["rows"]), ["SO-%03d" % i for i in range(40, 50)])
		self.assertEqual(page["counts"]["all"], 100)

	def test_outstanding_filter_and_count(self):
		rows = [_invoice("A", 10, due="2026-01-01"), _invoice("B", 0, posted="2026-01-02"), _invoice("C", 5, due="2026-01-03")]
		page = page_rows(rows, kind="invoice", status="outstanding", search="", start=0, page_length=20)
		self.assertEqual([row["name"] for row in page["rows"]], ["A", "C"])
		self.assertEqual(page["counts"], {"all": 3, "outstanding": 2})
		every = page_rows(rows, kind="invoice", status="all", search="", start=0, page_length=20)
		self.assertEqual(every["total"], 3)

	def test_payment_search_matches_reference_and_invoice(self):
		rows = [
			{"name": "PE-1", "reference_no": "QWE123", "posting_date": "2026-01-01", "invoice_names": ["SINV-9"]},
			{"name": "PE-2", "reference_no": "ZZZ", "posting_date": "2026-01-02", "invoice_names": []},
		]
		self.assertEqual(
			[r["name"] for r in page_rows(rows, kind="payment", status="all", search="qwe", start=0, page_length=5)["rows"]],
			["PE-1"],
		)
		self.assertEqual(
			[r["name"] for r in page_rows(rows, kind="payment", status="all", search="sinv-9", start=0, page_length=5)["rows"]],
			["PE-1"],
		)


class SlimFacilityRecordsTests(unittest.TestCase):
	def _row(self):
		orders = [
			{"name": "SO-DRAFT", "is_draft": True},
			{"name": "SO-INVOICEABLE", "can_create_invoice": True},
			{"name": "SO-PKG", "crm_token_package_item": "TOK-A"},
			{"name": "SO-OLD-PKG", "crm_token_package_item": "TOK-B"},
		] + [{"name": "SO-DONE-%d" % i} for i in range(60)]
		invoices = [{"name": "SINV-DUE", "amount": 50}] + [{"name": "SINV-PAID-%d" % i, "amount": 0} for i in range(80)]
		payments = [{"name": "PE-PENDING", "status": "Pending Verification"}] + [
			{"name": "PE-%d" % i, "status": "Recorded"} for i in range(80)
		]
		return {"orders": orders, "invoices": invoices, "payments": payments}

	def test_keeps_only_actionable_records(self):
		row = slim_facility_records(self._row())
		self.assertEqual([o["name"] for o in row["orders"]], ["SO-DRAFT", "SO-INVOICEABLE", "SO-PKG"])
		self.assertEqual([i["name"] for i in row["invoices"]], ["SINV-DUE"])
		self.assertEqual([p["name"] for p in row["payments"]], ["PE-PENDING"])

	def test_counts_cover_the_full_history(self):
		row = slim_facility_records(self._row())
		self.assertEqual(
			row["record_counts"],
			{"order": 64, "order_draft": 1, "invoice": 81, "invoice_due": 1, "payment": 81, "payment_pending": 1},
		)

	def test_empty_row(self):
		row = slim_facility_records({})
		self.assertEqual((row["orders"], row["invoices"], row["payments"]), ([], [], []))
		self.assertEqual(row["record_counts"]["order"], 0)


if __name__ == "__main__":
	unittest.main()


class InvoiceTotalsTests(unittest.TestCase):
	def test_billed_paid_outstanding(self):
		from crm.api.facility_documents import invoice_totals

		totals = invoice_totals(
			[
				{"grand_total": 98922.24, "amount": 98922},  # unpaid; rounding is not a payment
				{"grand_total": 6960, "amount": 0},
				{"grand_total": 1000, "amount": 400},
			]
		)
		self.assertEqual(totals, {"billed": 106882.24, "paid": 7560.0, "outstanding": 99322.0})
