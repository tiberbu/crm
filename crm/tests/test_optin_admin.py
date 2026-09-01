from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.optin_admin import (
	duplicate_negotiated_price_list,
	import_facilities_csv,
	list_facilities,
	list_networks,
)


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
						"price_list_override": "",
						"status": "Active",
						"contact_name": "Jane Doe",
						"contact_email": "jane@example.com",
						"contact_phone": "0712000001",
					}
				],
			}
		)


class TestOptInPriceListTools(UnitTestCase):
	def test_import_passes_a_facility_price_list_override(self):
		csv_data = (
			"mfl_code,facility_name,price_list_override,keph_level,contact_name,contact_email,contact_phone\n"
			"1001,First Clinic,Negotiated Year 2,Level 3,Jane Doe,jane@example.com,0712000001\n"
		)

		with (
			patch("crm.api.optin_admin._assert_network_access"),
			patch("crm.api.optin_admin.frappe.db.exists", return_value=True),
			patch("crm.api.optin_admin.save_facility") as save_facility,
		):
			result = import_facilities_csv(csv_data, "network-a", dry_run=0)

		self.assertEqual(result["valid_count"], 1)
		self.assertEqual(
			save_facility.call_args.args[0]["memberships"][0]["price_list_override"],
			"Negotiated Year 2",
		)

	def test_duplicate_price_list_copies_all_selling_item_prices(self):
		source = frappe._dict({"name": "Negotiated Year 1", "currency": "KES"})
		new_price_list = frappe._dict(
			{
				"name": "Negotiated Facility A",
				"currency": "KES",
				"insert": lambda **kwargs: None,
			}
		)

		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch("crm.api.optin_admin._get_negotiated_price_list", return_value=source),
			patch("crm.api.optin_admin.frappe.db.exists", side_effect=[False, "ITEM-PRICE-1"]),
			patch("crm.api.optin_admin.frappe.get_meta") as get_meta,
			patch("crm.api.optin_admin.frappe.get_list") as get_list,
			patch("crm.api.optin_admin.frappe.get_doc", return_value=new_price_list) as get_doc,
		):
			get_meta.return_value.get_fieldnames.return_value = {
				"item_code",
				"uom",
				"currency",
				"price_list_rate",
			}
			get_list.return_value = [
				frappe._dict(
					{
						"name": "ITEM-PRICE-1",
						"item_code": "CV-HIMS-KEPH-3",
						"uom": "Nos",
						"currency": "KES",
						"price_list_rate": 100,
					}
				)
			]

			result = duplicate_negotiated_price_list("Negotiated Year 1", "Negotiated Facility A")

		self.assertEqual(result["copied"], 1)
		self.assertEqual(get_doc.call_count, 2)


class TestOptInNetworkList(UnitTestCase):
	def test_network_list_adds_the_visible_contact_count(self):
		network = frappe._dict(
			{
				"name": "network-a",
				"slug": "network-a",
				"display_name": "Network A",
				"enabled": 1,
			}
		)
		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch(
				"crm.api.optin_admin.frappe.get_list",
				side_effect=[
					[network],
					[
						frappe._dict({"network": "network-a", "status": "Opted In"}),
						frappe._dict({"network": "network-a"}),
					],
					[frappe._dict({"name": "network-a"})],
				],
			),
		):
			result = list_networks()

		self.assertEqual(result["total"], 1)
		self.assertEqual(result["rows"][0]["contact_count"], 2)
		self.assertEqual(result["rows"][0]["opted_in_count"], 1)
		self.assertTrue(result["rows"][0]["opted_in"])


class TestOptInFacilityList(UnitTestCase):
	def test_network_contacts_can_be_filtered_categorically_by_opt_in_state(self):
		memberships = [
			frappe._dict(
				{
					"name": "MEM-OPTED",
					"parent": "FAC-0001",
					"network": "network-a",
					"status": "Opted In",
					"contact_name": "Jane Doe",
					"contact_email": "jane@example.com",
					"contact_phone": "+254700000001",
					"invite_email_queue": None,
					"invite_sent_at": None,
				}
			),
			frappe._dict(
				{
					"name": "MEM-ACTIVE",
					"parent": "FAC-0002",
					"network": "network-a",
					"status": "Active",
					"contact_name": "John Doe",
					"contact_email": "john@example.com",
					"contact_phone": "+254700000002",
					"invite_email_queue": None,
					"invite_sent_at": None,
				}
			),
		]
		facility = frappe._dict(
			{
				"name": "FAC-0001",
				"mfl_code": "1001",
				"facility_name": "First Clinic",
				"organization": "Health Group",
				"keph_level": "Level 3",
			}
		)

		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch(
				"crm.api.optin_admin.frappe.get_list",
				side_effect=[
					memberships,
					[frappe._dict({"name": facility.name})],
					[facility],
				],
			) as get_list,
		):
			result = list_facilities(network="network-a", opted_in="1")

		self.assertEqual(result["total"], 1)
		self.assertEqual(result["rows"][0]["name"], "FAC-0001")
		self.assertEqual(get_list.call_args_list[0].kwargs["filters"]["network"], ["in", ["network-a"]])

	def test_network_contacts_can_be_filtered_by_facility_and_contact_details(self):
		membership = frappe._dict(
			{
				"name": "MEM-0001",
				"parent": "FAC-0001",
				"network": "network-a",
				"price_list_override": "Negotiated Year 2",
				"status": "Active",
				"contact_name": "Jane Doe",
				"contact_email": "jane@example.com",
				"contact_phone": "0712000001",
				"invite_email_queue": None,
				"invite_sent_at": None,
			}
		)
		facility = frappe._dict(
			{
				"name": "FAC-0001",
				"mfl_code": "1001",
				"facility_name": "First Clinic",
				"organization": "Health Group",
				"keph_level": "Level 3",
			}
		)

		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch(
				"crm.api.optin_admin.frappe.get_list",
				side_effect=[
					[membership],
					[frappe._dict({"name": facility.name})],
					[facility],
				],
			) as get_list,
		):
			result = list_facilities(
				network="network-a",
				status="Active",
				facility="First",
				facility_level="Level 3",
				organization="Health",
				contact="jane",
			)

		membership_call = get_list.call_args_list[0].kwargs
		self.assertEqual(membership_call["filters"]["network"], ["in", ["network-a"]])
		self.assertEqual(membership_call["filters"]["status"], "Active")
		self.assertEqual(membership_call["or_filters"][1], ["contact_email", "like", "%jane%"])

		facility_call = get_list.call_args_list[1].kwargs
		self.assertEqual(facility_call["filters"]["keph_level"], "Level 3")
		self.assertEqual(facility_call["filters"]["organization"], ["like", "%Health%"])
		self.assertEqual(facility_call["or_filters"][0], ["facility_name", "like", "%First%"])
		self.assertEqual(result["total"], 1)
		self.assertEqual(result["rows"][0]["memberships"][0]["invite_status"], "Not Sent")
		self.assertEqual(
			result["rows"][0]["memberships"][0]["price_list_override"],
			"Negotiated Year 2",
		)
