import frappe
from frappe.tests import UnitTestCase
from unittest.mock import patch

from crm.finance.access import has_access
from crm.finance.api import _handoff_schedule, get_ar_invoices, get_finance_kpis
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
