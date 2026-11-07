"""Linking a Facility ID onto the register and the matching Lead/Deal rows."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

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
			{"doctype": doctype, "parent": parent, "parenttype": parenttype, "parentfield": "facilities", "mfl_code": mfl}
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
			{"doctype": "CRM Pre-Qualified Facility", "mfl_code": FID_A, "facility_name": "Express row"}
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
		other_row = self._insert_row("CRM Deal Facility", self.deal_name, "CRM Deal", MFL_OTHER)
		result = record_facility_id("", FID_B, source="manual", actor="staff@example.test", deal_row=other_row)
		self.assertEqual(result["status"], "linked")
		self.assertEqual(result["filled"], 1)
		self.assertEqual(result["deals"], [self.deal_name])
		self.assertEqual(frappe.db.get_value("CRM Deal Facility", other_row, "hfr_facility_id"), FID_B)
		# MFL B rows and the register are untouched.
		self.assertEqual(frappe.db.get_value("CRM Deal Facility", {"parent": self.deal_name, "mfl_code": MFL_B}, "hfr_facility_id"), "")
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
