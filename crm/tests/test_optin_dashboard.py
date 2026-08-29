import json
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.optin import get_optin_dashboard


class TestOptInDashboard(UnitTestCase):
	def test_dashboard_aggregates_optin_value_facilities_and_signing(self):
		configured_networks = [
			frappe._dict({"name": "network-a"}),
			frappe._dict({"name": "network-b"}),
		]
		prequalified_facilities = [
			frappe._dict({"name": "FAC-0001"}),
			frappe._dict({"name": "FAC-0002"}),
			frappe._dict({"name": "FAC-0003"}),
		]
		memberships = [
			frappe._dict({"parent": "FAC-0001", "network": "network-a"}),
			frappe._dict({"parent": "FAC-0002", "network": "network-a"}),
			frappe._dict({"parent": "FAC-0003", "network": "network-b"}),
		]
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
								{
									"mfl_code": "1001",
									"facility_name": "First Clinic",
									"keph_level": "Level 2",
									"annual_kes": 1000,
								},
								{
									"mfl_code": "1002",
									"facility_name": "Second Clinic",
									"keph_level": "Level 3A",
									"annual_kes": 3000,
								},
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
							"pricing": [
								{
									"mfl_code": "2001",
									"facility_name": "Third Clinic",
									"keph_level": "Level 3A",
									"annual_kes": 2000,
								}
							],
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
			frappe._dict(
				{
					"name": "CONT-0002",
					"deal": "DEAL-0002",
					"status": "Awaiting Signatures",
					"creation": "2026-08-29 10:30:00",
				}
			),
			frappe._dict(
				{
					"name": "CONT-0001",
					"deal": "DEAL-0001",
					"status": "Fully Executed",
					"creation": "2026-08-28 10:30:00",
				}
			),
		]
		signatories = [
			frappe._dict(
				{
					"parent": "CONT-0001",
					"signatory_name": "Facility Signatory",
					"signatory_email": "facility@example.com",
					"signatory_role": "Facility Signatory",
					"status": "Signed",
					"signed_at": "2026-08-28 11:00:00",
					"invite_token": "sent",
					"invite_expiry": "2099-01-01 00:00:00",
				}
			),
			frappe._dict(
				{
					"parent": "CONT-0001",
					"signatory_name": "Facility Witness",
					"signatory_email": "witness@example.com",
					"signatory_role": "Facility Witness",
					"status": "Signed",
					"signed_at": "2026-08-28 12:00:00",
					"invite_token": "sent",
					"invite_expiry": "2099-01-01 00:00:00",
				}
			),
			frappe._dict(
				{
					"parent": "CONT-0001",
					"signatory_name": "Network Champion",
					"signatory_email": "network@example.com",
					"signatory_role": "Network Signatory",
					"status": "Signed",
					"signed_at": "2026-08-28 14:00:00",
					"invite_token": "sent",
					"invite_expiry": "2099-01-01 00:00:00",
				}
			),
			frappe._dict(
				{
					"parent": "CONT-0001",
					"signatory_name": "Tiberbu Champion",
					"signatory_email": "tiberbu@example.com",
					"signatory_role": "Tiberbu Signatory",
					"status": "Signed",
					"signed_at": "2026-08-28 16:00:00",
					"invite_token": "sent",
					"invite_expiry": "2099-01-01 00:00:00",
				}
			),
			frappe._dict(
				{
					"parent": "CONT-0002",
					"signatory_name": "Second Facility Signatory",
					"signatory_email": "second-facility@example.com",
					"signatory_role": "Facility Signatory",
					"status": "Pending",
					"signed_at": None,
					"invite_token": "sent",
					"invite_expiry": "2099-01-01 00:00:00",
				}
			),
			frappe._dict(
				{
					"parent": "CONT-0002",
					"signatory_name": "Network Champion",
					"signatory_email": "network@example.com",
					"signatory_role": "Network Signatory",
					"status": "Pending",
					"signed_at": None,
					"invite_token": None,
					"invite_expiry": None,
				}
			),
			frappe._dict(
				{
					"parent": "CONT-0002",
					"signatory_name": "Tiberbu Champion",
					"signatory_email": "tiberbu@example.com",
					"signatory_role": "Tiberbu Signatory",
					"status": "Pending",
					"signed_at": None,
					"invite_token": None,
					"invite_expiry": None,
				}
			),
		]

		with (
			patch("crm.api.optin.frappe.has_permission", return_value=True),
			patch("crm.api.optin.frappe.utils.now_datetime", return_value=datetime(2026, 8, 29)),
			patch(
				"crm.api.optin.frappe.get_list",
				side_effect=[
					configured_networks,
					prequalified_facilities,
					memberships,
					submissions,
					quotes,
					contracts,
					signatories,
				],
			) as get_list,
		):
			result = get_optin_dashboard(period="all")

		self.assertEqual(get_list.call_count, 7)
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

		network_a = next(row for row in result["networks"] if row["network"] == "network-a")
		self.assertEqual(network_a["eligible_facilities"], 2)
		self.assertEqual(network_a["submitted_facilities"], 2)
		self.assertEqual(network_a["opted_in_facilities"], 2)
		self.assertEqual(network_a["fully_executed_facilities"], 2)
		self.assertEqual(network_a["opt_in_rate"], 100.0)
		self.assertEqual(network_a["full_execution_rate"], 100.0)

		first_clinic = next(
			row for row in result["facility_progress"] if row["facility_name"] == "First Clinic"
		)
		self.assertTrue(first_clinic["facility"]["complete"])
		self.assertTrue(first_clinic["network_signatories"]["complete"])
		self.assertTrue(first_clinic["tiberbu_signatories"]["complete"])
		self.assertTrue(first_clinic["fully_executed"])

		self.assertEqual(result["signatory_leaderboard"][0]["name"], "Network Champion")
		self.assertEqual(result["signatory_leaderboard"][0]["signed"], 1)
		self.assertEqual(result["signatory_leaderboard"][0]["assigned"], 2)
		self.assertEqual(result["signatory_leaderboard"][0]["median_response_hours"], 2.0)

		tat = {row["key"]: row for row in result["tat"]}
		self.assertEqual(tat["submission_to_contract"]["median_hours"], 0.5)
		self.assertEqual(tat["facility_complete_to_network_signatory"]["median_hours"], 2.0)
		self.assertEqual(tat["submission_to_full_execution"]["median_hours"], 6.0)
		self.assertEqual(result["facility_leaderboard"][0]["facility_name"], "First Clinic")
