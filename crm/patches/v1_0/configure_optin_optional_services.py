"""Seed the curated optional-services price-list setting and remove subscription prices.

Items remain intact for historical quotations. Only Item Price rows for the
subscription SKU prefix are removed from Standard Selling, preventing the
subscription catalogue from appearing as an optional service. The operation is
idempotent and leaves a site's explicit optional list untouched.
"""

import frappe


def execute():
	# CRM Opt-In Settings is a Single DocType, so its fields live in tabSingles
	# rather than a tabCRM Opt-In Settings table. Use metadata instead of
	# Database.has_column, which raises TableMissingError on a valid Single.
	if frappe.db.exists("DocType", "CRM Opt-In Settings") and frappe.get_meta(
		"CRM Opt-In Settings"
	).has_field("optional_services_price_list"):
		settings = frappe.get_single("CRM Opt-In Settings")
		if not settings.get("optional_services_price_list") and frappe.db.exists(
			"Price List", {"name": "Standard Selling", "selling": 1, "enabled": 1}
		):
			settings.optional_services_price_list = "Standard Selling"
			settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL

	if not frappe.db.exists("DocType", "Item Price") or not frappe.db.exists(
		"Price List", "Standard Selling"
	):
		return
	item_rows = frappe.get_list(
		"Item",
		filters={"disabled": 0},
		fields=["name", "item_name"],
		limit_page_length=0,
		ignore_permissions=True,  # SYSTEM-INTERNAL
	)
	subscription_codes = [
		row.name
		for row in item_rows
		if frappe.utils.cstr(row.item_name or "").casefold().startswith("careverse hmis subscription")
	]
	if subscription_codes:
		prices = frappe.get_list(
			"Item Price",
			filters={"price_list": "Standard Selling", "item_code": ["in", subscription_codes]},
			fields=["name"],
			limit_page_length=0,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
		for row in prices:
			frappe.delete_doc("Item Price", row.name, ignore_permissions=True)
	frappe.clear_cache()
