"""Settings › Packages: Sales Managers run the Value Express package catalogue.

The catalogue is the `token_packages` table of CRM Opt-In Settings; each package's price is
its Item Price on the token selling Price List. Every call changes one package and carries
the settings version it was read at, so two people editing never overwrite each other.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from crm.api.optin_admin import _is_admin
from crm.utils import value_express as vx

SETTINGS = "CRM Opt-In Settings"
DEFAULT_ITEM_GROUP = "Services"


def _require_package_manager():
	if not _is_admin():
		frappe.throw(_("Only Sales Managers can change the package catalogue."), frappe.PermissionError)


def _settings(version: Any = None):
	settings = frappe.get_doc(SETTINGS)
	if version is not None and cstr(version) != cstr(settings.modified):
		frappe.throw(
			_("Someone else changed the packages since you opened them. Reload and try again."),
			frappe.TimestampMismatchError,
		)
	return settings


def _price_list(settings) -> str:
	return cstr(settings.get("token_price_list")).strip()


def _prices(price_list: str, items: list[str]) -> dict[str, dict]:
	if not price_list or not items:
		return {}
	rows = frappe.get_all(
		"Item Price",
		filters={"price_list": price_list, "item_code": ("in", items), "selling": 1},
		fields=["item_code", "price_list_rate", "currency"],
		order_by="modified desc",
	)
	prices: dict[str, dict] = {}
	for row in rows:
		prices.setdefault(row.item_code, row)
	return prices


def _sold_orders(items: list[str]) -> dict[str, int]:
	"""How many live Quotations and Sales Orders sell each item: their tokens are fixed once sold."""
	if not items:
		return {}
	counts: dict[str, int] = {}
	for doctype in ("Sales Order", "Quotation"):
		for row in frappe.get_all(
			f"{doctype} Item",
			filters={"item_code": ("in", items), "docstatus": ("<", 2)},
			fields=["item_code", "count(distinct parent) as orders"],
			group_by="item_code",
		):
			counts[row.item_code] = counts.get(row.item_code, 0) + cint(row.orders)
	return counts


def _metrics(row) -> dict:
	try:
		value = json.loads(row.get("coverage_metrics") or "{}")
	except (TypeError, ValueError):
		value = {}
	return value if isinstance(value, dict) else {}


def _row_view(row, prices: dict, sold: dict, currency: str) -> dict:
	metrics = _metrics(row)
	price = prices.get(row.item_code) or {}
	return {
		"row_name": row.name,
		"item_code": row.item_code,
		"item_name": frappe.db.get_value("Item", row.item_code, "item_name") or row.item_code,
		"display_name": cstr(row.display_name),
		"plan": vx.plan_of(row),
		"status": vx.status_of(row),
		"billing_period": cstr(row.billing_period) or "Monthly",
		"token_quantity": cint(row.token_quantity),
		"price": flt(price.get("price_list_rate")),
		"currency": cstr(price.get("currency")) or currency,
		"facility_levels": vx.levels_of(row),
		"description": cstr(row.description),
		"coverage_summary": cstr(row.coverage_summary),
		"journeys": cstr(metrics.get("journeys")),
		"popular": "popular" in cstr(metrics.get("badge")).lower(),
		"discontinued_on": cstr(row.get("discontinued_on")),
		"sold_orders": sold.get(row.item_code, 0),
	}


@frappe.whitelist()
def get_package_catalogue():
	_require_package_manager()
	settings = _settings()
	price_list = _price_list(settings)
	currency = (frappe.db.get_value("Price List", price_list, "currency") if price_list else "") or "KES"
	rows = settings.get("token_packages") or []
	items = [row.item_code for row in rows if row.item_code]
	prices, sold = _prices(price_list, items), _sold_orders(items)
	allowed = cstr(settings.get("self_onboarding_allowed_facility_levels"))
	return {
		"version": cstr(settings.modified),
		"price_list": price_list,
		"currency": currency,
		"periods": list(vx.PERIOD_MONTHS),
		"level_suggestions": [line.strip() for line in allowed.splitlines() if line.strip()],
		"packages": [_row_view(row, prices, sold, currency) for row in rows],
	}


def _candidate_rows(settings, prices: dict) -> list[dict]:
	return [
		{
			"row_name": row.name,
			"item_code": row.item_code,
			"display_name": row.display_name,
			"plan": vx.plan_of(row),
			"status": vx.status_of(row),
			"token_quantity": cint(row.token_quantity),
			"facility_levels": row.facility_levels,
			"billing_period": row.billing_period,
			"price": flt((prices.get(row.item_code) or {}).get("price_list_rate")),
		}
		for row in settings.get("token_packages") or []
	]


def _check_catalogue(rows: list[dict]):
	errors = vx.validate_catalogue(rows)
	if errors:
		frappe.throw("<br>".join(frappe.utils.escape_html(error) for error in errors), title=_("Cannot save the package"))


def _new_item_code(display_name: str) -> str:
	base = "VX-" + (re.sub(r"[^A-Z0-9]+", "-", display_name.upper()).strip("-") or "PACKAGE")
	code, n = base[:120], 2
	while frappe.db.exists("Item", code):
		code, n = f"{base[:115]}-{n}", n + 1
	return code


def _create_item(display_name: str, description: str, settings) -> str:
	"""A non-stock sales item for a new package, grouped like the packages already on sale."""
	template = next((row.item_code for row in settings.get("token_packages") or [] if row.item_code), None)
	group, uom = (
		frappe.db.get_value("Item", template, ["item_group", "stock_uom"]) if template else (None, None)
	) or (None, None)
	code = _new_item_code(display_name)
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": display_name[:140],
			"item_group": group or DEFAULT_ITEM_GROUP,
			"stock_uom": uom or "Nos",
			"is_sales_item": 1,
			"is_stock_item": 0,
			"include_item_in_manufacturing": 0,
			"description": description or display_name,
		}
	).insert(ignore_permissions=True)  # SYSTEM-INTERNAL: guarded by _require_package_manager
	return code


def _set_price(item_code: str, price_list: str, rate: float):
	name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list, "selling": 1}, "name")
	if name:
		doc = frappe.get_doc("Item Price", name)
		if flt(doc.price_list_rate) == flt(rate):
			return
		doc.price_list_rate = rate
		doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL: guarded by _require_package_manager
		return
	frappe.get_doc(
		{"doctype": "Item Price", "item_code": item_code, "price_list": price_list, "price_list_rate": rate, "selling": 1}
	).insert(ignore_permissions=True)  # SYSTEM-INTERNAL: guarded by _require_package_manager


def _audit(settings, message: str):
	settings.add_comment("Info", message)


@frappe.whitelist(methods=["POST"])
def save_package(package: Any, version: Any = None):
	"""Create or edit one package, its item and its price; returns the refreshed catalogue."""
	_require_package_manager()
	package = frappe.parse_json(package) if isinstance(package, str) else (package or {})
	settings = _settings(version)
	price_list = _price_list(settings)
	if not price_list:
		frappe.throw(_("Set the token selling Price List in Settings › Opt-In Process first."))

	row_name = cstr(package.get("row_name")).strip()
	row = next((r for r in settings.get("token_packages") or [] if r.name == row_name), None) if row_name else None
	if row_name and not row:
		frappe.throw(_("That package no longer exists. Reload and try again."))
	if row and vx.status_of(row) == vx.DISCONTINUED:
		frappe.throw(_("A discontinued package is kept for history. Duplicate it to sell it again."))

	plan = cstr(package.get("plan") or "Flex").strip()
	if plan not in (vx.FLEX, vx.FIXED, vx.CUSTOM):
		frappe.throw(_("Choose Flex, Fixed or Custom as the plan."))
	display_name = cstr(package.get("display_name")).strip()
	description = cstr(package.get("description")).strip()
	if not display_name or not description:
		frappe.throw(_("Each package needs a name and a description."))
	tokens = 1 if plan == vx.CUSTOM else max(0, cint(package.get("token_quantity")))
	if plan == vx.FIXED:
		tokens = 0
	price = flt(package.get("price"), 2)
	if price < 0:
		frappe.throw(_("The price cannot be negative."))
	period = cstr(package.get("billing_period") or "Monthly").strip()
	levels = package.get("facility_levels") or []
	levels_text = "\n".join(vx.levels_of({"facility_levels": levels})) if plan == vx.FIXED else ""
	item_code = cstr(package.get("item_code")).strip()

	if row:
		sold = _sold_orders([row.item_code]).get(row.item_code, 0)
		changed = (item_code and item_code != row.item_code) or plan != vx.plan_of(row) or tokens != cint(row.token_quantity)
		if sold and changed:
			frappe.throw(
				_(
					"{0} is on {1} orders, so its item, plan and tokens are fixed. Duplicate it to sell a different package."
				).format(row.display_name, sold)
			)
		item_code = item_code or row.item_code
	elif item_code:
		item = frappe.db.get_value("Item", item_code, ["disabled", "is_sales_item"], as_dict=True)
		if not item or item.disabled or not item.is_sales_item:
			frappe.throw(_("Item {0} must be an enabled sales item.").format(item_code))

	rows = _candidate_rows(settings, _prices(price_list, [r.item_code for r in settings.get("token_packages") or []]))
	candidate = {
		"row_name": row_name or "__new__",
		"item_code": item_code or "__new__",
		"display_name": display_name,
		"plan": plan,
		"status": vx.status_of(row) if row else (cstr(package.get("status")) or vx.ACTIVE),
		"token_quantity": tokens,
		"facility_levels": levels_text,
		"billing_period": period,
		"price": price,
	}
	if candidate["status"] not in (vx.ACTIVE, vx.DISABLED):
		frappe.throw(_("A new package is either Active or Disabled."))
	rows = [candidate if r["row_name"] == row_name else r for r in rows] if row else rows + [candidate]
	_check_catalogue(rows)

	if not item_code:
		item_code = _create_item(display_name, description, settings)
	if plan != vx.CUSTOM or price:
		_set_price(item_code, price_list, price)

	if not row:
		row = settings.append("token_packages", {"status": candidate["status"]})
	metrics = _metrics(row)
	journeys = cstr(package.get("journeys")).strip()
	metrics.pop("journeys", None)
	if journeys:
		metrics["journeys"] = journeys
	badge = cstr(metrics.get("badge"))
	if package.get("popular"):
		metrics["badge"] = badge if "popular" in badge.lower() else "Most popular"
	elif "popular" in badge.lower():
		metrics.pop("badge")
	row.update(
		{
			"item_code": item_code,
			"display_name": display_name,
			"plan": plan,
			"facility_levels": levels_text,
			"token_quantity": tokens,
			"billing_period": period,
			"description": description,
			"coverage_summary": cstr(package.get("coverage_summary")).strip() or description,
			"coverage_metrics": json.dumps(metrics) if metrics else "",
		}
	)
	_audit(settings, _("Package {0} saved ({1}, {2})").format(display_name, plan, row.status or vx.ACTIVE))
	settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL: guarded by _require_package_manager
	return get_package_catalogue()


@frappe.whitelist(methods=["POST"])
def set_package_status(row_name: Any, status: Any, version: Any = None):
	"""Disable (hide, reversible), enable, or discontinue (final) one package."""
	_require_package_manager()
	settings = _settings(version)
	status = cstr(status).strip()
	if status not in (vx.ACTIVE, vx.DISABLED, vx.DISCONTINUED):
		frappe.throw(_("Choose Active, Disabled or Discontinued."))
	row = next((r for r in settings.get("token_packages") or [] if r.name == cstr(row_name)), None)
	if not row:
		frappe.throw(_("That package no longer exists. Reload and try again."))
	if vx.status_of(row) == vx.DISCONTINUED:
		frappe.throw(_("A discontinued package is kept for history. Duplicate it to sell it again."))
	rows = _candidate_rows(settings, _prices(_price_list(settings), [r.item_code for r in settings.get("token_packages") or []]))
	for candidate in rows:
		if candidate["row_name"] == row.name:
			candidate["status"] = status
	_check_catalogue(rows)
	row.status = status
	row.discontinued_on = frappe.utils.today() if status == vx.DISCONTINUED else None
	_audit(settings, _("Package {0} set to {1}").format(row.display_name, status))
	settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL: guarded by _require_package_manager
	return get_package_catalogue()


@frappe.whitelist(methods=["POST"])
def move_package(row_name: Any, direction: Any, version: Any = None, visible: Any = None):
	"""Move a package one place up or down among the packages of its plan: cards follow this order.

	`visible` lists the packages the user is looking at, so it passes the hidden ones (say,
	disabled packages under the Active filter) and always moves one card along.
	"""
	_require_package_manager()
	settings = _settings(version)
	rows = list(settings.get("token_packages") or [])
	index = next((i for i, r in enumerate(rows) if r.name == cstr(row_name)), None)
	if index is None:
		frappe.throw(_("That package no longer exists. Reload and try again."))
	visible = set(frappe.parse_json(visible) if isinstance(visible, str) else visible or [r.name for r in rows])
	plan, step = vx.plan_of(rows[index]), -1 if cstr(direction) == "up" else 1
	other = index + step
	while 0 <= other < len(rows) and (vx.plan_of(rows[other]) != plan or rows[other].name not in visible):
		other += step
	if not 0 <= other < len(rows):
		return get_package_catalogue()
	rows[index], rows[other] = rows[other], rows[index]
	for idx, row in enumerate(rows, start=1):
		row.idx = idx
	settings.set("token_packages", rows)
	settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL: guarded by _require_package_manager
	return get_package_catalogue()
