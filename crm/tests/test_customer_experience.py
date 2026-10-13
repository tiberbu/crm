import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import customer_experience as cx
from crm.api.facility_onboarding import _token_packages
from crm.utils.quotation_tax import calculate_vat_totals

OWNER = "cx-test-owner@example.com"
OTHER = "cx-test-other@example.com"


def _website_user(email):
	return frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "CX Test",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)


def _submission(email, mfl):
	ois = frappe.get_doc(
		{
			"doctype": "CRM Opt-In Submission",
			"naming_series": "OIS-.YYYY.-",
			"status": "Processed",
			"network_slug": frappe.db.get_value("CRM Opt-In Network", {}, "name"),
			"submitter_email": email,
			"facility_signatory_name": "CX Owner %s" % mfl,
			"facility_signatory_email": email,
			"raw_json": json.dumps(
				{"facilities": [{"mfl_code": mfl, "facility_name": "CX Clinic %s" % mfl}]}
			),
			"submitted_at": frappe.utils.now_datetime(),
		}
	)
	ois.flags.skip_auto_processing = True
	ois.insert(ignore_permissions=True)
	frappe.get_doc(
		{"doctype": "User Permission", "user": email, "allow": "CRM Opt-In Submission", "for_value": ois.name}
	).insert(ignore_permissions=True)
	return ois.name


class TestTokenPurchaseChain(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("cx_purchase_test")
		self.addCleanup(frappe.db.rollback, save_point="cx_purchase_test")
		packages = _token_packages()
		if not packages:
			self.skipTest("No enabled token package with a price on this site")
		self.package = packages[0]
		_website_user(OWNER)
		_website_user(OTHER)
		self.ois = _submission(OWNER, "90001")
		self.other_ois = _submission(OTHER, "90002")
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(OWNER)

	def _order(self, **overrides):
		args = {
			"ois_number": self.ois,
			"facility_mfl": "90001",
			"package_item_code": self.package["item_code"],
			**overrides,
		}
		return cx.create_token_order(**args)["data"]

	def _count(self, doctype):
		return frappe.db.count(doctype, {"crm_optin_submission": self.ois, "docstatus": ["!=", 2]})

	def test_order_creates_a_submitted_priced_order_with_a_linked_quotation(self):
		data = self._order()
		order = frappe.get_doc("Sales Order", data["sales_order"])
		quotation = frappe.get_doc("Quotation", data["quotation"])
		totals = calculate_vat_totals(self.package["price"])
		self.assertEqual(order.docstatus, 1)
		self.assertEqual(order.items[0].rate, self.package["price"])
		self.assertEqual(order.grand_total, totals.grand_total)
		self.assertEqual(quotation.grand_total, totals.grand_total)
		self.assertEqual(order.crm_optin_quotation, quotation.name)
		self.assertEqual(order.crm_optin_submission, self.ois)
		self.assertEqual(order.crm_token_facility_mfl, "90001")
		self.assertEqual(order.crm_token_package_item, self.package["item_code"])
		self.assertEqual(order.crm_token_purchase_key, quotation.crm_token_purchase_key)

	def test_order_retry_returns_the_same_chain_even_with_another_key(self):
		first = self._order()
		second = self._order(purchase_key="a-different-browser-key")
		self.assertEqual(
			(second["sales_order"], second["quotation"]), (first["sales_order"], first["quotation"])
		)
		self.assertTrue(second["idempotent"])
		self.assertEqual(self._count("Sales Order"), 1)
		self.assertEqual(self._count("Quotation"), 1)

	def test_payment_creates_one_invoice_and_retry_returns_it(self):
		order = self._order()["sales_order"]
		first = cx.start_token_payment(order)["data"]
		second = cx.start_token_payment(order)["data"]
		invoice = frappe.get_doc("Sales Invoice", first["invoice"])
		self.assertEqual(second["invoice"], first["invoice"])
		self.assertFalse(first["idempotent"])
		self.assertTrue(second["idempotent"])
		self.assertEqual(self._count("Sales Invoice"), 1)
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(invoice.grand_total, frappe.db.get_value("Sales Order", order, "grand_total"))
		self.assertEqual(invoice.crm_optin_submission, self.ois)
		self.assertEqual(invoice.crm_token_package_item, self.package["item_code"])
		self.assertGreater(frappe.utils.getdate(invoice.due_date), frappe.utils.getdate(invoice.posting_date))

	def test_no_invoice_exists_until_payment_starts(self):
		self._order()
		self.assertEqual(self._count("Sales Invoice"), 0)

	def test_next_billing_period_creates_a_new_chain(self):
		first = self._order()
		with patch.object(cx, "_period_key", return_value="2099-01"):
			second = self._order()
		self.assertNotEqual(first["sales_order"], second["sales_order"])
		self.assertEqual(self._count("Sales Order"), 2)

	def test_context_lists_open_orders_then_the_open_invoice(self):
		order = self._order()["sales_order"]
		rows = cx.get_purchase_context()["data"]["ois"]
		self.assertEqual([row["ois"] for row in rows], [self.ois])
		self.assertEqual([o["name"] for o in rows[0]["orders"]], [order])
		self.assertTrue(rows[0]["orders"][0]["can_create_invoice"])
		invoice = cx.start_token_payment(order)["data"]["invoice"]
		rows = cx.get_purchase_context()["data"]["ois"]
		self.assertEqual(rows[0]["orders"], [])
		self.assertEqual([i["name"] for i in rows[0]["invoices"]], [invoice])

	def test_partially_billed_orders_only_offer_invoices_when_the_status_allows_it(self):
		order = self._order()["sales_order"]
		frappe.db.set_value("Sales Order", order, "per_billed", 35)
		for status, can_create_invoice in (
			("To Deliver and Bill", True),
			("On Hold", False),
			("Closed", False),
		):
			frappe.db.set_value("Sales Order", order, "status", status)
			rows = cx.get_purchase_context()["data"]["ois"]
			projected_order = rows[0]["orders"][0]
			self.assertEqual(projected_order["can_create_invoice"], can_create_invoice)
			if not can_create_invoice:
				with self.assertRaises(frappe.ValidationError):
					cx.start_token_payment(order)

	def test_another_customers_selectors_are_denied(self):
		order = self._order()["sales_order"]
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			cx.create_token_order(self.ois, "90001", self.package["item_code"])
		with self.assertRaises(frappe.PermissionError):
			cx.start_token_payment(order)
		self.assertEqual([row["ois"] for row in cx.get_purchase_context()["data"]["ois"]], [self.other_ois])

	def test_unknown_and_foreign_orders_are_indistinguishable(self):
		order = self._order()["sales_order"]
		frappe.set_user(OTHER)
		messages = []
		for name in (order, "SAL-ORD-DOES-NOT-EXIST"):
			with self.assertRaises(frappe.PermissionError) as caught:
				cx.start_token_payment(name)
			messages.append(str(caught.exception))
		self.assertEqual(messages[0], messages[1])

	def test_facility_outside_the_request_and_unavailable_packages_are_rejected(self):
		with self.assertRaises(frappe.PermissionError):
			self._order(facility_mfl="99999")
		with self.assertRaises(frappe.ValidationError):
			self._order(package_item_code="NOT-A-PACKAGE")
		self.assertEqual(self._count("Sales Order"), 0)

	def test_staff_sessions_cannot_use_the_portal_endpoints(self):
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.PermissionError):
			cx.create_token_order(self.ois, "90001", self.package["item_code"])

	def test_purchase_documents_are_recorded_as_evidence(self):
		data = self._order()
		invoice = cx.start_token_payment(data["sales_order"])["data"]["invoice"]
		linked = {
			row.reference_name
			for row in frappe.get_all(
				"CRM Onboarding Evidence",
				filters={
					"event": "document_linked",
					"reference_name": ["in", [data["sales_order"], invoice]],
				},
				fields=["reference_name"],
			)
		}
		self.assertEqual(linked, {data["sales_order"], invoice})
