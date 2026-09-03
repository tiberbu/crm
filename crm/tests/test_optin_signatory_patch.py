from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.patches.v1_0.backfill_optin_signatory_modes import execute


class TestOptInSignatoryModePatch(UnitTestCase):
	def test_backfills_only_unambiguous_self_signing_submissions(self):
		with (
			patch(
				"crm.patches.v1_0.backfill_optin_signatory_modes.frappe.db.table_exists",
				return_value=True,
			),
			patch(
				"crm.patches.v1_0.backfill_optin_signatory_modes.frappe.db.has_column",
				return_value=True,
			),
			patch(
				"crm.patches.v1_0.backfill_optin_signatory_modes.frappe.get_all",
				return_value=[
					frappe._dict(
						name="OIS-SELF",
						signatory_mode="",
						submitter_email="signer@example.com",
						facility_signatory_email="SIGNER@example.com",
					),
					frappe._dict(
						name="OIS-DELEGATED",
						signatory_mode="",
						submitter_email="ict@example.com",
						facility_signatory_email="signer@example.com",
					),
					frappe._dict(
						name="OIS-ALREADY-MARKED",
						signatory_mode="delegate",
						submitter_email="ict@example.com",
						facility_signatory_email="signer@example.com",
					),
				],
			),
			patch(
				"crm.patches.v1_0.backfill_optin_signatory_modes.frappe.db.set_value"
			) as set_value,
		):
			execute()

		set_value.assert_called_once_with(
			"CRM Opt-In Submission",
			"OIS-SELF",
			"signatory_mode",
			"self",
			update_modified=False,
		)
