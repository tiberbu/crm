from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.finance.api import get_quotation_finance_context


class TestFinanceQuotationContext(UnitTestCase):
	def test_context_keeps_customer_facility_and_optin_network_distinct(self):
		quotation = {
			"name": "SAL-QTN-0001",
			"company": "Careverse HQ",
			"party_name": "CUSTOMER-1",
			"currency": "KES",
			"grand_total": 125000,
			"docstatus": 1,
			"crm_optin_submission": "OIS-0001",
			"optin_network": "care-network",
			"crm_deal": "CRM-DEAL-1",
		}
		submission = {
			"name": "OIS-0001",
			"network_slug": "care-network",
			"contract": "CONT-0001",
			"deal": "CRM-DEAL-1",
			"status": "Processed",
			"raw_json": '{"pricing":[{"mfl_code":"12345","facility_name":"Amani Clinic"}]}',
			"billing_schedule_json": "[]",
			"submitted_at": "2026-10-01",
		}

		def erp_list(doctype, filters, **kwargs):
			if doctype == "Quotation":
				return [quotation]
			if doctype == "Customer":
				return [{"name": "CUSTOMER-1", "customer_name": "Amani Health Ltd"}]
			if doctype == "Sales Order":
				return [
					{"name": "SO-0001", "company": "Careverse HQ", "customer": "CUSTOMER-1", "docstatus": 1, "status": "To Bill", "currency": "KES", "grand_total": 31250},
					{"name": "SO-OTHER", "company": "Other Company", "customer": "CUSTOMER-1", "docstatus": 1, "status": "To Bill", "currency": "KES", "grand_total": 31250},
				]
			if doctype == "Sales Invoice Item":
				return [{"parent": "SINV-0001"}, {"parent": "SINV-OTHER"}]
			if doctype == "Sales Invoice":
				return [
					{"name": "SINV-0001", "company": "Careverse HQ", "customer": "CUSTOMER-1", "docstatus": 1, "status": "Unpaid", "currency": "KES", "grand_total": 31250, "outstanding_amount": 31250, "posting_date": "2026-10-01", "due_date": "2026-10-31"},
					{"name": "SINV-OTHER", "company": "Other Company", "customer": "CUSTOMER-1", "docstatus": 1, "status": "Unpaid", "currency": "KES", "grand_total": 31250, "outstanding_amount": 31250, "posting_date": "2026-10-01", "due_date": "2026-10-31"},
				]
			if doctype == "Payment Entry Reference":
				return [{"parent": "ACC-PAY-0001"}, {"parent": "ACC-PAY-OTHER"}]
			if doctype == "Payment Entry":
				return [
					{"name": "ACC-PAY-0001", "company": "Careverse HQ", "docstatus": 1, "payment_type": "Receive", "posting_date": "2026-10-03", "paid_amount": 1000},
					{"name": "ACC-PAY-OTHER", "company": "Other Company", "docstatus": 1, "payment_type": "Receive", "posting_date": "2026-10-03", "paid_amount": 1000},
				]
			return []

		def local_list(doctype, filters, **kwargs):
			if doctype == "CRM Opt-In Submission":
				return [submission]
			if doctype == "CRM Opt-In Network":
				return [{"name": "NET-0001", "slug": "care-network", "display_name": "Care Network", "partner_id": "123456"}]
			if doctype == "CRM Pre-Qualified Facility":
				return [{"name": "PQF-0001", "mfl_code": "12345", "facility_name": "Amani Clinic"}]
			if doctype == "CRM Contract":
				return [{"name": "CONT-0001", "status": "Fully Executed"}]
			return []

		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User"]),
			patch("crm.finance.api._resolve_company", return_value="Careverse HQ"),
			patch("crm.finance.api.frappe.db.exists", return_value=True),
			patch("crm.finance.api.frappe.db.has_column", return_value=True),
			patch("crm.finance.api.frappe.get_list", side_effect=local_list),
			patch("crm.finance.api.erpnext_adapter.get_list", side_effect=erp_list) as adapter_list,
			patch("crm.finance.api._handoff_schedule", return_value={"invoice_issue_timing": "contract_signature", "invoice_date": "2026-10-02", "invoice_due_date": "2026-11-01"}),
		):
			context = get_quotation_finance_context("SAL-QTN-0001", "Careverse HQ")

		self.assertEqual(context["customer"], {"name": "CUSTOMER-1", "label": "Amani Health Ltd", "available": True})
		self.assertEqual(context["network"]["name"], "NET-0001")
		self.assertEqual(context["network"]["label"], "Care Network")
		self.assertEqual(context["facilities"], [{"name": "PQF-0001", "mfl_code": "12345", "label": "Amani Clinic", "available": True}])
		self.assertEqual(context["contract"]["status"], "Fully Executed")
		self.assertEqual(context["schedule"]["issue_timing"], "contract_signature")
		self.assertEqual([row["name"] for row in context["sales_orders"]], ["SO-0001"])
		self.assertEqual([row["name"] for row in context["sales_invoices"]], ["SINV-0001"])
		self.assertEqual([row["name"] for row in context["payments"]], ["ACC-PAY-0001"])
		for doctype in ("Sales Order", "Sales Invoice", "Payment Entry"):
			query = next(call for call in adapter_list.call_args_list if call.args[0] == doctype)
			self.assertIn(["company", "=", "Careverse HQ"], query.kwargs["filters"])

	def test_quote_from_another_company_returns_no_context(self):
		def cross_company_quote(doctype, filters, **kwargs):
			if doctype == "Quotation":
				return [{"name": "OTHER-COMPANY-QUOTE", "company": "Other Company"}]
			return []

		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User"]),
			patch("crm.finance.api._resolve_company", return_value="Careverse HQ"),
			patch("crm.finance.api.erpnext_adapter.get_list", side_effect=cross_company_quote) as get_list,
		):
			with self.assertRaises(frappe.PermissionError):
				get_quotation_finance_context("OTHER-COMPANY-QUOTE", "Careverse HQ")

		self.assertEqual(get_list.call_count, 1)
		self.assertIn(["company", "=", "Careverse HQ"], get_list.call_args.kwargs["filters"])

	def test_standard_quotation_item_link_finds_order_without_optin_tag(self):
		quotation = {
			"name": "SAL-QTN-0001",
			"company": "Careverse HQ",
			"party_name": "CUSTOMER-1",
			"currency": "KES",
			"grand_total": 125000,
			"docstatus": 1,
		}
		order = {
			"name": "SO-STANDARD-0001",
			"company": "Careverse HQ",
			"customer": "CUSTOMER-1",
			"docstatus": 1,
			"status": "To Bill",
			"currency": "KES",
			"grand_total": 31250,
		}

		def erp_list(doctype, filters, **kwargs):
			if doctype == "Quotation":
				return [quotation]
			if doctype == "Sales Order Item":
				return [{"parent": order["name"]}]
			if doctype == "Sales Order":
				if ["crm_optin_quotation", "=", quotation["name"]] in filters:
					return []
				return [order]
			return []

		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User"]),
			patch("crm.finance.api._resolve_company", return_value="Careverse HQ"),
			patch("crm.finance.api.frappe.db.exists", return_value=True),
			patch("crm.finance.api.frappe.db.has_column", return_value=True),
			patch("crm.finance.api.frappe.get_list", return_value=[]),
			patch("crm.finance.api.erpnext_adapter.get_list", side_effect=erp_list) as get_list,
		):
			context = get_quotation_finance_context("SAL-QTN-0001", "Careverse HQ")

		self.assertEqual([row["name"] for row in context["sales_orders"]], [order["name"]])
		order_queries = [call for call in get_list.call_args_list if call.args[0] == "Sales Order"]
		self.assertEqual(len(order_queries), 2)
		self.assertIn(["prevdoc_docname", "=", "SAL-QTN-0001"], next(
			call for call in get_list.call_args_list if call.args[0] == "Sales Order Item"
		).kwargs["filters"])
		for call in order_queries:
			self.assertIn(["company", "=", "Careverse HQ"], call.kwargs["filters"])

	def test_non_finance_user_cannot_read_quotation_context(self):
		with (
			patch("crm.finance.api._has_ar_access", return_value=False),
			patch("crm.finance.api._resolve_company") as resolve_company,
		):
			with self.assertRaises(frappe.PermissionError):
				get_quotation_finance_context("SAL-QTN-0001", "Careverse HQ")

		resolve_company.assert_not_called()
