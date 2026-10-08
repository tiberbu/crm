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


def execute():
	if frappe.db.exists("DocType", "Page") and frappe.db.exists("Page", "finance-cockpit"):
		page = frappe.get_doc("Page", "finance-cockpit")
		page.roles = [{"role": role} for role in sorted(ACCOUNTING_ROLES)]
		page.save(ignore_permissions=True)  # SYSTEM-INTERNAL: permission migration

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
