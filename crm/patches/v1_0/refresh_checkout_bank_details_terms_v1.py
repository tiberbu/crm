"""Add the seeded bank destination to the reviewed agreement template."""

from pathlib import Path

import frappe


TITLE = "CareverseHIMS Network Facility Agreement v1 (Facility Template)"
TEMPLATE_FILENAME = "chak_careverse_saas_agreement_v1.html"


def execute():
	if not frappe.db.exists("DocType", "Terms and Conditions"):
		return
	name = frappe.db.exists("Terms and Conditions", TITLE)
	if not name:
		return
	path = Path(frappe.get_app_path("crm", "setup", "templates", TEMPLATE_FILENAME))
	if not path.exists():
		return
	terms = path.read_text(encoding="utf-8")
	doc = frappe.get_doc("Terms and Conditions", name)
	if doc.terms == terms:
		return
	doc.terms = terms
	doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()
