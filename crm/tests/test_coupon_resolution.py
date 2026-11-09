"""Coupon resolution: partner vs CRM coupons, value rules, fallback, precedence, already-used."""

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from crm.utils import coupons


def _net(slug, partner_id, name):
	return (
		frappe.get_doc(
			{
				"doctype": "CRM Opt-In Network",
				"slug": slug,
				"display_name": name,
				"partner_id": partner_id,
				"enabled": 1,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _coupon(network=None, value_type="flat_tokens", value=100, max_tokens=0, targeting=None, **kw):
	return (
		frappe.get_doc(
			{
				"doctype": "CRM Coupon",
				"coupon_title": kw.pop("coupon_title", "test coupon"),
				"network": network,
				"value_type": value_type,
				"value": value,
				"max_tokens": max_tokens,
				"targeting": targeting,
				**kw,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _facility(mfl, network, customer, partner_coupon=True, level="Level 2"):
	# A membership always points at a network record; a facility without a partner coupon uses the
	# dedicated "no-network" record (never blank).
	if not network:
		network = "no-network"
	return (
		frappe.get_doc(
			{
				"doctype": "CRM Pre-Qualified Facility",
				"mfl_code": mfl,
				"facility_name": "Coupon Facility %s" % mfl,
				"keph_level": level,
				"memberships": [
					{
						"network": network,
						"customer": customer,
						"status": "Active",
						"partner_coupon": 1 if partner_coupon else 0,
						"contact_name": "Owner",
						"contact_email": "owner@example.test",
						"contact_phone": "+254700000000",
					}
				],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestCouponResolution(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("coupon_resolution_test")
		self.addCleanup(frappe.db.rollback, save_point="coupon_resolution_test")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.clear_document_cache, "CRM Opt-In Settings", "CRM Opt-In Settings")
		# test_live_redemption_blocks inserts a redemption with a synthetic order name.
		self._link_patch = patch.object(Document, "_validate_links", lambda self: None)
		self._link_patch.start()
		self.addCleanup(self._link_patch.stop)
		self.customer = self._customer()

	def _customer(self):
		name = "Coupon Resolution Customer"
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

	def _set_global(self, amount):
		frappe.db.set_single_value("CRM Opt-In Settings", "partner_coupon_tokens", amount)
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")

	def test_flat_and_percentage_stamp_different_counts(self):
		self._set_global(0)  # prove it is independent of the global
		a = _net("res-a", "920001", "Res A")
		b = _net("res-b", "920002", "Res B")
		_coupon(a, "flat_tokens", 1000)
		_coupon(b, "percentage_of_purchase", 5, max_tokens=500)
		_facility("920101", a, self.customer)
		_facility("920102", b, self.customer)
		ra = coupons.resolve_coupon(self.customer, "920101", "FID-A", 1234)
		rb = coupons.resolve_coupon(self.customer, "920102", "FID-B", 1234)
		self.assertEqual(ra["tokens"], 1000)
		self.assertEqual(ra["type"], "Partner Coupon")
		self.assertTrue(ra["coupon"])
		self.assertEqual(rb["tokens"], 61)  # floor(1234 * 5%) = 61
		self.assertTrue(rb["coupon"])

	def test_fallback_only_when_no_coupon_ever(self):
		self._set_global(150)
		none = _net("res-none", "920003", "Res None")
		_facility("920103", none, self.customer)
		self.assertEqual(coupons.resolve_coupon(self.customer, "920103", "FID-N", 100)["coupon"], None)
		self.assertEqual(coupons.resolve_coupon(self.customer, "920103", "FID-N", 100)["tokens"], 150)

	def test_revoked_expired_exhausted_do_not_fall_back(self):
		self._set_global(150)
		for slug, pid, mfl, mut in [
			(
				"res-rev",
				"920004",
				"920104",
				lambda c: frappe.db.set_value("CRM Coupon", c, "status", "Revoked"),
			),
			(
				"res-exp",
				"920005",
				"920105",
				lambda c: frappe.db.set_value("CRM Coupon", c, "valid_to", "2020-01-01"),
			),
			(
				"res-exh",
				"920006",
				"920106",
				lambda c: frappe.db.set_value("CRM Coupon", c, "redeemed_count", 5),
			),
		]:
			net = _net(slug, pid, slug.title())
			c = _coupon(net, "flat_tokens", 1000, max_redemptions=5)
			mut(c)
			_facility(mfl, net, self.customer)
			self.assertIsNone(coupons.resolve_coupon(self.customer, mfl, "FID-X", 100), slug)

	def test_crm_assigned_coupon(self):
		c = _coupon(None, "flat_tokens", 250, targeting="Assigned Facilities")
		_facility("920107", None, self.customer, partner_coupon=False)
		frappe.get_doc(
			{"doctype": "CRM Coupon Assignment", "coupon": c, "facility_mfl": "920107", "source": "Manual"}
		).insert(ignore_permissions=True)
		r = coupons.resolve_coupon(self.customer, "920107", "FID-C", 100)
		self.assertEqual(r["type"], "CRM Coupon")
		self.assertEqual(r["tokens"], 250)
		self.assertEqual(r["coupon"], c)

	def test_crm_facility_level_case_insensitive(self):
		c = _coupon(None, "flat_tokens", 300, targeting="Facility Level", facility_levels="Level 2")
		# Lowercase facility level must still match the coupon's "Level 2" (case-insensitive).
		_facility("920108", None, self.customer, partner_coupon=False, level="level 2")
		r = coupons.resolve_coupon(self.customer, "920108", "FID-L", 100)
		self.assertEqual(r["coupon"], c)

	def test_crm_coupon_no_match_gives_no_line(self):
		_coupon(None, "flat_tokens", 300, targeting="Facility Level", facility_levels="Level 5")
		_facility("920109", None, self.customer, partner_coupon=False, level="Level 2")
		self.assertIsNone(coupons.resolve_coupon(self.customer, "920109", "FID-NOMATCH", 100))

	def test_precedence_partner_over_crm_assignment(self):
		net = _net("res-pre", "920007", "Res Pre")
		_coupon(net, "flat_tokens", 1000)
		_facility("920110", net, self.customer)  # partner coupon
		crm = _coupon(None, "flat_tokens", 999, targeting="Assigned Facilities")
		frappe.get_doc(
			{"doctype": "CRM Coupon Assignment", "coupon": crm, "facility_mfl": "920110", "source": "Manual"}
		).insert(ignore_permissions=True)
		r = coupons.resolve_coupon(self.customer, "920110", "FID-P", 100)
		self.assertEqual(r["type"], "Partner Coupon")
		self.assertEqual(r["tokens"], 1000)

	def test_live_redemption_blocks(self):
		net = _net("res-used", "920008", "Res Used")
		_coupon(net, "flat_tokens", 1000)
		_facility("920111", net, self.customer)
		frappe.get_doc(
			{
				"doctype": "CRM Coupon Redemption",
				"facility_mfl": "920111",
				"sales_order": "NO-SUCH-ORDER",
				"status": "Reserved",
			}
		).insert(ignore_permissions=True)
		self.assertIsNone(coupons.resolve_coupon(self.customer, "920111", "FID-U", 100))

	def test_confirmed_coupon_line_blocks(self):
		net = _net("res-line", "920009", "Res Line")
		_coupon(net, "flat_tokens", 1000)
		_facility("920112", net, self.customer)
		with patch.object(coupons, "_facility_has_coupon_line", return_value=True):
			self.assertIsNone(coupons.resolve_coupon(self.customer, "920112", "FID-LN", 100))

	def test_dispensed_grant_blocks(self):
		net = _net("res-grant", "920010", "Res Grant")
		_coupon(net, "flat_tokens", 1000)
		_facility("920113", net, self.customer)
		with patch.object(coupons, "coupon_grant_status", return_value={"dispensed": True}):
			self.assertIsNone(coupons.resolve_coupon(self.customer, "920113", "FID-G", 100))
