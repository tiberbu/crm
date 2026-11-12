from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.patches.v1_0.add_cx_portal_awaiting_signature_status import NEW_OPTIONS, execute


class TestCxPortalAwaitingSignatureStatusPatch(UnitTestCase):
	def test_patch_updates_options_when_the_field_exists(self):
		with (
			patch("crm.patches.v1_0.add_cx_portal_awaiting_signature_status.frappe.db.exists", return_value=True) as exists,
			patch("crm.patches.v1_0.add_cx_portal_awaiting_signature_status.frappe.db.set_value") as set_value,
			patch("crm.patches.v1_0.add_cx_portal_awaiting_signature_status.frappe.clear_cache") as clear_cache,
		):
			execute()

		exists.assert_called_once_with("Custom Field", "CRM Opt-In Submission-portal_invitation_status")
		set_value.assert_called_once_with(
			"Custom Field", "CRM Opt-In Submission-portal_invitation_status", "options", NEW_OPTIONS
		)
		clear_cache.assert_called_once_with(doctype="CRM Opt-In Submission")

	def test_patch_is_a_no_op_when_the_field_is_missing(self):
		with (
			patch("crm.patches.v1_0.add_cx_portal_awaiting_signature_status.frappe.db.exists", return_value=False) as exists,
			patch("crm.patches.v1_0.add_cx_portal_awaiting_signature_status.frappe.db.set_value") as set_value,
			patch("crm.patches.v1_0.add_cx_portal_awaiting_signature_status.frappe.clear_cache") as clear_cache,
		):
			execute()

		exists.assert_called_once()
		set_value.assert_not_called()
		clear_cache.assert_not_called()

	def test_option_order_keeps_pending_first(self):
		self.assertEqual(
			NEW_OPTIONS.split("\n"),
			["Pending", "Awaiting signature", "Sent", "Already active", "Blocked", "Failed"],
		)
