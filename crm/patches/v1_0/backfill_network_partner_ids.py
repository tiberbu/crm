"""Backfill six-digit public IDs for existing Opt-In Networks."""

import secrets

import frappe
from frappe import _


def execute():
	if not frappe.db.has_column("CRM Opt-In Network", "partner_id"):
		return

	rows = frappe.get_all(
		"CRM Opt-In Network",
		fields=["name", "partner_id"],
		limit_page_length=0,
		ignore_permissions=True,
	)
	for row in rows:
		if row.get("partner_id"):
			continue
		partner_id = _next_partner_id()
		frappe.db.set_value(
			"CRM Opt-In Network",
			row.name,
			"partner_id",
			partner_id,
			update_modified=False,
		)


def _next_partner_id():
	for _attempt in range(100):
		candidate = str(secrets.randbelow(900000) + 100000)
		if not frappe.db.exists("CRM Opt-In Network", {"partner_id": candidate}):
			return candidate
	frappe.throw(_("Could not generate a unique six-digit Partner ID during backfill."))
