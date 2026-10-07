from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.website_redirect import (
	CRM_LOGIN_MARKER,
	_portal_progress,
	ensure_website_user_for_ois,
	get_login_team_route,
	get_user_ois_numbers,
	on_login,
)


class TestCustomerExperienceProgress(UnitTestCase):
	def test_progress_projects_network_contact_golive(self):
		submission = frappe._dict(
			{
				"name": "OIS-TEST-0001",
				"network_slug": "network-a",
				"contract": "CONT-TEST-0001",
				"raw_json": '{"facilities":[{"mfl_code":"1001","facility_name":"First Clinic","keph_level":"Level 3"}]}',
			}
		)
		with (
			patch("crm.api.website_redirect.frappe.db.exists", return_value=True),
			patch("crm.api.website_redirect.frappe.db.get_value", return_value="Awaiting Signatures"),
			patch("crm.api.website_redirect.frappe.db.has_column", return_value=True),
			patch(
				"crm.api.website_redirect.frappe.get_all",
				side_effect=[
					[frappe._dict({"status": "Signed"}), frappe._dict({"status": "Pending"})],
					[
						frappe._dict(
							{
								"name": "FAC-0001",
								"mfl_code": "1001",
								"facility_name": "First Clinic",
								"keph_level": "Level 3",
							}
						)
					],
					[
						frappe._dict(
							{
								"name": "MEM-0001",
								"parent": "FAC-0001",
								"network": "network-a",
								"status": "Opted In",
								"go_live": 1,
							}
						)
					],
				],
			),
		):
			result = _portal_progress(submission)

		self.assertTrue(result["facilities"][0]["network_contact"]["go_live"])
		self.assertEqual(result["facilities"][0]["network_contact"]["source"], "token_self_onboarding")
		self.assertEqual(result["steps"][-1]["key"], "golive")
		self.assertEqual(result["steps"][-1]["status"], "complete")


class TestCustomerExperienceAccess(UnitTestCase):
	def test_branded_login_uses_selected_team_route(self):
		with (
			patch(
				"crm.api.website_redirect.frappe.form_dict",
				{CRM_LOGIN_MARKER: "1", "login_team": "finance"},
			),
			patch("crm.api.website_redirect.frappe.cache.hset") as hset,
		):
			on_login(frappe._dict(user="finance@example.com"))

		hset.assert_called_once_with("redirect_after_login", "finance@example.com", "/finance-cockpit")

	def test_login_team_routes_are_allow_listed(self):
		self.assertEqual(get_login_team_route("sales"), "/crm")
		self.assertEqual(get_login_team_route("finance"), "/finance-cockpit")

	def test_unselected_or_unknown_login_team_defaults_to_customer_experience(self):
		self.assertEqual(get_login_team_route(None), "/cx-portal")
		self.assertEqual(get_login_team_route("/finance-cockpit"), "/cx-portal")

	def test_user_ois_permissions_are_deduplicated_and_stale_values_ignored(self):
		with (
			patch(
				"crm.api.website_redirect.frappe.get_all",
				return_value=[
					frappe._dict({"for_value": "OIS-0001", "creation": "2026-01-01"}),
					frappe._dict({"for_value": "OIS-0001", "creation": "2026-01-02"}),
					frappe._dict({"for_value": "OIS-STALE", "creation": "2026-01-03"}),
				],
			),
			patch(
				"crm.api.website_redirect.frappe.db.exists",
				side_effect=lambda doctype, name: name == "OIS-0001",
			),
		):
			self.assertEqual(get_user_ois_numbers("facility@example.com"), ["OIS-0001"])

	def test_existing_website_user_is_linked_without_resending_invitation(self):
		submission = frappe._dict(
			{
				"name": "OIS-0002",
				"facility_signatory_email": "facility@example.com",
				"facility_signatory_name": "Facility Admin",
			}
		)
		user = frappe._dict({"name": "facility@example.com", "user_type": "Website User", "enabled": 1})
		with (
			patch("crm.api.website_redirect.frappe.db.get_value", return_value=user.name),
			patch("crm.api.website_redirect.frappe.get_doc", return_value=user),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[{"name": "UP-0001"}]),
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = ensure_website_user_for_ois(submission)

		self.assertEqual(result, {"status": "linked", "user": "facility@example.com"})
		self.assertFalse(
			any(call.args[0] == "portal_invitation_sent_at" for call in set_field.call_args_list)
		)

	def test_existing_ois_user_link_wins_over_changed_contact_email(self):
		submission = frappe._dict(
			{
				"name": "OIS-0005",
				"portal_user": "existing@example.com",
				"facility_signatory_email": "old@example.com",
				"facility_signatory_name": "Facility Admin",
			}
		)
		user = frappe._dict({"name": "existing@example.com", "user_type": "Website User", "enabled": 1})
		with (
			patch("crm.api.website_redirect.frappe.db.exists", return_value=True),
			patch("crm.api.website_redirect.frappe.get_doc", return_value=user),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[{"name": "UP-0005"}]),
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = ensure_website_user_for_ois(
				submission,
				email="new-contact@example.com",
				display_name="Updated Contact",
			)

		self.assertEqual(result, {"status": "linked", "user": "existing@example.com"})
		self.assertIn(
			("portal_invitation_status", "Already active"),
			[(call.args[1], call.args[2]) for call in set_field.call_args_list],
		)

	def test_new_website_user_gets_native_welcome_and_ois_scoped_permission(self):
		submission = frappe._dict(
			{
				"name": "OIS-0003",
				"facility_signatory_email": "new-facility@example.com",
				"facility_signatory_name": "New Facility Admin",
			}
		)
		user = frappe._dict(
			{
				"name": "new-facility@example.com",
				"user_type": "Website User",
				"enabled": 1,
				"flags": frappe._dict({"email_sent": 1}),
			}
		)
		user.insert = lambda **kwargs: None
		permission = frappe._dict()
		permission.insert = lambda **kwargs: None
		with (
			patch("crm.api.website_redirect.frappe.db.get_value", return_value=None),
			patch("crm.api.website_redirect.frappe.new_doc", side_effect=[user, permission]),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[]),
			patch("crm.api.website_redirect._set_submission_portal_field"),
		):
			result = ensure_website_user_for_ois(submission)

		self.assertEqual(result["status"], "sent")
		self.assertEqual(user.user_type, "Website User")
		self.assertEqual(user.send_welcome_email, 1)
		self.assertEqual(permission.apply_to_all_doctypes, 0)
		self.assertEqual(permission.applicable_for, "CRM Opt-In Submission")

	def test_welcome_email_failure_is_not_reported_as_sent(self):
		submission = frappe._dict(
			{
				"name": "OIS-0004",
				"facility_signatory_email": "mail-failure@example.com",
				"facility_signatory_name": "Mail Failure Admin",
			}
		)
		user = frappe._dict(
			{
				"name": "mail-failure@example.com",
				"user_type": "Website User",
				"enabled": 1,
				"flags": frappe._dict(),
			}
		)
		user.insert = lambda **kwargs: None
		permission = frappe._dict()
		permission.insert = lambda **kwargs: None
		with (
			patch("crm.api.website_redirect.frappe.db.get_value", return_value=None),
			patch("crm.api.website_redirect.frappe.new_doc", side_effect=[user, permission]),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[]),
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = ensure_website_user_for_ois(submission)

		self.assertEqual(result["status"], "failed")
		self.assertIn(
			("portal_invitation_status", "Failed"),
			[(call.args[1], call.args[2]) for call in set_field.call_args_list],
		)
