from unittest.mock import patch

from frappe.tests import UnitTestCase

from crm.api.optin_admin import import_facilities_csv


class TestOptInFacilityCsvImport(UnitTestCase):
	def test_preview_returns_authoritative_rows_and_defaults_organization(self):
		csv_data = (
			"\ufeffmfl_code,facility_name,organization,keph_level,contact_name,contact_email,contact_phone\n"
			"1001,First Clinic,Health Group,Level 3,Jane Doe,jane@example.com,0712000001\n"
			"1002,Second Clinic,,Level 4,John Doe,john@example.com,0712000002\n"
		)

		with (
			patch("crm.api.optin_admin._assert_network_access") as assert_access,
			patch("crm.api.optin_admin.save_facility") as save_facility,
		):
			result = import_facilities_csv(csv_data, "network-a", dry_run=1)

		assert_access.assert_called_once_with("network-a")
		save_facility.assert_not_called()
		self.assertEqual(result["valid_count"], 2)
		self.assertEqual(result["imported"], 2)
		self.assertEqual(result["error_count"], 0)
		self.assertEqual(result["rows"][0]["organization"], "Health Group")
		self.assertEqual(result["rows"][1]["organization"], "Second Clinic")
		self.assertIsNone(result["rows"][1]["error"])

	def test_preview_marks_invalid_and_duplicate_rows_without_breaking_count(self):
		csv_data = (
			"mfl_code,facility_name,keph_level,contact_name,contact_email,contact_phone\n"
			"1001,First Clinic,Level 3,Jane Doe,jane@example.com,0712000001,overflow\n"
			"1001,Duplicate Clinic,Level 3,John Doe,john@example.com,0712000002\n"
			"1003,Missing Phone Clinic,Level 3,Sam Doe,sam@example.com,\n"
		)

		with patch("crm.api.optin_admin._assert_network_access"):
			result = import_facilities_csv(csv_data, "network-a", dry_run=1)

		self.assertEqual(result["valid_count"], 1)
		self.assertEqual(result["error_count"], 2)
		self.assertIsNone(result["rows"][0]["error"])
		self.assertEqual(result["rows"][1]["error"], "duplicate mfl_code in this CSV")
		self.assertEqual(result["rows"][2]["error"], "contact_phone is required")

	def test_import_passes_the_organization_to_the_facility_save(self):
		csv_data = (
			"mfl_code,facility_name,organization,keph_level,contact_name,contact_email,contact_phone\n"
			"1001,First Clinic,Health Group,Level 3,Jane Doe,jane@example.com,0712000001\n"
		)

		with (
			patch("crm.api.optin_admin._assert_network_access"),
			patch("crm.api.optin_admin.save_facility") as save_facility,
		):
			result = import_facilities_csv(csv_data, "network-a", dry_run=0)

		self.assertEqual(result["imported"], 1)
		self.assertEqual(result["error_count"], 0)
		save_facility.assert_called_once_with(
			{
				"mfl_code": "1001",
				"facility_name": "First Clinic",
				"organization": "Health Group",
				"keph_level": "Level 3",
				"memberships": [
					{
						"network": "network-a",
						"status": "Active",
						"contact_name": "Jane Doe",
						"contact_email": "jane@example.com",
						"contact_phone": "0712000001",
					}
				],
			}
		)
