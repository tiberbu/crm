"""Synthetic fixture for the coupon level-rewards journey (e2e/metering/coupon_level_rewards.spec.ts).

Run explicitly on a CRM site with openmeter_mediator (OpenMeter itself may be off):

    bench --site <site> execute crm.tests.e2e_coupon_level_fixture.setup \
        --kwargs '{"run_id": "0001", "admin_password": "...", "owner_password": "..."}'
    # after the journey has reviewed the draft orders:
    bench --site <site> execute crm.tests.e2e_coupon_level_fixture.confirm_orders --kwargs '{"run_id": "0001"}'
    # when done:
    bench --site <site> execute crm.tests.e2e_coupon_level_fixture.teardown --kwargs '{"run_id": "0001"}'

Each run adds a synthetic partner network with one **Both** coupon rewarded by facility level
(Level 2: 1,000 tokens / 10% off Fixed; Level 3B: 1,800 tokens / 4% off Fixed; Level 4: 2,500
tokens; every other level: nothing), and four facilities of the synthetic E2E customer that entered
that network's Partner Coupon, each with its draft Express order: Level 2 Flex, Level 4 Flex,
Level 2 Fixed and Level 3B Fixed (the catalogue's Fixed fees exist for Levels 2 and 3x).
``confirm_orders`` confirms the Level 4 Flex and Level 3B Fixed orders (claiming the coupon),
invoices the Flex one without paying it, and reports what the metering app's grant check would
grant from that invoice. ``teardown`` revokes the run's coupons and disables its network.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, nowdate

from crm.tests.e2e_coupon_plan_fixture import ADMIN_EMAIL, COUPON_ADMIN_EMAIL, FIXED_ITEM, FLEX_ITEM

FIXED_L3_ITEM = "CV-FIXED-L3"
LEVEL_REWARDS = [
	{"facility_level": "Level 2", "flex_value": 1000, "fixed_discount_percent": 10},
	{"facility_level": "Level 3B", "flex_value": 1800, "fixed_discount_percent": 4},
	{"facility_level": "Level 4", "flex_value": 2500, "fixed_discount_percent": 0},
]
FACILITIES = {
	# key: (MFL/FID tag, level, plan, item)
	"l2_flex": ("LF2", "Level 2", "Flex", FLEX_ITEM),
	"l4_flex": ("LF4", "Level 4", "Flex", FLEX_ITEM),
	"l2_fixed": ("LX2", "Level 2", "Fixed", FIXED_ITEM),
	"l3b_fixed": ("LX3", "Level 3B", "Fixed", FIXED_L3_ITEM),
}


def _ids(run_id: str) -> dict:
	run_id = frappe.utils.cstr(run_id).strip()
	if not run_id.isalnum():
		frappe.throw("run_id must be alphanumeric")
	digits = "".join(ch for ch in run_id if ch.isdigit()) or "1"
	ids = {"run": run_id, "slug": f"e2e-clr-{run_id.lower()}", "partner_id": ("7" + digits.zfill(5))[-6:]}
	for key, (tag, *_rest) in FACILITIES.items():
		ids[f"{key}_mfl"] = f"E2E-{tag}{run_id}"
		ids[f"{key}_fid"] = f"FID-00-E2E{tag}-{run_id}"
	return ids


def coupon_titles(run_id: str) -> tuple[str, str]:
	"""The fixture's coupon and the one the journey creates in the dialog."""
	run = _ids(run_id)["run"]
	return (f"E2E by level {run}", f"E2E levels in dialog {run}")


def _facility(mfl, fid, name, level, network, customer, owner_email):
	frappe.get_doc(
		{
			"doctype": "CRM Pre-Qualified Facility",
			"mfl_code": mfl,
			"facility_name": name,
			"keph_level": level,
			"hfr_facility_id": fid,
			"memberships": [
				{
					"network": network,
					"status": "Active",
					"customer": customer,
					"contact_name": "E2E Facility Owner",
					"contact_email": owner_email,
					"contact_phone": "+254700000000",
					"partner_coupon": 1,
				}
			],
		}
	).insert(ignore_permissions=True)


def setup(run_id: str, admin_password: str, owner_password: str) -> dict:
	from openmeter_mediator.services.sites import ensure_site_for_fid
	from openmeter_mediator.tests import e2e_fixture as base

	from crm.api.customer_experience import create_express_draft_order
	from crm.api.facility_onboarding import _order_package

	ids = _ids(run_id)
	customer = base._ensure_customer()
	base._ensure_user(base.OWNER_EMAIL, "E2E Facility Owner", owner_password, user_type="Website User")
	if not frappe.db.exists("User Permission", {"user": base.OWNER_EMAIL, "allow": "Customer", "for_value": customer}):
		frappe.get_doc(
			{"doctype": "User Permission", "user": base.OWNER_EMAIL, "allow": "Customer", "for_value": customer}
		).insert(ignore_permissions=True)
	base._ensure_user(ADMIN_EMAIL, "E2E Metering Admin", admin_password, roles=("OpenMeter Admin", "Sales Manager"))
	base._ensure_user(COUPON_ADMIN_EMAIL, "E2E Coupon Admin", admin_password, roles=("System Manager", "Sales Manager"))

	network_name = f"E2E Coupon Level Network {ids['run']} (synthetic)"
	network = frappe.get_doc(
		{"doctype": "CRM Opt-In Network", "slug": ids["slug"], "display_name": network_name,
		 "partner_id": ids["partner_id"], "enabled": 1}
	).insert(ignore_permissions=True).name
	coupon = frappe.get_doc(
		{
			"doctype": "CRM Coupon",
			"coupon_title": coupon_titles(run_id)[0],
			"network": network,
			"applies_to": "Both",
			"value_type": "flat_tokens",
			"value": 0,
			"fixed_discount_percent": 0,
			"reward_by_level": 1,
			"level_rewards": [dict(row) for row in LEVEL_REWARDS],
			"valid_from": nowdate(),
			"status": "Active",
		}
	).insert(ignore_permissions=True).name

	for key, (_tag, level, plan, _item) in FACILITIES.items():
		_facility(ids[f"{key}_mfl"], ids[f"{key}_fid"], f"E2E {level} {plan} Clinic {ids['run']} (synthetic)", level,
			network, customer, base.OWNER_EMAIL)
		site = ensure_site_for_fid(ids[f"{key}_fid"])
		frappe.db.set_value("OpenMeter Site", site.name, "status", "Active")
	frappe.db.set_value("Customer", customer, "tax_id", "")
	frappe.db.commit()

	orders = {}
	for key, (_tag, _level, plan, item) in FACILITIES.items():
		orders[key] = create_express_draft_order(
			customer, ids[f"{key}_mfl"], _order_package({"plan": plan, "item_code": item})
		)["data"]["sales_order"]
	frappe.db.commit()

	stamped = {}
	for key, name in orders.items():
		order = frappe.get_doc("Sales Order", name)
		stamped[key] = {
			"coupon_tokens": sum(
				int(row.crm_bonus_tokens or 0) for row in order.items if row.get("crm_bonus_type") == "Partner Coupon"
			),
			"discount_percent": max([flt(row.discount_percentage) for row in order.items] or [0]),
		}
	return {
		**ids,
		"network": network,
		"network_name": network_name,
		"coupon": coupon,
		"customer": customer,
		"orders": orders,
		"stamped": stamped,
		"owner": base.OWNER_EMAIL,
		"coupon_admin": COUPON_ADMIN_EMAIL,
	}


def confirm_orders(run_id: str) -> dict:
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
	from openmeter_mediator.services import grants

	from crm.utils import coupons

	ids = _ids(run_id)
	result = {}
	for key in ("l4_flex", "l3b_fixed"):
		_tag, _level, _plan, item = FACILITIES[key]
		order = frappe.get_doc(
			"Sales Order", {"crm_token_facility_mfl": ids[f"{key}_mfl"], "crm_token_package_item": item, "docstatus": 0}
		)
		order.flags.ignore_permissions = True
		order.submit()
		result[key] = {
			"order": order.name,
			"redemption": frappe.db.get_value(
				"CRM Coupon Redemption",
				{"sales_order": order.name},
				["status", "plan", "facility_level", "tokens_awarded", "discount_percent"],
				as_dict=True,
			),
		}
	frappe.db.commit()

	# The Flex invoice, unpaid: what the metering grant check would let through for its coupon line.
	invoice = make_sales_invoice(result["l4_flex"]["order"], ignore_permissions=True)
	invoice.flags.ignore_permissions = True
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	frappe.db.commit()
	purchased = coupons.purchased_tokens(frappe.get_doc("Sales Order", result["l4_flex"]["order"]))
	bonuses = grants._invoice_bonuses(invoice.name, purchased, ids["l4_flex_fid"])
	result["l4_flex"]["invoice"] = invoice.name
	result["l4_flex"]["grant_check"] = [
		{"type": b["type"], "tokens": b["tokens"], "refused": b.get("refused")} for b in bonuses
	]
	return result


def teardown(run_id: str) -> dict:
	"""Retire the run's synthetic coupon and network so they never offer anything again."""
	ids = _ids(run_id)
	network = frappe.db.get_value("CRM Opt-In Network", {"slug": ids["slug"]}, "name")
	revoked = []
	for name in frappe.get_all(
		"CRM Coupon",
		filters={"coupon_title": ["in", list(coupon_titles(run_id))], "status": ["!=", "Revoked"]},
		pluck="name",
	):
		frappe.db.set_value("CRM Coupon", name, {"status": "Revoked", "revocation_reason": "E2E run finished"})
		revoked.append(name)
	if network:
		frappe.db.set_value("CRM Opt-In Network", network, "enabled", 0)
	frappe.db.commit()
	return {"revoked": revoked, "network_disabled": network}
