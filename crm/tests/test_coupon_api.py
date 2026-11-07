"""Coupon admin API: save, revoke (terminal), assign, list, release, scope."""

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from crm.api import coupons as api


class TestCouponApi(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("coupon_api_test")
		self.addCleanup(frappe.db.rollback, save_point="coupon_api_test")
		self.addCleanup(frappe.set_user, "Administrator")
		# Redemption rows here reference synthetic order names; skip the sales_order link check.
		self._link_patch = patch.object(Document, "_validate_links", lambda self: None)
		self._link_patch.start()
		self.addCleanup(self._link_patch.stop)

	def _customer(self):
		name = "Coupon Api Customer"
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

	def _network(self, slug, pid, name):
		return frappe.get_doc(
			{"doctype": "CRM Opt-In Network", "slug": slug, "display_name": name, "partner_id": pid, "enabled": 1}
		).insert(ignore_permissions=True).name

	def test_save_creates_and_get_returns(self):
		net = self._network("api-a", "940001", "API A")
		res = api.save_coupon("", {"coupon_title": "API coupon", "network": net, "value_type": "flat_tokens", "value": 200})
		name = res["name"]
		self.assertTrue(name)
		got = api.get_coupon(name)
		self.assertEqual(got["value_type"], "flat_tokens")
		self.assertEqual(got["derived_status"], "Active")

	def test_revoke_is_terminal(self):
		net = self._network("api-b", "940002", "API B")
		name = api.save_coupon("", {"coupon_title": "rev", "network": net, "value_type": "flat_tokens", "value": 100})["name"]
		api.revoke_coupon(name, "policy")
		row = frappe.db.get_value("CRM Coupon", name, ["status", "revoked_by", "revocation_reason"], as_dict=True)
		self.assertEqual(row.status, "Revoked")
		self.assertEqual(row.revoked_by, "Administrator")
		self.assertEqual(row.revocation_reason, "policy")
		# terminal: a second revoke is a no-op, not an error
		self.assertEqual(api.revoke_coupon(name)["status"], "Revoked")
		self.assertTrue(frappe.db.get_value("CRM Coupon", name, "revoked_on"))

	def test_assign_requires_crm_coupon_and_active(self):
		net = self._network("api-c", "940003", "API C")
		net_coupon = api.save_coupon("", {"coupon_title": "net", "network": net, "value_type": "flat_tokens", "value": 100})["name"]
		with self.assertRaises(frappe.ValidationError):
			api.assign_coupon(net_coupon, "940101")
		crm = api.save_coupon("", {"coupon_title": "crm", "value_type": "flat_tokens", "value": 100, "targeting": "Assigned Facilities"})["name"]
		res1 = api.assign_coupon(crm, "940101")
		res2 = api.assign_coupon(crm, "940101")
		self.assertEqual(res1["assigned"], ["940101"])
		self.assertEqual(res2["already"], ["940101"])
		self.assertEqual(len(api.list_assignments(crm)["assignments"]), 1)

	def test_release_redemption_requires_admin(self):
		net = self._network("api-d", "940004", "API D")
		name = api.save_coupon("", {"coupon_title": "rel", "network": net, "value_type": "flat_tokens", "value": 100})["name"]
		red = frappe.get_doc(
			{"doctype": "CRM Coupon Redemption", "coupon": name, "facility_mfl": "940102", "sales_order": "SO-X", "status": "Reserved"}
		).insert(ignore_permissions=True).name
		frappe.set_user("guest@none.test")
		with self.assertRaises(Exception):
			api.release_redemption(red)
		frappe.set_user("Administrator")
		self.assertEqual(api.release_redemption(red, "never paid")["status"], "Released")
		self.assertEqual(frappe.db.get_value("CRM Coupon", name, "redeemed_count"), 0)

	def test_list_redemptions_filters_by_coupon(self):
		net = self._network("api-e", "940005", "API E")
		name = api.save_coupon("", {"coupon_title": "lst", "network": net, "value_type": "flat_tokens", "value": 100})["name"]
		frappe.get_doc(
			{"doctype": "CRM Coupon Redemption", "coupon": name, "facility_mfl": "940103", "sales_order": "SO-Y", "status": "Reserved"}
		).insert(ignore_permissions=True)
		rows = api.list_redemptions(coupon=name)["redemptions"]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["facility_mfl"], "940103")

	def test_redeem_code_invalid(self):
		frappe.set_user("guest@none.test")
		with self.assertRaises(Exception):
			api.redeem_code("NOPE", self._customer(), "940104")
