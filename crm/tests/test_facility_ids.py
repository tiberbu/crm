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

	def test_hfr_lookup_rejects_a_hit_whose_mfl_does_not_match(self):
		hit = {"mfl_code": "SOME-OTHER-MFL", "fid": "FID-00-FIDTEST-9", "name": "Other", "level": "3"}
		with patch("crm.api.hfr.search_facility", return_value=[hit]):
			with self.assertRaises(frappe.ValidationError):
				lookup_hfr(MFL_UNLINKED)

	def test_csv_preview_keeps_a_looked_up_facility_id(self):
		# The register row and the CSV row both lack a FID, so the import must
		# run the HFR lookup and keep the FID it finds (metering needs it).
		csv_data = (
			"mfl_code,hfr_facility_id,facility_name,keph_level,contact_name,contact_email,contact_phone\n"
			"%s,,Unlinked,Level 3,B Person,b@example.test,0700000002\n"
		) % MFL_UNLINKED
		hit = {"mfl_code": MFL_UNLINKED, "fid": "FID-00-FIDTEST-3", "name": "Unlinked", "level": "3"}
		with (
			patch("crm.api.optin_admin._assert_network_access"),
			patch("crm.api.hfr.search_facility", return_value=[hit]),
		):
			rows = import_facilities_csv(csv_data, "network-a", dry_run=1)["rows"]
		self.assertEqual(rows[0]["hfr_facility_id"], "FID-00-FIDTEST-3")

	def test_csv_import_never_overwrites_a_stored_facility_id(self):
		# The register has a FID for MFL_LINKED and HFR would return a different
		# one: the stored value wins, so the lookup must not even run.
		csv_data = (
			"mfl_code,hfr_facility_id,facility_name,keph_level,contact_name,contact_email,contact_phone\n"
			"%s,,Linked,Level 3,A Person,a@example.test,0700000001\n"
		) % MFL_LINKED
		with (
			patch("crm.api.optin_admin._assert_network_access"),
			patch("crm.api.hfr.search_facility", return_value=[
				{"mfl_code": MFL_LINKED, "fid": "FID-00-OTHER", "name": "Linked", "level": "3"},
			]) as search,
		):
			rows = import_facilities_csv(csv_data, "network-a", dry_run=1)["rows"]
		self.assertEqual(rows[0]["hfr_facility_id"], FID)
		search.assert_not_called()

	def test_hfr_lookup_prefers_a_hit_carrying_a_fid(self):
		blank = {"mfl_code": MFL_UNLINKED, "fid": "", "name": "Unlinked", "level": "3"}
		hit = {"mfl_code": MFL_UNLINKED, "fid": "FID-00-FIDTEST-2", "name": "Unlinked", "level": "3"}
		with patch("crm.api.hfr.search_facility", return_value=[blank, hit]):
			result = lookup_hfr(MFL_UNLINKED)
		self.assertEqual(result["hfr_facility_id"], "FID-00-FIDTEST-2")

	def test_hfr_lookup_treats_conflicting_fids_as_not_found(self):
		one = {"mfl_code": MFL_UNLINKED, "fid": "FID-00-ONE", "name": "Unlinked", "level": "3"}
		two = {"mfl_code": MFL_UNLINKED, "fid": "FID-00-TWO", "name": "Unlinked", "level": "3"}
		with patch("crm.api.hfr.search_facility", return_value=[one, two]):
			with self.assertRaises(frappe.ValidationError):
				lookup_hfr(MFL_UNLINKED)

	def test_fid_lookup_budget_counts_only_lookup_time(self):
		# Slow saves and the gap between rows must not spend the lookup budget; a
		# slow registry stops the best-effort lookups once the budget is used up.
		clock = _FakeClock()
		csv_data = (
			"mfl_code,hfr_facility_id,facility_name,keph_level,contact_name,contact_email,contact_phone\n"
			"9001,,Budget One,Level 3,A Person,a@example.test,0700000011\n"
			"9002,,Budget Two,Level 3,B Person,b@example.test,0700000012\n"
			"9003,,Budget Three,Level 3,C Person,c@example.test,0700000013\n"
		)

		def slow_lookup(mfl_code):
			clock.now += 3  # simulated slow registry
			return {"mfl_code": mfl_code, "fid": "FID-00-%s" % mfl_code, "name": "Budget", "level": "3"}

		def slow_save(payload):
			clock.now += 10  # slow saves must not consume the lookup budget

		with (
			patch("crm.api.optin_admin.time", clock),
			patch("crm.api.optin_admin._CSV_FID_LOOKUP_BUDGET_SECONDS", 5.0),
			patch("crm.api.optin_admin._assert_network_access"),
			patch("crm.api.hfr.search_facility", side_effect=slow_lookup) as search,
			patch("crm.api.optin_admin.save_facility", side_effect=slow_save),
		):
			result = import_facilities_csv(csv_data, "network-a", dry_run=0)

		# 3s + 3s = 6s of lookup time >= the 5s budget, so the third row is not
		# looked up and stays "not linked yet" — despite 30s of saved wall time.
		self.assertEqual(search.call_count, 2)
		self.assertEqual(
			[row["hfr_facility_id"] for row in result["rows"]],
			["FID-00-9001", "FID-00-9002", ""],
		)


class _FakeClock:
	def __init__(self):
		self.now = 0.0

	def monotonic(self):
		return self.now
