"""Seed one default coupon per existing network and backfill coupon redemptions.

Idempotent and safe to re-run.

Seeding: for every network with a ``partner_id`` (excluding the default onboarding network) that has
no coupon yet, create a flat coupon carrying the current global ``partner_coupon_tokens`` value, with
no limits and no window. When the global is 0, nothing is seeded (coupon off), matching today.

Backfill: every confirmed order line already stamped ``Partner Coupon`` gets a
``CRM Coupon Redemption`` so the deprecated global setting no longer governs it, and the coupon's
``redeemed_count`` is kept correct. The global ``partner_coupon_tokens`` is not removed.
"""

import frappe
from frappe.utils import cint, cstr


def execute():
	_seed_network_coupons()
	_backfill_redemptions()


def _seed_network_coupons():
	settings = frappe.get_cached_doc("CRM Opt-In Settings")
	amount = cint(settings.get("partner_coupon_tokens"))
	if amount <= 0:
		return
	default_id = cstr(settings.get("facility_onboarding_default_partner_id") or "").strip()

	networks = frappe.get_all(
		"CRM Opt-In Network",
		filters={"partner_id": ["is", "set"]},
		fields=["name", "display_name", "partner_id"],
		ignore_permissions=True,
	)
	for net in networks:
		if net.partner_id == default_id:
			continue
		if frappe.db.exists("CRM Coupon", {"network": net.name}):
			continue
		frappe.get_doc(
			{
				"doctype": "CRM Coupon",
				"coupon_title": "{} coupon".format(net.display_name or net.name),
				"network": net.name,
				"value_type": "flat_tokens",
				"value": amount,
				"max_tokens": 0,
				"max_redemptions": 0,
				"status": "Active",
			}
		).insert(ignore_permissions=True)


def _backfill_redemptions():
	items = frappe.get_all(
		"Sales Order Item",
		filters={"crm_bonus_type": "Partner Coupon"},
		fields=["name", "parent", "crm_bonus_tokens"],
		ignore_permissions=True,
	)
	ledger_available = frappe.db.exists("DocType", "OpenMeter Grant")
	for item in items:
		order = frappe.db.get_value(
			"Sales Order",
			item.parent,
			["docstatus", "crm_token_facility_mfl", "crm_token_facility_fid", "customer", "creation"],
			as_dict=True,
		)
		if not order or cint(order.docstatus) != 1:
			continue
		mfl = cstr(order.crm_token_facility_mfl or "").strip()
		if not mfl:
			continue
		# Already covered (a live redemption holds the facility, or this order already has one).
		if frappe.db.exists("CRM Coupon Redemption", {"facility_guard": mfl}):
			continue
		if frappe.db.exists("CRM Coupon Redemption", {"sales_order": item.parent}):
			continue

		fid = cstr(order.crm_token_facility_fid or "").strip()
		network = _coupon_network(order.customer, mfl)
		coupon = frappe.db.get_value("CRM Coupon", {"network": network}, "name") if network else None

		granted = False
		if coupon is not None and ledger_available and fid:
			granted = frappe.db.get_value("OpenMeter Grant", "coupon:{}".format(fid), "status") == "Granted"
		status = "Granted" if granted else "Reserved"

		frappe.get_doc(
			{
				"doctype": "CRM Coupon Redemption",
				"coupon": coupon,
				"network": network,
				"bonus_type": "Partner Coupon",
				"facility_mfl": mfl,
				"facility_fid": fid or None,
				"customer": order.customer,
				"sales_order": item.parent,
				"status": status,
				"tokens_awarded": cint(item.crm_bonus_tokens),
				"redeemed_on": order.creation,
				"granted_on": order.creation if granted else None,
				"ledger_key": "coupon:{}".format(fid) if fid else None,
				"status_reason": "Backfilled from an existing order",
			}
		).insert(ignore_permissions=True)

		if coupon:
			frappe.db.set_value(
				"CRM Coupon",
				coupon,
				"redeemed_count",
				cint(frappe.db.get_value("CRM Coupon", coupon, "redeemed_count")) + 1,
				update_modified=False,
			)
			if status == "Reserved":
				frappe.db.set_value("Sales Order Item", item.name, "crm_coupon", coupon)
				invoice_items = frappe.get_all(
					"Sales Invoice Item",
					filters={"so_detail": item.name},
					pluck="name",
					ignore_permissions=True,
				)
				for invoice_item in invoice_items:
					frappe.db.set_value("Sales Invoice Item", invoice_item, "crm_coupon", coupon)


def _coupon_network(customer, facility_mfl):
	from crm.utils.token_bonus import _coupon_network as _resolve

	return _resolve(customer, facility_mfl)
