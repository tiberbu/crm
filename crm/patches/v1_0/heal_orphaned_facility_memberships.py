"""
Heal orphaned CRM Facility Membership rows whose parent is blank or dangling.

A membership row with a blank parent cannot be resolved to a facility and
silently breaks the opt-in flow (see crm/api/optin.py::_get_membership).
This patch:

1. Finds rows where ``parent`` is blank or points to a deleted
   ``CRM Pre-Qualified Facility`` doc.
2. Attempts to re-link each orphan to an existing PQF matched by
   ``network`` + ``contact_email`` (case-insensitive).
3. Deletes orphans that cannot be matched anywhere.

Safe to run repeatedly — already-linked rows are skipped.
"""

import frappe


def execute():
	if not frappe.db.table_exists("CRM Facility Membership"):
		return

	if not frappe.db.table_exists("CRM Pre-Qualified Facility"):
		return

	# --- 1. Collect orphans ---------------------------------------------------
	orphan_rows = frappe.db.sql(
		"""SELECT m.name AS membership_name,
		          m.network,
		          m.contact_email,
		          m.parent
		   FROM `tabCRM Facility Membership` m
		   LEFT JOIN `tabCRM Pre-Qualified Facility` p ON p.name = m.parent
		   WHERE (m.parent IS NULL OR m.parent = '')
		      OR (m.parent <> '' AND p.name IS NULL)""",
		as_dict=True,
	)

	if not orphan_rows:
		frappe.msgprint("No orphaned facility memberships found.")
		return

	frappe.msgprint(f"Found {len(orphan_rows)} orphaned membership row(s).")

	relinked = 0
	deleted = 0

	for row in orphan_rows:
		member_name = row["membership_name"]
		network = (row.get("network") or "").strip()
		email = (row.get("contact_email") or "").strip().lower()

		# Try to find a matching PQF by network + contact_email
		match_filters = {}
		if network:
			match_filters["network"] = network
		if email:
			# Contact email on PQF may differ in case; use LIKE for safety
			match_filters["contact_email"] = ["like", f"%{email}%"]

		pqf_match = None
		if match_filters:
			pqf_candidates = frappe.get_list(
				"CRM Pre-Qualified Facility",
				filters=match_filters,
				fields=["name"],
				limit=1,
				ignore_permissions=True,  # SYSTEM-INTERNAL
			)
			if pqf_candidates:
				pqf_match = pqf_candidates[0]["name"]

		if pqf_match:
			# Re-link the orphan to the matched PQF
			frappe.db.set_value(
				"CRM Facility Membership",
				member_name,
				{
					"parent": pqf_match,
					"parenttype": "CRM Pre-Qualified Facility",
					"parentfield": "memberships",
				},
				update_modified=False,
			)
			relinked += 1
			frappe.msgprint(
				f"Re-linked {member_name} → {pqf_match}"
			)
		else:
			# No match found — delete the unrecoverable orphan
			frappe.delete_doc(
				"CRM Facility Membership",
				member_name,
				force=True,
				ignore_permissions=True,  # SYSTEM-INTERNAL
			)
			deleted += 1
			frappe.msgprint(
				f"Deleted unrecoverable orphan {member_name}"
			)

	frappe.db.commit()
	frappe.msgprint(
		f"Heal complete: {relinked} re-linked, {deleted} deleted."
	)
