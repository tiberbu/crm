"""Coupon patches: per-network seeding, default-network exclusion, zero-global, idempotence."""

import frappe
from frappe.tests import IntegrationTestCase

from crm.patches.v1_0 import seed_network_coupons


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


class TestCouponPatchSeeding(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("coupon_patch_test")
		self.addCleanup(frappe.db.rollback, save_point="coupon_patch_test")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.clear_document_cache, "CRM Opt-In Settings", "CRM Opt-In Settings")

	def _set(self, partner_coupon_tokens, default_id=""):
		frappe.db.set_single_value(
			"CRM Opt-In Settings",
			{
				"partner_coupon_tokens": partner_coupon_tokens,
				"facility_onboarding_default_partner_id": default_id,
			},
		)
		frappe.clear_document_cache("CRM Opt-In Settings", "CRM Opt-In Settings")

	def test_seed_one_coupon_per_non_default_network(self):
		a = _net("seed-a", "910001", "Seed A")
		b = _net("seed-b", "910002", "Seed B")
		self._set(150, default_id="910002")  # b is the default network
		seed_network_coupons._seed_network_coupons()
		self.assertTrue(frappe.db.exists("CRM Coupon", {"network": a}))
		self.assertFalse(frappe.db.exists("CRM Coupon", {"network": b}))

	def test_seed_carries_the_global_value_as_flat(self):
		a = _net("seed-val", "910003", "Seed Val")
		self._set(250)
		seed_network_coupons._seed_network_coupons()
		row = frappe.db.get_value("CRM Coupon", {"network": a}, ["value_type", "value"], as_dict=True)
		self.assertEqual((row.value_type, row.value), ("flat_tokens", 250))

	def test_zero_global_seeds_nothing(self):
		a = _net("seed-zero", "910004", "Seed Zero")
		self._set(0)
		seed_network_coupons._seed_network_coupons()
		self.assertFalse(frappe.db.exists("CRM Coupon", {"network": a}))

	def test_seed_is_idempotent(self):
		a = _net("seed-idem", "910005", "Seed Idem")
		self._set(100)
		seed_network_coupons._seed_network_coupons()
		seed_network_coupons._seed_network_coupons()
		self.assertEqual(len(frappe.get_all("CRM Coupon", filters={"network": a})), 1)


# The backfill behaviour (a confirmed Partner Coupon order gains a Redemption row and a coupon link)
# is exercised by the real migration on the site (see seed_network_coupons._backfill_redemptions) and
# by the Express e2e journey; it needs a full order fixture that commits, so it is not duplicated here.
