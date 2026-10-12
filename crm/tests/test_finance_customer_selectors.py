from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.finance.api import create_customer_payment, get_customer_payment_options


class TestFinanceCustomerSelectors(UnitTestCase):
	def _options(self, company, search_term=""):
		rows = [
			{"company": "Careverse HQ", "docstatus": 1, "outstanding_amount": 75, "customer": "CUST-001", "invoice_customer_name": "Old Acme Snapshot"},
			{"company": "Careverse HQ", "docstatus": 1, "outstanding_amount": 35, "customer": "CUST-001", "invoice_customer_name": "Acme Holdings Snapshot"},
			{"company": "Careverse HQ", "docstatus": 1, "outstanding_amount": 20, "customer": "CUST-002", "invoice_customer_name": "Acme Snapshot"},
			{"company": "Careverse HQ", "docstatus": 1, "outstanding_amount": 1, "customer": "CUST-003", "invoice_customer_name": "Acme Health Snapshot"},
			{"company": "Careverse HQ", "docstatus": 0, "outstanding_amount": 99, "customer": "DRAFT-CUSTOMER", "invoice_customer_name": "Draft Customer"},
			{"company": "Careverse HQ", "docstatus": 1, "outstanding_amount": 0, "customer": "PAID-CUSTOMER", "invoice_customer_name": "Paid Customer"},
			{"company": "Other Company", "docstatus": 1, "outstanding_amount": 200, "customer": "OTHER-CUSTOMER", "invoice_customer_name": "Other Company Customer"},
		]
		customer_names = {
			"CUST-001": "Acme",
			"CUST-002": "Acme",
			"CUST-003": "Acme Health",
			"DRAFT-CUSTOMER": "Draft Customer",
			"PAID-CUSTOMER": "Paid Customer",
			"OTHER-CUSTOMER": "Other Company Customer",
		}
		self.last_adapter_calls = []

		def permission_filtered_list(doctype, filters, **kwargs):
			self.last_adapter_calls.append((doctype, filters, kwargs))
			if doctype == "Sales Invoice":
				self.assertIn(["company", "=", company], filters)
				self.assertIn(["docstatus", "=", 1], filters)
				self.assertIn(["outstanding_amount", ">", 0], filters)
				self.assertEqual(kwargs["fields"], ["customer"])
				self.assertEqual(kwargs["group_by"], "customer")
				self.assertNotIn("or_filters", kwargs)
				eligible_ids = sorted(
					{
						row["customer"]
						for row in rows
						if row["company"] == company
						and row["docstatus"] == 1
						and row["outstanding_amount"] > 0
					}
				)
				start = kwargs["limit_start"]
				page_size = kwargs["limit_page_length"]
				return [{"customer": name} for name in eligible_ids[start : start + page_size]]

			self.assertEqual(doctype, "Customer")
			self.assertEqual(kwargs["fields"], ["name", "customer_name"])
			self.assertNotIn("or_filters", kwargs)
			customer_ids = filters[0][2]
			return [
				{"name": name, "customer_name": customer_names[name]}
				for name in customer_ids
				if name in customer_names
			]

		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User"]),
			patch("crm.finance.api._resolve_company", return_value=company) as resolve_company,
			patch("crm.finance.api.erpnext_adapter.get_list", side_effect=permission_filtered_list),
		):
			options = get_customer_payment_options(company=company, search_term=search_term)

		resolve_company.assert_called_once_with(company)
		return options

	def test_options_are_derived_only_from_submitted_outstanding_invoices_in_company(self):
		options = self._options("Careverse HQ")

		self.assertEqual([row["value"] for row in options], ["CUST-001", "CUST-002", "CUST-003"])
		self.assertNotIn("DRAFT-CUSTOMER", [row["value"] for row in options])
		self.assertNotIn("PAID-CUSTOMER", [row["value"] for row in options])
		self.assertNotIn("OTHER-CUSTOMER", [row["value"] for row in options])
		self.assertEqual(options[0]["label"], "Acme · CUST-001")
		self.assertEqual(options[1]["label"], "Acme · CUST-002")
		self.assertEqual(options[2]["label"], "Acme Health · CUST-003")
		invoice_call = next(call for call in self.last_adapter_calls if call[0] == "Sales Invoice")
		self.assertEqual(set(invoice_call[2]), {"fields", "group_by", "order_by", "limit_start", "limit_page_length"})

	def test_same_customer_with_different_invoice_name_snapshots_returns_one_current_label(self):
		options = self._options("Careverse HQ")
		matching = [option for option in options if option["value"] == "CUST-001"]

		self.assertEqual(matching, [{"label": "Acme · CUST-001", "value": "CUST-001"}])
		invoice_call = next(call for call in self.last_adapter_calls if call[0] == "Sales Invoice")
		self.assertEqual(invoice_call[2]["fields"], ["customer"])

	def test_company_isolation_uses_the_requested_company_for_eligibility(self):
		options = self._options("Other Company")

		self.assertEqual(options, [{"label": "Other Company Customer · OTHER-CUSTOMER", "value": "OTHER-CUSTOMER"}])

	def test_search_matches_customer_id_and_display_name_without_collapsing_ids(self):
		by_id = self._options("Careverse HQ", "CUST-002")
		by_name = self._options("Careverse HQ", "Acme Health")

		self.assertEqual(by_id, [{"label": "Acme · CUST-002", "value": "CUST-002"}])
		self.assertEqual(by_name, [{"label": "Acme Health · CUST-003", "value": "CUST-003"}])

	def test_stale_or_non_eligible_invoice_is_rejected_before_payment_entry_creation(self):
		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User"]),
			patch("crm.finance.api._resolve_company", return_value="Careverse HQ"),
			patch("crm.finance.api.frappe.has_permission"),
			patch(
				"crm.finance.api._get_customer_payment_context",
				return_value={"configured": True, "account": "Cash - CHQ"},
			),
			patch("crm.finance.api.get_customer_outstanding_invoices", return_value=[]),
			patch("crm.finance.api._get_customer_payment_entry") as create_entry,
		):
			with self.assertRaises(frappe.ValidationError):
				create_customer_payment(
					company="Careverse HQ",
					customer="CUST-001",
					mode_of_payment="Cash",
					allocations=[{"invoice": "SINV-STALE", "amount": 10}],
				)

		create_entry.assert_not_called()
