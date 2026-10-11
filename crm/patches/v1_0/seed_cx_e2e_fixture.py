"""Seed one synthetic Network and token package for end-to-end tests.

Runs only when the site opts in through site_config (`crm_enable_e2e_fixtures`);
without it the patch does nothing. It only creates or reconciles records under
the reserved CX-E2E prefix and never edits other commercial or customer data.
"""

import frappe

FLAG = "crm_enable_e2e_fixtures"
ITEM_CODE = "CX-E2E-TOKEN"
NETWORK_SLUG = "cx-e2e-network"
PARTNER_ID = "909091"
PRICE = 1000


def enabled() -> bool:
	return bool(frappe.conf.get(FLAG))


def execute():
	if not enabled():
		return
	settings = frappe.get_single("CRM Opt-In Settings")
	price_list = (settings.get("token_price_list") or "").strip()
	if not price_list:
		# Without a configured token Price List there is nowhere safe to price the package.
		return
	_ensure_network()
	_ensure_item(price_list)
	_ensure_item_price(price_list)
	_ensure_package(settings)


def _ensure_network():
	if frappe.db.exists("CRM Opt-In Network", NETWORK_SLUG) or frappe.db.exists(
		"CRM Opt-In Network", {"slug": NETWORK_SLUG}
	):
		return
	frappe.get_doc(
		{
			"doctype": "CRM Opt-In Network",
			"slug": NETWORK_SLUG,
			"display_name": "CX E2E Network (synthetic)",
			"partner_id": PARTNER_ID,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)  # SYSTEM-INTERNAL


def _ensure_item(price_list):
	if frappe.db.exists("Item", ITEM_CODE):
		return
	item_group = frappe.db.get_value("Item", {"item_code": ["like", "CV-TOKEN-%"]}, "item_group") or (
		"All Item Groups"
	)
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": ITEM_CODE,
			"item_name": "CX E2E token package (synthetic)",
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_sales_item": 1,
		}
	).insert(ignore_permissions=True)  # SYSTEM-INTERNAL


def _ensure_item_price(price_list):
	if frappe.db.exists("Item Price", {"item_code": ITEM_CODE, "price_list": price_list}):
		return
	frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": ITEM_CODE,
			"price_list": price_list,
			"selling": 1,
			"price_list_rate": PRICE,
		}
	).insert(ignore_permissions=True)  # SYSTEM-INTERNAL


def _ensure_package(settings):
	if any(row.item_code == ITEM_CODE for row in settings.get("token_packages") or []):
		return
	settings.append(
		"token_packages",
		{
			"item_code": ITEM_CODE,
			"display_name": "CX E2E package (synthetic)",
			"token_quantity": 10,
			"billing_period": "Monthly",
			"description": "Synthetic package for end-to-end tests only.",
			"coverage_summary": "Not a real offering.",
			"enabled": 1,
		},
	)
	settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL
