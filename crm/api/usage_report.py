"""Facility token usage report on the CX Portal (P-135, docs/cx-facility-usage-report.md).

The facility owner picks a date range and sees, for one of their facilities: tokens added
(by source) and consumed, the per-billing-event breakdown, patient registrations, a daily
series and a per-event price check, and can download the same report as CSV.

CRM decides who may see a facility; the metering app answers through the
`crm_get_facility_usage_report` hook, so CRM never imports it.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr, flt

from crm.api.token_alerts import _portal_facilities
from crm.api.website_redirect import require_portal_user

HOOK = "crm_get_facility_usage_report"

CHECK_LABELS = {
	"matches": "Matches the price",
	"price_differs": "Price differs from current list",
	"charge_differs": "Charge differs from quantity × price",
	"pre_priced": "Pre-priced (ledger export)",
}
SOURCE_LABELS = {"paid": "Paid tokens", "package": "Initial package", "bonus": "Welcome bonus", "coupon": "Coupon", "other": "Other"}


def _facility_for_owner(mfl_code: Any) -> dict:
	require_portal_user()
	facility = _portal_facilities(frappe.session.user).get(cstr(mfl_code).strip().lower())
	if not facility:
		frappe.throw(_("That facility is not part of your account."), frappe.PermissionError)
	if not facility["fid"]:
		frappe.throw(_("The usage report needs the facility's HFR Facility ID. Link the facility to the registry first."))
	return facility


def _report(facility: dict, from_date: Any, to_date: Any) -> dict:
	methods = frappe.get_hooks(HOOK)
	if not methods:
		return {"status": "disabled"}
	try:
		report = frappe.get_attr(methods[-1])(facility["fid"], from_date, to_date) or {"status": "unavailable"}
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.log_error(title="Facility usage report failed", message=frappe.get_traceback())
		report = {"status": "unavailable"}
	report["facility"] = {"mfl_code": facility["mfl_code"], "facility_name": facility["facility_name"], "fid": facility["fid"]}
	return report


@frappe.whitelist(methods=["GET", "POST"])
def get_facility_usage_report(mfl_code: Any, from_date: Any, to_date: Any):
	"""The usage report for one of the signed-in owner's facilities."""
	return _report(_facility_for_owner(mfl_code), from_date, to_date)


def _cell(value):
	"""Neutralise spreadsheet formulas in text cells (CSV injection)."""
	if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
		return "'" + value
	return value


def _number(value):
	if value is None or value == "":
		return ""
	value = flt(value, 4)
	return int(value) if value == int(value) else value


def report_csv(report: dict) -> str:
	"""The report as one CSV with summary, tokens added, breakdown, daily and event sections."""
	out = io.StringIO()
	writer = csv.writer(out)

	def row(*values):
		writer.writerow([_cell(v) for v in values])

	facility = report.get("facility") or {}
	summary = report.get("summary") or {}
	added = summary.get("tokens_added") or {}
	detail = report.get("detail") or {}
	row("Token usage report")
	row("Facility", facility.get("facility_name"))
	row("Facility ID", facility.get("fid"))
	row("MFL code", facility.get("mfl_code"))
	row("From", report.get("from_date"))
	row("To", report.get("to_date"))
	row("Time zone", report.get("time_zone"))
	row("Generated", report.get("generated_at"))
	row()
	row("Summary")
	row("Tokens added in range", _number((added.get("in_range") or {}).get("total")))
	row("Tokens added since onboarding", _number(added.get("all_time")))
	row("Tokens consumed in range", _number(summary.get("tokens_consumed")))
	row("Available tokens now", _number(summary.get("balance")))
	for key, label in (("patient_registrations", "Patient registrations"), ("consultations", "Consultations")):
		entry = summary.get(key) or {}
		row(label, _number(entry.get("value")), "estimate" if entry.get("estimated") else "")
	if detail.get("available"):
		row("Event detail covers", "from %s" % detail.get("from"), "complete" if detail.get("complete") else "partial")
	else:
		row("Event detail covers", "not available for this range")
	for key, count in (summary.get("checks") or {}).items():
		row("Price check: %s" % CHECK_LABELS.get(key, key), count)
	row()
	row("Tokens added")
	row("Date", "Source", "Tokens", "Invoice")
	for grant in added.get("rows") or []:
		row(grant.get("date"), grant.get("source"), _number(grant.get("tokens")), grant.get("reference"))
	row()
	row("Consumption by billing event")
	row("Billing event", "Code", "Category", "Quantity", "Quantity is estimate", "Current price (tokens)", "Tokens consumed", "Share %")
	for item in report.get("breakdown") or []:
		row(
			item.get("label"),
			item.get("billing_event"),
			item.get("category"),
			_number(item.get("quantity")),
			"yes" if item.get("quantity_estimated") else "no",
			_number(item.get("current_price")),
			_number(item.get("tokens")),
			_number(flt(item.get("share")) * 100),
		)
	row()
	row("Daily consumption")
	row("Date", "Tokens consumed")
	for day in report.get("daily") or []:
		row(day.get("date"), _number(day.get("tokens")))
	row()
	row("Billing events")
	row("Time", "Event ID", "Billing event", "Quantity", "Unit price charged", "Tokens charged", "Quantity × unit price", "Current price", "Catalog version", "Price check")
	for event in report.get("events") or []:
		row(
			event.get("time"),
			event.get("event_id"),
			event.get("billing_event"),
			_number(event.get("quantity")),
			_number(event.get("unit_tokens")),
			_number(event.get("tokens")),
			_number(event.get("expected_tokens")),
			_number(event.get("current_price")),
			event.get("catalog_version"),
			CHECK_LABELS.get(event.get("check"), event.get("check")),
		)
	return out.getvalue()


@frappe.whitelist(methods=["GET"])
def download_facility_usage_report(mfl_code: Any, from_date: Any, to_date: Any):
	"""The same report as a CSV file."""
	facility = _facility_for_owner(mfl_code)
	report = _report(facility, from_date, to_date)
	if report.get("status") != "ok":
		frappe.throw(_("The usage report is not available right now. Please try again later."))
	safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in facility["fid"])
	frappe.local.response.filename = "token-usage-%s-%s-to-%s.csv" % (safe, report["from_date"], report["to_date"])
	frappe.local.response.filecontent = "﻿" + report_csv(report)
	frappe.local.response.type = "download"
