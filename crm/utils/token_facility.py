"""Facility identity for token purchases.

OpenMeter grants are keyed by the HFR Facility ID (FID), so every token-purchase
Quotation, Sales Order and Sales Invoice carries the FID beside its MFL code.
"""

import frappe
from frappe.utils import cstr

FID_FIELD = "crm_token_facility_fid"


def facility_fid_for_mfl(mfl_code):
	"""Return the one FID CRM records for an MFL code, or "" when it has none or several."""
	mfl = cstr(mfl_code).strip()
	if not mfl:
		return ""
	fids = {}
	for doctype in ("CRM Deal Facility", "CRM Pre-Qualified Facility"):
		for fid in frappe.get_all(
			doctype, filters={"mfl_code": mfl, "hfr_facility_id": ["is", "set"]}, pluck="hfr_facility_id"
		):
			fid = cstr(fid).strip()
			if fid:
				fids.setdefault(fid.casefold(), fid)
	return next(iter(fids.values())) if len(fids) == 1 else ""


def stamp_facility_fid(doc, method=None):
	"""Fill the purchase's FID from its MFL code when it is not already set."""
	if not doc.meta.has_field(FID_FIELD) or doc.get(FID_FIELD):
		return
	mfl = doc.get("crm_token_facility_mfl")
	if mfl:
		doc.set(FID_FIELD, facility_fid_for_mfl(mfl))
