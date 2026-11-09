"""Pure, site-free decision logic for the customer portal's commercial projection.

Every rule in ``SPEC.md`` section 4 that the browser or the serializer applies
lives here as a plain function so it can be unit-tested without a site. This
module must not import ``frappe``; the server-side helpers in
``crm.api.portal_commercial`` do the querying and call these.
"""

from __future__ import annotations

JOURNEY_NETWORK = "network_optin"
JOURNEY_SELF = "self_onboarding"
JOURNEY_UNKNOWN = "unknown"

PLAN_TIME_BOUND = "time_bound"
PLAN_TOKEN = "token"
PLAN_UNKNOWN = "unknown"

_CYCLE_LABELS = {
	"monthly": "Billed monthly",
	"quarterly": "Billed quarterly",
	"semi-annual": "Billed every six months",
	"semiannual": "Billed every six months",
	"semi annual": "Billed every six months",
	"annual": "Billed annually",
}


def clean_mfl(value) -> str:
	"""Return the MFL as a stripped string; ``None`` becomes ``""``."""
	if value is None:
		return ""
	return str(value).strip()


def _as_int(value) -> int:
	try:
		return int(float(value))
	except (TypeError, ValueError):
		return 0


def _dedupe_mfls(values) -> list[str]:
	seen: set[str] = set()
	out: list[str] = []
	for value in values or []:
		text = clean_mfl(value)
		if not text:
			continue
		key = text.casefold()
		if key in seen:
			continue
		seen.add(key)
		out.append(text)
	return out


def attribute_facilities(header_mfl, item_mfls, ois_mfls, account_mfls) -> list[str]:
	"""Resolve the facilities a document belongs to; first match wins (SPEC 4.1).

	Comparison is trimmed and case-insensitive; returned values keep their stored
	case. An empty result means the document is account-level.
	"""
	header = clean_mfl(header_mfl)
	if header:
		return [header]
	items = _dedupe_mfls(item_mfls)
	if items:
		return items
	ois = _dedupe_mfls(ois_mfls)
	if ois:
		return ois
	account = _dedupe_mfls(account_mfls)
	if len(account) == 1:
		return account
	return []


def is_schedule_governed(billing_key, optin_year) -> bool:
	"""True when only the Network schedule may raise this order's invoice (SPEC 2)."""
	if billing_key is not None and str(billing_key).strip():
		return True
	return _as_int(optin_year) > 0


def period_label(year, quarter) -> str:
	"""``Year {year} · Quarter {quarter}``; empty when the year is not positive."""
	year_int = _as_int(year)
	if year_int <= 0:
		return ""
	quarter_text = "" if quarter is None else str(quarter).strip()
	if quarter_text:
		return "Year %d · Quarter %s" % (year_int, quarter_text)
	return "Year %d" % year_int


def order_doc_kind(governed, package_plan) -> str:
	"""Classify an order for display (SPEC 4.4)."""
	plan = (package_plan or "").strip()
	if governed:
		return "subscription"
	if plan == "Fixed":
		return "subscription"
	if plan in ("Flex", "Custom"):
		return "token"
	return "other"


def order_display_title(doc_kind, governed, period, package_name) -> str:
	"""Human title for an order row; never an item code (SPEC 4.4)."""
	name = (package_name or "").strip()
	if doc_kind == "subscription":
		if governed:
			return (period + " subscription") if period else "Subscription order"
		return name or "Subscription order"
	if doc_kind == "token":
		return name or "Token order"
	return "Order"


def order_display_status(docstatus, status, per_billed, governed) -> str:
	"""Display status for an order row, first match wins (SPEC 4.4)."""
	docstatus = _as_int(docstatus)
	if docstatus == 0:
		return "Needs your review"
	text = (status or "").strip().lower()
	if text == "closed":
		return "Closed"
	if text == "on hold":
		return "On hold"
	if text == "completed":
		return "Complete"
	if float(per_billed or 0) >= 100:
		return "Invoiced"
	if governed:
		return "Confirmed"
	return "Awaiting invoice"


def can_create_invoice(is_draft, status, governed) -> bool:
	"""False for drafts, schedule-governed orders and closed/on-hold/cancelled ones."""
	if is_draft or governed:
		return False
	text = (status or "").strip().lower()
	if text in ("closed", "on hold", "cancelled", "canceled"):
		return False
	return True


def _journey_label(journey) -> str:
	if journey == JOURNEY_NETWORK:
		return "Network Opt-In"
	if journey == JOURNEY_SELF:
		return "Self-Onboarding"
	return ""


def _balance_is_positive(status, balance) -> bool:
	if status != "ok":
		return False
	try:
		return float(balance) > 0
	except (TypeError, ValueError):
		return False


def decide_commercial(
	has_network_plan,
	package_plan,
	is_self_onboarding,
	token_order_count,
	balance_status=None,
	balance=None,
) -> dict:
	"""The journey/plan decision table (SPEC 4.3).

	Recurrence is deliberately not an input: a recurring token order stays a token
	plan (invariant I4).
	"""
	plan = (package_plan or "").strip()
	token_count = _as_int(token_order_count)

	if has_network_plan:
		journey = JOURNEY_NETWORK
	elif is_self_onboarding or plan:
		journey = JOURNEY_SELF
	else:
		journey = JOURNEY_UNKNOWN

	if has_network_plan or plan == "Fixed":
		plan_type = PLAN_TIME_BOUND
	elif plan in ("Flex", "Custom") or token_count > 0:
		plan_type = PLAN_TOKEN
	else:
		plan_type = PLAN_UNKNOWN

	has_tokens = (
		plan_type == PLAN_TOKEN
		or token_count > 0
		or _balance_is_positive(balance_status, balance)
	)
	return {
		"journey": journey,
		"journey_label": _journey_label(journey),
		"plan_type": plan_type,
		"has_tokens": has_tokens,
	}


def apply_live_balance(commercial, token_balance) -> dict:
	"""Recompute ``has_tokens`` once the live metering balance is known.

	``token_balance`` is the metering entry ``{"status": "ok", "balance": ...}``
	(or ``not_metered`` / ``unavailable`` with no balance).
	"""
	out = dict(commercial or {})
	entry = token_balance or {}
	if isinstance(entry, dict):
		status = entry.get("status")
		balance = entry.get("balance")
	else:
		status, balance = None, None
	if not out.get("has_tokens") and _balance_is_positive(status, balance):
		out["has_tokens"] = True
	return out


def _schedule_state(row, contract_complete) -> str:
	if row.get("sales_invoice") or str(row.get("status") or "").strip().lower() == "invoiced":
		return "invoiced"
	if str(row.get("status") or "").strip().lower() == "failed":
		return "preparing"
	return "upcoming"


def schedule_rows(rows, contract_complete) -> list[dict]:
	"""Allow-listed projection of ``billing_schedule_json`` rows (SPEC 4.5)."""
	out = []
	for row in rows or []:
		if not isinstance(row, dict):
			continue
		label = str(row.get("period_label") or "").strip()
		if not label:
			year = row.get("year_number")
			quarter = row.get("quarter_number")
			if year and quarter:
				label = "Year %s · Quarter %s" % (year, quarter)
			elif year:
				label = "Year %s" % year
		out.append(
			{
				"label": label,
				"invoice_date": row.get("invoice_date") or None,
				"due_date": row.get("invoice_due_date") or None,
				"amount_incl_vat": row.get("amount_incl_vat"),
				"state": _schedule_state(row, contract_complete),
				"projected": bool(row.get("preview")) or not contract_complete,
			}
		)
	return out


def next_invoice(schedule) -> dict | None:
	"""The earliest not-yet-invoiced schedule row, or ``None`` (SPEC 4.5)."""
	candidates = [row for row in (schedule or []) if row.get("state") != "invoiced"]
	if not candidates:
		return None
	return sorted(candidates, key=lambda row: str(row.get("invoice_date") or ""))[0]


def network_plan_status(ois_status, contract_complete) -> str:
	"""Network plan status (SPEC 4.6)."""
	if str(ois_status or "").strip().lower() != "processed":
		return "Being set up"
	if not contract_complete:
		return "Awaiting signatures"
	return "Active"


def fixed_plan_status(has_paid_invoice) -> str:
	"""Fixed plan status (SPEC 4.6)."""
	return "Active" if has_paid_invoice else "Awaiting first payment"


def cycle_label(cycle) -> str:
	"""``Billed monthly`` and friends; empty for unknown or empty cycles."""
	return _CYCLE_LABELS.get(str(cycle or "").strip().lower(), "")


def term_label(years) -> str:
	"""``1 year`` / ``N years``; empty when the term is not positive."""
	year = _as_int(years)
	if year <= 0:
		return ""
	if year == 1:
		return "1 year"
	return "%d years" % year


def quote_status_label(docstatus) -> str:
	"""``Accepted`` for submitted quotes, ``Planned`` for drafts (SPEC 5.3)."""
	docstatus = _as_int(docstatus)
	if docstatus == 1:
		return "Accepted"
	if docstatus == 0:
		return "Planned"
	return ""


def _empty_plan() -> dict:
	return {
		"name": "",
		"source": "none",
		"status": "",
		"cycle": "",
		"cycle_label": "",
		"term_years": None,
		"term_label": "",
		"currency": "",
		"facilities_on_plan": None,
		"facility_monthly_excl_vat": None,
		"facility_annual_excl_vat": None,
		"cycle_amount_incl_vat": None,
		"current_period": None,
		"next_invoice": None,
		"schedule": [],
	}


def empty_commercial(unavailable=False) -> dict:
	"""The unknown-plan shape (SPEC 5.3) used for gaps and failures."""
	return {
		"journey": JOURNEY_UNKNOWN,
		"journey_label": "",
		"plan_type": PLAN_UNKNOWN,
		"has_tokens": False,
		"unavailable": bool(unavailable),
		"plan": _empty_plan(),
		"quotes": [],
	}
