import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from crm.finance.access import ACCOUNTING_ROLES
from crm.patches.v1_0.restrict_finance_cockpit_to_accounts import execute, restrict_page_roles

PAGE = "finance-cockpit"


def _page_roles():
	return sorted(frappe.get_all("Has Role", filters={"parent": PAGE, "parenttype": "Page"}, pluck="role"))


class TestFinanceCockpitRolesPatch(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Page", PAGE):
			self.skipTest("Finance Cockpit page is not synced on this site")

	def tearDown(self):
		frappe.db.rollback()

	def _set_roles(self, roles):
		page = frappe.get_doc("Page", PAGE)
		page.set("roles", [])
		for role in roles:
			page.append("roles", {"role": role})
		page.flags.do_not_update_json = True
		page.save(ignore_permissions=True)

	def test_skips_save_when_roles_already_match(self):
		self._set_roles(sorted(ACCOUNTING_ROLES))

		self.assertFalse(restrict_page_roles())
		self.assertEqual(_page_roles(), sorted(ACCOUNTING_ROLES))

	def test_replaces_other_roles_with_accounts_roles(self):
		self._set_roles(["System Manager", "Accounts User"])

		self.assertTrue(restrict_page_roles())
		self.assertEqual(_page_roles(), sorted(ACCOUNTING_ROLES))

	def test_role_rows_are_child_documents(self):
		self._set_roles(["System Manager"])
		saved = []
		original_save = Document.save

		def spy(doc, *args, **kwargs):
			if doc.doctype == "Page":
				saved.append([type(row) for row in doc.roles])
				self.assertTrue(doc.flags.do_not_update_json)
			return original_save(doc, *args, **kwargs)

		Document.save = spy
		try:
			execute()
		finally:
			Document.save = original_save

		self.assertEqual(len(saved), 1)
		self.assertTrue(all(issubclass(cls, Document) for cls in saved[0]))
