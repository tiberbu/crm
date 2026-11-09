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
		"description": "Best for small and lower-volume outpatient facilities starting their digital journey.",
		"coverage_summary": "1,000 Care Tokens at KES 6.00 per token. Starter pricing applies to any single purchase of 1,000 to 2,499 tokens.",
		"token_quantity": 1000,
		"coverage_metrics": '{"audience": "For small OPD clinics & pilots", "badge": "Entry Tier", "features": ["1,000 Care Tokens", "KES 6.00 per token", "Starter rate for 1,000-2,499 tokens per purchase", "No expiry while your account is active", "Top up any time"]}',
	},
	{
		"item_code": "CV-TOKEN-GROWTH",
		"item_name": "Growth Care Operations",
		"rate": 13750,
		"display_name": "Growth",
		"description": "Best for facilities with increasing patient volumes and higher CareverseHIMS usage.",
		"coverage_summary": "2,500 Care Tokens at KES 5.50 per token. Growth pricing applies to any single purchase of 2,500 to 4,999 tokens.",
		"token_quantity": 2500,
		"coverage_metrics": '{"audience": "For active & growing clinics", "badge": "Most popular", "features": ["2,500 Care Tokens", "KES 5.50 per token", "Growth rate for 2,500-4,999 tokens per purchase", "No expiry while your account is active", "Top up any time"]}',
	},
	{
		"item_code": "CV-TOKEN-SCALE",
		"item_name": "Scale Care Operations",
		"rate": 25000,
		"display_name": "Scale",
		"description": "Best for facilities with high patient volumes and higher CareverseHIMS usage.",
		"coverage_summary": "5,000 Care Tokens at KES 5.00 per token. Scale pricing applies to any single purchase of 5,000 tokens or more.",
		"token_quantity": 5000,
		"coverage_metrics": '{"audience": "For high-volume clinics & hospitals", "badge": "Best Value", "features": ["5,000 Care Tokens", "KES 5.00 per token", "Scale rate for 5,000+ tokens per purchase", "No expiry while your account is active", "Top up any time"]}',
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


# Value Express Fixed (monthly, by facility level, no tokens) and Custom (any amount at the Flex rates).
VALUE_EXPRESS_PACKAGES = [
	{
		"item_code": "CV-FIXED-L2",
		"item_name": "Value Express Fixed - Level 2",
		"rate": 15000,
		"plan": "Fixed",
		"facility_levels": "Level 2",
		"token_quantity": 0,
		"display_name": "Value Express Fixed - Level 2",
		"description": "One predictable monthly fee for a Level 2 facility, with no token balance to monitor.",
	},
	{
		"item_code": "CV-FIXED-L3",
		"item_name": "Value Express Fixed - Level 3",
		"rate": 18000,
		"plan": "Fixed",
		"facility_levels": "Level 3\nLevel 3A\nLevel 3B\nLevel 3C",
		"token_quantity": 0,
		"display_name": "Value Express Fixed - Level 3",
		"description": "One predictable monthly fee for a Level 3 facility, with no token balance to monitor.",
	},
	{
		"item_code": "CV-TOKEN-CUSTOM",
		"item_name": "Value Express Flex - Custom tokens",
		"rate": None,
		"plan": "Custom",
		"facility_levels": "",
		"token_quantity": 1,
		"display_name": "Custom",
		"description": "Set your own amount. Tokens are worked out at the rate of the package your amount reaches.",
	},
]


# Datasheet wording for the Flex cards (dev sites; production text is maintained in settings).
FLEX_DESCRIPTIONS = {
	"CV-TOKEN-STARTER": "Best for small and lower-volume outpatient facilities starting their digital journey.",
	"CV-TOKEN-GROWTH": "Best for facilities with increasing patient volumes and higher CareverseHIMS usage.",
	"CV-TOKEN-SCALE": "Best for facilities with high patient volumes and higher CareverseHIMS usage.",
}


def run_value_express():
	"""Add or update the Fixed and Custom rows without touching the Flex packages.

	bench --site <dev site> execute "crm.demo.seed_token_package_catalog.run_value_express"
	"""
	if "erpnext" not in frappe.get_installed_apps():
		frappe.throw(_("ERPNext is required to seed the token catalogue."))
	settings = frappe.get_single("CRM Opt-In Settings")
	price_list = frappe.get_doc("Price List", settings.token_price_list or _ensure_price_list().name)
	for package in VALUE_EXPRESS_PACKAGES:
		_ensure_item(package)
		if package["rate"] is not None:
			_ensure_item_price(package, price_list)
		values = {
			key: package[key] for key in ("display_name", "plan", "facility_levels", "token_quantity", "description")
		}
		values.update(billing_period="Monthly", coverage_summary=package["description"], enabled=1)
		row = next((r for r in settings.token_packages if r.item_code == package["item_code"]), None)
		if row:
			row.update(values)
		else:
			settings.append("token_packages", {"item_code": package["item_code"], **values})
	for row in settings.token_packages:
		if row.item_code in FLEX_DESCRIPTIONS:
			row.description = FLEX_DESCRIPTIONS[row.item_code]
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	return [row.item_code for row in settings.token_packages if row.plan != "Flex"]
