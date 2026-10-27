"""Complimentary Care Tokens on token orders: the first-purchase bonus and the Partner Coupon.

Both are zero-rated lines on the facility's token Sales Order (and so its invoice), marked with
`crm_bonus_type` and `crm_bonus_tokens`. openmeter_mediator grants each type once per facility
when the invoice is paid, separately from the bought tokens. Quantities come from CRM Opt-In
Settings. A facility gets each bonus on one confirmed order only: the first-purchase bonus while it
has no other confirmed token order, the Partner Coupon while no confirmed order carried one.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

BONUS_ITEM = "CV-TOKEN-BONUS"
WELCOME_BONUS = "Welcome Bonus"
PARTNER_COUPON = "Partner Coupon"


def bonus_settings() -> dict[str, int]:
	settings = frappe.get_cached_doc("CRM Opt-In Settings")
	return {
		WELCOME_BONUS: max(cint(settings.get("welcome_bonus_tokens")), 0),
		PARTNER_COUPON: max(cint(settings.get("partner_coupon_tokens")), 0),
	}


def _installed() -> bool:
	return frappe.db.has_column("Sales Order Item", "crm_bonus_type") and frappe.db.exists("Item", BONUS_ITEM)


def _other_confirmed_orders(facility_mfl: str, exclude_order: str | None) -> list[str]:
	filters = {"crm_token_facility_mfl": facility_mfl, "docstatus": 1}
	if exclude_order:
		filters["name"] = ["!=", exclude_order]
	return frappe.get_all("Sales Order", filters=filters, pluck="name", ignore_permissions=True)


def _coupon_network(customer: str, facility_mfl: str) -> str | None:
	"""The Network whose Partner Coupon this customer entered when onboarding the facility."""
	if not frappe.db.has_column("CRM Facility Membership", "partner_coupon"):
		return None
	facilities = frappe.get_all(
		"CRM Pre-Qualified Facility", filters={"mfl_code": facility_mfl}, pluck="name", ignore_permissions=True
	)
	if not facilities:
		return None
	network = frappe.db.get_value(
		"CRM Facility Membership",
		{"parent": ["in", facilities], "customer": customer, "partner_coupon": 1},
		"network",
	)
	return network or None


def eligible_bonuses(customer: str, facility_mfl: str, exclude_order: str | None = None) -> list[dict]:
	"""The complimentary lines a facility's next confirmed token order should carry."""
	facility_mfl = cstr(facility_mfl).strip()
	if not facility_mfl or not _installed():
		return []
	amounts = bonus_settings()
	others = _other_confirmed_orders(facility_mfl, exclude_order)
	lines = []
	if amounts[WELCOME_BONUS] and not others:
		lines.append(
			{
				"type": WELCOME_BONUS,
				"tokens": amounts[WELCOME_BONUS],
				"description": _("First-purchase bonus: {0} complimentary Care Tokens (no charge)").format(
					f"{amounts[WELCOME_BONUS]:,}"
				),
			}
		)
	network = _coupon_network(customer, facility_mfl) if amounts[PARTNER_COUPON] else None
	if network and not (
		others
		and frappe.db.exists(
			"Sales Order Item", {"parent": ["in", others], "crm_bonus_type": PARTNER_COUPON}
		)
	):
		label = frappe.db.get_value("CRM Opt-In Network", network, "display_name") or network
		lines.append(
			{
				"type": PARTNER_COUPON,
				"tokens": amounts[PARTNER_COUPON],
				"description": _("Partner Coupon ({0}): {1} complimentary Care Tokens (no charge)").format(
					label, f"{amounts[PARTNER_COUPON]:,}"
				),
			}
		)
	return lines


def _earns_bonus(package_item: str | None) -> bool:
	"""Bonus tokens come with the Flex packages only, not a Custom amount or a Fixed fee."""
	plan = frappe.db.get_value(
		"CRM Token Package",
		{"parenttype": "CRM Opt-In Settings", "item_code": cstr(package_item).strip()},
		"plan",
	)
	return (plan or "Flex") == "Flex"


def apply_bonus_lines(order) -> list[dict]:
	"""Replace the order's complimentary lines with the ones the facility is eligible for now."""
	if not _installed():
		return []
	order.set("items", [row for row in order.items if not row.get("crm_bonus_type")])
	if not _earns_bonus(order.get("crm_token_package_item")):
		return []
	bonuses = eligible_bonuses(order.customer, order.get("crm_token_facility_mfl"), exclude_order=order.name)
	if not bonuses:
		return []
	item = frappe.db.get_value("Item", BONUS_ITEM, ["item_name", "stock_uom"], as_dict=True)
	delivery_date = order.get("delivery_date") or (order.items[0].delivery_date if order.items else None)
	for bonus in bonuses:
		order.append(
			"items",
			{
				"item_code": BONUS_ITEM,
				"item_name": item.item_name,
				"description": bonus["description"],
				"qty": 1,
				"uom": item.stock_uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": 1,
				"price_list_rate": 0,
				"rate": 0,
				"delivery_date": delivery_date,
				"crm_bonus_type": bonus["type"],
				"crm_bonus_tokens": bonus["tokens"],
			},
		)
	return bonuses
