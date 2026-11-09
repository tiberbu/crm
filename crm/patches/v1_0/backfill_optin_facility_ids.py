"""
Backfill the Facility ID (HFR FID) on CRM Lead Facility and CRM Deal Facility rows.

Opt-in deals historically lost the Facility ID: the processor built Lead rows without
``hfr_facility_id`` and the register read that supplies it is mostly blank, so the
Metering tab shows "This facility has no Facility ID" for opt-in deals.

This patch:

1. Builds an MFL -> FID map from the pre-qualified facility register, skipping MFL
   codes with conflicting FIDs (ambiguous).
2. Fills the blank ``hfr_facility_id`` on Lead and Deal facility rows from that map.
3. Clears the false "HFR Verified" ``hfr_sync_status`` on rows that still have no
   Facility ID after the fill.

Local data only; no HFR calls during migrate. Safe to run repeatedly — rows that
already carry a Facility ID are never touched, and a FID is never overwritten.
"""

import frappe


def execute():
	for doctype in ("CRM Pre-Qualified Facility", "CRM Lead Facility", "CRM Deal Facility"):
		if not frappe.db.table_exists(doctype):
			return

	# --- 1. MFL -> FID map from the register --------------------------------
	register = {}
	for row in frappe.get_all(
		"CRM Pre-Qualified Facility",
		filters={"hfr_facility_id": ["is", "set"]},
		fields=["mfl_code", "hfr_facility_id"],
		ignore_permissions=True,  # SYSTEM-INTERNAL: migration runs as Administrator.
	):
		mfl = frappe.utils.cstr(row.mfl_code).strip()
		fid = frappe.utils.cstr(row.hfr_facility_id).strip()
		if not mfl or not fid:
			continue
		register.setdefault(mfl, set()).add(fid)

	facility_ids = {mfl: next(iter(fids)) for mfl, fids in register.items() if len(fids) == 1}

	filled = 0
	for doctype in ("CRM Lead Facility", "CRM Deal Facility"):
		rows = frappe.get_all(
			doctype,
			filters={"hfr_facility_id": ["is", "not set"]},
			fields=["name", "mfl_code"],
			ignore_permissions=True,  # SYSTEM-INTERNAL: migration runs as Administrator.
		)
		for row in rows:
			fid = facility_ids.get(frappe.utils.cstr(row.mfl_code).strip())
			if not fid:
				continue
			frappe.db.set_value(
				doctype, row.name, "hfr_facility_id", fid, update_modified=False
			)
			filled += 1

	# --- 2. Honest sync status ------------------------------------------------
	# A row without a Facility ID cannot claim "HFR Verified". Only that value is
	# cleared; "Manual" and other statuses are left untouched.
	cleared = 0
	for doctype in ("CRM Lead Facility", "CRM Deal Facility"):
		rows = frappe.get_all(
			doctype,
			filters={
				"hfr_facility_id": ["is", "not set"],
				"hfr_sync_status": "HFR Verified",
			},
			fields=["name"],
			ignore_permissions=True,  # SYSTEM-INTERNAL: migration runs as Administrator.
		)
		for row in rows:
			frappe.db.set_value(
				doctype, row.name, "hfr_sync_status", "", update_modified=False
			)
			cleared += 1

	frappe.db.commit()
	frappe.msgprint(
		f"Opt-in facility ID backfill complete: {filled} row(s) filled, "
		f"{cleared} false 'HFR Verified' status(es) cleared."
	)
