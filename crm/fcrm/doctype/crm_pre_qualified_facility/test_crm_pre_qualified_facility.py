from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility import (
	CRMPreQualifiedFacility,
	_send_membership_invitation,
)
from crm.patches.v1_0.backfill_prequalified_facility_organization import execute as backfill_organization


class TestCRMPreQualifiedFacility(UnitTestCase):
	def test_blank_organization_defaults_to_the_facility_name(self):
		facility = SimpleNamespace(organization="", facility_name="Example Hospital")

		CRMPreQualifiedFacility.before_validate(facility)

		self.assertEqual(facility.organization, "Example Hospital")

	def test_membership_invitation_tracks_its_email_queue(self):
		facility = SimpleNamespace(
			doctype="CRM Pre-Qualified Facility",
			name="FAC-0001",
			facility_name="Example Hospital",
		)
		membership = SimpleNamespace(
			name="MEM-0001",
			network="example-network",
			status="Active",
			contact_name="Jane Doe",
			contact_email="jane@example.com",
			invite_email_queue=None,
			invite_sent_at=None,
		)
		network = SimpleNamespace(slug="example-network", display_name="Example Network")
		queue = SimpleNamespace(name="EMAIL-QUEUE-0001", send=Mock())

		with (
			patch.object(frappe, "get_doc", return_value=network),
			patch.object(frappe, "sendmail", return_value=queue) as sendmail,
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(frappe.utils, "get_url", return_value="https://crm.example.test"),
			patch.object(frappe.utils, "now_datetime", return_value="2026-08-28 12:00:00"),
		):
			result = _send_membership_invitation(facility, membership)

		self.assertIs(result, queue)
		self.assertEqual(membership.invite_email_queue, queue.name)
		sendmail.assert_called_once_with(
			recipients=["jane@example.com"],
			subject="You've been pre-qualified: Example Network — CareverseHIMS",
			message=sendmail.call_args.kwargs["message"],
			reference_doctype="CRM Pre-Qualified Facility",
			reference_name="FAC-0001",
			now=True,
		)
		set_value.assert_called_once()
		queue.send.assert_not_called()

	def test_organization_backfill_only_updates_blank_organizations(self):
		facilities = [
			frappe._dict(
				{"name": "FAC-EMPTY", "facility_name": "Default Hospital", "organization": ""}
			),
			frappe._dict(
				{"name": "FAC-GROUP", "facility_name": "Branch Clinic", "organization": "Health Group"}
			),
			frappe._dict(
				{"name": "FAC-NAMELESS", "facility_name": "", "organization": ""}
			),
		]
		with (
			patch.object(frappe.db, "table_exists", return_value=True),
			patch.object(frappe.db, "has_column", return_value=True),
			patch.object(frappe, "get_all", return_value=facilities),
			patch.object(frappe.db, "set_value") as set_value,
		):
			backfill_organization()

		set_value.assert_called_once_with(
			"CRM Pre-Qualified Facility",
			"FAC-EMPTY",
			"organization",
			"Default Hospital",
			update_modified=False,
		)

	def test_after_insert_logs_an_invitation_failure_without_failing_the_insert(self):
		facility = SimpleNamespace(
			flags={},
			memberships=[
				SimpleNamespace(
					name="MEM-0001",
					network="example-network",
					status="Active",
					contact_email="jane@example.com",
				)
			],
		)

		with (
			patch(
				"crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility._send_membership_invitation",
				side_effect=frappe.ValidationError("SES unavailable"),
			),
			patch.object(frappe, "log_error") as log_error,
		):
			CRMPreQualifiedFacility.after_insert(facility)

		log_error.assert_called_once()
