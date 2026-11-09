"""Synthetic fixture for the Customer 360 facility-scope journey (e2e/tests/customer360_facility_scope.spec.ts).

Run explicitly on a CRM site (dev only; every record is marked "synthetic" and removed by teardown):

    bench --site <site> execute crm.tests.e2e_customer360_fixture.setup \
        --kwargs '{"run_id": "0001", "admin_password": "..."}'
    bench --site <site> execute crm.tests.e2e_customer360_fixture.teardown --kwargs '{"run_id": "0001"}'

Each run adds one owner organization with two facilities (A and B), a billing customer, one deal
listing both facilities, and:

- facility A: a Value Express draft order (with the quote that flow raises) and a direct quotation;
- facility B: a Value Express draft order (with its quote), confirmed and invoiced (draft invoice);
- one account-level quotation tied to no facility;
- ``bulk_quotes`` (default 11) more facility-A quotations, so its Quotes tab pages.

So facility A's view shows A's order and quotes only, facility B's its order, quote and invoice,
both note one record not tied to a facility, and the owner view shows everything.
"""

from __future__ import annotations

import frappe

ADMIN_EMAIL = "e2e.c360-admin@example.test"
# Sales/Accounts roles: this site's ERPNext doctypes carry no System Manager rows (docs/customer-360-view.md).
ADMIN_ROLES = ("System Manager", "Sales Manager", "Sales User", "Accounts User")
ITEM = "CV-TOKEN-STARTER"


def _ids(run_id: str) -> dict:
	run_id = frappe.utils.cstr(run_id).strip()
	if not run_id.isalnum():  # keeps the id safe in names
		frappe.throw("run_id must be alphanumeric")
	return {
		"run": run_id,
		"organization": f"E2E C360 Owner {run_id} (synthetic)",
		"customer": f"E2E C360 Customer {run_id} (synthetic)",
		"a_name": f"E2E C360 Clinic A {run_id} (synthetic)",
		"a_mfl": f"E2E-3A{run_id}",
		"a_fid": f"FID-00-E2E3A-{run_id}",
		"b_name": f"E2E C360 Clinic B {run_id} (synthetic)",
		"b_mfl": f"E2E-3B{run_id}",
		"b_fid": f"FID-00-E2E3B-{run_id}",
	}


def _quotation(customer: str, mfl: str | None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": customer,
			"items": [{"item_code": ITEM, "qty": 1}],
		}
	)
	if mfl:
		doc.crm_token_facility_mfl = mfl
	doc.insert(ignore_permissions=True)
	return doc.name


def setup(run_id: str, admin_password: str, bulk_quotes: int = 11) -> dict:
	"""``bulk_quotes`` extra facility-A quotations push its Quotes tab past one page (10 rows)."""
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
	from openmeter_mediator.tests import e2e_fixture as base

	from crm.api.customer_experience import create_express_draft_order
	from crm.api.facility_onboarding import _order_package

	ids = _ids(run_id)
	base._ensure_user(ADMIN_EMAIL, "E2E Customer360 Admin", admin_password, roles=ADMIN_ROLES)

	if not frappe.db.exists("Customer", ids["customer"]):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": ids["customer"],
				"customer_type": "Company",
				"customer_group": frappe.db.get_single_value("Selling Settings", "customer_group")
				or "All Customer Groups",
				"territory": frappe.db.get_single_value("Selling Settings", "territory") or "All Territories",
			}
		).insert(ignore_permissions=True)
	customer = ids["customer"]
	organization = frappe.get_doc(
		{"doctype": "CRM Organization", "organization_name": ids["organization"]}
	).insert(ignore_permissions=True)

	facilities = {}
	for key in ("a", "b"):
		facilities[key] = (
			frappe.get_doc(
				{
					"doctype": "CRM Pre-Qualified Facility",
					"mfl_code": ids[f"{key}_mfl"],
					"facility_name": ids[f"{key}_name"],
					"hfr_facility_id": ids[f"{key}_fid"],
					"organization": ids["organization"],
					"keph_level": "Level 2",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	deal = (
		frappe.get_doc(
			{
				"doctype": "CRM Deal",
				"organization": organization.name,
				"cx_customer": customer,
				"status": "Qualification",
				"facilities": [
					{
						"facility_name": ids[f"{key}_name"],
						"mfl_code": ids[f"{key}_mfl"],
						"hfr_facility_id": ids[f"{key}_fid"],
						"facility_level": "Level 2",
					}
					for key in ("a", "b")
				],
			}
		)
		.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		.name
	)
	frappe.db.commit()

	package = _order_package({"plan": "Flex", "item_code": ITEM})
	a_order = create_express_draft_order(customer, ids["a_mfl"], package)["data"]["sales_order"]
	b_order = create_express_draft_order(customer, ids["b_mfl"], package)["data"]["sales_order"]
	a_quote = _quotation(customer, ids["a_mfl"])
	account_quote = _quotation(customer, None)
	for _ in range(max(0, min(int(bulk_quotes or 0), 30))):
		_quotation(customer, ids["a_mfl"])

	# Facility B's order is confirmed and invoiced (draft invoice; the header facility carries over).
	order = frappe.get_doc("Sales Order", b_order)
	if order.docstatus == 0:
		order.flags.ignore_permissions = True
		order.submit()
	invoice = make_sales_invoice(b_order)
	invoice.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		**ids,
		"admin": ADMIN_EMAIL,
		"organization_doc": organization.name,
		"a_facility": facilities["a"],
		"b_facility": facilities["b"],
		"deal": deal,
		"a_order": a_order,
		"b_order": b_order,
		"a_quote": a_quote,
		"account_quote": account_quote,
		"b_invoice": invoice.name,
		"a_quote_count": frappe.db.count(
			"Quotation", {"party_name": customer, "crm_token_facility_mfl": ids["a_mfl"]}
		),
		"quote_count": frappe.db.count("Quotation", {"party_name": customer}),
		"b_invoice_mfl": frappe.db.get_value("Sales Invoice", invoice.name, "crm_token_facility_mfl"),
	}


def teardown(run_id: str) -> dict:
	"""Remove everything setup created for this run (documents are cancelled before deletion)."""
	ids = _ids(run_id)
	customer = ids["customer"]
	removed = []

	def drop(doctype, name):
		if not frappe.db.exists(doctype, name):
			return
		doc = frappe.get_doc(doctype, name)
		if doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		removed.append((doctype, name))

	for doctype, field in (
		("Sales Invoice", "customer"),
		("Sales Order", "customer"),
		("Quotation", "party_name"),
	):
		for name in frappe.get_all(
			doctype, filters={field: customer}, pluck="name", order_by="creation desc"
		):
			drop(doctype, name)
	for name in frappe.get_all("CRM Deal", filters={"cx_customer": customer}, pluck="name"):
		drop("CRM Deal", name)
	for key in ("a", "b"):
		for name in frappe.get_all(
			"CRM Pre-Qualified Facility", filters={"mfl_code": ids[f"{key}_mfl"]}, pluck="name"
		):
			drop("CRM Pre-Qualified Facility", name)
	for name in frappe.get_all(
		"CRM Organization", filters={"organization_name": ids["organization"]}, pluck="name"
	):
		drop("CRM Organization", name)
	drop("Customer", customer)
	frappe.db.commit()
	return {"removed": len(removed)}
