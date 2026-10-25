"""Add the facility FID to token-purchase documents and backfill it from the MFL code."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from crm.utils.token_facility import FID_FIELD, facility_fid_for_mfl

DOCTYPES = ("Quotation", "Sales Order", "Sales Invoice")


def execute():
	field = {
		"fieldname": FID_FIELD,
		"fieldtype": "Data",
		"label": "Token Facility FID",
		"read_only": 1,
		"insert_after": "crm_token_facility_mfl",
	}
	create_custom_fields({doctype: [field] for doctype in DOCTYPES})
	for doctype in DOCTYPES:
		if not frappe.db.has_column(doctype, "crm_token_facility_mfl"):
			continue
		mfls = frappe.get_all(
			doctype,
			filters={"crm_token_facility_mfl": ["is", "set"], FID_FIELD: ["is", "not set"]},
			pluck="crm_token_facility_mfl",
			distinct=True,
		)
		for mfl in mfls:
			fid = facility_fid_for_mfl(mfl)
			if fid:
				frappe.db.sql(
					f"update `tab{doctype}` set `{FID_FIELD}`=%s"
					f" where crm_token_facility_mfl=%s and ifnull(`{FID_FIELD}`, '')=''",
					(fid, mfl),
				)
