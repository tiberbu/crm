import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.optin import get_optin_dashboard


class TestOptInDashboard(UnitTestCase):
	def test_dashboard_aggregates_optin_value_facilities_and_signing(self):
		submissions = [
			frappe._dict(
				{
					"name": "OIS-0001",
					"status": "Processed",
					"network_slug": "network-a",
					"submitter_email": "first@example.com",
					"submitted_at": "2026-08-28 10:00:00",
					"deal": "DEAL-0001",
					"error_log": "",
					"raw_json": json.dumps(
						{
							"contact": {"organisation": "First Facility Group"},
							"pricing": [
								{"keph_level": "Level 2", "annual_kes": 1000},
								{"keph_level": "Level 3A", "annual_kes": 3000},
							],
						}
					),
				}
			),
			frappe._dict(
				{
					"name": "OIS-0002",
					"status": "Processed",
					"network_slug": "network-b",
					"submitter_email": "second@example.com",
					"submitted_at": "2026-08-29 10:00:00",
					"deal": "DEAL-0002",
					"error_log": "",
					"raw_json": json.dumps(
						{
							"contact": {"organisation": "Second Facility Group"},
							"pricing": [{"keph_level": "Level 3A", "annual_kes": 2000}],
						}
					),
				}
			),
			frappe._dict(
				{
					"name": "OIS-0003",
					"status": "Failed",
					"network_slug": "network-a",
					"submitter_email": "failed@example.com",
					"submitted_at": "2026-08-29 12:00:00",
					"deal": "",
					"error_log": "Validation failed",
					"raw_json": json.dumps({"contact": {"organisation": "Failed Facility"}}),
				}
			),
		]
		quotes = [
			frappe._dict({"name": "QUO-0002", "crm_deal": "DEAL-0002", "grand_total": 2320}),
			frappe._dict({"name": "QUO-0001", "crm_deal": "DEAL-0001", "grand_total": 1160}),
		]
		contracts = [
			frappe._dict({"name": "CONT-0002", "deal": "DEAL-0002", "status": "Awaiting Signatures"}),
			frappe._dict({"name": "CONT-0001", "deal": "DEAL-0001", "status": "Fully Executed"}),
		]
		signatories = [
			frappe._dict(
				{
					"parent": "CONT-0001",
					"status": "Signed",
					"signed_at": "2026-08-28 12:00:00",
					"invite_token": "sent",
					"invite_expiry": "2099-01-01 00:00:00",
				}
			),
			frappe._dict(
				{
					"parent": "CONT-0002",
					"status": "Pending",
					"signed_at": None,
					"invite_token": "sent",
					"invite_expiry": "2099-01-01 00:00:00",
				}
			),
		]

		with (
			patch("crm.api.optin.frappe.has_permission", return_value=True),
			patch("crm.api.optin.frappe.utils.now_datetime", return_value=datetime(2026, 8, 29)),
			patch(
				"crm.api.optin.frappe.get_list",
				side_effect=[submissions, quotes, contracts, signatories],
			) as get_list,
		):
			result = get_optin_dashboard(period="all")

		self.assertEqual(get_list.call_count, 4)
		self.assertEqual(result["summary"]["submissions"], 3)
		self.assertEqual(result["summary"]["processed"], 2)
		self.assertEqual(result["summary"]["failed"], 1)
		self.assertEqual(result["summary"]["clients"], 2)
		self.assertEqual(result["summary"]["facilities"], 3)
		self.assertEqual(result["summary"]["annual_value"], 3480)
		self.assertEqual(result["summary"]["signature_rate"], 50.0)
		self.assertEqual(result["facility_levels"][1]["level"], "Level 3A")
		self.assertEqual(result["facility_levels"][1]["facilities"], 2)
		self.assertEqual(result["signing_breakdown"][0]["value"], 1)
		self.assertEqual(result["signing_breakdown"][1]["value"], 1)
		self.assertEqual(result["attention"][0]["issue"], "Submission failed")
