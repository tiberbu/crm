"""Linking a Facility ID onto the register and the matching Lead/Deal rows."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from crm.api import optin_admin
from crm.api.optin_admin import lookup_owner_facilities, save_facility
from crm.utils.facility_ids import (
	facility_id_holders,
	fill_facility_rows,
	is_valid_facility_id,
	owner_facility_candidates,
	record_facility_id,
)

MFL_A = "FIDLINK01"
MFL_B = "FIDLINK02"
MFL_OTHER = "FIDLINK03"
FID_A = "FID-00-FIDLINK-A"
FID_B = "FID-00-FIDLINK-B"
OWNER_ID = "12345678"


class TestIsValidFacilityId(UnitTestCase):
	def test_valid_formats_pass(self):
		self.assertTrue(is_valid_facility_id("FID-00-12345-1"))
		self.assertTrue(is_valid_facility_id("FID-99-abc"))
		self.assertTrue(is_valid_facility_id("fid-00-abc-def"))
		self.assertTrue(is_valid_facility_id("  FID-00-abc  "))

	def test_invalid_formats_fail(self):
		self.assertFalse(is_valid_facility_id("FID-1"))
		self.assertFalse(is_valid_facility_id("MFL-12345"))
		self.assertFalse(is_valid_facility_id("FID-AB-1"))
		self.assertFalse(is_valid_facility_id(""))
		self.assertFalse(is_valid_facility_id(None))
		self.assertFalse(is_valid_facility_id("FID-00-12 34"))


class TestOwnerFacilityCandidates(UnitTestCase):
	def test_invalid_id_makes_no_hfr_call(self):
		with patch("crm.api.facility_onboarding._hfr_facilities_for_owner") as lookup:
			for bad in ("", "no!", "ab" * 40):
				self.assertEqual(owner_facility_candidates(bad)["status"], "invalid_id")
		lookup.assert_not_called()

	def test_only_rows_with_a_valid_fid_are_usable(self):
		rows = [
			{"hie_id": "HIE-1", "facility_name": "No FID"},
			{"registration_number": "REG-9", "facility_name": "Registration only"},
			{"facility_fid": "not-a-fid", "facility_name": "Bad FID"},
			{"facility_fid": FID_A, "facility_name": "Alpha", "kephl_level": "Level 1"},
		]
		with patch("crm.api.facility_onboarding._hfr_facilities_for_owner", return_value=rows):
			result = owner_facility_candidates(OWNER_ID)
		self.assertEqual(result["status"], "ok")
		self.assertEqual(result["candidates"], [{"hfr_facility_id": FID_A, "facility_name": "Alpha", "facility_level": "Level 1", "facility_type": ""}])

	def test_dedupes_by_casefolded_fid(self):
		rows = [
			{"facility_fid": FID_A, "facility_name": "Alpha"},
			{"facility_fid": FID_A.upper(), "facility_name": "Alpha again"},
		]
		with patch("crm.api.facility_onboarding._hfr_facilities_for_owner", return_value=rows):
			result = owner_facility_candidates(OWNER_ID)
		self.assertEqual(len(result["candidates"]), 1)

	def test_no_rows_is_no_facilities(self):
		with patch("crm.api.facility_onboarding._hfr_facilities_for_owner", return_value=[]):
			self.assertEqual(owner_facility_candidates(OWNER_ID)["status"], "no_facilities")

	def test_registry_failure_is_unavailable_and_clears_messages(self):
		with patch("crm.api.facility_onboarding._hfr_facilities_for_owner", side_effect=RuntimeError("registry down")):
			result = owner_facility_candidates(OWNER_ID)
		self.assertEqual(result["status"], "unavailable")
		self.assertEqual(result["candidates"], [])

	def test_owner_id_never_reaches_log_error(self):
		with patch("crm.api.facility_onboarding._hfr_facilities_for_owner", side_effect=RuntimeError("registry down")):
			with patch("frappe.log_error") as log_error:
				owner_facility_candidates(OWNER_ID)
		for call in log_error.call_args_list:
			text = " ".join(str(part) for part in call.args + call.kwargs.values())
			self.assertNotIn(OWNER_ID, text)


class TestFacilityIdLinking(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("facility_id_linking_test")
		self.addCleanup(frappe.db.rollback, save_point="facility_id_linking_test")
		self.addCleanup(frappe.set_user, "Administrator")
		for mfl, fid in ((MFL_A, ""), (MFL_B, ""), (MFL_OTHER, "")):
			frappe.get_doc(
				{
					"doctype": "CRM Pre-Qualified Facility",
					"mfl_code": mfl,
					"facility_name": "Facility ID Link Test %s" % mfl,
					"keph_level": "Level 3",
					"hfr_facility_id": fid,
				}
			).insert(ignore_permissions=True)
		self.lead_name = self._make_lead(MFL_A, MFL_OTHER)
		self.deal_name = self._make_deal(MFL_B, MFL_OTHER)

	def _make_lead(self, *mfls) -> str:
		lead = frappe.get_doc(
			{"doctype": "CRM Lead", "first_name": "Link", "last_name": "Tester", "email": "link-tester-%s@example.com" % MFL_A}
		)
		lead.flags.ignore_permissions = True
		lead.flags.ignore_links = True
		lead.insert(ignore_permissions=True, ignore_links=True)
		for mfl in mfls:
			self._insert_row("CRM Lead Facility", lead.name, "CRM Lead", mfl)
		return lead.name

	def _make_deal(self, *mfls) -> str:
		deal = frappe.get_doc({"doctype": "CRM Deal", "status": "Qualification", "mobile_no": "0700000001"})
		deal.flags.ignore_permissions = True
		deal.flags.ignore_links = True
		deal.insert(ignore_permissions=True, ignore_links=True)
		for mfl in mfls:
			self._insert_row("CRM Deal Facility", deal.name, "CRM Deal", mfl)
		return deal.name

	def _insert_row(self, doctype, parent, parenttype, mfl):
		row = frappe.get_doc(
			{
				"doctype": doctype,
				"parent": parent,
				"parenttype": parenttype,
				"parentfield": "facilities",
				"mfl_code": mfl,
				"hfr_facility_id": "",
			}
		)
		row.flags.ignore_permissions = True
		row.flags.ignore_links = True
		row.insert(ignore_permissions=True, ignore_links=True)
		return row.name

	def _rows(self, mfl, doctype=None):
		filters = {"mfl_code": mfl}
		if doctype:
			filters["parenttype"] = doctype
		return frappe.get_all("CRM Lead Facility" if doctype == "CRM Lead" else "CRM Deal Facility", filters=filters, fields=["name", "parent", "hfr_facility_id"])

	def test_invalid_input_is_invalid(self):
		self.assertEqual(record_facility_id(MFL_A, "FID-1", source="manual", actor="a")["status"], "invalid")
		self.assertEqual(record_facility_id("", "", source="manual", actor="a")["status"], "invalid")

	def test_express_mfl_that_is_a_different_fid_is_refused(self):
		result = record_facility_id(FID_B, FID_A, source="manual", actor="a")
		self.assertEqual(result["status"], "different_fid")

	def test_conflicting_recorded_fid_is_refused(self):
		frappe.db.set_value("CRM Pre-Qualified Facility", {"mfl_code": MFL_A}, "hfr_facility_id", FID_B)
		result = record_facility_id(MFL_A, FID_A, source="manual", actor="a")
		self.assertEqual(result["status"], "different_fid")
		self.assertEqual(frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": MFL_A}, "hfr_facility_id"), FID_B)

	def test_express_row_holding_the_fid_counts_as_holder(self):
		frappe.get_doc(
			{"doctype": "CRM Pre-Qualified Facility", "mfl_code": FID_A, "facility_name": "Express row", "keph_level": "Level 3"}
		).insert(ignore_permissions=True)
		result = record_facility_id(MFL_A, FID_A, source="manual", actor="a")
		self.assertEqual(result["status"], "in_use")
		self.assertEqual(len(result["holders"]), 1)
		self.assertEqual(result["holders"][0]["doctype"], "CRM Pre-Qualified Facility")
		self.assertEqual(result["holders"][0]["mfl_code"], FID_A)
		# allow_shared links despite the holder.
		shared = record_facility_id(MFL_A, FID_A, source="manual", actor="a", allow_shared=True)
		self.assertEqual(shared["status"], "linked")

	def test_record_facility_id_links_register_and_rows(self):
		result = record_facility_id(MFL_A, FID_A, source="hfr", actor="owner@example.test")
		self.assertEqual(result["status"], "linked")
		self.assertEqual(frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": MFL_A}, "hfr_facility_id"), FID_A)
		self.assertEqual(frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": MFL_A}, "hfr_sync_status"), "HFR Verified")
		lead_rows = self._rows(MFL_A, "CRM Lead")
		self.assertEqual(len(lead_rows), 1)
		self.assertEqual(lead_rows[0].hfr_facility_id, FID_A)
		# The other facility row of the same lead is untouched.
		other_rows = self._rows(MFL_OTHER, "CRM Lead")
		self.assertEqual(other_rows[0].hfr_facility_id, "")

	def test_second_identical_call_is_already_linked_and_changes_nothing(self):
		record_facility_id(MFL_A, FID_A, source="hfr", actor="owner@example.test")
		result = record_facility_id(MFL_A, FID_A, source="hfr", actor="owner@example.test")
		self.assertEqual(result["status"], "already_linked")
		self.assertEqual(result["filled"], 0)

	def test_fill_skips_a_row_with_a_different_fid(self):
		lead_row = self._rows(MFL_A, "CRM Lead")[0].name
		frappe.db.set_value("CRM Lead Facility", lead_row, "hfr_facility_id", FID_B)
		result = fill_facility_rows(MFL_A, FID_A, sync_status="Manual")
		self.assertEqual(result["filled"], 0)
		self.assertEqual(result["skipped"], 1)
		self.assertEqual(frappe.db.get_value("CRM Lead Facility", lead_row, "hfr_facility_id"), FID_B)

	def test_replace_fid_updates_rows_holding_the_old_value(self):
		lead_row = self._rows(MFL_A, "CRM Lead")[0].name
		frappe.db.set_value("CRM Deal Facility", {"parent": self.deal_name, "mfl_code": MFL_B}, "hfr_facility_id", FID_B)
		result = fill_facility_rows(MFL_B, FID_A, sync_status="Manual", replace_fid=FID_B)
		self.assertEqual(result["filled"], 1)
		self.assertEqual(result["deals"], [self.deal_name])
		self.assertEqual(frappe.db.get_value("CRM Deal Facility", {"parent": self.deal_name, "mfl_code": MFL_B}, "hfr_facility_id"), FID_A)

	def test_blank_mfl_fills_nothing(self):
		result = fill_facility_rows("", FID_A, sync_status="Manual")
		self.assertEqual(result, {"filled": 0, "skipped": 0, "deals": []})

	def test_blank_mfl_deal_row_links_that_row_only(self):
		blank_row = self._insert_row("CRM Deal Facility", self.deal_name, "CRM Deal", "")
		result = record_facility_id("", FID_B, source="manual", actor="staff@example.test", deal_row=blank_row)
		self.assertEqual(result["status"], "linked")
		self.assertEqual(result["filled"], 1)
		self.assertEqual(frappe.db.get_value("CRM Deal Facility", blank_row, "hfr_facility_id"), FID_B)
		# The MFL-keyed rows and the register are untouched.
		self.assertEqual(frappe.db.get_value("CRM Deal Facility", {"parent": self.deal_name, "mfl_code": MFL_B}, "hfr_facility_id"), "")
		self.assertEqual(frappe.db.get_value("CRM Deal Facility", {"parent": self.deal_name, "mfl_code": MFL_OTHER}, "hfr_facility_id"), "")
		self.assertEqual(frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": MFL_B}, "hfr_facility_id"), "")

	def test_membership_rows_of_other_deals_are_untouched(self):
		lead_rows_before = frappe.get_all("CRM Lead Facility", fields=["name", "hfr_facility_id"])
		record_facility_id(MFL_A, FID_A, source="manual", actor="a")
		lead_rows_after = frappe.get_all("CRM Lead Facility", fields=["name", "hfr_facility_id"])
		self.assertEqual(len(lead_rows_before), len(lead_rows_after))
		before = {row.name: row.hfr_facility_id or "" for row in lead_rows_before}
		after = {row.name: row.hfr_facility_id or "" for row in lead_rows_after}
		for name in before:
			if name != self._rows(MFL_A, "CRM Lead")[0].name:
				self.assertEqual(before[name], after[name])

	def test_holders_exclude_the_same_mfl(self):
		frappe.db.set_value("CRM Pre-Qualified Facility", {"mfl_code": MFL_A}, "hfr_facility_id", FID_A)
		holders = facility_id_holders(FID_A, MFL_A)
		self.assertEqual([h["doctype"] for h in holders], [])
		holders_any = facility_id_holders(FID_A)
		self.assertEqual([h["doctype"] for h in holders_any], ["CRM Pre-Qualified Facility"])


class TestOwnerFacilityLookupGuard(UnitTestCase):
	def test_refuses_users_without_access(self):
		with (
			patch("crm.api.optin_admin._is_admin", return_value=False),
			patch("crm.api.optin_admin._get_coordinator_networks", return_value=[]),
		):
			self.assertRaises(frappe.PermissionError, lookup_owner_facilities, "12345678")

	def test_admin_lookup_passes_through(self):
		with (
			patch("crm.api.optin_admin._is_admin", return_value=True),
			patch.object(
				optin_admin, "owner_facility_candidates", return_value={"status": "ok", "candidates": []}
			) as lookup,
		):
			self.assertEqual(lookup_owner_facilities("12345678"), {"status": "ok", "candidates": []})
		lookup.assert_called_once_with("12345678")


class TestSaveFacilityIdRules(IntegrationTestCase):
	NETWORK = "fid-link-save"
	MFL = "FIDSAVETEST01"

	def setUp(self):
		frappe.set_user("Administrator")
		self._commit_patch = patch.object(frappe.db, "commit", lambda *args, **kwargs: None)
		self._commit_patch.start()
		self.addCleanup(self._commit_patch.stop)
		frappe.db.savepoint("save_facility_fid_test")
		self.addCleanup(frappe.db.rollback, save_point="save_facility_fid_test")
		self.addCleanup(frappe.set_user, "Administrator")
		if not frappe.db.exists("CRM Opt-In Network", self.NETWORK):
			frappe.get_doc(
				{"doctype": "CRM Opt-In Network", "slug": self.NETWORK, "display_name": "FID Save Test", "enabled": 1}
			).insert(ignore_permissions=True)
		for name in frappe.get_all("CRM Pre-Qualified Facility", {"mfl_code": self.MFL}, pluck="name"):
			frappe.delete_doc("CRM Pre-Qualified Facility", name, force=True, ignore_permissions=True)
		self.facility = frappe.get_doc(
			{
				"doctype": "CRM Pre-Qualified Facility",
				"mfl_code": self.MFL,
				"facility_name": "FID Save Test Facility",
				"keph_level": "Level 3",
			}
		)
		self.facility.flags.skip_invitation = True
		self.facility.insert(ignore_permissions=True)
		self.lead = frappe.get_doc(
			{"doctype": "CRM Lead", "first_name": "Save", "last_name": "Tester", "email": "save-fid-tester@example.com"}
		)
		self.lead.flags.ignore_permissions = True
		self.lead.flags.ignore_links = True
		self.lead.insert(ignore_permissions=True, ignore_links=True)
		row = frappe.get_doc(
			{
				"doctype": "CRM Lead Facility",
				"parent": self.lead.name,
				"parenttype": "CRM Lead",
				"parentfield": "facilities",
				"mfl_code": self.MFL,
			}
		)
		row.flags.ignore_permissions = True
		row.flags.ignore_links = True
		row.insert(ignore_permissions=True, ignore_links=True)
		self.lead_row = row.name

	def _save(self, **fields):
		data = {
			"name": self.facility.name,
			"mfl_code": self.MFL,
			"facility_name": self.facility.facility_name,
			"keph_level": "Level 3",
			"memberships": [
				{
					"network": self.NETWORK,
					"status": "Active",
					"contact_name": "Contact",
					"contact_email": "save-fid-contact@example.com",
					"contact_phone": "+254700000001",
				}
			],
		}
		data.update(fields)
		return save_facility(data)

	def test_typed_fid_is_saved_and_fills_rows(self):
		self._save(hfr_facility_id="FID-00-SAVETEST-1")
		self.facility.reload()
		self.assertEqual(self.facility.hfr_facility_id, "FID-00-SAVETEST-1")
		self.assertEqual(self.facility.hfr_sync_status, "Manual")
		self.assertEqual(frappe.db.get_value("CRM Lead Facility", self.lead_row, "hfr_facility_id"), "FID-00-SAVETEST-1")

	def test_invalid_fid_is_refused(self):
		self.assertRaises(frappe.ValidationError, self._save, hfr_facility_id="FID-1")
		self.facility.reload()
		self.assertFalse(self.facility.hfr_facility_id)

	def test_stored_fid_never_cleared_by_blank(self):
		self._save(hfr_facility_id="FID-00-SAVETEST-1")
		self._save(hfr_facility_id="")
		self.facility.reload()
		self.assertEqual(self.facility.hfr_facility_id, "FID-00-SAVETEST-1")

	def test_replacing_a_stored_fid_needs_the_flag(self):
		self._save(hfr_facility_id="FID-00-SAVETEST-1")
		self.assertRaises(frappe.ValidationError, self._save, hfr_facility_id="FID-00-SAVETEST-2")
		self.facility.reload()
		self.assertEqual(self.facility.hfr_facility_id, "FID-00-SAVETEST-1")

	def test_admin_replacement_updates_rows_holding_the_old_value(self):
		self._save(hfr_facility_id="FID-00-SAVETEST-1")
		self._save(hfr_facility_id="FID-00-SAVETEST-2", replace_facility_id=1)
		self.facility.reload()
		self.assertEqual(self.facility.hfr_facility_id, "FID-00-SAVETEST-2")
		self.assertEqual(self.facility.hfr_sync_status, "Manual")
		self.assertEqual(frappe.db.get_value("CRM Lead Facility", self.lead_row, "hfr_facility_id"), "FID-00-SAVETEST-2")

	def test_fid_on_another_facility_is_refused(self):
		other = frappe.get_doc(
			{
				"doctype": "CRM Pre-Qualified Facility",
				"mfl_code": "FIDSAVETEST02",
				"facility_name": "Other Facility",
				"keph_level": "Level 3",
				"hfr_facility_id": "FID-00-SAVETEST-1",
			}
		)
		other.flags.skip_invitation = True
		other.insert(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, self._save, hfr_facility_id="FID-00-SAVETEST-1")
