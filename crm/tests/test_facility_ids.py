"""Facility IDs are shown wherever a facility appears, including records that carry only an MFL code."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import facility_ids as api
from crm.api.optin_admin import import_facilities_csv, lookup_hfr
from crm.utils.facility_ids import facility_ids_by_mfl

MFL_LINKED = "FIDTEST01"
MFL_UNLINKED = "FIDTEST02"
FID = "FID-00-FIDTEST-1"


class TestFacilityIds(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("facility_ids_test")
		self.addCleanup(frappe.db.rollback, save_point="facility_ids_test")
		self.addCleanup(frappe.set_user, "Administrator")
		for mfl, fid in ((MFL_LINKED, FID), (MFL_UNLINKED, "")):
			frappe.get_doc(
				{
					"doctype": "CRM Pre-Qualified Facility",
					"mfl_code": mfl,
					"facility_name": "Facility ID Test %s" % mfl,
					"keph_level": "Level 3",
					"hfr_facility_id": fid,
				}
			).insert(ignore_permissions=True)

	def test_maps_known_mfl_codes_and_leaves_out_the_rest(self):
		self.assertEqual(
			facility_ids_by_mfl([MFL_LINKED, " %s " % MFL_LINKED, MFL_UNLINKED, "UNKNOWN", ""]),
			{MFL_LINKED: FID},
		)
		self.assertEqual(facility_ids_by_mfl([]), {})

	def test_staff_lookup_is_refused_to_guests_and_website_users(self):
		self.assertEqual(api.get_facility_ids([MFL_LINKED]), {MFL_LINKED: FID})
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			api.get_facility_ids([MFL_LINKED])
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			api.get_facility_ids(["X"] * (api.MAX_CODES + 1))

	def test_csv_preview_shows_the_facility_id_on_record_or_in_the_file(self):
		csv_data = (
			"mfl_code,hfr_facility_id,facility_name,keph_level,contact_name,contact_email,contact_phone\n"
			"%s,,Linked,Level 3,A Person,a@example.test,0700000001\n"
			"%s,FID-00-FIDTEST-2,Unlinked,Level 3,B Person,b@example.test,0700000002\n"
		) % (MFL_LINKED, MFL_UNLINKED)
		with patch("crm.api.optin_admin._assert_network_access"):
			rows = import_facilities_csv(csv_data, "network-a", dry_run=1)["rows"]
		self.assertEqual([row["hfr_facility_id"] for row in rows], [FID, "FID-00-FIDTEST-2"])

	def test_hfr_lookup_returns_the_facility_id(self):
		hit = {"mfl_code": MFL_UNLINKED, "fid": "FID-00-FIDTEST-2", "name": "Unlinked", "level": "3"}
		with patch("crm.api.hfr.search_facility", return_value=[hit]):
			result = lookup_hfr(MFL_UNLINKED)
		self.assertEqual(result["hfr_facility_id"], "FID-00-FIDTEST-2")
		self.assertEqual(result["keph_level"], "Level 3")
