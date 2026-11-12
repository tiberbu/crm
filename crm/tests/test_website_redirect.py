from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.website_redirect import (
	CRM_LOGIN_MARKER,
	_cx_access_invitation_html,
	_portal_progress,
	_set_submission_portal_field,
	ensure_website_user_for_ois,
	get_login_team_route,
	get_user_ois_numbers,
	on_login,
	send_cx_access_invitation,
)


class TestCustomerExperienceProgress(UnitTestCase):
	def test_self_onboarding_progress_omits_signature_and_tracks_package_order_payment(self):
		submission = frappe._dict(
			{
				"name": "OIS-SELF-0001",
				"status": "Processed",
				"onboarding_source": "token_self_onboarding",
				"network_slug": "network-a",
				"contract": "CONT-SHOULD-NOT-BE-READ",
				"quote_names_json": "[]",
				"raw_json": '{"facilities":[{"mfl_code":"1001","facility_name":"First Clinic"}],"token_package":{"item_code":"TOK-1","display_name":"Starter","token_quantity":100}}',
			}
		)
		with (
			patch("crm.api.website_redirect.frappe.db.has_column", return_value=False),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[]),
			patch("crm.api.website_redirect.frappe.db.exists") as exists,
			patch("crm.api.customer_experience._order_rows", return_value=[]),
			patch("crm.api.website_redirect._portal_invoices", return_value=[]),
		):
			result = _portal_progress(submission)

		keys = [step["key"] for step in result["steps"]]
		self.assertEqual(keys, ["identity", "facility", "optin", "package", "order", "payment", "golive"])
		self.assertNotIn("signatures", keys)
		self.assertNotIn("contract", result)
		self.assertNotEqual(result["current"], "sign_contract")
		self.assertEqual(result["facilities"][0]["network_contact"]["source"], "token_self_onboarding")
		self.assertEqual(result["steps"][3]["status"], "complete")
		self.assertIn("allocation", result["token_credit_status"].lower())
		exists.assert_not_called()

	def test_self_onboarding_order_next_action_creates_invoice_before_payment(self):
		submission = frappe._dict(
			{
				"name": "OIS-SELF-0002",
				"status": "Processed",
				"onboarding_source": "token_self_onboarding",
				"quote_names_json": "[]",
				"raw_json": '{"facilities":[{"mfl_code":"1001","facility_name":"First Clinic"}],"token_package":{"item_code":"TOK-1","display_name":"Starter","token_quantity":100}}',
			}
		)
		with (
			patch("crm.api.website_redirect.frappe.db.has_column", return_value=False),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[]),
			patch("crm.api.website_redirect.frappe.db.exists", return_value=False),
			patch(
				"crm.api.customer_experience._order_rows",
				return_value=[{"name": "SAL-ORD-0001"}],
			),
			patch("crm.api.website_redirect._portal_invoices", return_value=[]),
		):
			result = _portal_progress(submission)

		self.assertEqual(result["next_action"]["key"], "review_order")
		self.assertEqual(result["next_action"]["label"], "Create an invoice for your token order")

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
		self.assertEqual(result["facilities"][0]["network_contact"]["source"], "network_optin")
		self.assertEqual(result["steps"][-1]["key"], "golive")
		self.assertEqual(result["steps"][-1]["status"], "complete")


class TestCustomerExperienceAccess(UnitTestCase):
	def test_self_onboarding_never_falls_back_to_facility_contact_email(self):
		submission = frappe._dict(
			{
				"name": "OIS-SELF-0001",
				"onboarding_source": "token_self_onboarding",
				"facility_signatory_email": "facility@example.com",
				"submitter_email": "submitter@example.com",
			}
		)
		with patch("crm.api.website_redirect._set_submission_portal_field") as set_field:
			result = ensure_website_user_for_ois(submission)

		self.assertEqual(result["status"], "blocked")
		self.assertIn(
			("portal_invitation_status", "Blocked"),
			[(call.args[1], call.args[2]) for call in set_field.call_args_list],
		)

	def test_self_onboarding_linked_account_requires_exact_account_email(self):
		submission = frappe._dict(
			{
				"name": "OIS-SELF-0002",
				"onboarding_source": "token_self_onboarding",
				"portal_user": "linked@example.com",
				"cx_account_email": "different@example.com",
			}
		)
		with (
			patch("crm.api.website_redirect.frappe.db.exists", return_value=True),
			patch("crm.api.website_redirect.frappe.db.get_value", return_value="linked@example.com"),
			patch("crm.api.website_redirect.frappe.get_doc") as get_doc,
			patch("crm.api.website_redirect.frappe.get_all") as get_all,
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = ensure_website_user_for_ois(submission)

		self.assertEqual(result["status"], "blocked")
		get_doc.assert_not_called()
		get_all.assert_not_called()
		self.assertIn(
			("portal_invitation_status", "Blocked"),
			[(call.args[1], call.args[2]) for call in set_field.call_args_list],
		)

	def test_self_onboarding_existing_link_uses_native_password_reset_once(self):
		submission = frappe._dict(
			{
				"name": "OIS-SELF-0003",
				"onboarding_source": "token_self_onboarding",
				"portal_user": "sam@example.com",
				"cx_account_email": "sam@example.com",
			}
		)
		user = frappe._dict(
			{
				"name": "sam@example.com",
				"email": "sam@example.com",
				"user_type": "Website User",
				"enabled": 1,
				"db_set": Mock(),
				"_reset_password": Mock(),
			}
		)
		permission = frappe._dict()
		permission.insert = lambda **kwargs: None
		def get_value(doctype, name=None, fieldname=None, **kwargs):
			if name == "OIS-SELF-0003":
				return None
			return "sam@example.com"

		with (
			patch("crm.api.website_redirect.frappe.db.exists", return_value=True),
			patch("crm.api.website_redirect.frappe.db.get_value", side_effect=get_value),
			patch("crm.api.website_redirect.frappe.get_doc", return_value=user),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[]),
			patch("crm.api.website_redirect.frappe.new_doc", return_value=permission),
			patch("crm.api.website_redirect.frappe.utils.now_datetime", return_value="2026-10-13 12:00:00"),
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = ensure_website_user_for_ois(submission)

		self.assertEqual(result, {"status": "reset_sent", "user": "sam@example.com"})
		user.db_set.assert_called_once_with("redirect_url", "/cx-portal", update_modified=False)
		user._reset_password.assert_called_once_with(send_email=True)
		self.assertIn(
			("portal_invitation_status", "Sent"),
			[(call.args[1], call.args[2]) for call in set_field.call_args_list],
		)

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

	def test_portal_field_write_is_mirrored_onto_the_document(self):
		submission = frappe._dict({"name": "OIS-0004", "portal_invitation_status": "Pending"})
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch("crm.api.website_redirect.frappe.get_meta", return_value=meta),
			patch("crm.api.website_redirect.frappe.db.set_value") as set_value,
		):
			_set_submission_portal_field(submission, "portal_invitation_status", "Sent")

		set_value.assert_called_once_with(
			"CRM Opt-In Submission", "OIS-0004", "portal_invitation_status", "Sent", update_modified=False
		)
		self.assertEqual(submission.portal_invitation_status, "Sent")

	def test_portal_field_write_is_skipped_when_field_is_absent(self):
		submission = frappe._dict({"name": "OIS-0005"})
		meta = Mock()
		meta.has_field.return_value = False
		with (
			patch("crm.api.website_redirect.frappe.get_meta", return_value=meta),
			patch("crm.api.website_redirect.frappe.db.set_value") as set_value,
		):
			_set_submission_portal_field(submission, "portal_invitation_status", "Sent")

		set_value.assert_not_called()
		self.assertNotIn("portal_invitation_status", submission)

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


class TestPortalTokenCatalog(UnitTestCase):
	def test_portal_catalog_carries_server_resolved_vat_totals(self):
		from crm.api.website_redirect import _portal_token_catalog

		package = {"item_code": "TOK-1", "price_ex_vat": 100.0, "vat_amount": 16.0, "gross_total": 116.0}
		with patch("crm.api.facility_onboarding._catalog_packages", return_value=[package]):
			self.assertEqual(_portal_token_catalog(), [package])

	def test_portal_catalog_is_empty_when_pricing_is_unavailable(self):
		from crm.api.website_redirect import _portal_token_catalog

		with patch("crm.api.facility_onboarding._catalog_packages", side_effect=RuntimeError("config")):
			self.assertEqual(_portal_token_catalog(), [])


class TestDeferredProvisioning(UnitTestCase):
	def _new_user(self, name="deferred@example.com"):
		user = frappe._dict({"name": name, "flags": frappe._dict({"email_sent": 0})})
		user.insert = lambda **kwargs: None
		return user

	def test_deferred_provisioning_creates_user_without_welcome_and_defers_status(self):
		submission = frappe._dict(
			{
				"name": "OIS-DEF-0001",
				"facility_signatory_email": "deferred@example.com",
				"facility_signatory_name": "Deferred Admin",
			}
		)
		user = self._new_user()
		permission = frappe._dict()
		permission.insert = lambda **kwargs: None
		with (
			patch("crm.api.website_redirect.frappe.db.get_value", return_value=None),
			patch("crm.api.website_redirect.frappe.new_doc", side_effect=[user, permission]),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[]),
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = ensure_website_user_for_ois(submission, send_access_email=False)

		self.assertEqual(result, {"status": "deferred", "user": "deferred@example.com", "created": True})
		self.assertEqual(user.send_welcome_email, 0)
		self.assertEqual(user.redirect_url, "/cx-portal")
		self.assertEqual(permission.apply_to_all_doctypes, 0)
		self.assertEqual(permission.applicable_for, "CRM Opt-In Submission")
		writes = [(call.args[1], call.args[2]) for call in set_field.call_args_list]
		self.assertIn(("portal_user", "deferred@example.com"), writes)
		self.assertIn(("portal_invitation_status", "Awaiting signature"), writes)
		self.assertIn(("portal_invitation_error", ""), writes)

	def test_deferred_provisioning_skips_status_when_already_sent(self):
		submission = frappe._dict(
			{
				"name": "OIS-DEF-0002",
				"portal_user": "existing@example.com",
				"facility_signatory_email": "existing@example.com",
			}
		)
		user = frappe._dict(
			{
				"name": "existing@example.com",
				"email": "existing@example.com",
				"user_type": "Website User",
				"enabled": 1,
				"db_set": Mock(),
			}
		)
		permission = frappe._dict()
		permission.insert = lambda **kwargs: None

		def get_value(doctype, name=None, fieldname=None, **kwargs):
			if name == "OIS-DEF-0002":
				return "Sent"
			return "existing@example.com"

		with (
			patch("crm.api.website_redirect.frappe.db.exists", return_value=True),
			patch("crm.api.website_redirect.frappe.db.get_value", side_effect=get_value),
			patch("crm.api.website_redirect.frappe.get_doc", return_value=user),
			patch("crm.api.website_redirect.frappe.get_all", return_value=[]),
			patch("crm.api.website_redirect.frappe.new_doc", return_value=permission),
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = ensure_website_user_for_ois(submission, send_access_email=False)

		self.assertEqual(result["status"], "deferred")
		writes = [(call.args[1], call.args[2]) for call in set_field.call_args_list]
		self.assertNotIn(("portal_invitation_status", "Awaiting signature"), writes)
		self.assertIn(("portal_invitation_error", ""), writes)


class TestCxAccessInvitation(UnitTestCase):
	def _submission(self, **overrides):
		base = {
			"name": "OIS-ACC-0001",
			"status": "Processed",
			"onboarding_source": "",
			"network_slug": "network-a",
			"facility_signatory_name": "Admin One",
			"raw_json": '{"facilities":[{"mfl_code":"1001","facility_name":"First Clinic"}]}',
			"save": Mock(),
		}
		base.update(overrides)
		return frappe._dict(base)

	def _user(self, name="new@example.com", first_name="New"):
		user = frappe._dict(
			{
				"name": name,
				"email": name,
				"first_name": first_name,
				"db_set": Mock(),
				"_reset_password": Mock(return_value="https://site.example/api/reset/KEY"),
			}
		)
		return user

	def _patches(
		self,
		*,
		exists_side_effect=None,
		get_value=(None, None, None),
		get_single_value=1200,
		ensure_result=None,
		network_doc=None,
	):
		if network_doc is None:
			network_doc = {"display_name": "Test Network"}
		ensure_kwargs = {} if ensure_result is None else {"return_value": ensure_result}
		return (
			patch("crm.api.website_redirect.frappe.db.exists", side_effect=exists_side_effect or (lambda *a, **k: True)),
			patch("crm.api.website_redirect.frappe.db.get_value", return_value=get_value),
			patch("crm.api.website_redirect.frappe.db.get_single_value", return_value=get_single_value),
			patch("crm.api.website_redirect.frappe.utils.get_url", return_value="https://site.example/cx-portal"),
			patch("crm.api.website_redirect.ensure_website_user_for_ois", **ensure_kwargs),
			patch("crm.api.optin._get_network_doc", return_value=network_doc),
		)

	def _submission_doc(self, submission, user):
		def get_doc(doctype, name=None, **kwargs):
			if doctype == "CRM Opt-In Submission":
				return submission
			if doctype == "User":
				return user
			return frappe._dict()

		return patch("crm.api.website_redirect.frappe.get_doc", side_effect=get_doc)

	def test_skips_missing_submission(self):
		with patch("crm.api.website_redirect.frappe.db.exists", return_value=False):
			result = send_cx_access_invitation("OIS-MISSING-00001")
		self.assertEqual(result, {"status": "skipped", "reason": "missing_submission"})

	def test_skips_empty_name_without_any_lookup(self):
		with patch("crm.api.website_redirect.frappe.db.exists") as exists:
			result = send_cx_access_invitation("")
		self.assertEqual(result, {"status": "skipped", "reason": "missing_submission"})
		exists.assert_not_called()

	def test_skips_self_onboarding(self):
		submission = self._submission(onboarding_source="token_self_onboarding")
		user = self._user()
		patches = self._patches()
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail") as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result, {"status": "skipped", "reason": "self_onboarding"})
		sendmail.assert_not_called()

	def test_skips_submission_not_processed(self):
		submission = self._submission(status="Processing")
		user = self._user()
		patches = self._patches()
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail") as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result, {"status": "skipped", "reason": "submission_not_processed"})
		sendmail.assert_not_called()

	def test_already_sent_is_not_requeued(self):
		submission = self._submission()
		user = self._user(name="existing@example.com")
		patches = self._patches(get_value=("Sent", "2026-11-01 10:00:00", "existing@example.com"))
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail") as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result, {"status": "already_sent", "user": "existing@example.com"})
		sendmail.assert_not_called()
		user._reset_password.assert_not_called()

	def test_new_user_without_password_gets_set_password_link(self):
		submission = self._submission()
		user = self._user()

		def exists(doctype, *args, **kwargs):
			if doctype == "__Auth":
				return False
			return True

		patches = self._patches(
			exists_side_effect=exists,
			ensure_result={"status": "deferred", "user": "new@example.com", "created": True},
		)
		queue = frappe._dict({"name": "Email Queue-1"})
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail", return_value=queue) as sendmail,
			patch("crm.api.website_redirect.frappe.utils.now_datetime", return_value="2026-11-05 10:00:00"),
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result["status"], "sent")
		self.assertEqual(result["kind"], "set_password")
		self.assertEqual(result["email_queue"], "Email Queue-1")
		user.db_set.assert_called_once_with("redirect_url", "/cx-portal", update_modified=False)
		user._reset_password.assert_called_once_with(send_email=False)
		message = sendmail.call_args.kwargs["message"]
		self.assertIn("https://site.example/api/reset/KEY", message)
		self.assertIn("This link expires in 20 minutes", message)
		self.assertIn("First Clinic", message)
		self.assertIn("Test Network", message)
		self.assertIn("background:#bc1823", message)
		self.assertNotIn("#0284c7", message)
		self.assertEqual(sendmail.call_args.kwargs["recipients"], ["new@example.com"])
		self.assertEqual(
			sendmail.call_args.kwargs["subject"], "Contract signed — access Tiberbu Express for Test Network"
		)
		self.assertEqual(sendmail.call_args.kwargs["reference_doctype"], "CRM Opt-In Submission")
		self.assertEqual(sendmail.call_args.kwargs["reference_name"], "OIS-ACC-0001")
		self.assertTrue(sendmail.call_args.kwargs["now"])
		self.assertNotIn("communication", sendmail.call_args.kwargs)
		writes = [(call.args[1], call.args[2]) for call in set_field.call_args_list]
		self.assertIn(("portal_invitation_status", "Sent"), writes)
		self.assertIn(("portal_invitation_sent_at", "2026-11-05 10:00:00"), writes)
		self.assertIn(("portal_invitation_error", ""), writes)
		submission.save.assert_not_called()

	def test_existing_password_gets_login_link_without_reset(self):
		submission = self._submission()
		user = self._user(name="existing@example.com")

		def exists(doctype, *args, **kwargs):
			if doctype == "__Auth":
				return True
			return True

		patches = self._patches(
			exists_side_effect=exists,
			ensure_result={"status": "deferred", "user": "existing@example.com", "created": False},
		)
		queue = frappe._dict({"name": "Email Queue-2"})
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail", return_value=queue) as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result["kind"], "login")
		user._reset_password.assert_not_called()
		message = sendmail.call_args.kwargs["message"]
		self.assertIn("https://site.example/cx-portal", message)
		self.assertNotIn("This link expires in", message)

	def test_blocked_provisioning_returns_without_email(self):
		submission = self._submission()
		user = self._user()
		patches = self._patches(ensure_result={"status": "blocked", "reason": "No valid facility email"})
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail") as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result, {"status": "blocked", "reason": "No valid facility email"})
		sendmail.assert_not_called()

	def test_queue_failure_marks_failed(self):
		submission = self._submission()
		user = self._user()
		patches = self._patches(
			ensure_result={"status": "deferred", "user": "new@example.com", "created": True}
		)
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail", return_value=None),
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result, {"status": "failed", "user": "new@example.com", "reason": "queue_failed"})
		writes = [(call.args[1], call.args[2]) for call in set_field.call_args_list]
		self.assertIn(("portal_invitation_status", "Failed"), writes)
		self.assertIn(("portal_invitation_error", "The access email could not be queued."), writes)

	def test_sendmail_exception_is_logged_not_raised(self):
		submission = self._submission()
		user = self._user()
		patches = self._patches(
			ensure_result={"status": "deferred", "user": "new@example.com", "created": True}
		)
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail", side_effect=RuntimeError("smtp down")),
			patch("crm.api.website_redirect.frappe.log_error") as log_error,
			patch("crm.api.website_redirect._set_submission_portal_field") as set_field,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result, {"status": "failed", "reason": "exception"})
		log_error.assert_called_once()
		writes = [(call.args[1], call.args[2]) for call in set_field.call_args_list]
		self.assertIn(("portal_invitation_status", "Failed"), writes)

	def test_force_resends_when_already_sent(self):
		submission = self._submission()
		user = self._user(name="existing@example.com")

		def exists(doctype, *args, **kwargs):
			if doctype == "__Auth":
				return True
			return True

		patches = self._patches(
			exists_side_effect=exists,
			get_value=("Sent", "2026-11-01 10:00:00", "existing@example.com"),
			ensure_result={"status": "deferred", "user": "existing@example.com", "created": False},
		)
		queue = frappe._dict({"name": "Email Queue-5"})
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail", return_value=queue) as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001", force=True)

		self.assertEqual(result["status"], "sent")
		sendmail.assert_called_once()

	def test_legacy_sent_without_sent_at_still_sends(self):
		submission = self._submission()
		user = self._user(name="existing@example.com")

		def exists(doctype, *args, **kwargs):
			if doctype == "__Auth":
				return True
			return True

		patches = self._patches(
			exists_side_effect=exists,
			get_value=("Sent", None, "existing@example.com"),
			ensure_result={"status": "deferred", "user": "existing@example.com", "created": False},
		)
		queue = frappe._dict({"name": "Email Queue-6"})
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail", return_value=queue) as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result["status"], "sent")
		sendmail.assert_called_once()

	def test_failed_provisioning_returns_without_email(self):
		submission = self._submission()
		user = self._user()
		patches = self._patches(ensure_result={"status": "failed", "user": "new@example.com"})
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail") as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result, {"status": "failed", "user": "new@example.com"})
		sendmail.assert_not_called()

	def test_multi_facility_label_and_network_escaping(self):
		submission = self._submission(
			raw_json='{"facilities":[{"mfl_code":"1001","facility_name":"First Clinic"},{"mfl_code":"1002","facility_name":"Second Clinic"}]}'
		)
		user = self._user()

		def exists(doctype, *args, **kwargs):
			if doctype == "__Auth":
				return False
			return True

		patches = self._patches(
			exists_side_effect=exists,
			ensure_result={"status": "deferred", "user": "new@example.com", "created": True},
			network_doc={"display_name": "Test <Network>"},
		)
		queue = frappe._dict({"name": "Email Queue-3"})
		with (
			patches[0],
			patches[1],
			patches[2],
			patches[3],
			patches[4],
			patches[5],
			self._submission_doc(submission, user),
			patch("crm.api.website_redirect.frappe.sendmail", return_value=queue) as sendmail,
		):
			result = send_cx_access_invitation("OIS-ACC-0001")

		self.assertEqual(result["status"], "sent")
		message = sendmail.call_args.kwargs["message"]
		self.assertIn("First Clinic + 1 more facilities", message)
		self.assertIn("Test &lt;Network&gt;", message)
		self.assertEqual(sendmail.call_args.kwargs["subject"], "Contract signed — access Tiberbu Express for Test <Network>")

	def test_access_email_button_uses_brand_colour_rules(self):
		html = _cx_access_invitation_html(
			"Admin", "Net", "Clinic", "https://a.example.test", "https://p.example.test",
			"login", "facility_side_signed", "", brand_colour="#123abc",
		)
		self.assertIn("background:#123abc", html)
		for colour in (None, "", "red", "#12345", "url(x)"):
			html = _cx_access_invitation_html(
				"Admin", "Net", "Clinic", "https://a.example.test", "https://p.example.test",
				"login", "facility_side_signed", "", brand_colour=colour,
			)
			self.assertIn("background:#bc1823", html, colour)

	def test_expiry_text_variants(self):
		submission = self._submission()
		user = self._user()

		def exists(doctype, *args, **kwargs):
			if doctype == "__Auth":
				return False
			return True

		def run(get_single_value):
			patches = self._patches(
				exists_side_effect=exists,
				get_single_value=get_single_value,
				ensure_result={"status": "deferred", "user": "new@example.com", "created": True},
			)
			queue = frappe._dict({"name": "Email Queue-4"})
			with (
				patches[0],
				patches[1],
				patches[2],
				patches[3],
				patches[4],
				patches[5],
				self._submission_doc(submission, user),
				patch("crm.api.website_redirect.frappe.sendmail", return_value=queue) as sendmail,
			):
				send_cx_access_invitation("OIS-ACC-0001")
			return sendmail.call_args.kwargs["message"]

		self.assertIn("This link expires in 24 hours", run(86400))
		self.assertIn("This link expires in 1 hour", run(3600))
		message = run(0)
		self.assertNotIn("This link expires in", message)
