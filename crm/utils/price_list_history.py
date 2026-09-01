"""Structured price-list history shared by quote and contract surfaces.

Price-list changes used to be recorded only as human-readable Deal comments.
That is useful for an activity feed but not reliable enough for a customer-facing
summary: comments are difficult to parse and older quotations have no event data.
These helpers keep a small, append-only JSON history on the quotation and copy it
to the generated contract.  They are deliberately defensive so an older site can
run the application code before its migration has added the optional fields.
"""

from __future__ import annotations

import json

import frappe

HISTORY_FIELD = "crm_price_list_history"
INITIAL_FIELD = "crm_initial_price_list"


def _has_field(doctype: str, fieldname: str) -> bool:
	"""Return whether an optional history column is available on this site."""
	try:
		return bool(frappe.db.has_column(doctype, fieldname))
	except Exception:
		return False


def _get(doc, fieldname: str, default=""):
	try:
		if hasattr(doc, "get"):
			return doc.get(fieldname, default)
		return getattr(doc, fieldname, default)
	except Exception:
		return default


def _set(doc, fieldname: str, value) -> None:
	try:
		if hasattr(doc, "set"):
			doc.set(fieldname, value)
		else:
			setattr(doc, fieldname, value)
	except Exception:
		# Optional fields are intentionally non-critical on legacy installations.
		return


def _now_string() -> str:
	"""Return a timestamp without making audit bookkeeping block a request."""
	try:
		return frappe.utils.cstr(frappe.utils.now_datetime())
	except Exception:
		return ""


def read_history(doc, fieldname: str = HISTORY_FIELD) -> list[dict]:
	"""Parse a quotation/contract history field, returning only valid objects."""
	raw = _get(doc, fieldname, "")
	if isinstance(raw, list):
		items = raw
	else:
		try:
			items = json.loads(raw or "[]")
		except (TypeError, ValueError):
			items = []
	if not isinstance(items, list):
		return []
	return [item for item in items if isinstance(item, dict) and item.get("to")]


def current_price_list(doc, fallback="Standard Selling") -> str:
	"""Return the effective list from a quotation-like document."""
	return frappe.utils.cstr(
		_get(doc, "selling_price_list", "") or _get(doc, "negotiated_price_list", "") or fallback
	).strip()


def ensure_initial(doc, price_list: str | None = None) -> list[dict]:
	"""Seed an initial event once, without overwriting an existing history."""
	history = read_history(doc)
	current = frappe.utils.cstr(price_list or current_price_list(doc)).strip()
	if not current:
		return history

	initial = frappe.utils.cstr(_get(doc, INITIAL_FIELD, "") or "").strip()
	if not initial:
		initial = frappe.utils.cstr((history[0].get("to") if history else "") or current).strip()
		if _has_field("Quotation", INITIAL_FIELD) or _has_field("CRM Contract", INITIAL_FIELD):
			_set(doc, INITIAL_FIELD, initial)

	if not history:
		history = [
			{
				"event": "Initial price list",
				"from": "",
				"to": initial,
				"at": frappe.utils.cstr(_get(doc, "creation", "") or _now_string()),
				"by": frappe.utils.cstr(_get(doc, "owner", "") or "System"),
			}
		]

	if _has_field("Quotation", HISTORY_FIELD) or _has_field("CRM Contract", HISTORY_FIELD):
		_set(doc, HISTORY_FIELD, json.dumps(history, separators=(",", ":"), default=str))
	return history


def append_change(doc, previous: str, current: str) -> list[dict]:
	"""Append one change event, suppressing no-op changes and duplicate retries."""
	previous = frappe.utils.cstr(previous or "").strip()
	current = frappe.utils.cstr(current or "").strip()
	history = ensure_initial(doc, previous or current)
	if not current or previous == current:
		return history

	event = {
		"event": "Price list changed",
		"from": previous,
		"to": current,
		"at": _now_string(),
		"by": frappe.utils.cstr(frappe.session.user or "System"),
	}
	last = history[-1] if history else None
	if not last or not (
		last.get("from") == event["from"] and last.get("to") == event["to"] and last.get("at") == event["at"]
	):
		history.append(event)
	if _has_field("Quotation", HISTORY_FIELD) or _has_field("CRM Contract", HISTORY_FIELD):
		_set(doc, HISTORY_FIELD, json.dumps(history, separators=(",", ":"), default=str))
	return history


def snapshot(doc) -> dict:
	"""Return a stable API/contract payload for the quotation's price history."""
	history = ensure_initial(doc)
	initial = frappe.utils.cstr(_get(doc, INITIAL_FIELD, "") or "").strip()
	if not initial and history:
		initial = frappe.utils.cstr(history[0].get("to") or "").strip()
	current = current_price_list(doc)
	return {"initial": initial or current, "negotiated": current, "history": history}


def set_snapshot(doc, data: dict) -> None:
	"""Copy a quotation snapshot to a CRM Contract when its fields are available."""
	if not data:
		return
	if _has_field("CRM Contract", "initial_price_list"):
		_set(doc, "initial_price_list", data.get("initial") or data.get("negotiated") or "")
	if _has_field("CRM Contract", "negotiated_price_list"):
		_set(doc, "negotiated_price_list", data.get("negotiated") or data.get("initial") or "")
	if _has_field("CRM Contract", "price_list_history"):
		_set(
			doc,
			"price_list_history",
			json.dumps(data.get("history") or [], separators=(",", ":"), default=str),
		)


def contract_snapshot(doc, quote=None) -> dict:
	"""Read a contract snapshot, falling back to its linked quotation for legacy rows."""
	history = (
		read_history(doc, "price_list_history") if _has_field("CRM Contract", "price_list_history") else []
	)
	initial = frappe.utils.cstr(_get(doc, "initial_price_list", "") or "").strip()
	negotiated = frappe.utils.cstr(_get(doc, "negotiated_price_list", "") or "").strip()
	if (not history or not initial or not negotiated) and quote:
		quote_data = snapshot(quote)
		history = history or quote_data["history"]
		initial = initial or quote_data["initial"]
		negotiated = negotiated or quote_data["negotiated"]
	return {"initial": initial or negotiated, "negotiated": negotiated or initial, "history": history}
