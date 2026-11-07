"""Coupon claim/release/outcome: the CRM-side lifecycle and count handling."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from crm.utils import coupons


def _order(doc_name, mfl, fid, customer, coupon, stamped, bonus_type="Partner Coupon"):
	# The order is a plain namespace (no .get needed); its item lines are _dict so they support
	# both attribute access and .get() as claim_on_submit/purchased_tokens expect.
	return SimpleNamespace(
		name=doc_name,
		customer=customer,
		crm_token_facility_mfl=mfl,
		crm_token_facility_fid=fid,
		items=[frappe._dict(crm_bonus_type=bonus_type, crm_bonus_tokens=stamped, crm_coupon=coupon)],
	)


class TestCouponRedemptionFlow(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("coupon_flow_test")
		self.addCleanup(frappe.db.rollback, save_point="coupon_flow_test")
		self.addCleanup(frappe.set_user, "Administrator")
		# The order names here are synthetic (no real Sales Order doc); skip the sales_order link
		# check so we can exercise the claim/release logic in isolation.
		self._link_patch = patch.object(Document, "_validate_links", lambda self: None)
		self._link_patch.start()
		self.addCleanup(self._link_patch.stop)
		self.customer = self._customer()

	def _customer(self):
		name = "Coupon Flow Customer"
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

	def _coupon(self, **kw):
		base = {"coupon_title": "flow coupon", "value_type": "flat_tokens", "value": 1000, "max_tokens": 0, "targeting": "Assigned Facilities"}
		base.update(kw)
		return frappe.get_doc({"doctype": "CRM Coupon", **base}).insert(ignore_permissions=True).name

	def test_claim_creates_reserved_and_overwrites_stamped(self):
		c = self._coupon()
		doc = _order("SO-C1", "930001", "FID-C1", self.customer, c, 999)
		coupons.claim_on_submit(doc)
		row = frappe.db.get_value("CRM Coupon Redemption", {"sales_order": "SO-C1"}, ["status", "tokens_awarded"], as_dict=True)
		self.assertEqual(row.status, "Reserved")
		self.assertEqual(row.tokens_awarded, 1000)  # server value (1000) wins over stamped (999)
		self.assertEqual(frappe.db.get_value("CRM Coupon", c, "redeemed_count"), 1)

	def test_claim_is_idempotent(self):
		c = self._coupon()
		doc = _order("SO-C2", "930002", "FID-C2", self.customer, c, 1000)
		coupons.claim_on_submit(doc)
		coupons.claim_on_submit(doc)
		self.assertEqual(len(frappe.get_all("CRM Coupon Redemption", {"sales_order": "SO-C2"})), 1)
		self.assertEqual(frappe.db.get_value("CRM Coupon", c, "redeemed_count"), 1)

	def test_claim_rejects_non_active_coupon(self):
		c = self._coupon()
		frappe.db.set_value("CRM Coupon", c, "status", "Revoked")
		doc = _order("SO-C3", "930003", "FID-C3", self.customer, c, 1000)
		with self.assertRaises(frappe.ValidationError):
			coupons.claim_on_submit(doc)
		self.assertFalse(frappe.db.exists("CRM Coupon Redemption", {"sales_order": "SO-C3"}))

	def test_claim_uses_for_update_on_the_coupon_read(self):
		c = self._coupon()
		with patch.object(coupons.frappe.db, "get_value", wraps=frappe.db.get_value) as spy:
			coupons.claim_on_submit(_order("SO-C4", "930004", "FID-C4", self.customer, c, 1000))
		coupon_reads = [call for call in spy.call_args_list if call.args and call.args[0] == "CRM Coupon"]
		self.assertTrue(any(call.kwargs.get("for_update") for call in coupon_reads))

	def test_facility_guard_collision_is_unavailable(self):
		c = self._coupon()
		frappe.get_doc(
			{"doctype": "CRM Coupon Redemption", "facility_mfl": "930005", "sales_order": "SO-OTHER", "status": "Reserved"}
		).insert(ignore_permissions=True)
		doc = _order("SO-C5", "930005", "FID-C5", self.customer, c, 1000)
		with self.assertRaises(frappe.ValidationError):
			coupons.claim_on_submit(doc)

	def test_query_deadlock_is_unavailable(self):
		c = self._coupon()
		real_get_doc = coupons.frappe.get_doc

		def _raise_on_dict(*args, **kwargs):
			# Only the redemption creation (a dict doc) should deadlock; the get_single call inside
			# purchased_tokens passes a doctype string and must keep working.
			if args and isinstance(args[0], dict):
				raise frappe.QueryDeadlockError("locked")
			return real_get_doc(*args, **kwargs)

		with patch.object(coupons.frappe, "get_doc", side_effect=_raise_on_dict):
			with self.assertRaises(frappe.ValidationError):
				coupons.claim_on_submit(_order("SO-C6", "930006", "FID-C6", self.customer, c, 1000))

	def test_cancel_releases_reserved_and_returns_count(self):
		c = self._coupon()
		doc = _order("SO-C7", "930007", "FID-C7", self.customer, c, 1000)
		coupons.claim_on_submit(doc)
		self.assertEqual(frappe.db.get_value("CRM Coupon", c, "redeemed_count"), 1)
		coupons.release_on_cancel(frappe._dict(name="SO-C7"))
		self.assertEqual(frappe.db.get_value("CRM Coupon", c, "redeemed_count"), 0)
		row = frappe.db.get_value("CRM Coupon Redemption", {"sales_order": "SO-C7"}, ["status", "facility_guard"], as_dict=True)
		self.assertEqual(row.status, "Released")
		self.assertFalse(row.facility_guard)  # guard cleared (NULL) so the facility is free

	def test_record_grant_outcome_granted_keeps_count(self):
		c = self._coupon()
		doc = _order("SO-C8", "930008", "FID-C8", self.customer, c, 1000)
		coupons.claim_on_submit(doc)
		red = frappe.db.get_value("CRM Coupon Redemption", {"sales_order": "SO-C8"}, "name")
		coupons.record_grant_outcome(red, "Granted", tokens=1000, invoice="INV-1")
		self.assertEqual(frappe.db.get_value("CRM Coupon Redemption", red, "status"), "Granted")
		self.assertEqual(frappe.db.get_value("CRM Coupon", c, "redeemed_count"), 1)  # unchanged
		# idempotent: a second call is a no-op
		coupons.record_grant_outcome(red, "Lapsed", reason="x")
		self.assertEqual(frappe.db.get_value("CRM Coupon Redemption", red, "status"), "Granted")

	def test_record_grant_outcome_lapsed_reduces_count(self):
		c = self._coupon()
		doc = _order("SO-C9", "930009", "FID-C9", self.customer, c, 1000)
		coupons.claim_on_submit(doc)
		red = frappe.db.get_value("CRM Coupon Redemption", {"sales_order": "SO-C9"}, "name")
		coupons.record_grant_outcome(red, "Lapsed", reason="revoked", invoice="INV-2")
		self.assertEqual(frappe.db.get_value("CRM Coupon Redemption", red, "status"), "Lapsed")
		self.assertEqual(frappe.db.get_value("CRM Coupon", c, "redeemed_count"), 0)
