from unittest.mock import patch

from frappe.tests import UnitTestCase


class TestFinancePrintFormatPatch(UnitTestCase):
	def test_patch_delegates_to_idempotent_print_format_bootstrap(self):
		with patch(
			"crm.patches.v1_0.configure_finance_print_formats_v1.ensure_finance_print_formats"
		) as ensure:
			from crm.patches.v1_0.configure_finance_print_formats_v1 import execute

			execute()

		ensure.assert_called_once_with()
