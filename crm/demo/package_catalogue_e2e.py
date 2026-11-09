"""Remove what the package-catalogue Playwright journey adds to a dev site.

The journey names every package it creates "E2E <run> …" and gives it a new item; this drops
those catalogue rows, their Item Prices and the items no order uses.
  bench --site <site> execute crm.demo.package_catalogue_e2e.remove_e2e_packages
"""

import frappe

PREFIX = "E2E "


def remove_e2e_packages(prefix: str = PREFIX):
	settings = frappe.get_single("CRM Opt-In Settings")
	removed = [row for row in settings.token_packages if (row.display_name or "").startswith(prefix)]
	if not removed:
		return []
	settings.set("token_packages", [row for row in settings.token_packages if row not in removed])
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)
	for row in removed:
		for price in frappe.get_all("Item Price", {"item_code": row.item_code}, pluck="name"):
			frappe.delete_doc("Item Price", price, ignore_permissions=True, force=True)
		used = any(
			frappe.db.exists(doctype, {"item_code": row.item_code}) for doctype in ("Sales Order Item", "Quotation Item", "Sales Invoice Item")
		)
		if row.item_code.startswith("VX-E2E-") and not used:
			frappe.delete_doc("Item", row.item_code, ignore_permissions=True, force=True)
	frappe.db.commit()
	return [row.display_name for row in removed]
