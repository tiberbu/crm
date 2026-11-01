"""Complimentary Care Tokens on token orders: the first-purchase bonus and the Partner Coupon.

Both are zero-rated lines on the facility's token Sales Order (and so its invoice), marked with
`crm_bonus_type` and `crm_bonus_tokens`. openmeter_mediator grants each type once per facility
when the invoice is paid, separately from the bought tokens. Quantities come from CRM Opt-In
Settings. A facility gets each bonus on one confirmed order only: the first-purchase bonus while it
has no other confirmed token order, the Partner Coupon while no confirmed order carried one.

The welcome bonus can also go out before any payment (P-76): an admin dispenses it from the
Deal's Metering tab, or CRM Opt-In Settings auto-assigns it when the facility selects a package.
openmeter_mediator keeps one `welcome:<FID>` grant per facility for all three paths, so once it is
out, later orders carry no welcome line and the first paid invoice grants only the package.
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


def _hook(name: str):
	methods = frappe.get_hooks(name)
	return frappe.get_attr(methods[-1]) if methods else None


def auto_dispense_enabled() -> bool:
	return bool(cint(frappe.get_cached_doc("CRM Opt-In Settings").get("auto_dispense_welcome_bonus")))


def welcome_bonus_status(facility_fid: str | None) -> dict:
	"""The metering app's record of this facility's welcome bonus; never dispensed without one."""
	facility_fid = cstr(facility_fid).strip()
	method = _hook("crm_welcome_bonus_status")
	if not (method and facility_fid):
		return {"fid": facility_fid, "dispensed": False, "status": None, "available": bool(method)}
	return {**(method(facility_fid) or {}), "fid": facility_fid, "available": True}


def dispense_welcome_bonus(facility_fid: str, source_doctype: str | None = None, source_name: str | None = None) -> dict:
	"""Grant the facility's welcome bonus now. The metering app grants it at most once per facility."""
	method = _hook("crm_dispense_welcome_bonus")
	if not method:
		frappe.throw(_("No metering app is installed on this site."))
	facility_fid = cstr(facility_fid).strip()
	outcome = method(facility_fid, bonus_settings()[WELCOME_BONUS], source_doctype=source_doctype, source_name=source_name)
	if outcome.get("dispensed"):
		drop_welcome_lines_from_drafts(facility_fid)
	return outcome


def drop_welcome_lines_from_drafts(facility_fid: str) -> list[str]:
	"""Take the welcome line off the facility's unconfirmed orders once the bonus is out.

	The client reviews a draft before confirming it, so the review must not promise a bonus the
	facility already has. Confirmed orders keep their lines; the payment grants only the package.
	"""
	if not (facility_fid and frappe.db.has_column("Sales Order", "crm_token_facility_fid") and _installed()):
		return []
	drafts = frappe.get_all(
		"Sales Order",
		filters={"crm_token_facility_fid": facility_fid, "docstatus": 0},
		pluck="name",
		ignore_permissions=True,
	)
	changed = []
	for name in drafts:
		order = frappe.get_doc("Sales Order", name)
		rows = [row for row in order.items if row.get("crm_bonus_type") != WELCOME_BONUS]
		if len(rows) == len(order.items):
			continue
		order.set("items", rows)
		order.save(ignore_permissions=True)  # SYSTEM-INTERNAL: removes a zero-rated line only
		changed.append(name)
	return changed


def _order_fid(order) -> str:
	from crm.utils.token_facility import facility_fid_for_mfl

	return cstr(order.get("crm_token_facility_fid")).strip() or facility_fid_for_mfl(order.get("crm_token_facility_mfl"))


def auto_dispense_on_package_selection(doc, method=None):
	"""Sales Order hook: with auto-assign on, a Flex package selection releases the welcome bonus."""
	if not (doc.get("crm_token_package_item") and doc.get("crm_token_facility_mfl")):
		return
	if not (auto_dispense_enabled() and bonus_settings()[WELCOME_BONUS] and _hook("crm_dispense_welcome_bonus")):
		return
	if not _earns_bonus(doc.get("crm_token_package_item")):
		return
	frappe.enqueue(
		"crm.utils.token_bonus.auto_dispense_job",
		queue="short",
		enqueue_after_commit=True,
		sales_order=doc.name,
	)


def auto_dispense_job(sales_order: str):
	order = frappe.get_doc("Sales Order", sales_order)
	if order.docstatus == 2 or not auto_dispense_enabled():
		return
	fid = _order_fid(order)
	if not fid or welcome_bonus_status(fid).get("dispensed"):
		return
	outcome = dispense_welcome_bonus(fid, "Sales Order", order.name)
	if not outcome.get("dispensed"):
		# The first paid invoice still carries the bonus, and an admin can dispense it by hand.
		frappe.log_error(
			title=f"Welcome bonus not auto-assigned for {fid}",
			message=frappe.as_json({"sales_order": order.name, **outcome}),
			reference_doctype="Sales Order",
			reference_name=order.name,
		)


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


def eligible_bonuses(
	customer: str, facility_mfl: str, exclude_order: str | None = None, facility_fid: str | None = None
) -> list[dict]:
	"""The complimentary lines a facility's next confirmed token order should carry."""
	facility_mfl = cstr(facility_mfl).strip()
	if not facility_mfl or not _installed():
		return []
	amounts = bonus_settings()
	others = _other_confirmed_orders(facility_mfl, exclude_order)
	lines = []
	if not facility_fid:
		from crm.utils.token_facility import facility_fid_for_mfl

		facility_fid = facility_fid_for_mfl(facility_mfl)
	# Already dispensed (admin button or auto-assign): the paid order grants the package only.
	if amounts[WELCOME_BONUS] and not others and not welcome_bonus_status(facility_fid).get("dispensed"):
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
	bonuses = eligible_bonuses(
		order.customer,
		order.get("crm_token_facility_mfl"),
		exclude_order=order.name,
		facility_fid=cstr(order.get("crm_token_facility_fid")).strip() or None,
	)
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
