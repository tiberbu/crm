from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.patches.v1_0.backfill_contract_signatory_statuses import (
	_canonical_status,
	execute,
)


class TestContractSignatoryStatusPatch(UnitTestCase):
	def test_canonicalizes_supported_and_legacy_statuses(self):
		self.assertEqual(_canonical_status({"status": "pending"}), "Pending")
		self.assertEqual(_canonical_status({"status": "Awaiting signature"}), "Pending")
		self.assertEqual(_canonical_status({"status": "completed"}), "Signed")
		self.assertEqual(_canonical_status({"status": "cancelled"}), "Declined")

	def test_unknown_status_never_reopens_a_captured_signature(self):
		self.assertEqual(
			_canonical_status({"status": "legacy", "signature_data": "data"}),
			"Signed",
		)
		self.assertEqual(
			_canonical_status({"status": "Pending", "signed_at": "2026-08-29 12:00:00"}),
			"Signed",
		)
		self.assertEqual(_canonical_status({"status": "legacy"}), "Pending")

	def test_execute_updates_only_noncanonical_rows(self):
		contract_doc = SimpleNamespace(
			signatories=[
				frappe._dict(name="ROW-1", status="pending"),
				frappe._dict(name="ROW-2", status="Declined"),
			]
		)
		with (
			patch(
				"crm.patches.v1_0.backfill_contract_signatory_statuses.frappe.db.table_exists",
				return_value=True,
			),
			patch(
				"crm.patches.v1_0.backfill_contract_signatory_statuses.frappe.db.has_column",
				return_value=True,
			),
			patch(
				"crm.patches.v1_0.backfill_contract_signatory_statuses.frappe.get_list",
				return_value=[SimpleNamespace(name="CONT-1")],
			),
			patch(
				"crm.patches.v1_0.backfill_contract_signatory_statuses.frappe.get_doc",
				return_value=contract_doc,
			),
			patch("crm.patches.v1_0.backfill_contract_signatory_statuses.frappe.db.set_value") as set_value,
		):
			execute()

		set_value.assert_called_once_with(
			"CRM Contract Signatory", "ROW-1", "status", "Pending", update_modified=False
		)
