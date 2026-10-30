"""Low-token email alerts that facility owners manage from the CX Portal.

An owner sets a threshold per facility. A scheduled check reads every alerted facility's
live balance through the metering hook in one call and emails the owner once when the
balance reaches the threshold; a top-up above the threshold re-arms the alert. Without a
live balance (metering off, unavailable, or not yet metered) nothing is sent.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, escape_html, get_url, now_datetime

from crm.api.customer_experience import _snapshot_facilities
from crm.api.website_redirect import (
	PORTAL_ROUTE,
	_customer_portal_accounts,
	fetch_facility_token_balances,
	get_user_ois_numbers,
	require_portal_user,
)

DOCTYPE = "CRM Facility Token Alert"
ALERT_FIELDS = ["name", "mfl_code", "hfr_facility_id", "facility_name", "enabled", "threshold", "below_threshold", "last_balance", "last_checked_at", "alert_sent_at"]


def _facility_fid(row: dict) -> str:
	for key in ("hfr_facility_id", "facility_fid", "fid", "facility_id"):
		value = cstr(row.get(key)).strip()
		if value.upper().startswith("FID-"):
			return value
	return ""


def _portal_facilities(user: str) -> dict[str, dict]:
	"""The facilities the CX Portal shows this user, keyed by lower-cased MFL code."""
	facilities = {}
	for account in _customer_portal_accounts(user, include_balances=False):
		for row in account.get("facilities") or []:
			mfl = cstr(row.get("mfl_code")).strip()
			if mfl:
				facilities.setdefault(mfl.lower(), {"mfl_code": mfl, "facility_name": cstr(row.get("facility_name")), "fid": _facility_fid(row)})
	for ois_number in get_user_ois_numbers(user):
		submission = frappe.get_doc("CRM Opt-In Submission", ois_number)
		for row in _snapshot_facilities(submission):
			mfl = cstr(row.get("mfl_code")).strip()
			if mfl:
				facilities.setdefault(mfl.lower(), {"mfl_code": mfl, "facility_name": cstr(row.get("facility_name")), "fid": _facility_fid(row)})
	return facilities


def _serialize(alert) -> dict:
	return {field: alert.get(field) for field in ALERT_FIELDS}


@frappe.whitelist(methods=["GET", "POST"])
def get_token_alerts():
	"""The signed-in owner's alerts, keyed by MFL code."""
	require_portal_user()
	rows = frappe.get_all(DOCTYPE, filters={"user": frappe.session.user}, fields=ALERT_FIELDS, ignore_permissions=True)
	return {"alerts": {row.mfl_code: row for row in rows}}


@frappe.whitelist(methods=["POST"])
def save_token_alert(mfl_code: Any, enabled: Any = 1, threshold: Any = None):
	"""Create or update the owner's alert for one of their facilities, then check it against the live balance."""
	require_portal_user()
	user = frappe.session.user
	facility = _portal_facilities(user).get(cstr(mfl_code).strip().lower())
	if not facility:
		frappe.throw(_("That facility is not part of your account."), frappe.PermissionError)
	if not facility["fid"]:
		frappe.throw(_("Token alerts need the facility's HFR Facility ID. Link the facility to the registry first."))

	enabled = cint(enabled)
	threshold = cint(threshold)
	name = frappe.db.get_value(DOCTYPE, {"user": user, "mfl_code": facility["mfl_code"]})
	alert = frappe.get_doc(DOCTYPE, name) if name else frappe.new_doc(DOCTYPE)
	# A new threshold, or switching back on, starts a fresh drop so the owner hears about it.
	if alert.is_new() or threshold != alert.threshold or (enabled and not alert.enabled):
		alert.below_threshold = 0
	alert.update({
		"user": user,
		"mfl_code": facility["mfl_code"],
		"hfr_facility_id": facility["fid"],
		"facility_name": facility["facility_name"],
		"enabled": enabled,
		"threshold": threshold,
	})
	alert.save(ignore_permissions=True)

	check = {"balance_status": None, "balance": None, "alert_sent": False}
	if alert.enabled:
		entry = fetch_facility_token_balances([alert.hfr_facility_id]).get(alert.hfr_facility_id)
		check["balance_status"] = (entry or {}).get("status") or "unavailable"
		if check["balance_status"] == "ok":
			check["balance"] = float(entry.get("balance") or 0)
		check["alert_sent"] = _evaluate(alert, entry)
		alert.reload()
	return {"alert": _serialize(alert), **check}


def _evaluate(alert, entry: dict | None) -> bool:
	"""Record the live balance and send the email on a new drop to or below the threshold."""
	state = {"last_checked_at": now_datetime()}
	sent = False
	if entry and entry.get("status") == "ok":
		balance = float(entry.get("balance") or 0)
		state["last_balance"] = balance
		if balance > alert.threshold:
			state["below_threshold"] = 0
		elif not alert.below_threshold:
			_send_alert_email(alert, balance)
			state.update(below_threshold=1, alert_sent_at=now_datetime())
			sent = True
	# State fields only: no version row or modified bump every scheduled check.
	frappe.db.set_value(DOCTYPE, alert.name, state, update_modified=False)
	return sent


def _send_alert_email(alert, balance: float):
	recipient = frappe.db.get_value("User", alert.user, "email") or alert.user
	facility = escape_html(alert.facility_name or alert.mfl_code)
	portal = get_url(PORTAL_ROUTE)
	frappe.sendmail(
		recipients=[recipient],
		subject=_("Low tokens: {0} has {1} tokens left").format(alert.facility_name or alert.mfl_code, f"{balance:,.0f}"),
		message=_(
			"<p>{facility} (Facility ID {fid}, MFL {mfl}) has <strong>{balance}</strong> tokens available, "
			"at or below the alert threshold of {threshold} you set.</p>"
			"<p>Clinical work stops when tokens run out. Top up from the facility portal: "
			'<a href="{portal}">{portal}</a></p>'
			"<p>You can change or turn off this alert on the facility's page in the portal.</p>"
		).format(
			facility=facility,
			fid=escape_html(alert.hfr_facility_id),
			mfl=escape_html(alert.mfl_code),
			balance=f"{balance:,.0f}",
			threshold=f"{alert.threshold:,}",
			portal=portal,
		),
		reference_doctype=DOCTYPE,
		reference_name=alert.name,
	)


def check_token_alerts():
	"""Scheduled: check every enabled alert against one batched balance lookup."""
	alerts = frappe.get_all(DOCTYPE, filters={"enabled": 1}, pluck="name")
	if not alerts:
		return
	docs = [frappe.get_doc(DOCTYPE, name) for name in alerts]
	balances = fetch_facility_token_balances(doc.hfr_facility_id for doc in docs)
	for alert in docs:
		try:
			_evaluate(alert, balances.get(cstr(alert.hfr_facility_id).strip()))
		except Exception:
			frappe.log_error(title=f"Token alert {alert.name} failed", message=frappe.get_traceback())
