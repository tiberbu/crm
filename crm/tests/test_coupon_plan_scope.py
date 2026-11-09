"""Plan-scoped coupons (P-107 to P-115): Flex tokens, Fixed discount, Flex-only bonus tokens.

Uses the catalogue's own Flex and Fixed packages (CRM Opt-In Settings › token_packages).
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from crm.tests.test_coupon_resolution import _facility, _net
from crm.utils import coupons, token_bonus


def _catalogue_item(plan):
	return frappe.db.get_value("CRM Token Package", {"parenttype": "CRM Opt-In Settings", "plan": plan}, "item_code")


def _coupon(**kw):
	base = {
		"coupon_title": "plan coupon",
		"value_type": "flat_tokens",
		"value": 500,
		"max_tokens": 0,
		"targeting": "Assigned Facilities",
		"status": "Active",
	}
	base.update(kw)
	return frappe.get_doc({"doctype": "CRM Coupon", **base}).insert(ignore_permissions=True)


def _order(name, item, customer, mfl, rows, fid="FID-PS-1"):
	return SimpleNamespace(
		name=name,
		customer=customer,
		crm_token_package_item=item,
		crm_token_facility_mfl=mfl,
		crm_token_facility_fid=fid,
		items=rows,
		calculate_taxes_and_totals=lambda: None,
	)


class _Doc(SimpleNamespace):
	"""Just enough of a Sales Order for apply_bonus_lines."""

	def get(self, field, default=None):
		return getattr(self, field, default)

	def set(self, field, value):
		setattr(self, field, value)


class CouponPlanCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("coupon_plan_scope")
		self.addCleanup(frappe.db.rollback, save_point="coupon_plan_scope")
		self.addCleanup(frappe.set_user, "Administrator")
		self._links = patch.object(Document, "_validate_links", lambda self: None)
		self._links.start()
		self.addCleanup(self._links.stop)
		self.flex_item = _catalogue_item("Flex")
		self.fixed_item = _catalogue_item("Fixed")
		if not (self.flex_item and self.fixed_item):
			self.skipTest("The catalogue needs a Flex and a Fixed package")
		self.customer = self._customer()

	def _customer(self):
		name = "Coupon Plan Customer"
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_type": "Company",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
					"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
				}
			).insert(ignore_permissions=True)
		return name


class TestCouponPlanValidation(CouponPlanCase):
	def test_existing_style_coupon_defaults_to_flex(self):
		doc = _coupon()
		self.assertEqual(doc.applies_to, "Flex")
		self.assertEqual(doc.fixed_discount_percent, 0)

	def test_fixed_coupon_needs_a_discount_and_gives_no_tokens(self):
		self.assertRaises(frappe.ValidationError, _coupon, applies_to="Fixed", fixed_discount_percent=0)
		self.assertRaises(frappe.ValidationError, _coupon, applies_to="Fixed", fixed_discount_percent=101)
		doc = _coupon(applies_to="Fixed", fixed_discount_percent=5, value_type=None, value=0)
		self.assertEqual((doc.value_type, doc.value, doc.max_tokens), (None, 0, 0))

	def test_both_needs_tokens_and_a_discount(self):
		self.assertRaises(frappe.ValidationError, _coupon, applies_to="Both", fixed_discount_percent=5, value=0)
		self.assertRaises(frappe.ValidationError, _coupon, applies_to="Both", fixed_discount_percent=0)
		doc = _coupon(applies_to="Both", fixed_discount_percent=7.5, value=300)
		self.assertEqual((doc.applies_to, doc.fixed_discount_percent, doc.value), ("Both", 7.5, 300))

	def test_plan_is_immutable_once_used(self):
		doc = _coupon(applies_to="Both", fixed_discount_percent=5)
		frappe.get_doc(
			{"doctype": "CRM Coupon Redemption", "coupon": doc.name, "facility_mfl": "PS-IMM", "status": "Reserved",
			 "sales_order": "SO-PS-IMM", "plan": "Fixed"}
		).insert(ignore_permissions=True)
		doc.reload()
		doc.applies_to = "Flex"
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.fixed_discount_percent = 10
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_applies_to_plan_matrix(self):
		cases = {("Flex", "Flex"): True, ("Flex", "Fixed"): False, ("Fixed", "Fixed"): True,
			("Fixed", "Flex"): False, ("Both", "Flex"): True, ("Both", "Fixed"): True, (None, "Flex"): True}
		for (applies_to, plan), expected in cases.items():
			self.assertEqual(coupons.applies_to_plan(applies_to, plan), expected, (applies_to, plan))


class TestPlanScopedResolution(CouponPlanCase):
	def _network_facility(self, mfl, **coupon):
		network = _net(f"ps-{mfl}", mfl[-6:], f"Plan Net {mfl}")
		_coupon(network=network, targeting=None, **coupon)
		_facility(mfl, network, self.customer)
		return network

	def test_flex_coupon_gives_tokens_on_flex_and_nothing_on_fixed(self):
		self._network_facility("940001", value=500)
		flex = coupons.resolve_coupon(self.customer, "940001", "FID-1", 1000)
		self.assertEqual((flex["tokens"], flex["plan"]), (500, "Flex"))
		self.assertIsNone(coupons.resolve_coupon(self.customer, "940001", "FID-1", 0, plan="Fixed"))

	def test_fixed_coupon_gives_a_discount_on_fixed_and_nothing_on_flex(self):
		self._network_facility("940002", applies_to="Fixed", fixed_discount_percent=5, value_type=None, value=0)
		self.assertIsNone(coupons.resolve_coupon(self.customer, "940002", "FID-2", 1000))
		fixed = coupons.resolve_coupon(self.customer, "940002", "FID-2", 0, plan="Fixed")
		self.assertEqual((fixed["discount_percent"], fixed["plan"], fixed["type"]), (5, "Fixed", "Partner Coupon"))
		self.assertNotIn("tokens", fixed)

	def test_both_coupon_gives_each_plan_its_own_benefit(self):
		self._network_facility("940003", applies_to="Both", fixed_discount_percent=10, value=250)
		self.assertEqual(coupons.resolve_coupon(self.customer, "940003", "FID-3", 1000)["tokens"], 250)
		self.assertEqual(coupons.resolve_coupon(self.customer, "940003", "FID-3", 0, plan="Fixed")["discount_percent"], 10)

	def test_global_fallback_tokens_are_flex_only(self):
		frappe.db.set_single_value("CRM Opt-In Settings", "partner_coupon_tokens", 150)
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")
		network = _net("ps-fallback", "940004", "Plan Net Fallback")
		_facility("940004", network, self.customer)
		self.assertEqual(coupons.resolve_coupon(self.customer, "940004", "FID-4", 100)["tokens"], 150)
		self.assertIsNone(coupons.resolve_coupon(self.customer, "940004", "FID-4", 0, plan="Fixed"))

	def test_crm_coupon_candidates_are_plan_scoped(self):
		flex = _coupon(coupon_title="crm flex", value=900)
		fixed = _coupon(coupon_title="crm fixed", applies_to="Fixed", fixed_discount_percent=12, value_type=None, value=0)
		for c in (flex, fixed):
			frappe.get_doc({"doctype": "CRM Coupon Assignment", "coupon": c.name, "facility_mfl": "940005"}).insert(
				ignore_permissions=True
			)
		_facility("940005", None, self.customer, partner_coupon=False)
		self.assertEqual(coupons.resolve_coupon(self.customer, "940005", "FID-5", 1000)["coupon"], flex.name)
		self.assertEqual(coupons.resolve_coupon(self.customer, "940005", "FID-5", 0, plan="Fixed")["coupon"], fixed.name)

	def test_public_offer_carries_both_benefits(self):
		network = self._network_facility("940006", applies_to="Both", fixed_discount_percent=5, value=500)
		offer = coupons.public_offer(network)
		self.assertEqual((offer["applies_to"], offer["value"], offer["fixed_discount_percent"]), ("Both", 500, 5))


class TestFixedDiscountOnOrders(CouponPlanCase):
	def _row(self, item, rate=10000, **kw):
		return frappe._dict(item_code=item, qty=1, price_list_rate=rate, rate=rate, amount=rate, **kw)

	def test_fixed_order_gets_the_discount_on_its_package_line_and_no_bonus_lines(self):
		resolved = {"type": "Partner Coupon", "coupon": "CPN-FIX", "discount_percent": 5, "label": "x", "plan": "Fixed"}
		row = self._row(self.fixed_item)
		order = _Doc(name="SO-PS-1", customer=self.customer, crm_token_package_item=self.fixed_item,
			crm_token_facility_mfl="940101", crm_token_facility_fid="FID-PS-1", items=[row])
		with patch.object(token_bonus, "_installed", return_value=True), patch.object(
			coupons, "resolve_coupon", return_value=resolved
		) as resolve:
			applied = token_bonus.apply_bonus_lines(order)
		self.assertEqual(resolve.call_args.kwargs["plan"], "Fixed")
		self.assertEqual(applied[0]["type"], token_bonus.FIXED_DISCOUNT)
		self.assertEqual(len(order.items), 1)
		line = order.items[0]
		self.assertEqual((line.crm_coupon, line.discount_percentage, line.rate, line.discount_amount), ("CPN-FIX", 5, 9500, 500))
		# Re-applying with no coupon restores the list price.
		with patch.object(token_bonus, "_installed", return_value=True), patch.object(coupons, "resolve_coupon", return_value=None):
			token_bonus.apply_bonus_lines(order)
		self.assertEqual((line.crm_coupon, line.discount_percentage, line.rate), (None, 0, 10000))

	def test_claim_records_a_fixed_discount_redemption(self):
		c = _coupon(applies_to="Fixed", fixed_discount_percent=5, value_type=None, value=0)
		row = self._row(self.fixed_item, crm_coupon=c.name)
		token_bonus._set_line_discount(row, 5)
		coupons.claim_on_submit(_order("SO-PS-2", self.fixed_item, self.customer, "940102", [row]))
		red = frappe.db.get_value(
			"CRM Coupon Redemption", {"sales_order": "SO-PS-2"},
			["status", "plan", "bonus_type", "discount_percent", "discount_amount", "tokens_awarded", "ledger_key"], as_dict=True,
		)
		self.assertEqual((red.status, red.plan, red.bonus_type), ("Reserved", "Fixed", "Fixed Discount"))
		self.assertEqual((red.discount_percent, red.discount_amount, red.tokens_awarded, red.ledger_key), (5, 500, 0, None))
		self.assertEqual(frappe.db.get_value("CRM Coupon", c.name, "redeemed_count"), 1)

	def test_claim_refuses_a_coupon_used_on_the_wrong_plan(self):
		flex_coupon = _coupon(value=500)
		fixed_coupon = _coupon(coupon_title="fixed only", applies_to="Fixed", fixed_discount_percent=5, value_type=None, value=0)
		# A Flex coupon as a discount on a Fixed order.
		row = self._row(self.fixed_item, crm_coupon=flex_coupon.name)
		with self.assertRaisesRegex(frappe.ValidationError, "Flex token packages only"):
			coupons.claim_on_submit(_order("SO-PS-3", self.fixed_item, self.customer, "940103", [row]))
		# A Fixed coupon as a token line on a Flex order.
		line = frappe._dict(crm_bonus_type="Partner Coupon", crm_bonus_tokens=500, crm_coupon=fixed_coupon.name, item_code="CV-TOKEN-BONUS", qty=1)
		with self.assertRaisesRegex(frappe.ValidationError, "Fixed plans only"):
			coupons.claim_on_submit(_order("SO-PS-4", self.flex_item, self.customer, "940104", [self._row(self.flex_item), line]))
		# Any complimentary token line on a Fixed order (P-107).
		with self.assertRaisesRegex(frappe.ValidationError, "Flex token packages only"):
			coupons.claim_on_submit(_order("SO-PS-5", self.fixed_item, self.customer, "940105", [self._row(self.fixed_item), line]))
		self.assertFalse(frappe.db.exists("CRM Coupon Redemption", {"sales_order": ["in", ["SO-PS-3", "SO-PS-4", "SO-PS-5"]]}))

	def test_fixed_redemption_is_granted_when_its_invoice_is_paid(self):
		c = _coupon(applies_to="Fixed", fixed_discount_percent=5, value_type=None, value=0)
		red = frappe.get_doc(
			{"doctype": "CRM Coupon Redemption", "coupon": c.name, "facility_mfl": "940106", "status": "Reserved",
			 "sales_order": "SO-PS-6", "plan": "Fixed", "bonus_type": "Fixed Discount"}
		).insert(ignore_permissions=True)
		with patch.object(frappe, "get_all", side_effect=lambda dt, *a, **k: ["SO-PS-6"] if dt == "Sales Invoice Item" and k.get("pluck") == "sales_order" else _real_get_all(dt, *a, **k)):
			settled = coupons.settle_fixed_discount_for_invoice("SINV-PS-6")
		self.assertEqual(settled, [red.name])
		red.reload()
		self.assertEqual((red.status, red.sales_invoice, red.tokens_awarded), ("Granted", "SINV-PS-6", 0))

	def test_reconcile_settles_fixed_rows_by_paid_invoice(self):
		c = _coupon(applies_to="Fixed", fixed_discount_percent=5, value_type=None, value=0)
		red = frappe.get_doc(
			{"doctype": "CRM Coupon Redemption", "coupon": c.name, "facility_mfl": "940107", "status": "Reserved",
			 "sales_order": "SO-PS-7", "plan": "Fixed", "bonus_type": "Fixed Discount"}
		).insert(ignore_permissions=True)
		with patch.object(coupons, "_paid_invoice_for_order", return_value=None):
			coupons.reconcile_redemptions()
		self.assertEqual(frappe.db.get_value("CRM Coupon Redemption", red.name, "status"), "Reserved")
		with patch.object(coupons, "_paid_invoice_for_order", return_value="SINV-PS-7"):
			coupons.reconcile_redemptions()
		self.assertEqual(frappe.db.get_value("CRM Coupon Redemption", red.name, "status"), "Granted")


_real_get_all = frappe.get_all


class TestFlexOnlyBonus(CouponPlanCase):
	def _sales_order(self, item, mfl, docstatus=0):
		name = frappe.generate_hash(length=10)
		frappe.db.sql(
			"""insert into `tabSales Order` (name, docstatus, customer, crm_token_package_item, crm_token_facility_mfl,
			company, transaction_date, creation, modified) values (%s, %s, %s, %s, %s, %s, curdate(), now(), now())""",
			(name, docstatus, self.customer, item, mfl, frappe.get_all("Company", pluck="name")[0]),
		)
		return name

	def test_flex_purchase_means_a_live_flex_package_order(self):
		self.assertFalse(token_bonus.has_flex_purchase(facility_mfl="940201"))
		self._sales_order(self.fixed_item, "940201", docstatus=1)
		self.assertFalse(token_bonus.has_flex_purchase(facility_mfl="940201"), "a Fixed order is not a Flex purchase")
		self._sales_order(self.flex_item, "940201", docstatus=2)
		self.assertFalse(token_bonus.has_flex_purchase(facility_mfl="940201"), "a cancelled order does not count")
		self._sales_order(self.flex_item, "940201", docstatus=0)
		self.assertTrue(token_bonus.has_flex_purchase(facility_mfl="940201"))

	def test_flex_purchase_found_from_the_fid_through_its_mfl(self):
		_facility("940202", None, self.customer, partner_coupon=False)
		frappe.db.set_value("CRM Pre-Qualified Facility", {"mfl_code": "940202"}, "hfr_facility_id", "FID-PS-202")
		self._sales_order(self.flex_item, "940202", docstatus=1)
		self.assertTrue(token_bonus.has_flex_purchase("FID-PS-202"))

	def test_dispense_is_refused_without_a_flex_purchase(self):
		with patch.object(token_bonus, "_hook", return_value=lambda *a, **k: {"dispensed": True}), patch.object(
			token_bonus, "has_flex_purchase", return_value=False
		):
			with self.assertRaisesRegex(frappe.ValidationError, "bought a Flex token package"):
				token_bonus.dispense_welcome_bonus("FID-PS-NONE", "User", "Administrator")

	def test_metering_card_says_whether_the_bonus_can_be_given(self):
		from crm.api import metering_admin

		with patch.object(token_bonus, "has_flex_purchase", return_value=False):
			self.assertFalse(metering_admin._welcome_bonus_view("FID-PS-X")["flex_purchase"])
		with patch.object(token_bonus, "has_flex_purchase", return_value=True):
			self.assertTrue(metering_admin._welcome_bonus_view("FID-PS-X")["flex_purchase"])


class TestCustomerSubscription(CouponPlanCase):
	def test_portal_facilities_carry_the_subscription_term(self):
		from crm.api import website_redirect

		plan = {
			"plan_type": "subscription",
			"subscription": {"status": "active", "package": "Fixed L2", "billing_period": "Monthly",
				"activated_at": "2026-11-09T10:00:00Z", "expires_at": "2026-12-09T10:00:00Z", "cancelled_at": None,
				"package_item": "CV-FIXED-L2"},
			"terms": [{"invoice": "SINV-SECRET"}],
		}
		accounts = [{"facilities": [{"hfr_facility_id": "FID-PS-SUB"}, {"hfr_facility_id": "FID-PS-NONE"}]}]
		with patch.object(website_redirect, "fetch_facility_token_balances", return_value={}), patch(
			"frappe.get_hooks", side_effect=lambda name=None, *a, **k: ["x.y"] if name == "crm_get_facility_plan" else []
		), patch("frappe.get_attr", return_value=lambda fid: plan if fid == "FID-PS-SUB" else {"plan_type": "none"}):
			website_redirect._attach_token_balances(accounts)
		with_sub, without = accounts[0]["facilities"]
		self.assertEqual(with_sub["subscription"]["expires_at"], "2026-12-09T10:00:00Z")
		# Only the customer-facing fields: no invoices or item codes.
		self.assertEqual(
			set(with_sub["subscription"]), {"status", "package", "billing_period", "activated_at", "expires_at", "cancelled_at"}
		)
		self.assertNotIn("subscription", without)
