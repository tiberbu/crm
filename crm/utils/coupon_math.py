"""Coupon value math: the single source of truth for how many tokens a coupon is worth.

This module is deliberately free of any frappe import so both the CRM app and the
openmeter_mediator app can use it, and so it can be unit-tested without a site.
"""

from decimal import ROUND_FLOOR, Decimal

FLAT = "flat_tokens"
PERCENTAGE = "percentage_of_purchase"


def _level_key(value) -> str:
	from crm.utils.value_express import level_key  # pure module too; imported lazily for the mediator

	return level_key(value)


def level_reward(reward_by_level, level_rewards, facility_level, value, fixed_discount_percent) -> dict:
	"""The reward a coupon gives a facility of ``facility_level`` (P-116 to P-118).

	Returns ``{"value", "fixed_discount_percent", "level"}``: the matching level row's values, or the
	coupon's own values ("All other levels") when levels are off, the level is unknown or not listed.
	``level`` is the matched row's level, or None. ``level_rewards`` rows are dicts (or documents)
	(anything with ``.get``) with ``facility_level``, ``flex_value`` and ``fixed_discount_percent``.
	"""
	fallback = {"value": float(value or 0), "fixed_discount_percent": float(fixed_discount_percent or 0), "level": None}
	if not int(reward_by_level or 0):
		return fallback
	key = _level_key(facility_level)
	if not key:
		return fallback
	for row in level_rewards or []:
		if _level_key(row.get("facility_level")) == key:
			return {
				"value": float(row.get("flex_value") or 0),
				"fixed_discount_percent": float(row.get("fixed_discount_percent") or 0),
				"level": " ".join(str(row.get("facility_level") or "").split()),
			}
	return fallback


def coupon_tokens(value_type, value, max_tokens, purchased_tokens) -> int:
	"""Tokens a coupon is worth on an order: floor first, then the cap.

	A result of 0 means no bonus line is added. ``purchased_tokens`` is the base for a
	percentage coupon (the purchased package tokens only, never the bonus lines).
	"""
	purchased = max(int(purchased_tokens or 0), 0)
	if value_type == FLAT:
		tokens = int(value or 0)
	elif value_type == PERCENTAGE:
		exact = Decimal(purchased) * Decimal(str(value or 0)) / Decimal(100)
		tokens = int(exact.to_integral_value(rounding=ROUND_FLOOR))
	else:
		return 0
	cap = int(max_tokens or 0)
	if cap > 0:
		tokens = min(tokens, cap)
	return max(tokens, 0)


def derived_status(status, valid_from, valid_to, today, max_redemptions, redeemed_count) -> str:
	"""The effective status of a coupon: Revoked > Inactive > Scheduled > Expired > Exhausted > Active.

	Dates are ``datetime.date`` (or ``datetime.datetime``) objects, or None. Expiry is never
	stored; it is derived here so it cannot drift from ``valid_to``.
	"""
	if status == "Revoked":
		return "Revoked"
	if status == "Inactive":
		return "Inactive"
	if valid_from and today < valid_from:
		return "Scheduled"
	if valid_to and today > valid_to:
		return "Expired"
	if int(max_redemptions or 0) > 0 and int(redeemed_count or 0) >= int(max_redemptions):
		return "Exhausted"
	return "Active"
