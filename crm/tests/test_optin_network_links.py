from unittest.mock import patch

from frappe.tests import UnitTestCase

from crm.patches.v1_0.link_optin_records_to_network import _add_conflict


class TestOptInNetworkLinkConflicts(UnitTestCase):
	def test_reports_disagreeing_canonical_network_sources(self):
		conflicts = []
		with patch(
			"crm.patches.v1_0.link_optin_records_to_network.network_name",
			side_effect=lambda value: value if value in {"network-a", "network-b"} else "",
		):
			_add_conflict(
				conflicts,
				"Sales Invoice",
				"SINV-001",
				{"optin_network": "network-a", "crm_deal": "network-b"},
			)

		self.assertEqual(len(conflicts), 1)
		self.assertEqual(conflicts[0]["name"], "SINV-001")
		self.assertEqual(conflicts[0]["sources"]["optin_network"], "network-a")

	def test_does_not_report_matching_sources(self):
		conflicts = []
		with patch(
			"crm.patches.v1_0.link_optin_records_to_network.network_name",
			return_value="network-a",
		):
			_add_conflict(
				conflicts,
				"Sales Invoice",
				"SINV-001",
				{"optin_network": "network-a", "crm_deal": "network-a"},
			)

		self.assertEqual(conflicts, [])

	def test_reports_a_populated_reference_that_is_not_a_network(self):
		conflicts = []
		with patch(
			"crm.patches.v1_0.link_optin_records_to_network.network_name",
			side_effect=lambda value: value if value == "network-a" else "",
		):
			_add_conflict(
				conflicts,
				"CRM Contract",
				"CONTRACT-001",
				{"optin_network": "old-network-name", "network_slug": "network-a"},
			)

		self.assertEqual(len(conflicts), 1)
		self.assertEqual(conflicts[0]["sources"]["optin_network"], "old-network-name")
