"""Seed the Level 6 negotiated catalogue entries without changing live pricing."""

from __future__ import annotations

import frappe

ITEM_CODE = "CV-HIMS-KEPH-6"
ITEM_NAME = "CareverseHIMS -- Level 6"
PRICES = {
	"Negotiated Year 1": 386978.91,
	"Negotiated Year 2": 386978.91,
	"Negotiated Year 3": 305450.49,
	"Negotiated Year 4": 320723.01,
	"Negotiated Year 5": 336759.16,
}


def execute():
	"""Create missing Level 6 records; never overwrite existing records or rates."""
	if "erpnext" not in frappe.get_installed_apps():
		return

	_item_group = _ensure_item()
	if not _item_group:
		return

	for price_list_name, rate in PRICES.items():
		price_list = _ensure_price_list(price_list_name)
		if not price_list or not price_list.selling or not price_list.enabled:
			continue
		if frappe.db.exists("Item Price", {"price_list": price_list_name, "item_code": ITEM_CODE}):
			continue
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"price_list": price_list_name,
				"item_code": ITEM_CODE,
				"price_list_rate": rate,
				"currency": price_list.currency or "KES",
				"selling": 1,
				"buying": 0,
				"uom": "Nos",
			}
		).insert(ignore_permissions=True)  # SYSTEM-INTERNAL

	frappe.db.commit()


def _ensure_item():
	if frappe.db.exists("Item", ITEM_CODE):
		return True

	item_group = "Services"
	if not frappe.db.exists("Item Group", item_group):
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
	if not item_group:
		return False

	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": ITEM_CODE,
			"item_name": ITEM_NAME,
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_sales_item": 1,
			"is_stock_item": 0,
		}
	).insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	return True


def _ensure_price_list(name):
	if frappe.db.exists("Price List", name):
		return frappe.get_doc("Price List", name)
	return frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": name,
			"currency": "KES",
			"selling": 1,
			"buying": 0,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
