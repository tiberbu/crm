from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.optin_admin import (
	create_sellable_item,
	duplicate_negotiated_price_list,
	get_facility_sample_quote,
	import_facilities_csv,
	list_facilities,
	list_negotiated_price_lists,
	list_networks,
	list_price_list_facilities,
	save_item_prices,
	update_item_price,
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
	def test_price_list_metadata_counts_effective_facility_assignments(self):
		price_list = frappe._dict(
			{
				"name": "Negotiated Year 1",
				"currency": "KES",
				"creation": "2026-09-01 10:00:00",
				"modified": "2026-09-01 11:00:00",
				"owner": "manager@example.com",
				"modified_by": "manager@example.com",
			}
		)
		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch(
				"crm.api.optin_admin.frappe.get_list",
				side_effect=[
					[price_list],
					[
						frappe._dict({"parent": "FAC-1", "network": "NET-1", "price_list_override": ""}),
						frappe._dict(
							{
								"parent": "FAC-1",
								"network": "NET-2",
								"price_list_override": "Negotiated Year 1",
							}
						),
					],
					[
						frappe._dict(
							{"name": "NET-1", "slug": "network-a", "price_list_override": "Negotiated Year 1"}
						)
					],
				],
			),
			patch("crm.api.optin_admin.frappe.db.has_column", return_value=True),
			patch("crm.api.optin_admin.frappe.db.get_single_value", return_value="Negotiated Year 1"),
		):
			result = list_negotiated_price_lists()

		self.assertEqual(result[0]["facility_count"], 1)
		self.assertEqual(result[0]["network_count"], 2)
		self.assertEqual(result[0]["owner"], "manager@example.com")

	def test_price_list_facilities_returns_network_context_for_sample_quotes(self):
		price_list = frappe._dict({"name": "Negotiated Year 1", "currency": "KES"})
		facility = frappe._dict(
			{
				"name": "FAC-1",
				"facility_name": "First Clinic",
				"organization": "Health Group",
				"mfl_code": "1001",
				"keph_level": "Level 3",
			}
		)
		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch("crm.api.optin_admin._get_negotiated_price_list", return_value=price_list),
			patch(
				"crm.api.optin_admin._price_list_assignments",
				return_value={"Negotiated Year 1": {"facility_networks": {("FAC-1", "network-a")}}},
			),
			patch("crm.api.optin_admin.frappe.get_list", return_value=[facility]),
		):
			result = list_price_list_facilities("Negotiated Year 1")

		self.assertEqual(result[0]["facility_name"], "First Clinic")
		self.assertEqual(result[0]["network"], "network-a")

	def test_price_list_facilities_can_return_a_bounded_page(self):
		price_list = frappe._dict({"name": "Negotiated Year 1", "currency": "KES"})
		facilities = [
			frappe._dict(
				{
					"name": "FAC-%s" % index,
					"facility_name": "Clinic %s" % index,
					"organization": "Health Group",
					"mfl_code": "10%s" % index,
					"keph_level": "Level 3",
				}
			)
			for index in range(1, 4)
		]
		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch("crm.api.optin_admin._get_negotiated_price_list", return_value=price_list),
			patch(
				"crm.api.optin_admin._price_list_assignments",
				return_value={
					"Negotiated Year 1": {
						"facility_networks": {(facility.name, "network-a") for facility in facilities}
					}
				},
			),
			patch("crm.api.optin_admin.frappe.get_list", return_value=facilities),
		):
			result = list_price_list_facilities("Negotiated Year 1", page=2, page_length=1)

		self.assertEqual(result["total"], 3)
		self.assertEqual(result["page"], 2)
		self.assertEqual(result["page_length"], 1)
		self.assertTrue(result["has_more"])
		self.assertEqual(result["rows"][0]["facility_name"], "Clinic 2")

	def test_facility_sample_quote_uses_selected_price_list_and_exclusive_vat(self):
		facility = frappe._dict(
			{
				"facility_name": "First Clinic",
				"organization": "Health Group",
				"mfl_code": "1001",
				"keph_level": "Level 3",
				"memberships": [frappe._dict({"network": "network-a", "price_list_override": ""})],
			}
		)
		vat = frappe._dict(
			{"net_total": 100, "vat_amount": 16, "grand_total": 116, "vat_rate": 16, "vat_label": "VAT (16%)"}
		)
		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch("crm.api.optin_admin.frappe.get_doc", return_value=facility),
			patch(
				"crm.api.optin_admin.frappe.get_list",
				return_value=[frappe._dict({"display_name": "Network A", "price_list_override": ""})],
			),
			patch("crm.api.optin_admin.frappe.db.get_single_value", return_value="Negotiated Year 1"),
			patch("crm.api.optin_admin.frappe.db.exists", return_value=True),
			patch("crm.api.optin_admin.frappe.db.get_value", return_value="CareverseHIMS - Level 3"),
			patch("crm.api.quotes._get_item_price", return_value=100),
			patch("crm.utils.quotation_tax.calculate_vat_totals", return_value=vat),
		):
			result = get_facility_sample_quote("FAC-1", "network-a", "Negotiated Year 2")

		self.assertEqual(result["price_list"], "Negotiated Year 2")
		self.assertEqual(result["monthly_net"], 100)
		self.assertEqual(result["monthly_gross"], 116)

	def test_catalogue_item_creation_is_manager_only_and_uses_service_defaults(self):
		item = frappe._dict(
			{
				"name": "CV-HIMS-KEPH-6",
				"item_name": "CareverseHIMS -- Level 6",
				"stock_uom": "Nos",
				"insert": lambda **kwargs: None,
			}
		)
		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch("crm.api.optin_admin.frappe.db.exists", return_value=False),
			patch("crm.api.optin_admin.frappe.get_doc", return_value=item) as get_doc,
		):
			result = create_sellable_item("CV-HIMS-KEPH-6", "CareverseHIMS -- Level 6")

		self.assertEqual(result["value"], "CV-HIMS-KEPH-6")
		payload = get_doc.call_args.args[0]
		self.assertEqual(payload["item_group"], "Services")
		self.assertEqual(payload["is_sales_item"], 1)
		self.assertEqual(payload["is_stock_item"], 0)

	def test_bulk_item_prices_upsert_once_per_unique_item(self):
		price_list = frappe._dict({"name": "Negotiated Year 1", "currency": "KES"})
		new_price = frappe._dict({"save": lambda **kwargs: None})
		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch("crm.api.optin_admin._get_negotiated_price_list", return_value=price_list),
			patch(
				"crm.api.optin_admin.frappe.db.exists",
				side_effect=lambda doctype, *args, **kwargs: doctype == "Item",
			) as exists,
			patch("crm.api.optin_admin.frappe.new_doc", return_value=new_price),
			patch("crm.api.optin_admin.frappe.db.get_value", return_value="Nos"),
		):
			result = save_item_prices(
				"Negotiated Year 1",
				[
					{"item_code": "ITEM-1", "rate": 100},
					{"item_code": "ITEM-1", "rate": 200},
				],
			)

		self.assertEqual(result["saved"], 1)
		self.assertEqual(new_price.price_list_rate, 100)
		self.assertEqual(exists.call_count, 2)

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
			get_meta.return_value = SimpleNamespace(
				fields=[
					frappe._dict({"fieldname": field})
					for field in ("item_code", "uom", "currency", "price_list_rate")
				]
			)
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

	def test_item_price_can_be_removed_and_audited(self):
		source = frappe._dict({"name": "Negotiated Year 1", "currency": "KES"})
		item_price = frappe._dict(
			{
				"name": "ITEM-PRICE-1",
				"price_list": source.name,
				"selling": 1,
				"item_code": "CV-HIMS-KEPH-3",
			}
		)

		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch("crm.api.optin_admin._get_negotiated_price_list", return_value=source),
			patch("crm.api.optin_admin.frappe.get_doc", return_value=item_price),
			patch("crm.api.optin_admin.frappe.delete_doc") as delete_doc,
			patch("crm.api.optin_admin._log_price_list_event") as log_event,
			patch("crm.api.optin_admin.frappe.db.commit") as commit,
		):
			result = update_item_price(source.name, item_price.name, "")

		self.assertEqual(result["action"], "removed")
		delete_doc.assert_called_once_with("Item Price", item_price.name, ignore_permissions=True)
		log_event.assert_called_once_with(
			source.name,
			"Removed item price CV-HIMS-KEPH-3 from Negotiated Year 1.",
		)
		commit.assert_called_once_with()

	def test_item_price_can_be_moved_and_audited_on_both_lists(self):
		source = frappe._dict({"name": "Negotiated Year 1", "currency": "KES"})
		target = frappe._dict({"name": "Negotiated Facility A", "currency": "KES"})
		item_price = frappe._dict(
			{
				"name": "ITEM-PRICE-1",
				"price_list": source.name,
				"selling": 1,
				"item_code": "CV-HIMS-KEPH-3",
				"price_list_rate": 100,
				"currency": "KES",
				"save": lambda **kwargs: None,
			}
		)

		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch(
				"crm.api.optin_admin._get_negotiated_price_list",
				side_effect=[source, target],
			),
			patch("crm.api.optin_admin.frappe.get_doc", return_value=item_price),
			patch("crm.api.optin_admin.frappe.db.exists", return_value=False),
			patch("crm.api.optin_admin._log_price_list_event") as log_event,
		):
			result = update_item_price(source.name, item_price.name, target.name, rate=125)

		self.assertEqual(result["action"], "moved")
		self.assertEqual(item_price.price_list, target.name)
		self.assertEqual(item_price.price_list_rate, 125)
		self.assertEqual(log_event.call_count, 2)
		self.assertEqual(log_event.call_args_list[0].args[0], source.name)
		self.assertEqual(log_event.call_args_list[1].args[0], target.name)

	def test_item_price_cannot_move_when_it_belongs_to_another_list(self):
		source = frappe._dict({"name": "Negotiated Year 1", "currency": "KES"})
		item_price = frappe._dict(
			{
				"name": "ITEM-PRICE-1",
				"price_list": "Negotiated Year 2",
				"selling": 1,
				"item_code": "CV-HIMS-KEPH-3",
			}
		)

		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch("crm.api.optin_admin._get_negotiated_price_list", return_value=source),
			patch("crm.api.optin_admin.frappe.get_doc", return_value=item_price),
		):
			with self.assertRaises(frappe.ValidationError):
				update_item_price(source.name, item_price.name, "")

	def test_item_price_move_rejects_an_existing_item_in_target_list(self):
		source = frappe._dict({"name": "Negotiated Year 1", "currency": "KES"})
		target = frappe._dict({"name": "Negotiated Facility A", "currency": "KES"})
		item_price = frappe._dict(
			{
				"name": "ITEM-PRICE-1",
				"price_list": source.name,
				"selling": 1,
				"item_code": "CV-HIMS-KEPH-3",
			}
		)

		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch(
				"crm.api.optin_admin._get_negotiated_price_list",
				side_effect=[source, target],
			),
			patch("crm.api.optin_admin.frappe.get_doc", return_value=item_price),
			patch("crm.api.optin_admin.frappe.db.exists", return_value="ITEM-PRICE-2"),
			patch("crm.api.optin_admin._log_price_list_event") as log_event,
		):
			with self.assertRaises(frappe.ValidationError):
				update_item_price(source.name, item_price.name, target.name)

		self.assertEqual(item_price.price_list, source.name)
		log_event.assert_not_called()


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
