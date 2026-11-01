"""Synthetic fixture for the Express draft-order Playwright journey (e2e/metering/express_draft_order.spec.ts).

Run it explicitly on a CRM site that has openmeter_mediator with OpenMeter configured, after
openmeter_mediator.tests.e2e_fixture.setup has created the E2E users:

    bench --site <site> execute crm.tests.e2e_express_fixture.setup \
        --kwargs '{"run_id": "0001", "key_file": "/secure/path"}'

Each run adds one synthetic facility (MFL `E2E-X<run_id>`) to the E2E customer, onboarded with a
Partner Coupon unless `partner_coupon` is false, then does what Express submission and HMIS
provisioning do for a paid package: the metering hook runs with the package grant deferred, and a
draft token order is raised (with the first-purchase bonus and coupon lines). `partner_coupon_tokens`,
when given, sets that CRM setting first. The customer's KRA PIN is cleared so the journey has to
enter it. A site key for the facility is written to `key_file` (mode 600).

For the welcome-bonus journey (welcome_bonus_dispense.spec.ts, P-76), `admin_password` also creates
the synthetic OpenMeter Admin `e2e.metering-admin@example.test` and a Deal listing the facility, so
its Metering tab shows the Dispense button. `auto_dispense` sets that CRM setting first.
"""

from __future__ import annotations

import os

import frappe

ADMIN_EMAIL = "e2e.metering-admin@example.test"


def setup(
	run_id: str,
	key_file: str,
	package_item: str = "CV-TOKEN-STARTER",
	partner_coupon: bool = True,
	partner_coupon_tokens: int | None = None,
	admin_password: str | None = None,
	auto_dispense: bool | None = None,
) -> dict:
	from openmeter_mediator.services.provisioning import on_provisioning_submitted
	from openmeter_mediator.services.site_keys import issue_site_key
	from openmeter_mediator.tests import e2e_fixture as base

	from crm.api.customer_experience import _package, create_express_draft_order
	from crm.api.facility_onboarding import _no_network

	run_id = frappe.utils.cstr(run_id).strip()
	if not run_id.isalnum():
		frappe.throw("run_id must be alphanumeric")
	package = _package(package_item)
	if not package or not package["price"]:
		frappe.throw(f"{package_item} is not an enabled paid token package")

	if partner_coupon_tokens is not None:
		frappe.db.set_single_value("CRM Opt-In Settings", "partner_coupon_tokens", int(partner_coupon_tokens))
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")
	if auto_dispense is not None:
		frappe.db.set_single_value("CRM Opt-In Settings", "auto_dispense_welcome_bonus", 1 if auto_dispense else 0)
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")
	customer = base._ensure_customer()
	# Without a Partner Coupon, self-onboarding records the No Network record, as here.
	network = base._ensure_network() if partner_coupon else _no_network()["name"]
	mfl, fid = f"E2E-X{run_id}", f"FID-00-E2EX-{run_id}"
	facility = frappe.get_doc(
		{
			"doctype": "CRM Pre-Qualified Facility",
			"mfl_code": mfl,
			"facility_name": f"E2E Express Clinic {run_id} (synthetic)",
			"keph_level": "Level 2",
			"hfr_facility_id": fid,
			"memberships": [
				{
					"network": network,
					"status": "Active",
					"customer": customer,
					"contact_name": "E2E Facility Owner",
					"contact_email": base.OWNER_EMAIL,
					"contact_phone": "+254700000000",
					"partner_coupon": 1 if partner_coupon else 0,
				}
			],
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("Customer", customer, "tax_id", "")
	frappe.db.commit()

	on_provisioning_submitted(
		fid, {"fid": fid, "package_tokens": package["token_quantity"], "defer_package_grant": True}
	)
	order = create_express_draft_order(customer, mfl, package)["data"]["sales_order"]
	bonuses = {
		row.crm_bonus_type: row.crm_bonus_tokens
		for row in frappe.get_doc("Sales Order", order).items
		if row.get("crm_bonus_type")
	}
	deal = None
	if admin_password:
		base._ensure_user(ADMIN_EMAIL, "E2E Metering Admin", admin_password, roles=("OpenMeter Admin", "Sales Manager"))
		deal = frappe.get_doc(
			{
				"doctype": "CRM Deal",
				"organization_name": f"E2E Express Clinic {run_id} (synthetic)",
				"facilities": [
					{"facility_name": facility.facility_name, "mfl_code": mfl, "hfr_facility_id": fid, "facility_level": "Level 2"}
				],
			}
		).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True).name
	key = issue_site_key(fid)
	fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	with os.fdopen(fd, "w") as fh:
		fh.write(key)
	frappe.db.commit()
	return {
		"mfl": mfl,
		"fid": fid,
		"facility": facility.facility_name,
		"customer": customer,
		"sales_order": order,
		"package": package["display_name"],
		"package_tokens": package["token_quantity"],
		"bonuses": bonuses,
		"expected_tokens": package["token_quantity"] + sum(bonuses.values()),
		"deal": deal,
		"admin": ADMIN_EMAIL if admin_password else None,
	}
