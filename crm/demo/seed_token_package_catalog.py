"""Seed a small, idempotent token catalogue for the CRM development site.

Run explicitly with:
    bench --site cr-dev.tiberbu.app execute \
        "crm.demo.seed_token_package_catalog.run"

The sample rates are KES and exclude VAT. This helper is deliberately not a
migration so production sites do not receive demo commercial rates.
"""

from __future__ import annotations

import frappe

PRICE_LIST = "CRM Token Packages - DEV"

PACKAGES = [
	{
		"item_code": "CV-TOKEN-CORE",
		"item_name": "Core Care Operations",
		"rate": 30000,
		"display_name": "Core care operations",
		"description": "A practical starting package for core facility workflows and everyday service administration.",
		"coverage_summary": "Designed for approximately 100 routine transactions per month.",
		"token_quantity": 100,
	},
	{
		"item_code": "CV-TOKEN-STANDARD",
		"item_name": "Standard Care Operations",
		"rate": 75000,
		"display_name": "Standard care operations",
		"description": "A balanced package for facilities with regular clinical, laboratory, and billing activity.",
		"coverage_summary": "Designed for approximately 300 routine transactions per month.",
		"token_quantity": 300,
	},
	{
		"item_code": "CV-TOKEN-PLUS",
		"item_name": "Expanded Care Operations",
		"rate": 150000,
		"display_name": "Expanded care operations",
		"description": "A higher-capacity package for facilities managing larger daily workloads and multiple service lines.",
		"coverage_summary": "Designed for approximately 750 routine transactions per month.",
		"token_quantity": 750,
	},
]


def run():
	if "erpnext" not in frappe.get_installed_apps():
		frappe.throw("ERPNext is required to seed the token catalogue.")

	price_list = _ensure_price_list()
	rows = []
	for package in PACKAGES:
		_ensure_item(package)
		_ensure_item_price(package, price_list)
		rows.append(
			{
				"item_code": package["item_code"],
				"display_name": package["display_name"],
				"description": package["description"],
				"token_quantity": package["token_quantity"],
				"billing_period": "Monthly",
				"coverage_summary": package["coverage_summary"],
				"coverage_metrics": "{\"metric\": \"routine_transactions\", \"period\": \"monthly\"}",
				"enabled": 1,
			}
		)

	settings = frappe.get_single("CRM Opt-In Settings")
	settings.token_price_list = price_list.name
	settings.token_sales_order_validity_days = 30
	settings.token_invoice_due_days = 30
	settings.set("token_packages", rows)
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	return {"price_list": price_list.name, "packages": [row["item_code"] for row in rows]}


def _ensure_price_list():
	if frappe.db.exists("Price List", PRICE_LIST):
		price_list = frappe.get_doc("Price List", PRICE_LIST)
		price_list.selling = 1
		price_list.buying = 0
		price_list.enabled = 1
		price_list.currency = "KES"
		price_list.save(ignore_permissions=True)
		return price_list
	return frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": PRICE_LIST,
			"currency": "KES",
			"selling": 1,
			"buying": 0,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)


def _ensure_item(package):
	if frappe.db.exists("Item", package["item_code"]):
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": package["item_code"],
			"item_name": package["item_name"],
			"item_group": "CareVerse HMIS" if frappe.db.exists("Item Group", "CareVerse HMIS") else "Services",
			"stock_uom": "Nos",
			"is_sales_item": 1,
			"is_stock_item": 0,
			"description": package["description"],
		}
	).insert(ignore_permissions=True)


def _ensure_item_price(package, price_list):
	if frappe.db.exists("Item Price", {"item_code": package["item_code"], "price_list": price_list.name}):
		return
	frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": package["item_code"],
			"price_list": price_list.name,
			"price_list_rate": package["rate"],
			"currency": "KES",
			"selling": 1,
			"buying": 0,
			"uom": "Nos",
		}
	).insert(ignore_permissions=True)
