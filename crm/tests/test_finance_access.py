from frappe.tests import UnitTestCase

from crm.finance.access import has_access


class TestFinanceCockpitAccess(UnitTestCase):
	def test_accounts_user_and_manager_are_allowed(self):
		self.assertTrue(has_access(user="accounts@example.com", roles={"Accounts User"}))
		self.assertTrue(has_access(user="manager@example.com", roles={"Accounts Manager"}))

	def test_administrator_is_recovery_account(self):
		self.assertTrue(has_access(user="Administrator", roles=set()))

	def test_non_accounting_roles_are_denied(self):
		for role in ("System Manager", "Finance Manager", "AR Accountant", "Sales Manager"):
			self.assertFalse(has_access(user="user@example.com", roles={role}))
