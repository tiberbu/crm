"""Pure decisions for the Opt-In billing ledger (spec P-124 to P-134).

P-134: customers never invoice a period before its contract date; only staff may issue early.

No frappe import: the API module reads the schedule and the ERPNext documents and
hands plain dicts here, so every rule is unit-tested without a site.
"""

from __future__ import annotations

from datetime import date, datetime

MAX_ADVANCE_PERIODS = 4
MAX_UNPAID_INVOICES = 4

STATE_LABELS = {
	"scheduled": "Scheduled",
	"order_ready": "Order ready",
	"due": "Due",
	"overdue": "Overdue",
	"paid": "Paid",
	"paid_ahead": "Paid ahead",
	"needs_attention": "Needs attention",
}


def _int(value) -> int:
	try:
		return int(float(value or 0))
	except (TypeError, ValueError):
		return 0


def _num(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def to_date(value) -> date | None:
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	text = str(value or "").strip()[:10]
	if not text:
		return None
	try:
		return date.fromisoformat(text)
	except ValueError:
		return None


def _iso(value) -> str:
	parsed = to_date(value)
	return parsed.isoformat() if parsed else ""


def period_label(row: dict) -> str:
	year = _int(row.get("year_number"))
	quarter = _int(row.get("quarter_number"))
	if year and quarter:
		return "Year %d · Q%d" % (year, quarter)
	if year:
		return "Year %d" % year
	return str(row.get("period_label") or "Period").strip()


def scheduled_date(row: dict) -> str:
	"""The contract date of the period, even after an early issue moved ``invoice_date``."""
	return _iso(row.get("scheduled_invoice_date") or row.get("invoice_date") or row.get("scheduled_order_date"))


def scheduled_due_date(row: dict) -> str:
	return _iso(row.get("scheduled_due_date") or row.get("invoice_due_date"))


def sort_key(row: dict) -> tuple:
	return (_int(row.get("year_number")) or 999, _int(row.get("quarter_number")) or 9, scheduled_date(row))


def period_state(row: dict, invoice: dict | None, today) -> str:
	"""Customer-facing state of one schedule row (P-129)."""
	today = to_date(today) or date.today()
	if invoice and _int(invoice.get("docstatus")) == 1:
		if _num(invoice.get("outstanding")) <= 0:
			start = to_date(scheduled_date(row))
			return "paid_ahead" if start and today < start else "paid"
		due = to_date(invoice.get("due_date"))
		return "overdue" if due and today > due else "due"
	if str(row.get("status") or "").strip().lower() == "failed":
		return "needs_attention"
	if row.get("sales_order"):
		return "order_ready"
	return "scheduled"


def is_issued(row: dict) -> bool:
	return bool(str(row.get("sales_invoice") or "").strip())


def issuable_rows(rows) -> list[dict]:
	return sorted((row for row in rows or [] if isinstance(row, dict) and not is_issued(row)), key=sort_key)


def is_due(row: dict, today) -> bool:
	"""The period's contract invoice date has arrived (P-134)."""
	start = to_date(scheduled_date(row))
	today = to_date(today) or date.today()
	return bool(start) and start <= today


def eligible_rows(rows, today=None, due_only: bool = False) -> list[dict]:
	"""Unissued rows that may be invoiced now. Customers only get rows that are due (P-134)."""
	pending = issuable_rows(rows)
	if not due_only:
		return pending
	return [row for row in pending if is_due(row, today)]


def select_next_periods(rows, count, today=None, due_only: bool = False) -> list[dict]:
	"""The next ``count`` eligible rows, in schedule order (P-125). No holes by construction."""
	count = _int(count)
	if count < 1 or count > MAX_ADVANCE_PERIODS:
		raise ValueError("Choose between 1 and %d periods." % MAX_ADVANCE_PERIODS)
	return eligible_rows(rows, today, due_only)[:count]


def early_due_date(today, scheduled_due) -> str:
	"""Issuing early never brings a due date forward (P-127)."""
	today = to_date(today) or date.today()
	due = to_date(scheduled_due)
	return (due if due and due > today else today).isoformat()


def advance_policy(ois_status, contract_status, rows, unpaid_count, today=None, due_only: bool = False) -> dict:
	"""Whether periods can be invoiced now, and why not (P-125, P-126, P-134).

	``due_only`` is the customer rule: a period is invoiced only once its contract date
	arrives, never ahead of it. Staff may still issue early (``due_only=False``).
	"""
	pending = issuable_rows(rows)
	eligible = eligible_rows(rows, today, due_only)
	policy = {"allowed": False, "reason": "", "max_periods": 0, "remaining": len(pending)}
	if str(ois_status or "").strip() != "Processed":
		policy["reason"] = "Your Opt-In request is still being processed."
	elif str(contract_status or "").strip() != "Fully Executed":
		policy["reason"] = "Invoicing starts once every signatory has signed the contract."
	elif not pending:
		policy["reason"] = "Every period of your contract already has an invoice."
	elif not eligible:
		nxt = scheduled_date(pending[0])
		policy["reason"] = (
			"Your next invoice is created on %s. Invoices are issued on their scheduled date, not before." % nxt
			if nxt
			else "Your next invoice is created on its scheduled date."
		)
	elif _int(unpaid_count) >= MAX_UNPAID_INVOICES:
		policy["reason"] = "Pay your open invoices first. You can have up to %d unpaid invoices at a time." % MAX_UNPAID_INVOICES
	else:
		slots = MAX_UNPAID_INVOICES - _int(unpaid_count)
		policy.update({"allowed": True, "max_periods": max(1, min(MAX_ADVANCE_PERIODS, len(eligible), slots))})
	return policy


def ledger_summary(periods, today) -> dict:
	"""Money at a glance across every period (P-131)."""
	today = to_date(today) or date.today()
	totals = {
		"contract_total": 0.0,
		"invoiced_total": 0.0,
		"paid_total": 0.0,
		"outstanding_total": 0.0,
		"overdue_total": 0.0,
		"paid_ahead_total": 0.0,
	}
	next_payment = None
	for period in periods or []:
		amount = _num(period.get("amount"))
		state = period.get("state")
		totals["contract_total"] += amount
		if period.get("sales_invoice"):
			invoiced = _num(period.get("invoice_total")) or amount
			outstanding = max(_num(period.get("outstanding")), 0.0)
			totals["invoiced_total"] += invoiced
			totals["paid_total"] += max(invoiced - outstanding, 0.0)
			totals["outstanding_total"] += outstanding
			if state == "overdue":
				totals["overdue_total"] += outstanding
			if state == "paid_ahead":
				totals["paid_ahead_total"] += invoiced
		if next_payment is None and state not in ("paid", "paid_ahead"):
			date_value = period.get("due_date") if state in ("due", "overdue") else period.get("scheduled_date")
			next_payment = {
				"label": period.get("label"),
				"date": date_value or "",
				"amount": _num(period.get("outstanding")) if period.get("sales_invoice") else amount,
				"state": state,
				"sales_invoice": period.get("sales_invoice") or "",
			}
	summary = {key: round(value, 2) for key, value in totals.items()}
	summary["next_payment"] = next_payment
	return summary


def quote_status_label(contract_status) -> str:
	"""Yearly quotes are committed by the contract, not by their docstatus (P-130)."""
	return "Accepted" if str(contract_status or "").strip() == "Fully Executed" else "Awaiting signatures"
