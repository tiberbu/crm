"""Value Express pricing rules shared by the landing page, onboarding and submission.

Flex packages are prepaid token cards; Custom prices any amount at the published
per-token rate of the highest Flex package the amount reaches; Fixed is a monthly fee
for listed facility levels. Pure functions over catalogue rows, so they are unit-tested
without a site and the server never trusts numbers computed in the browser.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any

FLEX, FIXED, CUSTOM = "Flex", "Fixed", "Custom"
DEFAULT_MIN_TOKENS = 1000
# The business figure for "approx. patient journeys": one full journey uses about 40 tokens.
TOKENS_PER_JOURNEY = 40


def plan_of(package: dict[str, Any]) -> str:
	plan = str(package.get("plan") or FLEX).strip()
	return plan if plan in (FLEX, FIXED, CUSTOM) else FLEX


def level_key(value: Any) -> str:
	"""Canonicalize display-equivalent registry levels ("Level  3B" == "level 3b")."""
	normalized = unicodedata.normalize("NFKC", str(value or ""))
	normalized = re.sub(r"[​⁠﻿]", " ", normalized)
	return " ".join(normalized.split()).casefold()


def levels_of(package: dict[str, Any]) -> list[str]:
	raw = package.get("facility_levels") or ""
	lines = raw if isinstance(raw, list) else re.split(r"\r\n|\r|\n", str(raw))
	return [" ".join(str(line).split()) for line in lines if str(line).strip()]


def _price(package: dict[str, Any]) -> float:
	return float(package.get("price_ex_vat", package.get("price")) or 0)


def per_token_rate(package: dict[str, Any]) -> float:
	"""The published rate: package price ÷ tokens, to the cent (6.00, 5.36, 4.80)."""
	tokens = int(package.get("token_quantity") or 0)
	price = _price(package)
	return round(price / tokens, 2) if tokens > 0 and price > 0 else 0.0


def journeys(tokens: Any) -> int:
	return max(0, int(tokens or 0)) // TOKENS_PER_JOURNEY


def flex_tiers(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Paid Flex packages as Custom pricing tiers, cheapest first."""
	tiers = [
		{
			"name": package.get("display_name") or package.get("item_code"),
			"item_code": package.get("item_code"),
			"from_amount": _price(package),
			"rate": per_token_rate(package),
		}
		for package in packages
		if plan_of(package) == FLEX and per_token_rate(package) > 0
	]
	return sorted(tiers, key=lambda tier: tier["from_amount"])


def custom_min_amount(tiers: list[dict[str, Any]], min_tokens: int = DEFAULT_MIN_TOKENS) -> float:
	"""The cheapest amount that buys the minimum, at the entry rate."""
	return round(min_tokens * tiers[0]["rate"], 2) if tiers else 0.0


def custom_quote(amount: Any, tiers: list[dict[str, Any]], min_tokens: int = DEFAULT_MIN_TOKENS) -> dict[str, Any]:
	"""Tokens a Custom amount buys and what it costs; never charges more than the amount.

	The amount is priced at the rate of the highest tier it reaches; tokens are rounded
	down, and the charge is tokens × rate.
	"""
	try:
		value = Decimal(str(amount or 0)).quantize(Decimal("1"), rounding=ROUND_FLOOR)
	except InvalidOperation:
		value = Decimal(0)
	value = max(value, Decimal(0))
	result = {"ok": False, "amount": float(value), "tokens": 0, "rate": 0.0, "tier": "", "charge": 0.0}
	if not tiers:
		return {**result, "error": "unavailable"}
	tier = next((t for t in reversed(tiers) if value >= Decimal(str(t["from_amount"]))), tiers[0])
	rate = Decimal(str(tier["rate"]))
	tokens = int((value / rate).to_integral_value(rounding=ROUND_FLOOR))
	charge = float((rate * tokens).quantize(Decimal("0.01")))
	result.update(tokens=tokens, rate=float(rate), tier=tier["name"], charge=charge)
	if tokens < min_tokens:
		return {**result, "error": "below_minimum", "min_amount": custom_min_amount(tiers, min_tokens)}
	return {**result, "ok": True}


def fixed_package_for_level(level: Any, fixed_packages: list[dict[str, Any]]) -> dict[str, Any] | None:
	"""The Fixed package whose levels include the facility's registry level."""
	key = level_key(level)
	if not key:
		return None
	return next(
		(package for package in fixed_packages if key in {level_key(item) for item in levels_of(package)}),
		None,
	)


# Billing periods a package can be sold on, and the months each one covers.
PERIOD_MONTHS = {"Monthly": 1, "Quarterly": 3, "Semi-annual": 6, "Annual": 12}
PERIOD_UNITS = {"Monthly": "month", "Quarterly": "quarter", "Semi-annual": "half-year", "Annual": "year"}
ACTIVE, DISABLED, DISCONTINUED = "Active", "Disabled", "Discontinued"


def period_months(period: Any) -> int:
	return PERIOD_MONTHS.get(str(period or "").strip(), 1)


def period_label(period: Any) -> str:
	"""The price suffix: per month, per quarter, per half-year or per year."""
	return "per " + PERIOD_UNITS.get(str(period or "").strip(), "month")


def monthly_equivalent(price: Any, period: Any) -> float:
	return round(float(price or 0) / period_months(period), 2)


def grid_columns(count: Any, most: int = 4) -> int:
	"""Columns for `count` cards: at most `most` a row, rows as even as possible (5 → 3+2, 7 → 4+3)."""
	count, most = max(0, int(count or 0)), max(1, int(most))
	if count <= most:
		return max(count, 1)
	rows = -(-count // most)
	return -(-count // rows)


def status_of(package: dict[str, Any]) -> str:
	status = str(package.get("status") or "").strip()
	if status in (ACTIVE, DISABLED, DISCONTINUED):
		return status
	return ACTIVE if int(package.get("enabled") or 0) else DISABLED


def validate_catalogue(packages: list[dict[str, Any]]) -> list[str]:
	"""Why this catalogue cannot be published, as messages; empty when it can.

	Rows carry plan, status, item_code, display_name, token_quantity, facility_levels,
	billing_period and, for Flex and Fixed, price (ex VAT).
	"""
	errors: list[str] = []
	seen: set[str] = set()
	fixed_levels: dict[str, str] = {}
	active = [p for p in packages if status_of(p) == ACTIVE]
	for package in packages:
		name = str(package.get("display_name") or package.get("item_code") or "A package")
		item = str(package.get("item_code") or "").strip()
		if item in seen:
			errors.append(f"{name}: its item is already used by another package.")
		seen.add(item)
		if str(package.get("billing_period") or "Monthly") not in PERIOD_MONTHS:
			errors.append(f"{name}: choose Monthly, Quarterly, Semi-annual or Annual.")
	for package in active:
		name = str(package.get("display_name") or package.get("item_code") or "A package")
		plan, tokens, price = plan_of(package), int(package.get("token_quantity") or 0), float(package.get("price") or 0)
		if plan == FLEX:
			if tokens < 1:
				errors.append(f"{name}: a Flex package needs at least one token.")
			if price <= 0:
				errors.append(f"{name}: a Flex package needs a price.")
		elif plan == FIXED:
			levels = levels_of(package)
			if not levels:
				errors.append(f"{name}: a Fixed package needs the facility levels it applies to.")
			if price <= 0:
				errors.append(f"{name}: a Fixed package needs a price.")
			for level in levels:
				other = fixed_levels.get(level_key(level))
				if other:
					errors.append(f"{name}: {level} already has an active Fixed package ({other}).")
				fixed_levels[level_key(level)] = name
	customs = [p for p in active if plan_of(p) == CUSTOM]
	if len(customs) > 1:
		errors.append("Only one Custom offer can be active at a time.")
	if customs and not any(plan_of(p) == FLEX for p in active):
		errors.append("Custom is priced from the Flex packages, so it needs at least one active Flex package.")
	return errors
