from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.contracts import get_authenticated_signing_context
from crm.api.optin import _submission_pending_for_current_user
from crm.utils.optin_network import set_network_link


class TestOptInNetworkLinks(UnitTestCase):
	def test_set_network_link_is_optional_and_does_not_overwrite(self):
		doc = frappe._dict(doctype="CRM Contract", optin_network="existing-network")
		with (
			patch("crm.utils.optin_network.frappe.db.exists", return_value=True),
			patch("crm.utils.optin_network.frappe.db.has_column", return_value=True),
		):
			self.assertEqual(set_network_link(doc, "new-network"), "existing-network")
			self.assertEqual(doc.optin_network, "existing-network")

	def test_authenticated_context_matches_only_a_pending_counterparty(self):
		doc = SimpleNamespace(
			name="CONT-1",
			contract_html="<p>Terms</p>",
			deal="DEAL-1",
			signatories=[
				frappe._dict(
					name="FAC-1",
					signatory_role="Facility Signatory",
					signatory_email="facility@example.com",
					signatory_name="Facility Signer",
					status="Signed",
				),
				frappe._dict(
					name="ROW-1",
					signatory_role="Network Signatory",
					signatory_email="Signer@example.com",
					signatory_name="Network Signer",
					status="Pending",
				),
			],
		)
		with (
			patch("crm.api.contracts.frappe.local.session", frappe._dict(user="signer@example.com")),
			patch("crm.api.contracts.frappe.has_permission", return_value=True),
			patch(
				"crm.api.contracts.frappe.db.get_value",
				return_value=frappe._dict(email="signer@example.com", full_name="Network Signer"),
			),
			patch("crm.api.contracts.frappe.get_doc", return_value=doc),
		):
			result = get_authenticated_signing_context("CONT-1")

		self.assertTrue(result["action_required"])
		self.assertEqual(result["role"], "Network Signatory")
		self.assertEqual(result["email"], "signer@example.com")

	def test_pending_action_filter_matches_signatory_email(self):
		row = {"contract": "CONT-1", "deal": "DEAL-1", "facility_signing_status": "Signed"}
		contract = SimpleNamespace(name="CONT-1")
		signer = frappe._dict(
			signatory_email="signer@example.com",
			status="Pending",
		)
		with (
			patch("crm.api.optin.frappe.local.session", frappe._dict(user="signer@example.com")),
			patch(
				"crm.api.optin.frappe.db.get_value",
				return_value=frappe._dict(name="signer@example.com", email="signer@example.com"),
			),
		):
			self.assertTrue(
				_submission_pending_for_current_user(
					row,
					{"CONT-1": contract},
					{},
					{"CONT-1": {"Network Signatory": [signer]}},
				)
			)
