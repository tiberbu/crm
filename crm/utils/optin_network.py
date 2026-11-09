"""Helpers for linking CRM and ERPNext records to an Opt-In Network.

The link is deliberately additive.  ``network_slug`` remains the public/API
compatibility field, while ``optin_network`` is a real Link field used by
Frappe User Permissions to scope CRM records for network users.
"""

from __future__ import annotations

import frappe


def network_name(value: str | None) -> str:
	"""Return a valid CRM Opt-In Network name, or an empty string."""
	slug = frappe.utils.cstr(value or "").strip()
	if not slug:
		return ""
	try:
		return slug if frappe.db.exists("CRM Opt-In Network", slug) else ""
	except Exception:
		return ""


def set_network_link(doc, value: str | None, *, overwrite: bool = False) -> str:
	"""Set ``optin_network`` when that optional column exists.

	Returns the value written.  Missing ERPNext doctypes/columns are expected on
	CRM-only sites and are intentionally ignored for backward compatibility.
	"""
	slug = network_name(value)
	if not slug or not doc:
		return ""
	doctype = frappe.utils.cstr(getattr(doc, "doctype", "") or "").strip()
	if not doctype:
		return ""
	try:
		if not frappe.db.has_column(doctype, "optin_network"):
			return ""
		current = frappe.utils.cstr(doc.get("optin_network") or "").strip()
		if overwrite or not current:
			doc.set("optin_network", slug)
			return slug
		return current
	except Exception:
		return ""


def get_network_link(doctype: str, name: str) -> str:
	"""Read a populated network Link without failing on legacy schemas."""
	try:
		if not frappe.db.has_column(doctype, "optin_network"):
			return ""
		return frappe.utils.cstr(frappe.db.get_value(doctype, name, "optin_network") or "").strip()
	except Exception:
		return ""
