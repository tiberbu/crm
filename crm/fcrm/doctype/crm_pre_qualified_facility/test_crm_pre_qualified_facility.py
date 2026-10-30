from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility import (
	CRMPreQualifiedFacility,
	_send_membership_invitation,
	is_self_onboarded_facility,
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
		message = sendmail.call_args.kwargs["message"]
		self.assertIn(
			"https://crm.example.test/opt-in?network=example-network&facility=Example+Hospital",
			message,
		)
		self.assertNotIn("/facility-onboarding", message)
		sendmail.assert_called_once_with(
			recipients=["jane@example.com"],
			subject="You've been pre-qualified: Example Network — CareverseHIMS",
			message=message,
			reference_doctype="CRM Pre-Qualified Facility",
			reference_name="FAC-0001",
			now=True,
		)
		set_value.assert_called_once()
		queue.send.assert_not_called()

	def test_organization_backfill_only_updates_blank_organizations(self):
		facilities = [
			frappe._dict({"name": "FAC-EMPTY", "facility_name": "Default Hospital", "organization": ""}),
			frappe._dict(
				{"name": "FAC-GROUP", "facility_name": "Branch Clinic", "organization": "Health Group"}
			),
			frappe._dict({"name": "FAC-NAMELESS", "facility_name": "", "organization": ""}),
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

	def test_is_self_onboarded_facility_detection(self):
		self.assertFalse(is_self_onboarded_facility(None))
		standard = SimpleNamespace(is_self_onboarded=0, memberships=[])
		self.assertFalse(is_self_onboarded_facility(standard))

		flagged = SimpleNamespace(is_self_onboarded=1, memberships=[])
		self.assertTrue(is_self_onboarded_facility(flagged))

		with_customer = SimpleNamespace(
			is_self_onboarded=0,
			memberships=[SimpleNamespace(customer="CUST-001")],
		)
		self.assertTrue(is_self_onboarded_facility(with_customer))

	def test_self_onboarded_facility_invitation_alerts_user_to_login_to_customer_experience(self):
		facility = SimpleNamespace(
			doctype="CRM Pre-Qualified Facility",
			name="FAC-SELF-001",
			facility_name="Nairobi Wellness Centre",
			is_self_onboarded=1,
			memberships=[],
		)
		membership = SimpleNamespace(
			name="MEM-SELF-001",
			network="test-network",
			status="Active",
			contact_name="Sam Smith",
			contact_email="sam@example.com",
			customer="CUST-SAM",
			invite_email_queue=None,
			invite_sent_at=None,
		)
		network = SimpleNamespace(slug="test-network", display_name="Test Network")
		queue = SimpleNamespace(name="EMAIL-QUEUE-0002", send=Mock())

		with (
			patch.object(frappe, "get_doc", return_value=network),
			patch.object(frappe, "sendmail", return_value=queue) as sendmail,
			patch.object(frappe.db, "set_value"),
			patch.object(frappe.utils, "get_url", return_value="https://crm.example.test"),
			patch.object(frappe.utils, "now_datetime", return_value="2026-10-15 12:00:00"),
			patch(
				"crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility._ensure_self_onboarded_facility_cx_access"
			) as ensure_cx_access,
		):
			result = _send_membership_invitation(facility, membership)

		self.assertIs(result, queue)
		self.assertEqual(membership.invite_email_queue, queue.name)
		message = sendmail.call_args.kwargs["message"]
		subject = sendmail.call_args.kwargs["subject"]

		# Must NOT send the pre-qualification invitation
		self.assertNotIn("You've been pre-qualified", subject)
		self.assertNotIn("/facility-onboarding", message)
		self.assertNotIn("/opt-in", message)

		# MUST alert to login to Tiberbu Express
		self.assertEqual(subject, "You've been added to Test Network — Log in to Tiberbu Express")
		self.assertIn("Log in to Tiberbu Express", message)
		self.assertIn("https://crm.example.test/cx-portal", message)
		self.assertIn("Nairobi Wellness Centre", message)
		sendmail.assert_called_once_with(
			recipients=["sam@example.com"],
			subject="You've been added to Test Network — Log in to Tiberbu Express",
			message=message,
			reference_doctype="CRM Pre-Qualified Facility",
			reference_name="FAC-SELF-001",
			now=True,
		)
		ensure_cx_access.assert_called_once_with(facility, membership)

	def test_network_optin_membership_with_price_overrides_sends_optin_invite_not_self_onboarding_alert(self):
		facility = SimpleNamespace(
			doctype="CRM Pre-Qualified Facility",
			name="FAC-MIXED-001",
			facility_name="Mixed Journey Hospital",
			is_self_onboarded=1,
			memberships=[],
		)
		membership = SimpleNamespace(
			name="MEM-OPTIN-001",
			network="partner-network",
			status="Active",
			contact_name="Dr. Grace",
			contact_email="grace@example.com",
			customer=None,
			price_list_override="Negotiated Year 1",
			price_list_overrides_json='{"1":"Negotiated Year 1","2":"Negotiated Year 2"}',
			invite_email_queue=None,
			invite_sent_at=None,
		)
		network = SimpleNamespace(slug="partner-network", display_name="Partner Network")
		queue = SimpleNamespace(name="EMAIL-QUEUE-0003", send=Mock())

		with (
			patch.object(frappe, "get_doc", return_value=network),
			patch.object(frappe, "sendmail", return_value=queue) as sendmail,
			patch.object(frappe.db, "set_value"),
			patch.object(frappe.utils, "get_url", return_value="https://crm.example.test"),
			patch.object(frappe.utils, "now_datetime", return_value="2026-10-28 12:00:00"),
			patch(
				"crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility._ensure_self_onboarded_facility_cx_access"
			) as ensure_cx_access,
		):
			_send_membership_invitation(facility, membership)

		message = sendmail.call_args.kwargs["message"]
		subject = sendmail.call_args.kwargs["subject"]
		self.assertEqual(subject, "You've been pre-qualified: Partner Network — CareverseHIMS")
		self.assertIn(
			"https://crm.example.test/opt-in?network=partner-network&facility=Mixed+Journey+Hospital",
			message,
		)
		self.assertNotIn("/facility-onboarding", message)
		self.assertNotIn("/cx-portal", message)
		ensure_cx_access.assert_not_called()



	def _route(self, membership, **kwargs):
		facility = SimpleNamespace(
			doctype="CRM Pre-Qualified Facility",
			name="FAC-BOTH-001",
			facility_name="Synthetic Clinic",
			is_self_onboarded=1,
			memberships=[],
		)
		network = SimpleNamespace(slug="partner-network", display_name="Partner Network")
		queue = SimpleNamespace(name="EMAIL-QUEUE-0004", send=Mock())
		with (
			patch.object(frappe, "get_doc", return_value=network),
			patch.object(frappe, "sendmail", return_value=queue) as sendmail,
			patch.object(frappe.db, "set_value"),
			patch.object(frappe.utils, "get_url", return_value="https://crm.example.test"),
			patch.object(frappe.utils, "now_datetime", return_value="2026-10-30 12:00:00"),
			patch(
				"crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility._ensure_self_onboarded_facility_cx_access"
			),
		):
			_send_membership_invitation(facility, membership, **kwargs)
		return sendmail.call_args.kwargs

	def _membership(self, customer=None):
		return SimpleNamespace(
			name="MEM-ADMIN-001",
			network="partner-network",
			status="Active",
			contact_name="Network Contact",
			contact_email="contact@example.test",
			customer=customer,
			price_list_override="",
			price_list_overrides_json="",
			invite_email_queue=None,
			invite_sent_at=None,
		)

	def test_admin_added_contact_on_self_onboarded_facility_gets_the_optin_invitation(self):
		# The row decides the journey: a row without a Customer is a Network Opt-In contact,
		# even without negotiated pricing and even when the facility also self-onboarded.
		sent = self._route(self._membership())
		self.assertEqual(sent["subject"], "You've been pre-qualified: Partner Network — CareverseHIMS")
		self.assertIn("/opt-in?network=partner-network", sent["message"])
		self.assertNotIn("/cx-portal", sent["message"])

	def test_partner_coupon_row_gets_the_express_alert(self):
		sent = self._route(self._membership(customer="CUST-COUPON"))
		self.assertIn("Log in to Tiberbu Express", sent["subject"])
		self.assertNotIn("/opt-in", sent["message"])

	def test_explicit_express_invitation_sends_the_express_alert(self):
		sent = self._route(self._membership(), express=True)
		self.assertIn("Log in to Tiberbu Express", sent["subject"])
		self.assertNotIn("/opt-in", sent["message"])
