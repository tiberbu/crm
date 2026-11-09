"""Seed the reviewed network/facility CareverseHIMS agreement template.

This creates (or refreshes) the reviewed Terms and Conditions document for an
administrator; it deliberately does not change CRM Opt-In Settings.active_tc_document.
The template is kept as a static HTML asset so user-entered network and facility
data is supplied only at render time through the escaped Jinja context.
"""

from __future__ import annotations

from pathlib import Path

import frappe

TITLE = "CareverseHIMS Network Facility Agreement v1 (Facility Template)"
TEMPLATE_FILENAME = "chak_careverse_saas_agreement_v1.html"


def execute():
	"""Create or refresh the exact seeded template without changing the active setting."""
	if not frappe.db.exists("DocType", "Terms and Conditions"):
		return

	template_path = Path(frappe.get_app_path("crm", "setup", "templates", TEMPLATE_FILENAME))
	terms = template_path.read_text(encoding="utf-8")
	if not terms.strip():
		return

	existing_name = frappe.db.exists("Terms and Conditions", TITLE)
	if existing_name:
		existing = frappe.get_doc("Terms and Conditions", existing_name)
		if existing.terms == terms:
			return
		existing.terms = terms
		existing.save(ignore_permissions=True)  # SYSTEM-INTERNAL
		frappe.db.commit()
		return

	frappe.get_doc(
		{
			"doctype": "Terms and Conditions",
			"title": TITLE,
			"selling": 1,
			"terms": terms,
		}
	).insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()
