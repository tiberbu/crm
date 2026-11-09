"""Backfill the Tiberbu settings table from legacy singleton contact fields."""

import frappe


def execute():
	"""Seed only an empty table; never overwrite contacts configured by a user."""
	if not frappe.db.table_exists("CRM Opt-In Settings"):
		return
	meta = frappe.get_meta("CRM Opt-In Settings")
	if not meta.has_field("tiberbu_contacts"):
		return
	settings = frappe.get_single("CRM Opt-In Settings")
	if settings.get("tiberbu_contacts"):
		return
	rows = []
	signatory_name = settings.get("tiberbu_signatory_name") or ""
	signatory_email = settings.get("tiberbu_signatory_email") or ""
	signatory_phone = settings.get("tiberbu_signatory_phone") or ""
	# Older sites may only have the User link populated. Resolve its current
	# contact details so the new table is useful immediately after migration.
	if not signatory_name or not signatory_email:
		user_name = settings.get("tiberbu_signatory") or ""
		if user_name and frappe.db.exists("User", user_name):
			user = frappe.db.get_value(
				"User",
				user_name,
				["full_name", "email", "mobile_no"],
				as_dict=True,
			)
			if user:
				signatory_name = signatory_name or user.full_name
				signatory_email = signatory_email or user.email
				signatory_phone = signatory_phone or user.mobile_no
	if signatory_name and signatory_email:
		rows.append(
			{
				"role": "Signatory",
				"full_name": signatory_name,
				"email": signatory_email,
				"phone": signatory_phone,
			}
		)
	if settings.get("tiberbu_approver_name") and settings.get("tiberbu_approver_email"):
		rows.append(
			{
				"role": "Approver",
				"full_name": settings.tiberbu_approver_name,
				"email": settings.tiberbu_approver_email,
				"phone": settings.tiberbu_approver_phone or "",
			}
		)
	if rows:
		settings.set("tiberbu_contacts", rows)
		settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL
		frappe.db.commit()
