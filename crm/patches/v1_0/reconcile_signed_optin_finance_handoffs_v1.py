"""Reconcile signed Opt-In facilities into the native Finance handoff.

The patch is intentionally narrow and retry-safe: it only invokes the same
facility-signature handoff used for future signatures. Missing ERPNext
configuration is logged and skipped so a CRM-only site can migrate safely.
"""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "CRM Contract") or not frappe.db.exists(
		"DocType", "CRM Opt-In Submission"
	):
		return
	if not frappe.db.exists("DocType", "Sales Order") or not frappe.db.exists("DocType", "Quotation"):
		return

	from crm.automation.optin_billing import handoff_facility_signed

	for row in frappe.get_list(
		"CRM Contract",
		fields=["name"],
		limit_page_length=0,
		ignore_permissions=True,  # SYSTEM-INTERNAL: one-time reconciliation
	):
		try:
			contract = frappe.get_doc("CRM Contract", row.name)
			facility = next(
				(
					signatory
					for signatory in (contract.signatories or [])
					if signatory.signatory_role == "Facility Signatory"
				),
				None,
			)
			if not facility or facility.status != "Signed":
				continue
			result = handoff_facility_signed(
				contract.name,
				signed_at=getattr(facility, "signed_at", None) or contract.modified,
			)
			if not result.get("ok") and result.get("reason_code") != "missing_submission":
				frappe.log_error(
					result.get("reason") or "Finance handoff could not be reconciled",
					"Opt-In Finance handoff reconciliation: %s" % contract.name,
				)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"Opt-In Finance handoff reconciliation failed: %s" % row.name,
			)
