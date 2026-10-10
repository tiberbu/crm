import frappe
from frappe.tests import UnitTestCase
from unittest.mock import patch

from crm.finance.access import has_access
from crm.finance.api import (
	_action_item,
	_handoff_schedule,
	_request_filters,
	_request_page,
	_require_document_permission,
	get_ar_invoices,
	get_finance_kpis,
	global_search,
)
from crm.www.access_restricted import RESOURCE_COPY


class TestFinanceCockpitAccess(UnitTestCase):
	def test_accounts_user_and_manager_are_allowed(self):
		self.assertTrue(has_access(user="accounts@example.com", roles={"Accounts User"}))
		self.assertTrue(has_access(user="manager@example.com", roles={"Accounts Manager"}))

	def test_administrator_is_recovery_account(self):
		self.assertTrue(has_access(user="Administrator", roles=set()))

	def test_non_accounting_roles_are_denied(self):
		for role in ("System Manager", "Finance Manager", "AR Accountant", "Sales Manager"):
			self.assertFalse(has_access(user="user@example.com", roles={role}))

	def test_accounts_roles_are_registered_as_whitelisted_finance_endpoints(self):
		# Public Finance functions are wrapped after their module-level decorator so
		# the shared access check runs first. The guarded callable must itself remain
		# in Frappe's whitelist registry.
		self.assertIn(get_ar_invoices, frappe.whitelisted)
		self.assertIn(get_finance_kpis, frappe.whitelisted)

	def test_finance_access_restriction_explains_required_roles(self):
		self.assertIn("Accounts User", RESOURCE_COPY["finance"]["required_roles"])
		self.assertIn("Accounts Manager", RESOURCE_COPY["finance"]["required_roles"])

	def test_handoff_schedule_selects_native_year_one_quarter_one_row(self):
		submission = {
			"billing_schedule_json": (
				'[{"year_number": 2, "quarter_number": 1}, '
				'{"year_number": 1, "quarter_number": 1, "invoice_date": "2026-10-08"}]'
			)
		}
		with patch("crm.finance.api.frappe.db.has_column", return_value=True):
			self.assertEqual(_handoff_schedule(submission)["invoice_date"], "2026-10-08")

	def test_handoff_schedule_fails_closed_for_invalid_json(self):
		with patch("crm.finance.api.frappe.db.has_column", return_value=True):
			self.assertEqual(_handoff_schedule({"billing_schedule_json": "not-json"}), {})

	def test_action_item_handles_structured_row_values_without_lower_attribute_error(self):
		item = _action_item(
			"overdue_invoice",
			{"name": "Sales Invoice"},
			{"name": "SINV-0001"},
			"Customer",
			{"name": "Customer"},
			100,
			"KES",
			3,
			"warning",
			"record_payment",
			"Record Payment",
		)

		self.assertEqual(item["doctype"], "")
		self.assertEqual(item["docname"], "")
		self.assertEqual(item["record_url"], "")
		self.assertNotIn("erpnext_url", item)

	def test_request_filters_accepts_map_and_rejects_structured_conditions(self):
		self.assertEqual(_request_filters({"status": "Open"}), [["status", "=", "Open"]])
		with self.assertRaises(frappe.ValidationError) as context:
			_request_filters({"status": {"label": "Open"}})
		self.assertIn("Filter values", str(context.exception))

	def test_request_page_rejects_dictionary_instead_of_leaking_type_error(self):
		with self.assertRaises(frappe.ValidationError) as context:
			_request_page({"page": 1}, "Page", 0, 100)
		self.assertIn("Page must be a whole number", str(context.exception))

	def test_global_search_rejects_dictionary_query_with_readable_validation(self):
		with patch("crm.finance.api.require_access"):
			with self.assertRaises(frappe.ValidationError) as context:
				global_search({"query": "invoice"})
		self.assertIn("Search text must be plain text", str(context.exception))

	def test_document_actions_delegate_to_native_user_permission_checks(self):
		with patch("crm.finance.api.frappe.has_permission") as has_permission:
			self.assertEqual(
				_require_document_permission("Sales Invoice", "SINV-0001", "read"),
				"SINV-0001",
			)
		has_permission.assert_called_once_with(
			"Sales Invoice", doc="SINV-0001", ptype="read", throw=True
		)
