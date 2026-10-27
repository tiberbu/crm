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
	if frappe.db.exists("User", email):
		return frappe.get_doc("User", email)
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
		frappe.db.delete("CRM Opt-In Submission", {"submitter_email": ["in", [OWNER, OTHER]]})
		frappe.db.delete("User", {"email": ["in", [OWNER, OTHER]]})
		frappe.db.savepoint("cx_purchase_test")
		self.addCleanup(frappe.db.rollback, save_point="cx_purchase_test")
		packages = [p for p in _token_packages() if (p.get("price") or 0) > 0]
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

	def test_mask_national_id(self):
		self.assertEqual(cx._mask_national_id("12345678"), "12••••78")
		self.assertEqual(cx._mask_national_id("123"), "•••")
		self.assertEqual(cx._mask_national_id(""), "")
		self.assertEqual(cx._mask_national_id(None), "")

	def test_get_and_update_user_profile(self):
		profile = cx.get_user_profile()["data"]
		self.assertEqual(profile["email"], OWNER)

		# Create a customer linked to the owner user
		cust = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "Original Person Name",
			"customer_type": "Company",
		}).insert(ignore_permissions=True)
		perm = frappe.get_doc({
			"doctype": "User Permission",
			"user": OWNER,
			"allow": "Customer",
			"for_value": cust.name,
		}).insert(ignore_permissions=True)

		updated = cx.update_user_profile(
			national_id="28472910",
			mobile_no="0712345678",
			full_name="Updated Test Name",
			organization="Amina Healthcare Group",
		)["data"]
		self.assertEqual(updated["national_id"], "28472910")
		self.assertEqual(updated["masked_national_id"], "28••••10")
		self.assertEqual(updated["mobile_no"], "0712345678")
		self.assertEqual(updated["full_name"], "Updated Test Name")
		self.assertEqual(updated["organization"], "Amina Healthcare Group")
		self.assertTrue(updated["national_id_verified"])

		# Verify the customer record in DB was updated with the new organization name
		self.assertEqual(frappe.db.get_value("Customer", cust.name, "customer_name"), "Amina Healthcare Group")
		self.assertEqual(frappe.db.get_value("Customer", cust.name, "mobile_no"), "0712345678")

		with self.assertRaises(frappe.ValidationError):
			cx.update_user_profile(national_id="invalid-id")

	def test_ensure_website_user_persists_kyc_and_contact(self):
		from crm.api.website_redirect import ensure_website_user_for_customer

		user_email = "cx-kyc-verify@example.com"
		if frappe.db.exists("User", user_email):
			frappe.delete_doc("User", user_email, force=1)

		cust = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "Dr. Verification Customer",
			"customer_type": "Company",
		}).insert(ignore_permissions=True)

		with patch("frappe.core.doctype.user.user.User._reset_password"):
			res = ensure_website_user_for_customer(
				cust.name,
				email=user_email,
				display_name="Dr. Verification Customer",
				national_id="29481923",
				mobile_no="0722112233",
				identification_type="National ID",
				national_id_verified=True,
				hfr_owner_licence="LIC-99881",
				hfr_registration_number="REG-44332",
			)
			self.assertEqual(res["status"], "sent")
			user_doc = frappe.get_doc("User", user_email)
			self.assertEqual(user_doc.national_id, "29481923")
			self.assertTrue(user_doc.national_id_verified)
			self.assertEqual(user_doc.mobile_no, "0722112233")
			self.assertEqual(user_doc.first_name, "Dr.")
			self.assertEqual(user_doc.last_name, "Verification Customer")
			self.assertEqual(user_doc.hfr_owner_licence, "LIC-99881")
			self.assertEqual(user_doc.hfr_registration_number, "REG-44332")

	def test_lookup_facilities_by_owner_id(self):
		with patch.object(cx, "_hfr_facilities_for_owner") as mock_hfr:
			mock_hfr.return_value = [
				{"fid": "f1", "mfl_code": "90001", "name": "Linked Clinic", "level": "Level 2"},
				{"fid": "f2", "mfl_code": "90099", "name": "Unlinked Clinic", "level": "Level 3"},
			]
			res = cx.lookup_facilities_by_owner_id(national_id="28472910")
			results = res["data"]
			self.assertEqual(len(results), 2)
			self.assertTrue(results[0]["already_linked"])
			self.assertFalse(results[1]["already_linked"])

	def test_report_mpesa_payment_validation(self):
		with self.assertRaises(frappe.ValidationError):
			cx.report_mpesa_payment("NON-EXISTENT-INV", "SB65A1TU7X")

		with self.assertRaises(frappe.ValidationError):
			cx.report_mpesa_payment("NON-EXISTENT-INV", "123")

	def test_user_permission_lead_and_deal_resolution(self):
		from crm.api.website_redirect import (
			_customer_portal_accounts,
			get_user_customer_names,
			get_user_deal_names,
			get_user_lead_names,
		)

		test_user = "cx-test-desk@example.com"
		_website_user(test_user)

		frappe.set_user("Administrator")
		# Grant User Permission for a Deal
		deal = frappe.get_doc({
			"doctype": "CRM Deal",
			"organization": "Kiambu Level 4 Demonstration Hospital",
			"optin_network": "chak-cbsl",
			"facilities": [
				{
					"facility_name": "Desk Demo Clinic",
					"mfl_code": "88776",
					"facility_level": "Level 3",
				}
			],
		}).insert(ignore_permissions=True, ignore_links=True)

		perm = frappe.get_doc({
			"doctype": "User Permission",
			"user": test_user,
			"allow": "CRM Deal",
			"for_value": deal.name,
			"apply_to_all_doctypes": 1,
		}).insert(ignore_permissions=True)

		# Verify deal names resolved
		deals = get_user_deal_names(test_user)
		self.assertIn(deal.name, deals)

		# Verify customer portal accounts projects the deal and its facilities
		accounts = _customer_portal_accounts(test_user)
		self.assertTrue(len(accounts) >= 1)
		acc = accounts[0]
		self.assertEqual(acc["organization"], "Kiambu Level 4 Demonstration Hospital")
		self.assertEqual(len(acc["facilities"]), 1)
		self.assertEqual(acc["facilities"][0]["facility_name"], "Desk Demo Clinic")
		self.assertEqual(acc["facilities"][0]["mfl_code"], "88776")

	def test_portal_shows_no_partner_for_the_no_network_record(self):
		from crm.api.facility_onboarding import NO_NETWORK_SLUG, _no_network
		from crm.api.website_redirect import _partner_label, _portal_network

		_no_network()
		self.assertEqual(_partner_label(NO_NETWORK_SLUG), "")
		self.assertEqual(_partner_label(""), "")
		self.assertEqual(_portal_network(NO_NETWORK_SLUG), {})

	@patch("crm.api.website_redirect.frappe.get_all")
	def test_portal_hfr_fallback_is_scoped_to_authorized_org_and_mfl(self, mock_get_all):
		from crm.api.website_redirect import _portal_hfr_registry_by_mfl

		mock_get_all.return_value = [
			{"parent": "Example Organization", "mfl_code": "88776", "hfr_facility_id": "FID-29-88776-5"}
		]

		result = _portal_hfr_registry_by_mfl(["88776"], ["Example Organization"])

		self.assertEqual(result[("example organization", "88776")]["hfr_facility_id"], "FID-29-88776-5")
		filters = mock_get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["parent"], ["in", ["Example Organization"]])
		self.assertEqual(filters["mfl_code"], ["in", ["88776"]])
		self.assertEqual(mock_get_all.call_args.kwargs["fields"], ["parent", "mfl_code", "hfr_facility_id"])

	def test_customer_payments_projection(self):
		from crm.api.website_redirect import _customer_payments

		frappe.set_user("Administrator")
		cust = "Test Payment Cust"
		if not frappe.db.exists("Customer", cust):
			frappe.get_doc({"doctype": "Customer", "customer_name": cust}).insert(ignore_permissions=True)

		payments = _customer_payments("ZUHRI MEDICARE LIMITED")
		self.assertIsInstance(payments, list)



