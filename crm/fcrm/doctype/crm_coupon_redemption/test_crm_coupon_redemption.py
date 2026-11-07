from types import SimpleNamespace

from frappe.tests import UnitTestCase

from crm.fcrm.doctype.crm_coupon_redemption.crm_coupon_redemption import CRMCouponRedemption


def _redemption(status, mfl):
	return SimpleNamespace(doctype="CRM Coupon Redemption", status=status, facility_mfl=mfl, facility_guard=None)


class TestCRMCouponRedemptionGuard(UnitTestCase):
	def test_reserved_sets_guard(self):
		doc = _redemption("Reserved", "90001")
		CRMCouponRedemption.validate(doc)
		self.assertEqual(doc.facility_guard, "90001")

	def test_granted_sets_guard(self):
		doc = _redemption("Granted", "90002")
		CRMCouponRedemption.validate(doc)
		self.assertEqual(doc.facility_guard, "90002")

	def test_released_clears_guard(self):
		doc = _redemption("Released", "90003")
		CRMCouponRedemption.validate(doc)
		self.assertIsNone(doc.facility_guard)  # cleared to NULL so the facility is free

	def test_lapsed_clears_guard(self):
		doc = _redemption("Lapsed", "90004")
		CRMCouponRedemption.validate(doc)
		self.assertIsNone(doc.facility_guard)
