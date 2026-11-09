"""Pure-logic tests for the paged facility documents endpoint (no site needed)."""

import unittest

from crm.api.facility_documents import page_rows, sort_invoices


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


if __name__ == "__main__":
	unittest.main()
