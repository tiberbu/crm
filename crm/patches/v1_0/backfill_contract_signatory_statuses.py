"""Normalize legacy CRM Contract signatory statuses without reopening signatures."""

import frappe

_PENDING_STATUSES = {
	"",
	"pending",
	"awaiting",
	"awaiting signature",
	"awaiting signatures",
	"invited",
	"sent",
}
_SIGNED_STATUSES = {"signed", "completed", "complete", "fully signed"}
_DECLINED_STATUSES = {"declined", "rejected", "cancelled", "canceled"}


def _canonical_status(row):
	"""Return a supported child-row status, preserving evidence of a signature."""
	# Signature evidence wins over a stale or contradictory Select value. Never
	# reopen a row that has already captured a signature during a data cleanup.
	if row.get("signature_data") or row.get("signed_at"):
		return "Signed"

	raw = frappe.utils.cstr(row.get("status") or "").strip()
	status = " ".join(raw.lower().split())
	if status in _SIGNED_STATUSES:
		return "Signed"
	if status in _DECLINED_STATUSES:
		return "Declined"
	if status in _PENDING_STATUSES:
		return "Pending"
	# Unknown/empty pre-signing values are recoverable as Pending. The runtime
	# handler still protects any row that is changed after this patch runs.
	return "Pending"


def execute():
	"""Canonicalize child rows; leave already canonical data untouched."""
	if not all(frappe.db.table_exists(doctype) for doctype in ("CRM Contract", "CRM Contract Signatory")):
		return
	if not frappe.db.has_column("CRM Contract Signatory", "status"):
		return

	updated = 0
	for contract in frappe.get_list(
		"CRM Contract",
		fields=["name"],
		limit_page_length=0,
		ignore_permissions=True,
	):
		contract_doc = frappe.get_doc("CRM Contract", contract.name)
		for row in contract_doc.signatories or []:
			canonical = _canonical_status(row)
			if frappe.utils.cstr(row.status or "").strip() == canonical:
				continue
			frappe.db.set_value(
				"CRM Contract Signatory",
				row.name,
				"status",
				canonical,
				update_modified=False,
			)
			updated += 1
	if updated:
		frappe.logger("crm.contracts").info(
			"Normalized %s CRM Contract signatory statuses during migration", updated
		)
