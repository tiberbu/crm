from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

IMMUTABLE = ("network", "value_type", "value", "max_tokens", "targeting")


def _doc(**overrides):
	base = {
		"doctype": "CRM Coupon",
		"coupon_title": "Test coupon",
		"network": None,
		"value_type": "flat_tokens",
		"value": 100,
		"max_tokens": 0,
		"valid_from": None,
		"valid_to": None,
		"status": "Active",
		"max_redemptions": 0,
		"per_facility_limit": 1,
		"redeemed_count": 0,
		"targeting": "Coupon Code",
		"facility_levels": "",
		"coupon_code": "WELCOME",
	}
	base.update(overrides)
	return frappe.get_doc(base)


class TestCRMCouponValidation(UnitTestCase):
	def _validate(self, doc):
		doc.validate()
		return doc

	def test_flat_valid(self):
		self._validate(_doc())

	def test_flat_value_must_be_whole_and_in_range(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(value=0.5))
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(value=0))
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(value=1_000_001))

	def test_percentage_value_must_be_positive_and_le_100(self):
		self._validate(_doc(value_type="percentage_of_purchase", value=5))
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(value_type="percentage_of_purchase", value=0))
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(value_type="percentage_of_purchase", value=101))

	def test_cap_range(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(max_tokens=1_000_001))
		self._validate(_doc(max_tokens=500))

	def test_valid_to_must_be_after_valid_from(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(valid_from=frappe.utils.getdate("2026-06-01"), valid_to=frappe.utils.getdate("2026-05-01")))

	def test_max_redemptions_cannot_drop_below_redeemed(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(max_redemptions=2, redeemed_count=5))

	def test_per_facility_limit_fixed_at_one(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(per_facility_limit=2))

	def test_network_coupon_clears_targeting(self):
		# A network coupon cannot carry targeting; the controller clears it (no error).
		doc = self._validate(_doc(network="NET-1", targeting="Coupon Code", coupon_code="WELCOME"))
		self.assertIsNone(doc.targeting)

	def test_crm_coupon_requires_targeting(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(targeting=None))

	def test_crm_assigned_facilities_is_valid(self):
		self._validate(_doc(targeting="Assigned Facilities", coupon_code=None))

	def test_facility_level_needs_levels(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(targeting="Facility Level", facility_levels=""))

	def test_coupon_code_required_for_code_targeting(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(targeting="Coupon Code", coupon_code=""))

	def test_coupon_code_cannot_be_six_digits(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(targeting="Coupon Code", coupon_code="123456"))

	def test_coupon_code_charset(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(_doc(targeting="Coupon Code", coupon_code="bad code!"))

	def test_code_is_normalised_to_upper(self):
		doc = self._validate(_doc(targeting="Coupon Code", coupon_code="welcome"))
		self.assertEqual(doc.coupon_code, "WELCOME")


class TestCRMCouponImmutability(UnitTestCase):
	def test_immutable_field_change_rejected_after_redemption(self):
		doc = _doc(targeting="Assigned Facilities", coupon_code=None, value=200)
		previous = frappe._dict({f: getattr(doc, f) for f in IMMUTABLE})
		previous.value = 100  # differs from the current 200
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", return_value=previous),
			patch.object(doc, "is_new", return_value=False),
		):
			with self.assertRaises(frappe.ValidationError):
				doc._enforce_immutability()

	def test_no_redemption_allows_change(self):
		doc = _doc(targeting="Assigned Facilities", coupon_code=None)
		with (
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(doc, "is_new", return_value=False),
		):
			doc._enforce_immutability()  # no raise


class TestCRMCouponOverlap(UnitTestCase):
	def test_overlapping_active_coupon_rejected(self):
		doc = _doc(network="NET-1", targeting=None, coupon_code=None, valid_from=frappe.utils.getdate("2026-01-01"), valid_to=frappe.utils.getdate("2026-12-31"))
		other = frappe._dict(valid_from=frappe.utils.getdate("2026-06-01"), valid_to=frappe.utils.getdate("2026-09-30"))
		with patch.object(frappe, "get_all", return_value=[other]):
			with self.assertRaises(frappe.ValidationError):
				doc._reject_network_overlap()

	def test_revoked_or_disjoint_does_not_block(self):
		doc = _doc(network="NET-1", targeting=None, coupon_code=None, valid_from=frappe.utils.getdate("2026-01-01"), valid_to=frappe.utils.getdate("2026-03-31"))
		other = frappe._dict(valid_from=frappe.utils.getdate("2026-04-01"), valid_to=frappe.utils.getdate("2026-12-31"))
		with patch.object(frappe, "get_all", return_value=[other]):
			doc._reject_network_overlap()  # no raise (disjoint windows)
