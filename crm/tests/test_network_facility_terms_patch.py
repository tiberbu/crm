from pathlib import Path
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.optin import _safe_tc_pricing_rows, _safe_tc_text
from crm.patches.v1_0.seed_network_facility_terms_v1 import TITLE, execute


class TestNetworkFacilityTermsPatch(UnitTestCase):
	def test_creates_reviewable_template_without_changing_settings(self):
		terms_doc = Mock()
		template = Path(__file__).parents[1] / "setup" / "templates" / "chak_careverse_saas_agreement_v1.html"
		with (
			patch(
				"crm.patches.v1_0.seed_network_facility_terms_v1.frappe.db.exists",
				side_effect=[True, False],
			),
			patch(
				"crm.patches.v1_0.seed_network_facility_terms_v1.frappe.get_app_path",
				return_value=str(template),
			),
			patch(
				"crm.patches.v1_0.seed_network_facility_terms_v1.frappe.get_doc",
				return_value=terms_doc,
			) as get_doc,
			patch("crm.patches.v1_0.seed_network_facility_terms_v1.frappe.db.commit") as commit,
		):
			execute()

		payload = get_doc.call_args.args[0]
		self.assertEqual(payload["title"], TITLE)
		self.assertIn("{{ network.display_name }}", payload["terms"])
		self.assertIn("{{ pricing_table }}", payload["terms"])
		self.assertIn("Schedule B — Facility-specific pricing", payload["terms"])
		self.assertIn("Optional Services, Hardware and Software", payload["terms"])
		self.assertIn("{{ optional_services_table }}", payload["terms"])
		self.assertIn("Only optional services or hardware selected by the", payload["terms"])
		self.assertIn("All rates exclusive of VAT", payload["terms"])
		self.assertIn("{{ commitment_years_label }}", payload["terms"])
		self.assertNotIn("Endpoint Security/User/Year", payload["terms"])
		self.assertNotIn("Discounted Unit Price (KES) Excl. VAT", payload["terms"])
		self.assertNotIn("Total Price (KES) Excl. VAT", payload["terms"])
		self.assertNotIn("Per Facility Total Year 1 - Monthly", payload["terms"])
		self.assertNotIn("Endpoint workstations - DELL OPTIPLEX 7010 MT SYSTEM", payload["terms"])
		self.assertIn("1. CONTRACT INFORMATION", payload["terms"])
		self.assertIn("2. COMMERCIAL TERMS", payload["terms"])
		self.assertIn("Appendix A: Schedule A", payload["terms"])
		self.assertIn("Appendix C: Schedule C", payload["terms"])
		self.assertIn("Appendix 4: Schedule D", payload["terms"])
		self.assertIn("Appendix 5: Schedule E", payload["terms"])
		self.assertIn("Appendix 6: Schedule F", payload["terms"])
		self.assertIn("Appendix 7: Schedule G", payload["terms"])
		self.assertIn("G20. Order of Precedence", payload["terms"])
		self.assertIn("Data Migration and Exit Plan", payload["terms"])
		self.assertIn("{{ price_list_display }}", payload["terms"])
		self.assertIn("Contract schedule", payload["terms"])
		self.assertIn('class="source-section"', payload["terms"])
		self.assertNotIn("[Insert]", payload["terms"])
		terms_doc.insert.assert_called_once_with(ignore_permissions=True)
		commit.assert_called_once_with()

	def test_refreshes_existing_seeded_template_without_changing_settings(self):
		terms_doc = Mock(terms="old template")
		template = Path(__file__).parents[1] / "setup" / "templates" / "chak_careverse_saas_agreement_v1.html"
		with (
			patch(
				"crm.patches.v1_0.seed_network_facility_terms_v1.frappe.db.exists",
				side_effect=[True, True],
			),
			patch(
				"crm.patches.v1_0.seed_network_facility_terms_v1.frappe.get_app_path",
				return_value=str(template),
			),
			patch(
				"crm.patches.v1_0.seed_network_facility_terms_v1.frappe.get_doc",
				return_value=terms_doc,
			),
			patch("crm.patches.v1_0.seed_network_facility_terms_v1.frappe.db.commit") as commit,
		):
			execute()

		self.assertEqual(terms_doc.terms, template.read_text(encoding="utf-8"))
		terms_doc.save.assert_called_once_with(ignore_permissions=True)
		commit.assert_called_once_with()

	def test_template_scalar_values_are_escaped_before_jinja(self):
		self.assertEqual(
			_safe_tc_text('<img src=x onerror="alert(1)">'), "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
		)
		rows = _safe_tc_pricing_rows(
			[
				{
					"facility_name": "<script>alert(1)</script>",
					"mfl_code": "MFL-1",
					"keph_level": "Level 5",
					"item_code": "CV-HIMS-KEPH-5",
					"price_list": "Facility <Price List>",
					"monthly_kes": "1000.50",
					"annual_kes": "12006",
				}
			]
		)
		self.assertNotIn("<script>", rows[0]["facility_name"])
		self.assertEqual(rows[0]["monthly_kes"], 1000.5)
		self.assertEqual(rows[0]["annual_kes"], 12006)
