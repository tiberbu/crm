from unittest.mock import Mock

from frappe.tests import UnitTestCase

from crm.tests import patch_test_record_dependency_resolution


class TestCRMTestBootstrap(UnitTestCase):
	def test_site_fixture_dependencies_are_skipped(self):
		from frappe.tests.utils import generators

		original_resolver = generators.get_missing_records_doctypes
		was_patched = getattr(generators, "_crm_site_fixture_dependency_patch", False)
		delegated = Mock(return_value=["delegated"])

		try:
			generators.get_missing_records_doctypes = delegated
			if was_patched:
				del generators._crm_site_fixture_dependency_patch

			patch_test_record_dependency_resolution()

			for doctype in ("User", "Price List", "Item", "Tax Category", "Company", "Quotation"):
				self.assertEqual(generators.get_missing_records_doctypes(doctype), [])

			self.assertEqual(generators.get_missing_records_doctypes("CRM Lead", set()), ["delegated"])
			delegated.assert_called_once()
		finally:
			generators.get_missing_records_doctypes = original_resolver
			if was_patched:
				generators._crm_site_fixture_dependency_patch = True
			else:
				del generators._crm_site_fixture_dependency_patch
