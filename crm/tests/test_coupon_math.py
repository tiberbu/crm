"""Pure unit tests for the shared coupon value math (no site required)."""

import datetime
from frappe.tests import UnitTestCase

from crm.utils.coupon_math import coupon_tokens, derived_status


class TestCouponTokens(UnitTestCase):
	def test_flat_uncapped(self):
		self.assertEqual(coupon_tokens("flat_tokens", 1000, 0, 0), 1000)

	def test_flat_capped(self):
		self.assertEqual(coupon_tokens("flat_tokens", 1000, 500, 0), 500)

	def test_percentage_floored(self):
		# 5% of 1234 = 61.7 -> 61
		self.assertEqual(coupon_tokens("percentage_of_purchase", 5, 0, 1234), 61)

	def test_percentage_capped(self):
		# 5% of 1234 = 61.7, capped at 50
		self.assertEqual(coupon_tokens("percentage_of_purchase", 5, 50, 1234), 50)

	def test_percentage_fractional_rate(self):
		# 2.5% of 3000 = 75 exactly
		self.assertEqual(coupon_tokens("percentage_of_purchase", 2.5, 0, 3000), 75)

	def test_percentage_small_purchase_yields_zero(self):
		# 5% of 10 = 0.5 -> 0 (no line)
		self.assertEqual(coupon_tokens("percentage_of_purchase", 5, 0, 10), 0)

	def test_percentage_floor_not_round(self):
		# 0.07% of 100 = 0.07 -> 0 (floor), proving floor not round
		self.assertEqual(coupon_tokens("percentage_of_purchase", 0.07, 0, 100), 0)
		# 0.07% of 10000 = 7 -> 7
		self.assertEqual(coupon_tokens("percentage_of_purchase", 0.07, 0, 10000), 7)

	def test_unknown_type_is_zero(self):
		self.assertEqual(coupon_tokens("mystery", 1000, 0, 0), 0)

	def test_none_inputs_are_safe(self):
		self.assertEqual(coupon_tokens("flat_tokens", None, None, None), 0)
		self.assertEqual(coupon_tokens("percentage_of_purchase", None, None, None), 0)

	def test_cap_applied_after_floor(self):
		# 50% of 999 = 499.5 -> floor 499, cap 400 -> 400
		self.assertEqual(coupon_tokens("percentage_of_purchase", 50, 400, 999), 400)


class TestDerivedStatus(UnitTestCase):
	@staticmethod
	def _d(s):
		return datetime.date.fromisoformat(s)

	def test_revoked_wins(self):
		self.assertEqual(derived_status("Revoked", None, None, self._d("2026-01-01"), 0, 0), "Revoked")

	def test_scheduled_before_start(self):
		self.assertEqual(derived_status("Active", self._d("2026-06-01"), None, self._d("2026-01-01"), 0, 0), "Scheduled")

	def test_scheduled_inclusive_start_is_active(self):
		self.assertEqual(derived_status("Active", self._d("2026-06-01"), None, self._d("2026-06-01"), 0, 0), "Active")

	def test_expired_after_end(self):
		self.assertEqual(derived_status("Active", None, self._d("2026-05-31"), self._d("2026-06-01"), 0, 0), "Expired")

	def test_expired_inclusive_end_is_active(self):
		self.assertEqual(derived_status("Active", None, self._d("2026-05-31"), self._d("2026-05-31"), 0, 0), "Active")

	def test_exhausted_at_limit(self):
		self.assertEqual(derived_status("Active", None, None, self._d("2026-01-01"), 5, 5), "Exhausted")

	def test_exhausted_over_limit(self):
		self.assertEqual(derived_status("Active", None, None, self._d("2026-01-01"), 5, 9), "Exhausted")

	def test_unlimited_never_exhausted(self):
		self.assertEqual(derived_status("Active", None, None, self._d("2026-01-01"), 0, 999), "Active")

	def test_priority_revoked_over_expired(self):
		self.assertEqual(derived_status("Revoked", None, self._d("2020-01-01"), self._d("2026-01-01"), 0, 0), "Revoked")

	def test_plain_active(self):
		self.assertEqual(derived_status("Active", None, None, self._d("2026-01-01"), 0, 0), "Active")
