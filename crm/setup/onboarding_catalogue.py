"""Default Value Express catalogue, extra tokens and landing contacts for new sites.

Fills only what is missing, so values an admin has already set are never changed:
the packages table is seeded only when it is empty, and each setting only when blank
(or 0). It runs once per site, so an admin can still set the extra tokens to 0 later.
Runs on install (``after_install``) and once on existing sites through a patch.

Frappe marks every patch as done when the app is installed, so a new site never runs
the patches that add the Opt-In Settings fields this data lives in. ``after_install``
runs those (idempotent) patches first.
"""

from __future__ import annotations

import frappe

SETTINGS = "CRM Opt-In Settings"
PRICE_LIST = "CRM Token Packages"
CURRENCY = "KES"

FIELD_PATCHES = (
	"crm.patches.v1_0.add_token_catalog_settings",
	"crm.patches.v1_0.add_facility_onboarding_settings",
	# Also seeds the token calculator defaults.
	"crm.patches.v1_0.add_token_calculator_settings",
	# Also creates the complimentary token Item used for the extra tokens.
	"crm.patches.v1_0.add_token_bonus_and_partner_coupon",
)

# Active packages, matching the token pricing guide. Rates are KES, excluding VAT;
# the Custom plan has no list price (its tokens follow the Flex rates).
PACKAGES = [
	{
		"item_code": "CV-TOKEN-STARTER",
		"item_name": "Starter Care Operations",
		"rate": 6000,
		"display_name": "Starter",
		"plan": "Flex",
		"facility_levels": "",
		"token_quantity": 1000,
		"billing_period": "Monthly",
		"description": "Best for small and lower-volume outpatient facilities starting their digital journey.",
		"coverage_summary": "1,000 Care Tokens at KES 6.00 per token. Starter pricing applies to any single purchase of 1,000 to 2,499 tokens.",
		"coverage_metrics": '{"audience": "For small OPD clinics & pilots", "badge": "Entry Tier", "features": ["1,000 Care Tokens", "KES 6.00 per token", "Starter rate for 1,000-2,499 tokens per purchase", "No expiry while your account is active", "Top up any time"]}',
	},
	{
		"item_code": "CV-FIXED-L2",
		"item_name": "Value Express Fixed - Level 2",
		"rate": 15000,
		"display_name": "Value Express Fixed - Level 2",
		"plan": "Fixed",
		"facility_levels": "Level 2",
		"token_quantity": 0,
		"billing_period": "Monthly",
		"description": "One predictable monthly fee for a Level 2 facility, with no token balance to monitor.",
		"coverage_summary": "One predictable monthly fee for a Level 2 facility, with no token balance to monitor.",
		"coverage_metrics": "",
	},
	{
		"item_code": "CV-FIXED-L3",
		"item_name": "Value Express Fixed - Level 3",
		"rate": 18000,
		"display_name": "Value Express Fixed - Level 3",
		"plan": "Fixed",
		"facility_levels": "Level 3\nLevel 3A\nLevel 3B\nLevel 3C",
		"token_quantity": 0,
		"billing_period": "Monthly",
		"description": "One predictable monthly fee for a Level 3 facility, with no token balance to monitor.",
		"coverage_summary": "One predictable monthly fee for a Level 3 facility, with no token balance to monitor.",
		"coverage_metrics": "",
	},
	{
		"item_code": "CV-TOKEN-CUSTOM",
		"item_name": "Value Express Flex - Custom tokens",
		"rate": None,
		"display_name": "Custom",
		"plan": "Custom",
		"facility_levels": "",
		"token_quantity": 1,
		"billing_period": "Monthly",
		"description": "Set your own amount. Tokens are worked out at the rate of the package your amount reaches.",
		"coverage_summary": "Set your own amount. Tokens are worked out at the rate of the package your amount reaches.",
		"coverage_metrics": "",
	},
	{
		"item_code": "VX-GROWTH",
		"item_name": "Growth",
		"rate": 13750,
		"display_name": "Growth",
		"plan": "Flex",
		"facility_levels": "",
		"token_quantity": 2500,
		"billing_period": "Monthly",
		"description": "Best for facilities with increasing patient volumes and higher CareverseHIMS usage.",
		"coverage_summary": "2,500 Care Tokens at KES 5.50 per token. Growth pricing applies to any single purchase of 2,500 to 4,999 tokens.",
		"coverage_metrics": '{"audience": "For active & growing clinics", "badge": "Most popular", "features": ["2,500 Care Tokens", "KES 5.50 per token", "Growth rate for 2,500-4,999 tokens per purchase", "No expiry while your account is active", "Top up any time"]}',
	},
	{
		"item_code": "VX-SCALE",
		"item_name": "Scale",
		"rate": 25000,
		"display_name": "Scale",
		"plan": "Flex",
		"facility_levels": "",
		"token_quantity": 5000,
		"billing_period": "Monthly",
		"description": "Best for facilities with high patient volumes and higher CareverseHIMS usage.",
		"coverage_summary": "5,000 Care Tokens at KES 5.00 per token. Scale pricing applies to any single purchase of 5,000 tokens or more.",
		"coverage_metrics": '{"audience": "For high-volume clinics & hospitals", "badge": "Best Value", "features": ["5,000 Care Tokens", "KES 5.00 per token", "Scale rate for 5,000+ tokens per purchase", "No expiry while your account is active", "Top up any time"]}',
	},
]

DEFAULTS = {
	"token_sales_order_validity_days": 30,
	"token_invoice_due_days": 30,
	"welcome_bonus_tokens": 2500,
	"partner_coupon_tokens": 150,
	"landing_contact_phones": "0111 043 555\n0111 043 566",
	"landing_contact_email": "info@tiberbu.com",
	"landing_contact_hours": "Mon–Fri, 9:00 AM – 5:00 PM EAT",
}


def after_install():
	for patch in FIELD_PATCHES:
		frappe.get_attr(patch + ".execute")()
	ensure_default_catalogue()


def ensure_default_catalogue():
	"""Seed missing onboarding defaults. Safe to run repeatedly."""
	if not frappe.db.exists("DocType", SETTINGS):
		return
	settings = frappe.get_single(SETTINGS)
	meta = frappe.get_meta(SETTINGS)
	changed = False

	for fieldname, value in DEFAULTS.items():
		# A saved form stores empty numbers as 0, so 0 also counts as not set.
		if meta.has_field(fieldname) and not settings.get(fieldname):
			settings.set(fieldname, value)
			changed = True

	changed |= _seed_packages(settings, meta)

	if changed:
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)


def _seed_packages(settings, meta):
	if "erpnext" not in frappe.get_installed_apps() or not meta.has_field("token_packages"):
		return False
	if settings.get("token_packages"):
		return False

	price_list = settings.get("token_price_list") or _ensure_price_list()
	settings.token_price_list = price_list
	for package in PACKAGES:
		_ensure_item(package)
		if package["rate"] is not None:
			_ensure_item_price(package, price_list)
		row = {key: value for key, value in package.items() if key not in ("item_name", "rate")}
		settings.append("token_packages", {**row, "status": "Active", "enabled": 1})
	return True


def _ensure_price_list():
	if not frappe.db.exists("Price List", PRICE_LIST):
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": PRICE_LIST,
				"currency": CURRENCY,
				"selling": 1,
				"buying": 0,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
	return PRICE_LIST


def _ensure_item(package):
	if frappe.db.exists("Item", package["item_code"]):
		return
	item_group = next(
		(group for group in ("CareVerse HMIS", "Services") if frappe.db.exists("Item Group", group)),
		None,
	) or frappe.db.get_value("Item Group", {"is_group": 0}, "name")
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": package["item_code"],
			"item_name": package["item_name"],
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_sales_item": 1,
			"is_stock_item": 0,
			"description": package["description"],
		}
	).insert(ignore_permissions=True)


def _ensure_item_price(package, price_list):
	if frappe.db.exists("Item Price", {"item_code": package["item_code"], "price_list": price_list}):
		return
	frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": package["item_code"],
			"price_list": price_list,
			"price_list_rate": package["rate"],
			"currency": CURRENCY,
			"selling": 1,
			"buying": 0,
			"uom": "Nos",
		}
	).insert(ignore_permissions=True)
