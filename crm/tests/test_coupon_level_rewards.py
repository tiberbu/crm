"""Coupon rewards by facility level (P-116 to P-123).

One coupon, a reward per facility level: Flex tokens and a Fixed discount for each level, the
coupon's own values for every other level.
"""

from unittest.mock import patch

import frappe

from crm.api import coupons as coupons_api
from crm.tests.test_coupon_plan_scope import CouponPlanCase, _coupon, _order
from crm.tests.test_coupon_resolution import _facility, _net
from crm.utils import coupons, token_bonus
from crm.utils.coupon_math import level_reward

L2_L4 = [
	{"facility_level": "Level 2", "flex_value": 1000, "fixed_discount_percent": 10},
	{"facility_level": "Level 4", "flex_value": 2500, "fixed_discount_percent": 4},
]


def _level_coupon(**kw):
	base = {
		"applies_to": "Both",
		"value": 0,
		"fixed_discount_percent": 0,
		"reward_by_level": 1,
		"level_rewards": [dict(row) for row in L2_L4],
	}
	base.update(kw)
	return _coupon(**base)


class TestLevelRewardMath(CouponPlanCase):
	def test_level_row_wins_and_others_get_the_coupon_values(self):
		rows = [frappe._dict(row) for row in L2_L4]
		self.assertEqual(level_reward(1, rows, "Level 4", 300, 2), {"value": 2500, "fixed_discount_percent": 4, "level": "Level 4"})
		self.assertEqual(level_reward(1, rows, "Level 5", 300, 2), {"value": 300, "fixed_discount_percent": 2, "level": None})
		self.assertEqual(level_reward(1, rows, "", 300, 2)["level"], None)
		self.assertEqual(level_reward(0, rows, "Level 4", 300, 2)["value"], 300)

	def test_level_matching_ignores_case_and_spacing_but_is_not_fuzzy(self):
		rows = [{"facility_level": "Level 3B", "flex_value": 700, "fixed_discount_percent": 0}]
		self.assertEqual(level_reward(1, rows, "  level   3b ", 0, 0)["value"], 700)
		self.assertEqual(level_reward(1, rows, "Level 3", 0, 0)["value"], 0)


class TestLevelRewardValidation(CouponPlanCase):
	def test_needs_at_least_one_level(self):
		self.assertRaises(frappe.ValidationError, _level_coupon, level_rewards=[])

	def test_each_level_once(self):
		rows = [{"facility_level": "Level 2", "flex_value": 100}, {"facility_level": "level  2", "flex_value": 200}]
		with self.assertRaisesRegex(frappe.ValidationError, "more than once"):
			_level_coupon(applies_to="Flex", level_rewards=rows)

	def test_a_row_must_give_something_valid(self):
		with self.assertRaisesRegex(frappe.ValidationError, "gives nothing"):
			_level_coupon(level_rewards=[{"facility_level": "Level 2", "flex_value": 0, "fixed_discount_percent": 0}])
		with self.assertRaisesRegex(frappe.ValidationError, "whole number"):
			_level_coupon(level_rewards=[{"facility_level": "Level 2", "flex_value": 10.5}])
		with self.assertRaisesRegex(frappe.ValidationError, "at most 100%"):
			_level_coupon(level_rewards=[{"facility_level": "Level 2", "fixed_discount_percent": 120}])
		with self.assertRaisesRegex(frappe.ValidationError, "at most 100"):
			_level_coupon(
				value_type="percentage_of_purchase",
				level_rewards=[{"facility_level": "Level 2", "flex_value": 150}],
			)

	def test_other_levels_may_get_nothing_and_unused_columns_clear(self):
		doc = _level_coupon(applies_to="Flex")
		self.assertEqual((doc.value, doc.fixed_discount_percent), (0, 0))
		self.assertEqual([row.fixed_discount_percent for row in doc.level_rewards], [0, 0])
		self.assertEqual([row.flex_value for row in doc.level_rewards], [1000, 2500])
		fixed = _level_coupon(coupon_title="fixed by level", applies_to="Fixed", value_type=None)
		self.assertEqual([row.flex_value for row in fixed.level_rewards], [0, 0])

	def test_without_levels_the_coupon_values_are_still_required(self):
		self.assertRaises(frappe.ValidationError, _coupon, applies_to="Both", value=0, fixed_discount_percent=5)

	def test_turning_levels_off_drops_the_rows(self):
		doc = _level_coupon(value=500, fixed_discount_percent=5)
		doc.reward_by_level = 0
		doc.save()
		self.assertEqual(doc.level_rewards, [])

	def test_level_rewards_are_fixed_once_used(self):
		doc = _level_coupon()
		frappe.get_doc(
			{"doctype": "CRM Coupon Redemption", "coupon": doc.name, "facility_mfl": "LR-IMM", "status": "Reserved",
			 "sales_order": "SO-LR-IMM", "plan": "Flex"}
		).insert(ignore_permissions=True)
		doc.reload()
		doc.level_rewards[0].flex_value = 5000
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.append("level_rewards", {"facility_level": "Level 5", "flex_value": 9000})
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.reward_by_level = 0
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.description = "a note"  # other fields still edit
		doc.save()


class TestLevelRewardResolution(CouponPlanCase):
	def setUp(self):
		super().setUp()
		self.network = _net("lr-net", "950000", "Level Net")
		self.coupon = _level_coupon(network=self.network, targeting=None, value=300, fixed_discount_percent=2)
		_facility("950002", self.network, self.customer, level="Level 2")
		_facility("950004", self.network, self.customer, level="Level 4")
		_facility("950005", self.network, self.customer, level="Level 5")

	def test_same_coupon_gives_each_level_its_own_reward(self):
		l2 = coupons.resolve_coupon(self.customer, "950002", "FID-L2", 1000)
		l4 = coupons.resolve_coupon(self.customer, "950004", "FID-L4", 1000)
		self.assertEqual((l2["coupon"], l2["tokens"], l2["facility_level"]), (self.coupon.name, 1000, "Level 2"))
		self.assertEqual((l4["coupon"], l4["tokens"], l4["facility_level"]), (self.coupon.name, 2500, "Level 4"))
		fixed_l2 = coupons.resolve_coupon(self.customer, "950002", "FID-L2", 0, plan="Fixed")
		fixed_l4 = coupons.resolve_coupon(self.customer, "950004", "FID-L4", 0, plan="Fixed")
		self.assertEqual((fixed_l2["discount_percent"], fixed_l4["discount_percent"]), (10, 4))

	def test_unlisted_level_gets_the_coupon_values(self):
		other = coupons.resolve_coupon(self.customer, "950005", "FID-L5", 1000)
		self.assertEqual((other["tokens"], other["facility_level"]), (300, None))
		self.assertEqual(coupons.resolve_coupon(self.customer, "950005", "FID-L5", 0, plan="Fixed")["discount_percent"], 2)

	def test_other_levels_set_to_nothing_get_no_coupon(self):
		self.coupon.value = 0
		self.coupon.fixed_discount_percent = 0
		self.coupon.save()
		self.assertIsNone(coupons.resolve_coupon(self.customer, "950005", "FID-L5", 1000))
		self.assertIsNone(coupons.resolve_coupon(self.customer, "950005", "FID-L5", 0, plan="Fixed"))
		self.assertEqual(coupons.resolve_coupon(self.customer, "950004", "FID-L4", 1000)["tokens"], 2500)

	def test_percentage_levels_use_the_coupon_cap(self):
		self.coupon.status = "Revoked"
		self.coupon.save()
		_level_coupon(
			coupon_title="pct", network=_net("lr-pct", "950010", "Pct Net"), targeting=None, applies_to="Flex",
			value_type="percentage_of_purchase", max_tokens=400,
			level_rewards=[{"facility_level": "Level 2", "flex_value": 10}, {"facility_level": "Level 4", "flex_value": 50}],
		)
		_facility("950012", "lr-pct", self.customer, level="Level 2")
		_facility("950014", "lr-pct", self.customer, level="Level 4")
		self.assertEqual(coupons.resolve_coupon(self.customer, "950012", "FID-P2", 1000)["tokens"], 100)
		self.assertEqual(coupons.resolve_coupon(self.customer, "950014", "FID-P4", 1000)["tokens"], 400)

	def test_crm_coupon_choice_compares_the_reward_for_the_facility_level(self):
		big_at_l4 = _level_coupon(
			coupon_title="big at L4", applies_to="Flex",
			level_rewards=[{"facility_level": "Level 4", "flex_value": 5000}],
			targeting="Assigned Facilities",
		)
		plain = _coupon(coupon_title="plain", value=800)
		_facility("950102", None, self.customer, partner_coupon=False, level="Level 2")
		_facility("950104", None, self.customer, partner_coupon=False, level="Level 4")
		for mfl in ("950102", "950104"):
			for c in (big_at_l4, plain):
				frappe.get_doc({"doctype": "CRM Coupon Assignment", "coupon": c.name, "facility_mfl": mfl}).insert(
					ignore_permissions=True
				)
		self.assertEqual(coupons.resolve_coupon(self.customer, "950102", "FID-C2", 1000)["coupon"], plain.name)
		at_l4 = coupons.resolve_coupon(self.customer, "950104", "FID-C4", 1000)
		self.assertEqual((at_l4["coupon"], at_l4["tokens"]), (big_at_l4.name, 5000))

	def test_public_offer_lists_the_level_rewards(self):
		offer = coupons.public_offer(self.network)
		self.assertEqual(offer["reward_by_level"], 1)
		self.assertEqual(
			[(r["facility_level"], r["flex_value"], r["fixed_discount_percent"]) for r in offer["level_rewards"]],
			[("Level 2", 1000, 10), ("Level 4", 2500, 4)],
		)
		self.assertNotIn("redeemed_count", offer)

	def test_token_ceiling_is_per_level(self):
		self.assertEqual(coupons.token_ceiling(self.coupon.name, 1000, "Level 4"), 2500)
		self.assertEqual(coupons.token_ceiling(self.coupon.name, 1000, "Level 2"), 1000)
		self.assertEqual(coupons.token_ceiling(self.coupon.name, 1000, None), 300)
		self.assertEqual(coupons.token_ceiling("CPN-NOPE", 1000, "Level 2"), 0)


class TestLevelRewardClaim(CouponPlanCase):
	def setUp(self):
		super().setUp()
		self.coupon = _level_coupon(value=300, fixed_discount_percent=2)
		_facility("950202", None, self.customer, partner_coupon=False, level="Level 2")
		_facility("950204", None, self.customer, partner_coupon=False, level="Level 4")

	def _row(self, item, rate=10000, **kw):
		return frappe._dict(item_code=item, qty=1, price_list_rate=rate, rate=rate, amount=rate, **kw)

	def test_flex_claim_uses_the_facility_level_and_records_it(self):
		# The draft was stamped with the Level 2 amount; the facility is Level 4 at confirmation.
		line = frappe._dict(crm_bonus_type="CRM Coupon", crm_bonus_tokens=1000, crm_coupon=self.coupon.name,
			item_code="CV-TOKEN-BONUS", qty=1)
		coupons.claim_on_submit(_order("SO-LR-1", self.flex_item, self.customer, "950204", [self._row(self.flex_item), line]))
		self.assertEqual(line.crm_bonus_tokens, 2500)
		red = frappe.db.get_value("CRM Coupon Redemption", {"sales_order": "SO-LR-1"},
			["tokens_awarded", "facility_level", "plan"], as_dict=True)
		self.assertEqual((red.tokens_awarded, red.facility_level, red.plan), (2500, "Level 4", "Flex"))

	def test_fixed_claim_restamps_the_level_discount(self):
		row = self._row(self.fixed_item, crm_coupon=self.coupon.name)
		token_bonus._set_line_discount(row, 4)  # stamped while the facility was Level 4
		coupons.claim_on_submit(_order("SO-LR-2", self.fixed_item, self.customer, "950202", [row]))
		self.assertEqual((row.discount_percentage, row.rate), (10, 9000))
		red = frappe.db.get_value("CRM Coupon Redemption", {"sales_order": "SO-LR-2"},
			["discount_percent", "discount_amount", "facility_level"], as_dict=True)
		self.assertEqual((red.discount_percent, red.discount_amount, red.facility_level), (10, 1000, "Level 2"))

	def test_order_lines_carry_the_level_amount(self):
		frappe.get_doc({"doctype": "CRM Coupon Assignment", "coupon": self.coupon.name, "facility_mfl": "950204"}).insert(
			ignore_permissions=True
		)
		with patch.object(token_bonus, "_installed", return_value=True), patch.object(
			token_bonus, "bonus_settings", return_value={token_bonus.WELCOME_BONUS: 0, token_bonus.PARTNER_COUPON: 0}
		), patch.object(token_bonus, "welcome_bonus_status", return_value={}):
			lines = token_bonus.eligible_bonuses(self.customer, "950204", facility_fid="FID-LR-3", purchased_tokens=1000)
		self.assertEqual([(line["type"], line["tokens"]) for line in lines], [("CRM Coupon", 2500)])


class TestLevelRewardApi(CouponPlanCase):
	def test_save_and_read_back_level_rewards(self):
		saved = coupons_api.save_coupon(
			"",
			{
				"coupon_title": "api by level",
				"applies_to": "Both",
				"value_type": "flat_tokens",
				"value": 0,
				"fixed_discount_percent": 0,
				"targeting": "Assigned Facilities",
				"reward_by_level": 1,
				"level_rewards": [
					{"facility_level": " Level   2 ", "flex_value": 1000, "fixed_discount_percent": 10},
					{"facility_level": "Level 4", "flex_value": 2500, "fixed_discount_percent": 4},
				],
			},
		)
		coupon = coupons_api.get_coupon(saved["name"])
		self.assertEqual(coupon["reward_by_level"], 1)
		self.assertEqual(
			[(r.facility_level, r.flex_value, r.fixed_discount_percent) for r in coupon["level_rewards"]],
			[("Level 2", 1000, 10), ("Level 4", 2500, 4)],
		)
		listed = next(c for c in coupons_api.list_coupons()["coupons"] if c.name == saved["name"])
		self.assertEqual(len(listed["level_rewards"]), 2)
		coupons_api.save_coupon(saved["name"], {**coupon, "reward_by_level": 0, "value": 500, "fixed_discount_percent": 5})
		self.assertEqual(coupons_api.get_coupon(saved["name"])["level_rewards"], [])

	def test_level_options_merge_the_known_levels_once(self):
		_facility("950301", None, self.customer, partner_coupon=False, level="level 2")
		_facility("950302", None, self.customer, partner_coupon=False, level="Level 9Z")
		levels = coupons_api.coupon_level_options()["levels"]
		self.assertIn("Level 9Z", levels)
		self.assertEqual(sum(1 for level in levels if level.casefold() == "level 2"), 1)

	def test_level_options_need_coupon_access(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, coupons_api.coupon_level_options)
