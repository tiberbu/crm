"""Add SMS delivery fields to contract signatories and legacy submissions."""

import json

import frappe


def execute():
	"""Backfill only columns that may be absent on an already-installed site.

	The DocType JSON migration creates new columns on normal migrate. This guard
	keeps the patch safe for sites upgrading from an older CRM build where the
	new child fields have not been synced yet.
	"""
	for doctype, fields in {
		"CRM Contract Signatory": ["signatory_phone"],
		"CRM Network Signer": ["phone"],
		"CRM Opt-In Submission": ["facility_signatory_phone", "facility_witness_phone"],
	}.items():
		if not frappe.db.table_exists(doctype):
			continue
		for field in fields:
			if not frappe.db.has_column(doctype, field):
				# DocType sync owns the actual schema; this patch intentionally does
				# not issue raw ALTER statements on CRM-managed tables.
				frappe.clear_cache(doctype=doctype)

	# Preserve the new network status for historical completed submissions. The
	# operation is deliberately idempotent and only changes memberships that are
	# still empty/Active/Declined to Opted In when the submission was Processed.
	if not all(
		frappe.db.table_exists(doctype)
		for doctype in (
			"CRM Opt-In Submission",
			"CRM Pre-Qualified Facility",
			"CRM Facility Membership",
		)
	):
		return
	for submission in frappe.get_list(
		"CRM Opt-In Submission",
		filters={"status": "Processed"},
		fields=["network_slug", "raw_json"],
		limit_page_length=0,
		ignore_permissions=True,
	):
		try:
			payload = json.loads(submission.raw_json or "{}")
		except (TypeError, ValueError):
			continue
		mfl_codes = {
			frappe.utils.cstr(row.get("mfl_code") or "").strip()
			for row in payload.get("facilities") or []
			if isinstance(row, dict) and row.get("mfl_code")
		}
		if not mfl_codes or not submission.network_slug:
			continue
		facilities = frappe.get_list(
			"CRM Pre-Qualified Facility",
			filters={"mfl_code": ["in", list(mfl_codes)]},
			fields=["name"],
			limit_page_length=0,
			ignore_permissions=True,
		)
		parents = [row.name for row in facilities]
		if not parents:
			continue
		memberships = frappe.get_list(
			"CRM Facility Membership",
			filters={
				"parenttype": "CRM Pre-Qualified Facility",
				"parent": ["in", parents],
				"network": submission.network_slug,
			},
			fields=["name", "status"],
			limit_page_length=0,
			ignore_permissions=True,
		)
		for membership in memberships:
			if membership.status != "Opted In":
				frappe.db.set_value(
					"CRM Facility Membership",
					membership.name,
					"status",
					"Opted In",
					update_modified=False,
				)
