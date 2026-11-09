"""Synthetic fixture for the plan-scoped coupon journey (e2e/metering/coupon_plan_scope.spec.ts).

Run explicitly on a CRM site with openmeter_mediator (OpenMeter itself may be off):

    bench --site <site> execute crm.tests.e2e_coupon_plan_fixture.setup \
        --kwargs '{"run_id": "0001", "admin_password": "...", "owner_password": "..."}'
    # after the journey has looked at the draft order:
    bench --site <site> execute crm.tests.e2e_coupon_plan_fixture.confirm_and_pay_fixed --kwargs '{"run_id": "0001"}'

Each run adds a synthetic partner network with one **Both** coupon (500 tokens on Flex, 5% off
Fixed), two facilities of the synthetic E2E customer that entered that network's Partner Coupon
(one buys the Fixed Level 2 package, one a Flex package), each facility's draft Express order,
and a Deal listing both for the synthetic OpenMeter Admin. ``confirm_and_pay_fixed`` confirms
the Fixed order (claiming the coupon), invoices it, pays it in full and runs the subscription
activation the payment hook queues.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, nowdate

ADMIN_EMAIL = "e2e.metering-admin@example.test"
# Settings › Coupons is for System Managers in the CRM UI.
COUPON_ADMIN_EMAIL = "e2e.coupon-admin@example.test"
FIXED_ITEM = "CV-FIXED-L2"
FLEX_ITEM = "CV-TOKEN-STARTER"


def _ids(run_id: str) -> dict:
	run_id = frappe.utils.cstr(run_id).strip()
	if not run_id.isalnum():  # also keeps the id safe in names and SQL-free lookups
		frappe.throw("run_id must be alphanumeric")
	digits = "".join(ch for ch in run_id if ch.isdigit()) or "1"
	return {
		"run": run_id,
		"slug": f"e2e-cps-{run_id.lower()}",
		"partner_id": ("8" + digits.zfill(5))[-6:],
		"fixed_mfl": f"E2E-CF{run_id}",
		"fixed_fid": f"FID-00-E2ECF-{run_id}",
		"flex_mfl": f"E2E-CX{run_id}",
		"flex_fid": f"FID-00-E2ECX-{run_id}",
	}


def _facility(mfl, fid, name, network, customer, owner_email):
	frappe.get_doc(
		{
			"doctype": "CRM Pre-Qualified Facility",
			"mfl_code": mfl,
			"facility_name": name,
			"keph_level": "Level 2",
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

	network = frappe.get_doc(
		{
			"doctype": "CRM Opt-In Network",
			"slug": ids["slug"],
			"display_name": f"E2E Coupon Plan Network {ids['run']} (synthetic)",
			"partner_id": ids["partner_id"],
			"enabled": 1,
		}
	).insert(ignore_permissions=True).name
	coupon = frappe.get_doc(
		{
			"doctype": "CRM Coupon",
			"coupon_title": f"E2E both plans {ids['run']}",
			"network": network,
			"applies_to": "Both",
			"value_type": "flat_tokens",
			"value": 500,
			"fixed_discount_percent": 5,
			"valid_from": nowdate(),
			"status": "Active",
		}
	).insert(ignore_permissions=True).name

	_facility(ids["fixed_mfl"], ids["fixed_fid"], f"E2E Fixed Coupon Clinic {ids['run']} (synthetic)", network, customer, base.OWNER_EMAIL)
	_facility(ids["flex_mfl"], ids["flex_fid"], f"E2E Flex Coupon Clinic {ids['run']} (synthetic)", network, customer, base.OWNER_EMAIL)
	frappe.db.set_value("Customer", customer, "tax_id", "")
	frappe.db.commit()

	# The packages exactly as self-onboarding raises their draft orders.
	fixed_order = create_express_draft_order(
		customer, ids["fixed_mfl"], _order_package({"plan": "Fixed", "item_code": FIXED_ITEM})
	)["data"]["sales_order"]
	flex_order = create_express_draft_order(
		customer, ids["flex_mfl"], _order_package({"plan": "Flex", "item_code": FLEX_ITEM})
	)["data"]["sales_order"]
	deal = frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"organization_name": f"E2E Coupon Plan Clinics {ids['run']} (synthetic)",
			"facilities": [
				{"facility_name": "Fixed clinic", "mfl_code": ids["fixed_mfl"], "hfr_facility_id": ids["fixed_fid"], "facility_level": "Level 2"},
				{"facility_name": "Flex clinic", "mfl_code": ids["flex_mfl"], "hfr_facility_id": ids["flex_fid"], "facility_level": "Level 2"},
			],
		}
	).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True).name
	frappe.db.commit()

	fixed = frappe.get_doc("Sales Order", fixed_order)
	line = next(row for row in fixed.items if row.item_code == FIXED_ITEM)
	flex = frappe.get_doc("Sales Order", flex_order)
	return {
		**ids,
		"network": network,
		"coupon": coupon,
		"deal": deal,
		"customer": customer,
		"fixed_order": fixed_order,
		"fixed_list_rate": flt(line.price_list_rate),
		"fixed_rate": flt(line.rate),
		"fixed_discount_percent": flt(line.discount_percentage),
		"fixed_line_coupon": line.crm_coupon,
		"fixed_bonus_lines": [row.crm_bonus_type for row in fixed.items if row.get("crm_bonus_type")],
		"flex_order": flex_order,
		"flex_bonus_lines": {row.crm_bonus_type: row.crm_bonus_tokens for row in flex.items if row.get("crm_bonus_type")},
		"flex_discount": max(flt(row.discount_percentage) for row in flex.items),
		"owner": base.OWNER_EMAIL,
		"admin": ADMIN_EMAIL,
		"coupon_admin": COUPON_ADMIN_EMAIL,
		"network_name": f"E2E Coupon Plan Network {ids['run']} (synthetic)",
	}


def confirm_and_pay_fixed(run_id: str) -> dict:
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
	from openmeter_mediator.services import subscriptions

	ids = _ids(run_id)
	order = frappe.get_doc(
		"Sales Order", {"crm_token_facility_mfl": ids["fixed_mfl"], "crm_token_package_item": FIXED_ITEM, "docstatus": 0}
	)
	order.flags.ignore_permissions = True
	order.submit()
	invoice = make_sales_invoice(order.name, ignore_permissions=True)
	invoice.flags.ignore_permissions = True
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	company = invoice.company
	currency, debtors, cash = frappe.db.get_value(
		"Company", company, ["default_currency", "default_receivable_account", "default_cash_account"]
	)
	payment = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			"company": company,
			"party_type": "Customer",
			"party": invoice.customer,
			"paid_from": invoice.debit_to or debtors,
			"paid_to": cash,
			"paid_from_account_currency": currency,
			"paid_to_account_currency": currency,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
			"paid_amount": invoice.grand_total,
			"received_amount": invoice.grand_total,
			"reference_no": f"E2E-CPS-{ids['run']}",
			"reference_date": nowdate(),
			"references": [
				{"reference_doctype": "Sales Invoice", "reference_name": invoice.name, "allocated_amount": invoice.grand_total}
			],
		}
	).insert(ignore_permissions=True)
	payment.submit()
	frappe.db.commit()
	activation = subscriptions.activate_for_payment_entry(payment.name)
	frappe.db.commit()
	line = next(row for row in invoice.items if row.item_code == FIXED_ITEM)
	redemption = frappe.db.get_value(
		"CRM Coupon Redemption",
		{"sales_order": order.name},
		["status", "plan", "bonus_type", "discount_percent", "discount_amount", "tokens_awarded", "sales_invoice"],
		as_dict=True,
	)
	return {
		"order": order.name,
		"invoice": invoice.name,
		"invoice_line_discount": flt(line.discount_percentage),
		"invoice_line_rate": flt(line.rate),
		"invoice_net_total": flt(invoice.net_total),
		"payment": payment.name,
		"activation": activation,
		"redemption": redemption,
		"plan": subscriptions.facility_plan(ids["fixed_fid"]),
	}
