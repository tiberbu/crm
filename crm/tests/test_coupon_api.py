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
		return (
			frappe.get_doc(
				{
					"doctype": "CRM Opt-In Network",
					"slug": slug,
					"display_name": name,
					"partner_id": pid,
					"enabled": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_save_creates_and_get_returns(self):
		net = self._network("api-a", "940001", "API A")
		res = api.save_coupon(
			"", {"coupon_title": "API coupon", "network": net, "value_type": "flat_tokens", "value": 200}
		)
		name = res["name"]
		self.assertTrue(name)
		got = api.get_coupon(name)
		self.assertEqual(got["value_type"], "flat_tokens")
		# New coupons start Inactive; the card carries the network name and who created it.
		self.assertEqual(got["status"], "Inactive")
		self.assertEqual(got["derived_status"], "Inactive")
		self.assertEqual(got["network_name"], "API A")
		self.assertEqual(got["owner"], "Administrator")
		self.assertTrue(got["creation"])
		self.assertTrue(got["created_by_name"])

	def test_enable_disable_and_revoke_lifecycle(self):
		net = self._network("api-e", "940005", "API E")
		name = api.save_coupon(
			"", {"coupon_title": "toggle", "network": net, "value_type": "flat_tokens", "value": 100}
		)["name"]
		self.assertEqual(api.enable_coupon(name)["status"], "Active")
		self.assertEqual(api.get_coupon(name)["derived_status"], "Active")
		row = api.get_coupon(name)
		self.assertTrue(row["enabled_on"])
		self.assertEqual(row["enabled_by"], "Administrator")
		self.assertTrue(row["enabled_by_name"])
		self.assertIsNone(row["disabled_on"])
		self.assertEqual(api.disable_coupon(name)["status"], "Inactive")
		row = api.get_coupon(name)
		self.assertEqual(row["derived_status"], "Inactive")
		self.assertTrue(row["disabled_on"])
		self.assertEqual(row["disabled_by"], "Administrator")
		# A no-op toggle does not move the timestamps.
		before = row["disabled_on"]
		api.disable_coupon(name)
		self.assertEqual(api.get_coupon(name)["disabled_on"], before)
		api.revoke_coupon(name, "policy")
		row = api.get_coupon(name)
		self.assertEqual(row["revocation_reason"], "policy")
		self.assertTrue(row["revoked_by_name"])
		with self.assertRaises(frappe.ValidationError):
			api.enable_coupon(name)
		with self.assertRaises(frappe.ValidationError):
			api.disable_coupon(name)

	def test_enable_refuses_an_overlapping_live_coupon(self):
		net = self._network("api-f", "940006", "API F")
		first = api.save_coupon(
			"", {"coupon_title": "one", "network": net, "value_type": "flat_tokens", "value": 100}
		)["name"]
		second = api.save_coupon(
			"", {"coupon_title": "two", "network": net, "value_type": "flat_tokens", "value": 100}
		)["name"]
		api.enable_coupon(first)
		with self.assertRaises(frappe.ValidationError):
			api.enable_coupon(second)
		self.assertEqual(frappe.db.get_value("CRM Coupon", second, "status"), "Inactive")

	def test_list_coupons_returns_network_name_for_search(self):
		net = self._network("api-g", "940007", "Searchable Network")
		api.save_coupon("", {"coupon_title": "s", "network": net, "value_type": "flat_tokens", "value": 1})
		rows = [r for r in api.list_coupons()["coupons"] if r.network == net]
		self.assertEqual(rows[0]["network_name"], "Searchable Network")

	def test_revoke_is_terminal(self):
		net = self._network("api-b", "940002", "API B")
		name = api.save_coupon(
			"", {"coupon_title": "rev", "network": net, "value_type": "flat_tokens", "value": 100}
		)["name"]
		api.revoke_coupon(name, "policy")
		row = frappe.db.get_value(
			"CRM Coupon", name, ["status", "revoked_by", "revocation_reason"], as_dict=True
		)
		self.assertEqual(row.status, "Revoked")
		self.assertEqual(row.revoked_by, "Administrator")
		self.assertEqual(row.revocation_reason, "policy")
		# terminal: a second revoke is a no-op, not an error
		self.assertEqual(api.revoke_coupon(name)["status"], "Revoked")
		self.assertTrue(frappe.db.get_value("CRM Coupon", name, "revoked_on"))

	def test_assign_requires_crm_coupon_and_not_revoked(self):
		net = self._network("api-c", "940003", "API C")
		net_coupon = api.save_coupon(
			"", {"coupon_title": "net", "network": net, "value_type": "flat_tokens", "value": 100}
		)["name"]
		with self.assertRaises(frappe.ValidationError):
			api.assign_coupon(net_coupon, "940101")
		crm = api.save_coupon(
			"",
			{
				"coupon_title": "crm",
				"value_type": "flat_tokens",
				"value": 100,
				"targeting": "Assigned Facilities",
			},
		)["name"]
		res1 = api.assign_coupon(crm, "940101")
		res2 = api.assign_coupon(crm, "940101")
		self.assertEqual(res1["assigned"], ["940101"])
		self.assertEqual(res2["already"], ["940101"])
		self.assertEqual(len(api.list_assignments(crm)["assignments"]), 1)
		api.revoke_coupon(crm)
		with self.assertRaises(frappe.ValidationError):
			api.assign_coupon(crm, "940102")

	def test_release_redemption_requires_admin(self):
		net = self._network("api-d", "940004", "API D")
		name = api.save_coupon(
			"", {"coupon_title": "rel", "network": net, "value_type": "flat_tokens", "value": 100}
		)["name"]
		red = (
			frappe.get_doc(
				{
					"doctype": "CRM Coupon Redemption",
					"coupon": name,
					"facility_mfl": "940102",
					"sales_order": "SO-X",
					"status": "Reserved",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		frappe.set_user("guest@none.test")
		with self.assertRaises(Exception):
			api.release_redemption(red)
		frappe.set_user("Administrator")
		self.assertEqual(api.release_redemption(red, "never paid")["status"], "Released")
		self.assertEqual(frappe.db.get_value("CRM Coupon", name, "redeemed_count"), 0)

	def test_list_redemptions_filters_by_coupon(self):
		net = self._network("api-e", "940005", "API E")
		name = api.save_coupon(
			"", {"coupon_title": "lst", "network": net, "value_type": "flat_tokens", "value": 100}
		)["name"]
		frappe.get_doc(
			{
				"doctype": "CRM Coupon Redemption",
				"coupon": name,
				"facility_mfl": "940103",
				"sales_order": "SO-Y",
				"status": "Reserved",
			}
		).insert(ignore_permissions=True)
		rows = api.list_redemptions(coupon=name)["redemptions"]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["facility_mfl"], "940103")

	def test_redeem_code_invalid(self):
		frappe.set_user("guest@none.test")
		with self.assertRaises(Exception):
			api.redeem_code("NOPE", self._customer(), "940104")
