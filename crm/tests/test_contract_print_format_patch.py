from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase


class TestContractPrintFormatPatch(UnitTestCase):
	def test_contract_standard_template_delegates_body_to_terms_document(self):
		template = Path(
			frappe.get_app_path("crm", "setup", "templates", "crm_contract_standard.html")
		).read_text(encoding="utf-8")

		self.assertIn("{{ render_current_terms_for_contract(doc) }}", template)
		self.assertNotIn("CareverseHIMS Subscription Agreement", template)
		self.assertNotIn("Rates in the contract schedules", template)
		self.assertNotIn("price-history", template)

	def test_patch_delegates_to_idempotent_print_format_bootstrap(self):
		with patch(
			"crm.patches.v1_0.configure_contract_print_format_v1.ensure_contract_print_format"
		) as ensure:
			from crm.patches.v1_0.configure_contract_print_format_v1 import execute

			execute()

		ensure.assert_called_once_with()
