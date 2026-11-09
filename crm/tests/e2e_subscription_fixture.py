"""Synthetic fixture for the Fixed-subscription Playwright journey (e2e/metering/subscription_lifecycle.spec.ts).

Run it explicitly on a CRM site that has openmeter_mediator (OpenMeter itself may be off: the
journey checks the CRM side; the gateway's `/ingest/v1/plan` is covered by its own tests and
the Postman collection):

    bench --site <site> execute crm.tests.e2e_subscription_fixture.setup \
        --kwargs '{"run_id": "0001", "admin_password": "..."}'

Each run adds one synthetic facility (FID `FID-00-E2ES-<run_id>`) with an Active metering site,
a Deal listing it, and the synthetic OpenMeter Admin. It then raises a Fixed-package Sales
Invoice for the facility, pays it in full with a Payment Entry and runs the activation the
payment hook queues, so the facility has one active subscription term.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt, nowdate

ADMIN_EMAIL = "e2e.metering-admin@example.test"


def _company_accounts(company: str) -> tuple[str, str, str]:
	currency, debtors, cash = frappe.db.get_value(
		"Company", company, ["default_currency", "default_receivable_account", "default_cash_account"]
	)
	if not cash:
		cash = frappe.db.get_value(
			"Account", {"company": company, "account_type": "Cash", "is_group": 0, "account_currency": currency}, "name"
		)
	if not (debtors and cash):
		frappe.throw(f"{company} needs a default receivable account and a cash account")
	return currency, debtors, cash


def setup(run_id: str, admin_password: str, package_item: str = "CV-FIXED-L2", months_qty: int = 1) -> dict:
	from openmeter_mediator.services import subscriptions
	from openmeter_mediator.services.sites import ensure_site_for_fid
	from openmeter_mediator.tests import e2e_fixture as base

	run_id = frappe.utils.cstr(run_id).strip()
	if not run_id.isalnum():
		frappe.throw("run_id must be alphanumeric")
	package = subscriptions.fixed_packages().get(package_item)
	if not package:
		frappe.throw(f"{package_item} is not a Fixed package in the catalogue")

	customer = base._ensure_customer()
	mfl, fid = f"E2E-S{run_id}", f"FID-00-E2ES-{run_id}"
	name = f"E2E Subscription Clinic {run_id} (synthetic)"
	frappe.get_doc(
		{"doctype": "CRM Pre-Qualified Facility", "mfl_code": mfl, "facility_name": name, "keph_level": "Level 2",
		 "hfr_facility_id": fid}
	).insert(ignore_permissions=True)
	site = ensure_site_for_fid(fid)
	frappe.db.set_value("OpenMeter Site", site.name, {"status": "Active", "facility_name": name})
	base._ensure_user(ADMIN_EMAIL, "E2E Metering Admin", admin_password, roles=("OpenMeter Admin", "Sales Manager"))
	deal = frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"organization_name": name,
			"facilities": [{"facility_name": name, "mfl_code": mfl, "hfr_facility_id": fid, "facility_level": "Level 2"}],
		}
	).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True).name

	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	currency, debtors, cash = _company_accounts(company)
	rate = flt(subscriptions_price(package_item)) or 1000
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"company": company,
			"currency": currency,
			"conversion_rate": 1,
			"due_date": nowdate(),
			"crm_token_facility_fid": fid,
			"items": [{"item_code": package_item, "qty": int(months_qty), "rate": rate, "price_list_rate": rate}],
		}
	)
	invoice.set_missing_values()
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	payment = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			"company": company,
			"party_type": "Customer",
			"party": customer,
			"paid_from": debtors,
			"paid_to": cash,
			"paid_from_account_currency": currency,
			"paid_to_account_currency": currency,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
			"paid_amount": invoice.grand_total,
			"received_amount": invoice.grand_total,
			"reference_no": f"E2E-SUB-{run_id}",
			"reference_date": nowdate(),
			"references": [
				{"reference_doctype": "Sales Invoice", "reference_name": invoice.name, "allocated_amount": invoice.grand_total}
			],
		}
	)
	payment.insert(ignore_permissions=True)
	payment.submit()
	frappe.db.commit()
	# What the Payment Entry hook queues, run now so the journey does not wait on a worker.
	outcome = subscriptions.activate_for_payment_entry(payment.name)
	frappe.db.commit()
	plan = subscriptions.facility_plan(fid)
	return {
		"fid": fid,
		"mfl": mfl,
		"deal": deal,
		"invoice": invoice.name,
		"payment": payment.name,
		"activation": outcome,
		"package": package["display_name"],
		"activated_at": plan["subscription"]["activated_at"] if plan["subscription"] else None,
		"expires_at": plan["subscription"]["expires_at"] if plan["subscription"] else None,
		"admin": ADMIN_EMAIL,
	}


def subscriptions_price(item_code: str):
	from openmeter_mediator.services.grants import catalog_price

	return catalog_price(item_code)
