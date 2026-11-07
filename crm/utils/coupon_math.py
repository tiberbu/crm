"""Coupon value math: the single source of truth for how many tokens a coupon is worth.

This module is deliberately free of any frappe import so both the CRM app and the
openmeter_mediator app can use it, and so it can be unit-tested without a site.
"""

from decimal import ROUND_FLOOR, Decimal

FLAT = "flat_tokens"
PERCENTAGE = "percentage_of_purchase"


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
	"""The effective status of a coupon: Revoked > Scheduled > Expired > Exhausted > Active.

	Dates are ``datetime.date`` (or ``datetime.datetime``) objects, or None. Expiry is never
	stored; it is derived here so it cannot drift from ``valid_to``.
	"""
	if status == "Revoked":
		return "Revoked"
	if valid_from and today < valid_from:
		return "Scheduled"
	if valid_to and today > valid_to:
		return "Expired"
	if int(max_redemptions or 0) > 0 and int(redeemed_count or 0) >= int(max_redemptions):
		return "Exhausted"
	return "Active"
