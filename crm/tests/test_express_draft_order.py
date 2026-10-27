"""Express onboarding raises a draft token order; the client reviews and confirms it before paying."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import customer_experience as cx
from crm.api.facility_onboarding import _token_packages

OWNER = "cx-express-owner@example.test"
OTHER = "cx-express-other@example.test"
MFL = "90011"
KRA_PIN = "A123456789Z"


def _receivable_account(company, currency):
	"""A receivable account in the package currency, for sites whose company books in another one."""
	account = frappe.db.get_value("Account", {"company": company, "account_type": "Receivable", "account_currency": currency, "is_group": 0}, "name")
	if account:
		return account
	parent = frappe.db.get_value("Account", {"company": company, "account_type": "Receivable", "is_group": 0}, "parent_account")
	return frappe.get_doc(
		{"doctype": "Account", "account_name": "Express Test Debtors %s" % currency, "company": company, "parent_account": parent, "account_type": "Receivable", "account_currency": currency}
	).insert(ignore_permissions=True).name


def _portal_customer(email, name, receivable=None):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Express", "user_type": "Website User", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	customer = frappe.get_doc(
		{"doctype": "Customer", "customer_name": name, "customer_type": "Company", "default_currency": receivable and frappe.db.get_value("Account", receivable["account"], "account_currency"), "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"), "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name")}
	)
	if receivable:
		customer.append("accounts", receivable)
	customer.insert(ignore_permissions=True)
	frappe.get_doc(
		{"doctype": "User Permission", "user": email, "allow": "Customer", "for_value": customer.name}
	).insert(ignore_permissions=True)
	return customer.name


class TestExpressDraftOrder(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("cx_express_test")
		self.addCleanup(frappe.db.rollback, save_point="cx_express_test")
		self.addCleanup(frappe.set_user, "Administrator")
		if not frappe.db.has_column("Sales Order", "crm_order_frequency"):
			self.skipTest("Run bench migrate: token order frequency fields are missing")
		packages = [p for p in _token_packages() if (p.get("price") or 0) > 0]
		if not packages:
			self.skipTest("No enabled token package with a price on this site")
		self.package = packages[0]
		company_currency = frappe.db.get_value(
			"Company", frappe.db.get_single_value("Global Defaults", "default_company"), "default_currency"
		)
		receivable = None
		if company_currency != self.package["currency"]:
			company = frappe.db.get_single_value("Global Defaults", "default_company")
			receivable = {"company": company, "account": _receivable_account(company, self.package["currency"])}
			frappe.get_doc(
				{"doctype": "Currency Exchange", "date": "2000-01-01", "from_currency": self.package["currency"], "to_currency": company_currency, "exchange_rate": 0.0077, "for_selling": 1}
			).insert(ignore_permissions=True)
		# VAT templates are site configuration, covered by test_customer_experience; not needed here.
		for target in ("crm.utils.quotation_tax.apply_quotation_taxes", "crm.automation.optin_billing._apply_order_tax_template"):
			stub = patch(target)
			stub.start()
			self.addCleanup(stub.stop)
		self.customer = _portal_customer(OWNER, "Express Draft Test Customer", receivable)
		self.other_customer = _portal_customer(OTHER, "Express Draft Other Customer")
		self.order = cx.create_express_draft_order(self.customer, MFL, self.package)["data"]["sales_order"]

	def _confirm(self, **overrides):
		args = {
			"sales_order": self.order,
			"kra_pin": KRA_PIN,
			"frequency": "One-time",
			"new_address": {"address_line1": "1 Test Road", "city": "Nairobi", "county": "Nairobi"},
			**overrides,
		}
		frappe.set_user(OWNER)
		return cx.confirm_draft_order(**args)["data"]

	def test_express_submit_leaves_a_priced_draft_order_and_no_invoice(self):
		order = frappe.get_doc("Sales Order", self.order)
		self.assertEqual(order.docstatus, 0)
		self.assertEqual(order.items[0].rate, self.package["price"])
		self.assertEqual(order.crm_token_facility_mfl, MFL)
		self.assertTrue(order.crm_token_purchase_key)
		self.assertEqual(frappe.db.count("Sales Invoice", {"customer": self.customer}), 0)
		again = cx.create_express_draft_order(self.customer, MFL, self.package)["data"]
		self.assertEqual((again["sales_order"], again["idempotent"]), (self.order, True))

	def test_portal_lists_the_draft_for_review_not_for_invoicing(self):
		from crm.api.website_redirect import _customer_orders

		row = next(o for o in _customer_orders(self.customer) if o["name"] == self.order)
		self.assertTrue(row["is_draft"])
		self.assertFalse(row["can_create_invoice"])
		frappe.set_user(OWNER)
		data = cx.get_draft_order(self.order)["data"]
		self.assertTrue(data["is_draft"])
		self.assertEqual(data["frequency"], "One-time")
		self.assertEqual(data["addresses"], [])

	def test_confirm_requires_a_valid_kra_pin_and_a_billing_address(self):
		with self.assertRaises(frappe.ValidationError):
			self._confirm(kra_pin="12345")
		with self.assertRaises(frappe.ValidationError):
			self._confirm(new_address={})
		self.assertEqual(frappe.db.get_value("Sales Order", self.order, "docstatus"), 0)

	def test_confirm_submits_the_order_and_raises_its_invoice(self):
		data = self._confirm(kra_pin=" a123456789z ")
		order = frappe.get_doc("Sales Order", self.order)
		invoice = frappe.get_doc("Sales Invoice", data["invoice"])
		self.assertEqual(order.docstatus, 1)
		self.assertEqual(order.crm_order_frequency, "One-time")
		self.assertEqual(frappe.db.get_value("Customer", self.customer, "tax_id"), KRA_PIN)
		self.assertEqual(frappe.db.get_value("Address", order.customer_address, "address_type"), "Billing")
		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(invoice.customer_address, order.customer_address)
		self.assertEqual(invoice.crm_token_purchase_key, order.crm_token_purchase_key)
		self.assertEqual(invoice.grand_total, order.grand_total)
		self.assertEqual(self._confirm()["invoice"], data["invoice"])

	def test_saved_billing_address_is_reused(self):
		first = self._confirm()
		address = frappe.db.get_value("Sales Order", first["sales_order"], "customer_address")
		frappe.set_user("Administrator")
		with patch.object(cx, "_period_key", return_value="2099-01"):
			second = cx.create_express_draft_order(self.customer, MFL, self.package)["data"]["sales_order"]
		frappe.set_user(OWNER)
		self.assertEqual(cx.get_draft_order(second)["data"]["addresses"][0]["name"], address)
		cx.confirm_draft_order(second, kra_pin=KRA_PIN, billing_address=address)
		self.assertEqual(frappe.db.get_value("Sales Order", second, "customer_address"), address)

	def test_recurring_order_repeats_as_a_draft(self):
		data = self._confirm(frequency="Recurring", recurrence_period="Quarterly")
		repeat = frappe.get_doc("Auto Repeat", data["auto_repeat"])
		self.assertEqual((repeat.reference_document, repeat.frequency, repeat.submit_on_creation), (self.order, "Quarterly", 0))
		with self.assertRaises(frappe.ValidationError):
			self._confirm(frequency="Recurring", recurrence_period="Weekly")

	def test_repeated_order_without_a_purchase_key_gets_one_on_confirm(self):
		frappe.db.set_value("Sales Order", self.order, "crm_token_purchase_key", "")
		data = self._confirm()
		key = frappe.db.get_value("Sales Order", self.order, "crm_token_purchase_key")
		self.assertTrue(key)
		self.assertEqual(frappe.db.get_value("Sales Invoice", data["invoice"], "crm_token_purchase_key"), key)

	def test_billing_profile_shows_the_owner_their_billing_details(self):
		frappe.db.set_value("Customer", self.customer, "tax_id", KRA_PIN)
		address = frappe.get_doc(
			{"doctype": "Address", "address_title": "Clinic", "address_type": "Billing", "address_line1": "1 Clinic Rd", "city": "Nairobi", "country": "Kenya", "links": [{"link_doctype": "Customer", "link_name": self.customer}]}
		).insert(ignore_permissions=True)
		frappe.set_user(OWNER)
		profile = cx.get_billing_profile(self.customer)["data"]
		self.assertEqual(profile["customer_name"], "Express Draft Test Customer")
		self.assertEqual(profile["kra_pin"], KRA_PIN)
		self.assertEqual([row.name for row in profile["addresses"]], [address.name])

	def test_billing_profile_of_another_customer_is_refused(self):
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			cx.get_billing_profile(self.customer)
		with self.assertRaises(frappe.PermissionError):
			cx.get_billing_profile("")

	def test_another_customer_cannot_review_or_confirm(self):
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			cx.get_draft_order(self.order)
		with self.assertRaises(frappe.PermissionError):
			cx.confirm_draft_order(self.order, kra_pin=KRA_PIN, new_address={"address_line1": "x", "city": "y"})
		frappe.set_user(OWNER)
		other_address = frappe.get_doc(
			{"doctype": "Address", "address_title": "Other", "address_type": "Billing", "address_line1": "2 Other Rd", "city": "Mombasa", "country": "Kenya", "links": [{"link_doctype": "Customer", "link_name": self.other_customer}]}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			cx.confirm_draft_order(self.order, kra_pin=KRA_PIN, billing_address=other_address.name)

	def test_onboarding_submit_raises_the_draft_and_survives_a_failure(self):
		from crm.api.facility_onboarding import _create_express_draft_order

		facility = {"mfl_code": "90012"}
		name = _create_express_draft_order(self.customer, facility, {"item_code": self.package["item_code"]}, None)
		self.assertEqual(frappe.db.get_value("Sales Order", name, ["docstatus", "crm_token_facility_mfl"]), (0, "90012"))
		self.assertIsNone(_create_express_draft_order(self.customer, facility, {"item_code": "NO-SUCH-PACKAGE"}, None))
		with patch.object(cx, "create_express_draft_order", side_effect=frappe.ValidationError("boom")):
			self.assertIsNone(_create_express_draft_order(self.customer, facility, {"item_code": self.package["item_code"]}, None))


class TestTokenBonuses(TestExpressDraftOrder):
	"""First-purchase bonus and Partner Coupon lines on Express orders."""

	def setUp(self):
		frappe.db.set_single_value("CRM Opt-In Settings", {"welcome_bonus_tokens": 400, "partner_coupon_tokens": 150})
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")
		self.addCleanup(frappe.clear_document_cache, "CRM Opt-In Settings", "CRM Opt-In Settings")
		super().setUp()
		if not frappe.db.has_column("Sales Order Item", "crm_bonus_type"):
			self.skipTest("Run bench migrate: token bonus fields are missing")

	def _bonus_rows(self, order):
		return {
			row.crm_bonus_type: (row.crm_bonus_tokens, row.rate)
			for row in frappe.get_doc("Sales Order", order).items
			if row.crm_bonus_type
		}

	def _coupon_facility(self, mfl):
		network = frappe.db.get_value("CRM Opt-In Network", {}, "name") or frappe.get_doc(
			{"doctype": "CRM Opt-In Network", "slug": "express-coupon-test", "display_name": "Coupon Test Network", "partner_id": "909092", "enabled": 1}
		).insert(ignore_permissions=True).name
		frappe.get_doc(
			{
				"doctype": "CRM Pre-Qualified Facility",
				"mfl_code": mfl,
				"facility_name": "Coupon Clinic %s" % mfl,
				"keph_level": "Level 2",
				"memberships": [{"network": network, "customer": self.customer, "status": "Active", "partner_coupon": 1, "contact_name": "Owner", "contact_email": OWNER, "contact_phone": "+254700000000"}],
			}
		).insert(ignore_permissions=True)

	def test_first_order_carries_a_zero_rated_welcome_bonus(self):
		order = frappe.get_doc("Sales Order", self.order)
		self.assertEqual(self._bonus_rows(self.order), {"Welcome Bonus": (400, 0)})
		self.assertEqual(order.net_total, self.package["price"])

	def test_partner_coupon_facility_gets_both_and_the_invoice_shows_them(self):
		self._coupon_facility("90013")
		order = cx.create_express_draft_order(self.customer, "90013", self.package)["data"]["sales_order"]
		self.assertEqual(self._bonus_rows(order), {"Welcome Bonus": (400, 0), "Partner Coupon": (150, 0)})
		self.order = order
		invoice = frappe.get_doc("Sales Invoice", self._confirm()["invoice"])
		lines = {row.crm_bonus_type: row.crm_bonus_tokens for row in invoice.items if row.crm_bonus_type}
		self.assertEqual(lines, {"Welcome Bonus": 400, "Partner Coupon": 150})
		self.assertEqual(invoice.net_total, self.package["price"])

	def test_bonus_goes_to_the_first_confirmed_order_only(self):
		frappe.set_user("Administrator")
		with patch.object(cx, "_period_key", return_value="2099-01"):
			second = cx.create_express_draft_order(self.customer, MFL, self.package)["data"]["sales_order"]
		self.assertIn("Welcome Bonus", self._bonus_rows(second))
		self._confirm()
		frappe.set_user(OWNER)
		cx.confirm_draft_order(second, kra_pin=KRA_PIN, billing_address=frappe.db.get_value("Sales Order", self.order, "customer_address"))
		self.assertEqual(self._bonus_rows(second), {})
		frappe.set_user("Administrator")
		with patch.object(cx, "_period_key", return_value="2099-02"):
			third = cx.create_express_draft_order(self.customer, MFL, self.package)["data"]["sales_order"]
		self.assertEqual(self._bonus_rows(third), {})

	def test_no_coupon_without_the_flag_and_nothing_when_set_to_zero(self):
		self.assertNotIn("Partner Coupon", self._bonus_rows(self.order))
		frappe.db.set_single_value("CRM Opt-In Settings", "welcome_bonus_tokens", 0)
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")
		self._confirm()
		self.assertEqual(self._bonus_rows(self.order), {})
