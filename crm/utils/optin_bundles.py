"""Small, dependency-light helpers for multi-year Opt-In bundles.

The helpers deliberately accept old records and plain dictionaries.  They are
used by API, scheduled billing and presentation code so the compatibility rules
live in one place instead of being reimplemented in every surface.
"""

from __future__ import annotations

import calendar
import json
from datetime import date, datetime
from typing import Any


def decode_json(value: Any, default: Any):
	if isinstance(value, (dict, list)):
		return value
	if not value:
		return default
	try:
		result = json.loads(value)
	except (TypeError, ValueError, json.JSONDecodeError):
		return default
	return result if isinstance(result, type(default)) else default


def normalize_price_lists(rows: Any, legacy: str = "") -> list[dict[str, Any]]:
	"""Return ordered, enabled year/list pairs; legacy data becomes year 1."""
	rows = decode_json(rows, [])
	result = []
	seen = set()
	for index, row in enumerate(rows, start=1):
		if not isinstance(row, dict):
			continue
		price_list = str(row.get("price_list") or "").strip()
		if not price_list:
			continue
		try:
			year_number = max(int(row.get("year_number") or index), 1)
		except (TypeError, ValueError):
			year_number = index
		if year_number in seen:
			continue
		seen.add(year_number)
		result.append(
			{
				"year_number": year_number,
				"price_list": price_list,
				"label": str(row.get("label") or "Year %s" % year_number).strip(),
				"enabled": bool(row.get("enabled", True)),
			}
		)
	if result:
		return [row for row in sorted(result, key=lambda item: item["year_number"]) if row["enabled"]]
	legacy = str(legacy or "").strip()
	return [{"year_number": 1, "price_list": legacy, "label": "Year 1", "enabled": True}] if legacy else []


def membership_price_lists(overrides: Any, legacy: str = "") -> dict[int, str]:
	"""Decode a facility's optional year override map safely."""
	value = decode_json(overrides, {})
	if isinstance(value, list):
		value = {row.get("year_number"): row.get("price_list") for row in value if isinstance(row, dict)}
	if not isinstance(value, dict):
		value = {}
	result = {}
	for key, price_list in value.items():
		try:
			year = int(key)
		except (TypeError, ValueError):
			continue
		price_list = str(price_list or "").strip()
		if year > 0 and price_list:
			result[year] = price_list
	if result:
		return result
	legacy = str(legacy or "").strip()
	return {1: legacy} if legacy else {}


def effective_year_price_list(year: int, plans: list[dict[str, Any]], overrides: Any = None, legacy: str = "") -> str:
	"""Resolve facility override first, then network year plan, then legacy."""
	by_year = membership_price_lists(overrides, legacy)
	if year in by_year:
		return by_year[year]
	for plan in plans or []:
		if int(plan.get("year_number") or 0) == int(year):
			return str(plan.get("price_list") or "").strip()
	return str(legacy or "").strip()


def add_months(value: date | datetime, months: int) -> date:
	"""Calendar-month addition without a third-party dependency."""
	if isinstance(value, datetime):
		value = value.date()
	months = int(months or 0)
	month = value.month - 1 + months
	year, month = value.year + month // 12, month % 12 + 1
	# Clamp to the last day of the target month (31 Jan + 1 month = 28 Feb).
	return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def billing_schedule(
	submitted_at: date | datetime,
	years: list[int],
	offset_months: int = 3,
	key_prefix: str = "",
) -> list[dict[str, Any]]:
	"""Build deterministic four-quarter issue/due dates for each selected year.

	``key_prefix`` is optional for backwards compatibility.  Persisted Opt-In
	bundles pass their submission name so an idempotency key can never collide
	with the same year/quarter on another submission.
	"""
	if isinstance(submitted_at, datetime):
		submitted_at = submitted_at.date()
	base = add_months(submitted_at, max(int(offset_months or 3), 1))
	rows = []
	for year_number in sorted({int(year) for year in years if int(year) > 0}):
		for quarter in range(1, 5):
			issue = add_months(base, (year_number - 1) * 12 + (quarter - 1) * 3)
			key = "Y%s-Q%s" % (year_number, quarter)
			if key_prefix:
				key = "%s-%s" % (str(key_prefix).strip(), key)
			rows.append(
				{
					"year_number": year_number,
					"quarter_number": quarter,
					"scheduled_order_date": issue.isoformat(),
					"invoice_date": issue.isoformat(),
					"invoice_due_date": (issue.fromordinal(issue.toordinal() + 30)).isoformat(),
					"status": "Scheduled",
					"billing_key": key,
				}
			)
	return rows
