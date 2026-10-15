"""Seed a small, idempotent token catalogue for the CRM development site.

Run explicitly with:
    bench --site cr-dev.tiberbu.app execute \
        "crm.demo.seed_token_package_catalog.run"

The sample rates are KES and exclude VAT. This helper is deliberately not a
migration so production sites do not receive demo commercial rates.
"""

from __future__ import annotations

import frappe
from frappe import _

PRICE_LIST = "CRM Token Packages - DEV"

PACKAGES = [
	{
		"item_code": "CV-TOKEN-FREE",
		"item_name": "Free Community Care",
		"rate": 0,
		"display_name": "Free",
		"description": "A complimentary starter package for health posts, dispensaries, and solo clinics to verify facility records and start digital care workflows.",
		"coverage_summary": "Designed for up to 25 routine patient visits or monthly claims verification at zero cost.",
		"token_quantity": 25,
		"coverage_metrics": '{"audience": "For individuals & community clinics", "badge": "Free Forever", "features": ["25 Care Tokens included", "Digital Registry & HFR Verification", "Routine Patient Encounters", "Community Support"]}',
	},
	{
		"item_code": "CV-TOKEN-CORE",
		"item_name": "Core Care Operations",
		"rate": 30000,
		"display_name": "Pro",
		"description": "A practical package for growing health centers managing daily outpatient visits, pharmacy dispensing, and standard lab orders.",
		"coverage_summary": "Designed for approximately 100 routine transactions per month.",
		"token_quantity": 100,
		"coverage_metrics": '{"audience": "For active clinics & dispensaries", "badge": "Popular", "features": ["100 Care Tokens included", "Outpatient Consultations & Vitals", "Pharmacy Dispensing & Inventory", "Direct Email Support"]}',
	},
	{
		"item_code": "CV-TOKEN-STANDARD",
		"item_name": "Standard Care Operations",
		"rate": 75000,
		"display_name": "Standard Care",
		"description": "A balanced package for multi-department facilities with regular clinical consultations, laboratory, and insurance billing activity.",
		"coverage_summary": "Designed for approximately 300 routine transactions per month.",
		"token_quantity": 300,
		"coverage_metrics": '{"audience": "For growing medical centers", "badge": "Recommended", "features": ["300 Care Tokens included", "Multi-Department Coordination", "Laboratory & Diagnostics Workflow", "Insurance Billing & Claims Export"]}',
	},
	{
		"item_code": "CV-TOKEN-PLUS",
		"item_name": "Expanded Care Operations",
		"rate": 150000,
		"display_name": "Enterprise",
		"description": "High-capacity tier for sub-county hospitals and healthcare networks managing inpatient wards, surgery, and multi-facility operations.",
		"coverage_summary": "Designed for approximately 750 routine transactions per month.",
		"token_quantity": 750,
		"coverage_metrics": '{"audience": "For hospitals & health networks", "badge": "Enterprise", "features": ["750+ Care Tokens included", "Full Inpatient & Outpatient Management", "Multi-Facility Unified Analytics", "Dedicated Account Manager & SLA"]}',
	},
]


def run():
	if "erpnext" not in frappe.get_installed_apps():
		frappe.throw(_("ERPNext is required to seed the token catalogue."))

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
				"coverage_metrics": package.get("coverage_metrics") or '{"metric": "routine_transactions", "period": "monthly"}',
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
			"item_group": "CareVerse HMIS"
			if frappe.db.exists("Item Group", "CareVerse HMIS")
			else "Services",
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
