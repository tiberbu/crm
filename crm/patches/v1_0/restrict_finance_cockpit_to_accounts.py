"""Align Finance Cockpit page and CRM accounting permissions with Accounts roles."""

from __future__ import annotations

import frappe

from crm.finance.access import ACCOUNTING_ROLES


def _ensure_permission(doc, role, values):
	permissions = list(doc.permissions or [])
	row = next((item for item in permissions if item.role == role), None)
	if row:
		changed = False
		for field, value in values.items():
			if getattr(row, field, 0) != value:
				setattr(row, field, value)
				changed = True
		return changed
	doc.append("permissions", {"role": role, **values})
	return True


def _ensure_role(role):
	if frappe.db.exists("Role", role):
		return
	frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
		ignore_permissions=True  # SYSTEM-INTERNAL: permission migration
	)


def restrict_page_roles():
	"""Limit the Finance Cockpit page to Accounts roles.

	Rows are added with ``append`` so they are child documents; a raw list of dicts
	crashes ``save()`` with ``'dict' object has no attribute 'is_new'``. Model sync
	usually imports these roles from the page JSON already, so the save is skipped
	when nothing would change.
	"""
	if not frappe.db.exists("Page", "finance-cockpit"):
		return False

	page = frappe.get_doc("Page", "finance-cockpit")
	if sorted(row.role for row in page.get("roles") or []) == sorted(ACCOUNTING_ROLES):
		return False

	for role in sorted(ACCOUNTING_ROLES):
		_ensure_role(role)

	page.set("roles", [])
	for role in sorted(ACCOUNTING_ROLES):
		page.append("roles", {"role": role})
	# The page JSON in the app is the source of truth; never rewrite it from a migration.
	page.flags.do_not_update_json = True
	page.save(ignore_permissions=True)  # SYSTEM-INTERNAL: permission migration
	return True


def execute():
	restrict_page_roles()

	for doctype in ("CRM Partner Rebate Voucher", "CRM Sales Commission"):
		if not frappe.db.exists("DocType", doctype):
			continue
		doc = frappe.get_doc("DocType", doctype)
		changed = False
		for role in ACCOUNTING_ROLES:
			changed = _ensure_permission(
				doc,
				role,
				{
					"read": 1,
					"write": 1,
					"create": 1 if role == "Accounts Manager" else 0,
					"report": 1,
					"export": 1,
				},
			) or changed
		if changed:
			doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL: permission migration
