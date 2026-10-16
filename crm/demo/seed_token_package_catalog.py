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
		"display_name": "Free Trial",
		"description": "A complimentary starter package for health posts, dispensaries, and solo clinics to verify facility records and start digital care workflows with zero financial commitment.",
		"coverage_summary": "400 complimentary tokens to test 10 full clinical encounters with zero commitment. Promotional service liability: KES 2,400 (at KES 6.00/token base).",
		"token_quantity": 400,
		"coverage_metrics": '{"audience": "For trialing clinics & new facilities", "badge": "Free Trial • No Commitment", "features": ["400 Care Tokens included", "Covers 10 Full Patient Journeys", "Registration, Consultations & Vitals", "Labs, Prescriptions & Diagnostics", "Diagnostic Imaging & KES 5k Claims", "KES 0 Customer Commitment"]}',
	},
	{
		"item_code": "CV-TOKEN-STARTER",
		"item_name": "Starter Care Operations",
		"rate": 6000,
		"display_name": "Starter",
		"description": "Flexible entry tier for small outpatient clinics, solo doctors, and baseline top-ups.",
		"coverage_summary": "1,000 tokens at KES 6.00/token base rate. Designed for small facilities with ~25 full clinical encounters or ~70 outpatient visits.",
		"token_quantity": 1000,
		"coverage_metrics": '{"audience": "For small OPD clinics & pilots", "badge": "Entry Tier", "features": ["1,000 Care Tokens included", "KES 6.00 per token base rate", "Outpatient Consultations & Vitals", "Prescriptions & Laboratory Orders", "Flexible Top-Ups Allowed"]}',
	},
	{
		"item_code": "CV-TOKEN-GROWTH",
		"item_name": "Growth Care Operations",
		"rate": 15000,
		"display_name": "Growth",
		"description": "Recommended tier for growing outpatient facilities with steady daily patient volume and diagnostics.",
		"coverage_summary": "2,800 tokens (includes 300 bonus tokens • +12% yield). Effective rate KES 5.36/token. Designed for ~70 full clinical encounters or ~200 outpatient visits.",
		"token_quantity": 2800,
		"coverage_metrics": '{"audience": "For active & growing clinics", "badge": "Popular • +12% Bonus", "features": ["2,800 Care Tokens (300 Bonus)", "KES 5.36 per token effective rate", "Multi-Department Workflows", "Diagnostic Imaging & Labs", "Standard SLA Support"]}',
	},
	{
		"item_code": "CV-TOKEN-SCALE",
		"item_name": "Scale Care Operations",
		"rate": 30000,
		"display_name": "Scale",
		"description": "Best-value tier for high-volume outpatient clinics and multi-service hospitals with inpatient beds.",
		"coverage_summary": "6,250 tokens (includes 1,250 bonus tokens • +25% yield). Effective rate KES 4.80/token. Designed for ~156 full clinical encounters or ~440 outpatient visits.",
		"token_quantity": 6250,
		"coverage_metrics": '{"audience": "For high-volume clinics & hospitals", "badge": "Best Value • +25% Bonus", "features": ["6,250 Care Tokens (1,250 Bonus)", "KES 4.80 per token effective rate", "Full Inpatient Admission Support", "Surgical & Medical Procedures", "Priority Commercial Support"]}',
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
	if hasattr(settings, "token_calc_monthly_platform_fee") or frappe.get_meta("CRM Opt-In Settings").has_field("token_calc_monthly_platform_fee"):
		import json

		from crm.api.facility_onboarding import _default_calculator_config

		settings.token_calc_monthly_platform_fee = 500
		settings.token_calc_bill_value_per_token = 750
		settings.token_calc_default_avg_bill = 1500
		settings.token_calc_default_operating_days = 24
		settings.token_calc_parameters_json = json.dumps(_default_calculator_config(), indent=2)
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
	existing_price = frappe.db.get_value(
		"Item Price",
		{"item_code": package["item_code"], "price_list": price_list.name},
		"name",
	)
	if existing_price:
		doc = frappe.get_doc("Item Price", existing_price)
		if doc.price_list_rate != package["rate"]:
			doc.price_list_rate = package["rate"]
			doc.save(ignore_permissions=True)
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
