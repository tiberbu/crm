"""Mark unambiguous historic Opt-Ins as self-signing without touching contracts."""

import frappe


def execute():
	"""Backfill only records whose submitter and facility-signatory emails match."""
	if not frappe.db.table_exists("CRM Opt-In Submission"):
		return
	if not all(
		frappe.db.has_column("CRM Opt-In Submission", fieldname)
		for fieldname in ("signatory_mode", "submitter_email", "facility_signatory_email")
	):
		return

	for submission in frappe.get_all(
		"CRM Opt-In Submission",
		fields=["name", "signatory_mode", "submitter_email", "facility_signatory_email"],
		limit_page_length=0,
	):
		if frappe.utils.cstr(submission.signatory_mode).strip():
			continue
		submitter_email = frappe.utils.cstr(submission.submitter_email).strip().lower()
		signatory_email = frappe.utils.cstr(submission.facility_signatory_email).strip().lower()
		if submitter_email and submitter_email == signatory_email:
			frappe.db.set_value(
				"CRM Opt-In Submission",
				submission.name,
				"signatory_mode",
				"self",
				update_modified=False,
			)
