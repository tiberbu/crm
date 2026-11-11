"""Facility usage report on the CX Portal (P-135): who may see it, the hook seam and the CSV."""

import csv
import io
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import usage_report

MFL = "UR-10001"
FID = "FID-00-UR-10001"
FACILITIES = {MFL.lower(): {"mfl_code": MFL, "facility_name": "Usage Test Clinic", "fid": FID}}

REPORT = {
	"status": "ok",
	"fid": FID,
	"from_date": "2026-11-01",
	"to_date": "2026-11-07",
	"time_zone": "Africa/Nairobi",
	"generated_at": "2026-11-08 09:00:00",
	"detail": {"available": True, "from": "2026-11-01 00:00:00", "complete": True, "truncated": False},
	"summary": {
		"tokens_added": {"in_range": {"total": 600, "by_source": {"paid": 500, "bonus": 100}}, "all_time": 900, "rows": [{"date": "2026-11-02 10:00:00", "source": "Token Purchase", "group": "paid", "tokens": 500, "reference": "ACC-SINV-1"}]},
		"tokens_consumed": 13,
		"balance": 42,
		"patient_registrations": {"value": 3, "estimated": False},
		"consultations": {"value": 1, "estimated": False},
		"checks": {"matches": 2, "price_differs": 1},
	},
	"breakdown": [{"billing_event": "patient_registration", "label": "Patient registration", "category": "Front office", "current_price": 3, "quantity": 3, "quantity_estimated": False, "tokens": 9, "share": 0.69}],
	"daily": [{"date": "2026-11-02", "tokens": 13}],
	"events": [{"time": "2026-11-02 08:00:00", "event_id": "=HYPERLINK(1)", "billing_event": "patient_registration", "quantity": 2, "unit_tokens": 3, "tokens": 6, "expected_tokens": 6, "current_price": 3, "catalog_version": "1", "check": "matches"}],
}


class TestUsageReport(IntegrationTestCase):
	def setUp(self):
		self.calls = []

	@contextmanager
	def portal(self, facilities=FACILITIES, hooks=("x.report",), result=REPORT):
		def report(fid, from_date, to_date):
			self.calls.append((fid, from_date, to_date))
			if isinstance(result, Exception):
				raise result
			return dict(result)

		with patch.object(usage_report, "require_portal_user", return_value=[]), patch.object(
			usage_report, "_portal_facilities", return_value=facilities
		), patch.object(usage_report.frappe, "get_hooks", return_value=list(hooks)), patch.object(
			usage_report.frappe, "get_attr", return_value=report
		):
			yield

	def test_rejects_a_facility_outside_the_owners_portal(self):
		with self.portal(facilities={}), self.assertRaises(frappe.PermissionError):
			usage_report.get_facility_usage_report(MFL, "2026-11-01", "2026-11-07")
		self.assertEqual(self.calls, [])

	def test_requires_an_hfr_facility_id(self):
		with self.portal(facilities={MFL.lower(): {"mfl_code": MFL, "facility_name": "x", "fid": ""}}), self.assertRaises(frappe.ValidationError):
			usage_report.get_facility_usage_report(MFL, "2026-11-01", "2026-11-07")

	def test_asks_the_metering_app_by_fid_and_adds_the_facility(self):
		with self.portal():
			report = usage_report.get_facility_usage_report(MFL.lower(), "2026-11-01", "2026-11-07")
		self.assertEqual(self.calls, [(FID, "2026-11-01", "2026-11-07")])
		self.assertEqual(report["facility"]["fid"], FID)
		self.assertEqual(report["status"], "ok")

	def test_without_a_metering_app_reports_disabled(self):
		with self.portal(hooks=()):
			self.assertEqual(usage_report.get_facility_usage_report(MFL, "2026-11-01", "2026-11-07")["status"], "disabled")

	def test_a_failing_metering_app_is_unavailable_but_range_errors_reach_the_user(self):
		with self.portal(result=RuntimeError("boom")), patch.object(usage_report.frappe, "log_error"):
			self.assertEqual(usage_report.get_facility_usage_report(MFL, "2026-11-01", "2026-11-07")["status"], "unavailable")
		with self.portal(result=frappe.ValidationError("The end date must be on or after the start date.")), self.assertRaises(frappe.ValidationError):
			usage_report.get_facility_usage_report(MFL, "2026-11-07", "2026-11-01")

	def test_csv_has_every_section_and_neutralises_formulas(self):
		text = usage_report.report_csv(dict(REPORT, facility=FACILITIES[MFL.lower()]))
		rows = list(csv.reader(io.StringIO(text)))
		flat = [r[0] for r in rows if r]
		for heading in ("Summary", "Tokens added", "Consumption by billing event", "Daily consumption", "Billing events"):
			self.assertIn(heading, flat)
		self.assertIn(["Facility ID", FID], rows)
		self.assertIn(["Tokens consumed in range", "13"], rows)
		self.assertIn(["Price check: Price differs from current list", "1"], rows)
		event = next(r for r in rows if r and r[0] == "2026-11-02 08:00:00")
		self.assertEqual(event[1], "'=HYPERLINK(1)")
		self.assertEqual(event[-1], "Matches the price")

	def test_download_sets_a_csv_attachment(self):
		with self.portal():
			usage_report.download_facility_usage_report(MFL, "2026-11-01", "2026-11-07")
		self.assertEqual(frappe.local.response.type, "download")
		self.assertEqual(frappe.local.response.filename, "token-usage-FID-00-UR-10001-2026-11-01-to-2026-11-07.csv")
		self.assertTrue(frappe.local.response.filecontent.startswith("﻿Token usage report"))

	def test_download_refuses_when_the_report_is_unavailable(self):
		with self.portal(result={"status": "unavailable"}), self.assertRaises(frappe.ValidationError):
			usage_report.download_facility_usage_report(MFL, "2026-11-01", "2026-11-07")
