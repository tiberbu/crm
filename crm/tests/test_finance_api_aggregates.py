from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.finance.api import (
	_get_ar_overdue,
	_get_invoiced_mtd,
	_get_pending_rebates,
	_get_unpaid_commissions,
	_sum_query_value,
	get_finance_kpis,
)


class TestFinanceAPIAggregates(UnitTestCase):
	def test_v16_query_builder_sum_checks_permissions_and_preserves_filters(self):
		filters = [["company", "=", "Careverse HQ"], ["docstatus", "=", 1]]
		query = Mock()
		query.run.return_value = [{"total": 125.5}]

		with patch.object(frappe.qb, "get_query", return_value=query, create=True) as get_query:
			self.assertEqual(_sum_query_value("Sales Invoice", filters, "grand_total"), 125.5)

		get_query.assert_called_once_with(
			"Sales Invoice",
			fields=[{"SUM": "grand_total", "as": "total"}],
			filters=filters,
			ignore_permissions=False,
		)
		query.run.assert_called_once_with(as_dict=True)

	def test_v16_empty_sum_result_is_zero(self):
		query = Mock()
		query.run.return_value = [{"total": None}]

		with patch.object(frappe.qb, "get_query", return_value=query, create=True):
			self.assertEqual(_sum_query_value("Sales Invoice", [], "grand_total"), 0)

	def test_empty_invoice_filter_runs_through_the_installed_frappe_query_path(self):
		self.assertEqual(
			_sum_query_value("Sales Invoice", [["name", "=", "__no_such_invoice__"]], "grand_total"),
			0,
		)

	def test_v15_fallback_uses_permission_checked_fields_and_sums_rows(self):
		filters = [["company", "=", "Careverse HQ"], ["status", "=", "Pending"]]
		with (
			patch.object(frappe.qb, "get_query", None, create=True),
			patch("crm.finance.api.frappe.get_list", return_value=[{"rebate_amount": 12.5}, {"rebate_amount": 7}]) as get_list,
		):
			self.assertEqual(_sum_query_value("CRM Partner Rebate Voucher", filters, "rebate_amount"), 19.5)

		get_list.assert_called_once_with(
			"CRM Partner Rebate Voucher",
			filters=filters,
			fields=["rebate_amount"],
		)

	def test_v15_fallback_with_no_rows_returns_zero(self):
		with (
			patch.object(frappe.qb, "get_query", None, create=True),
			patch("crm.finance.api.frappe.get_list", return_value=[]),
		):
			self.assertEqual(_sum_query_value("Sales Invoice", [], "grand_total"), 0)

	def test_kpi_aggregates_preserve_company_status_and_date_filters(self):
		date_filter = ("2026-10-01", "2026-10-12")
		with (
			patch("crm.finance.api.today", return_value="2026-10-12"),
			patch("crm.finance.api._sum_query_value", return_value=0) as sum_value,
		):
			_get_ar_overdue("Careverse HQ", "KES")
			_get_invoiced_mtd("Careverse HQ", "KES", date_filter)

		self.assertEqual(
			sum_value.call_args_list[0].args,
			(
				"Sales Invoice",
				[
					["company", "=", "Careverse HQ"],
					["docstatus", "=", 1],
					["outstanding_amount", ">", 0],
					["due_date", "<", "2026-10-12"],
				],
				"outstanding_amount",
			),
		)
		self.assertEqual(
			sum_value.call_args_list[1].args,
			(
				"Sales Invoice",
				[
					["company", "=", "Careverse HQ"],
					["docstatus", "=", 1],
					["posting_date", ">=", "2026-10-01"],
					["posting_date", "<=", "2026-10-12"],
				],
				"grand_total",
			),
		)

	def test_partner_rm_and_sales_manager_role_filters_are_preserved(self):
		with (
			patch("crm.finance.api.frappe.db.exists", return_value=True),
			patch("crm.finance.api._company_currency", return_value="KES"),
			patch("crm.finance.api.frappe.local.session", frappe._dict(user="finance-user@example.com")),
			patch("crm.finance.api.frappe.get_list", side_effect=[["PARTNER-1"], ["DEAL-1"]]) as get_list,
			patch("crm.finance.api._sum_query_value", return_value=0) as sum_value,
		):
			_get_pending_rebates("Careverse HQ", ["Partner RM"])
			_get_unpaid_commissions("Careverse HQ", ["Sales Manager"])

		self.assertEqual(
			get_list.call_args_list[0].kwargs,
			{"filters": {"partner_rm": "finance-user@example.com"}, "pluck": "name"},
		)
		self.assertEqual(
			get_list.call_args_list[1].kwargs,
			{"filters": {"deal_owner": "finance-user@example.com"}, "pluck": "name"},
		)
		self.assertEqual(
			sum_value.call_args_list[0].args,
			("CRM Partner Rebate Voucher", [["status", "=", "Pending"], ["partner", "in", ["PARTNER-1"]]], "rebate_amount"),
		)
		self.assertEqual(
			sum_value.call_args_list[1].args,
			(
				"CRM Sales Commission",
				[["status", "in", ["Reported", "Confirmed"]], ["deal", "in", ["DEAL-1"]]],
				"commission_amount",
			),
		)

	def test_get_finance_kpis_keeps_response_shape_and_currency(self):
		cache = Mock()
		cache.get_value.return_value = None
		with (
			patch("crm.finance.api.require_access"),
			patch("crm.finance.api._resolve_company", return_value="Careverse HQ"),
			patch("crm.finance.api._company_currency", return_value="KES"),
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User", "Accounts Manager"]),
			patch("crm.finance.api.frappe.cache", return_value=cache),
			patch("crm.finance.api.frappe.db.exists", return_value=True),
			patch("crm.finance.api._sum_query_value", return_value=21.5),
		):
			result = get_finance_kpis(company="Careverse HQ", period="month", force=1)

		self.assertEqual(
			set(result),
			{
				"ar_outstanding",
				"ar_overdue",
				"invoiced_mtd",
				"collected_mtd",
				"ap_outstanding",
				"ap_overdue",
				"pending_rebates",
				"unpaid_commissions",
			},
		)
		for metric in result.values():
			self.assertEqual(metric["currency"], "KES")
			self.assertIsInstance(metric["value"], float)
			self.assertEqual(metric["delta_pct"], 0)
			self.assertEqual(metric["delta_direction"], "neutral")

	def test_kpi_server_failure_is_logged_and_returns_support_reference(self):
		with (
			patch("crm.finance.api._resolve_company", return_value="Careverse HQ"),
			patch(
				"crm.finance.api._get_finance_kpis_payload",
				side_effect=AttributeError("dict has no attribute lower"),
			),
			patch("crm.finance.api.frappe.log_error", return_value=frappe._dict(name="ERR-LOG-001")),
			patch("crm.finance.api.frappe.throw", side_effect=ValueError("Finance KPI failure")) as throw,
		):
			with self.assertRaisesRegex(ValueError, "Finance KPI failure"):
				get_finance_kpis(company="Careverse HQ", period="month", force=1)

		self.assertIn("ERR-LOG-001", throw.call_args.args[0])
