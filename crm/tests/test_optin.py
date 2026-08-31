import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, random_string, today

from crm.api.contracts import (
	_build_contract_document_html,
	_issue_and_send_invitation,
	_notify_internal_approvers,
	_send_contract_sms,
	_transition,
	generate,
	get_contract,
)
from crm.api.optin import (
	_KEPH_MAP,
	_facility_signing_state,
	_facility_witness_signing_state,
	_generate_contract_for_submission,
	_get_optin_deal_forecast_fields,
	_process_submission,
	_queue_confirmation_email,
	_submission_matches_facility_filter,
	list_submissions,
)
from crm.patches.v1_0.seed_negotiated_price_lists import PRICE_LISTS


class TestOptInForecastFields(UnitTestCase):
	def test_deal_forecast_uses_accepted_annual_prices(self):
		fields = _get_optin_deal_forecast_fields(
			[
				{"annual_kes": 12_000},
				{"annual_kes": 36_000.5},
			]
		)

		self.assertEqual(fields["expected_deal_value"], 48_000.5)
		self.assertEqual(fields["expected_closure_date"], add_days(today(), 30))


class TestOptInNegotiatedPricing(UnitTestCase):
	def test_keph_map_and_price_tables_include_level_3c_and_5a(self):
		item_codes = {row["keph_level"]: row["item_code"] for row in _KEPH_MAP}
		self.assertEqual(item_codes["Level 3C"], "CV-HIMS-KEPH-3C")
		self.assertEqual(item_codes["Level 5A"], "CV-HIMS-KEPH-5A")

		expected_rates = {
			"Negotiated Year 1": (28425.93, 201247.59),
			"Negotiated Year 2": (28425.93, 201247.59),
			"Negotiated Year 3": (22239.23, 166609.36),
			"Negotiated Year 4": (23351.19, 174939.83),
			"Negotiated Year 5": (24518.75, 183686.82),
		}
		for price_list, (level_3c_rate, level_5a_rate) in expected_rates.items():
			self.assertEqual(PRICE_LISTS[price_list]["CV-HIMS-KEPH-3C"], level_3c_rate)
			self.assertEqual(PRICE_LISTS[price_list]["CV-HIMS-KEPH-5A"], level_5a_rate)


class TestOptInSynchronousProcessor(UnitTestCase):
	def test_failed_submission_rolls_back_pipeline_records(self):
		marker = random_string(10)
		email = "sync-%s@example.test" % marker
		organization = "Sync Test %s" % marker
		submission = frappe.get_doc(
			{
				"doctype": "CRM Opt-In Submission",
				"naming_series": "OIS-.YYYY.-",
				"status": "Pending",
				"network_slug": "sync-test",
				"submitter_email": email,
				"raw_json": json.dumps(
					{
						"contact": {
							"first_name": "Synchronous",
							"last_name": "Test",
							"email": email,
							"organisation": organization,
						},
						"facilities": [],
						"pricing": [],
					}
				),
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		original_user = frappe.session.user
		callback_fired = []
		frappe.db.after_commit.add(lambda: callback_fired.append(True))

		try:
			# Empty canonical pricing fails after the Lead, Contact, and Organisation
			# would have been created. They must all be rolled back together.
			with patch("crm.api.optin.frappe.log_error"):
				self.assertFalse(_process_submission(submission.name))

			submission.reload()
			self.assertEqual(submission.status, "Failed")
			self.assertEqual(frappe.session.user, original_user)
			self.assertFalse(frappe.db.exists("CRM Lead", {"email": email}))
			self.assertFalse(frappe.db.exists("CRM Organization", {"organization_name": organization}))
			self.assertFalse(frappe.db.exists("Contact Email", {"email_id": email}))
			self.assertEqual(callback_fired, [])
		finally:
			frappe.db.delete("CRM Opt-In Submission", {"name": submission.name})
			frappe.db.commit()


class TestOptInConfirmationEmail(UnitTestCase):
	def test_confirmation_email_retains_its_queue_reference(self):
		submission = SimpleNamespace(
			name="OIS-TEST-00001",
			confirmation_email_queue=None,
			confirmation_email_queued_at=None,
			save=Mock(),
		)
		queue = SimpleNamespace(name="Email Queue-TEST-00001")
		network = {"display_name": "Test Network"}
		queued_at = frappe.utils.now_datetime()

		with (
			patch("crm.api.optin.frappe.sendmail", return_value=queue) as sendmail,
			patch("crm.api.optin.frappe.utils.now_datetime", return_value=queued_at),
		):
			result = _queue_confirmation_email(submission, "jane@example.com", "Jane", network, [])

		self.assertIs(result, queue)
		self.assertEqual(submission.confirmation_email_queue, queue.name)
		self.assertEqual(submission.confirmation_email_queued_at, queued_at)
		submission.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(sendmail.call_args.kwargs["recipients"], ["jane@example.com"])
		self.assertEqual(
			sendmail.call_args.kwargs["subject"],
			"Test Network Opt-In Confirmed — Reference OIS-TEST-00001",
		)
		self.assertEqual(sendmail.call_args.kwargs["reference_doctype"], "CRM Opt-In Submission")
		self.assertEqual(sendmail.call_args.kwargs["reference_name"], submission.name)
		self.assertTrue(sendmail.call_args.kwargs["now"])


class TestOptInTermsPrinting(UnitTestCase):
	def test_contract_pdf_renders_current_terms_instead_of_stale_snapshot(self):
		contract = SimpleNamespace(
			contract_html="<p>Old terms</p>",
			contract_date="2026-08-30",
			name="CONT-TEST-00001",
		)
		brand = {
			"accent": "#bc1823",
			"display_name": "Test Network",
			"logo": "",
			"contact_email": "",
			"footer_legal_name": "",
		}

		with (
			patch("crm.api.contracts._network_branding", return_value=brand),
			patch("crm.api.contracts._regenerate_contract_body", return_value="<p>Updated terms</p>"),
			patch("crm.api.contracts._render_signature_block", return_value=""),
			patch("crm.api.contracts._render_certificate_page", return_value=""),
		):
			html = _build_contract_document_html(contract)

		self.assertIn("Updated terms", html)
		self.assertNotIn("Old terms", html)


class TestOptInContractAutomation(UnitTestCase):
	def test_contract_generation_stays_in_submission_transaction_and_is_tracked(self):
		submission = SimpleNamespace(
			deal="DEAL-TEST-00001",
			facility_signatory_name="Jane Signatory",
			facility_signatory_email="jane@example.com",
			facility_witness_name="John Witness",
			facility_witness_email="john@example.com",
			contract=None,
			contract_invitation_email_queue=None,
			contract_invitation_queued_at=None,
			save=Mock(),
		)
		queued_at = frappe.utils.now_datetime()

		with (
			patch(
				"crm.api.contracts._generate_contract",
				return_value={
					"contract": "CONT-TEST-00001",
					"invitation_queue": "Email Queue-TEST-00002",
				},
			) as generate_contract,
			patch("crm.api.optin.frappe.utils.now_datetime", return_value=queued_at),
		):
			result = _generate_contract_for_submission(submission, "QUO-TEST-00001")

		self.assertEqual(result["contract"], "CONT-TEST-00001")
		self.assertEqual(submission.contract, "CONT-TEST-00001")
		self.assertEqual(submission.contract_invitation_email_queue, "Email Queue-TEST-00002")
		self.assertEqual(submission.contract_invitation_queued_at, queued_at)
		submission.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(generate_contract.call_args.kwargs["commit"], False)

	def test_contract_generation_requires_a_tracked_invitation_queue(self):
		submission = SimpleNamespace(
			deal="DEAL-TEST-00001",
			facility_signatory_name="Jane Signatory",
			facility_signatory_email="jane@example.com",
			facility_witness_name="John Witness",
			facility_witness_email="john@example.com",
			contract=None,
			contract_invitation_email_queue=None,
			contract_invitation_queued_at=None,
			save=Mock(),
		)

		with patch(
			"crm.api.contracts._generate_contract",
			return_value={"contract": "CONT-TEST-00001", "invitation_queue": ""},
		):
			with self.assertRaises(frappe.ValidationError):
				_generate_contract_for_submission(submission, "QUO-TEST-00001")

		submission.save.assert_not_called()

	def test_invitation_can_save_without_committing_the_caller_transaction(self):
		contract = SimpleNamespace(name="CONT-TEST-00001", network_slug="", save=Mock())
		signatory = SimpleNamespace(
			signatory_role="Facility Signatory",
			signatory_name="Jane Signatory",
			signatory_email="jane@example.com",
		)
		queue = SimpleNamespace(name="Email Queue-TEST-00002")

		with (
			patch("crm.api.contracts._gen_token", return_value="invitation-token"),
			patch("crm.api.contracts._network_for_contract", return_value=None),
			patch("crm.api.contracts.branded_email_html", return_value="email"),
			patch("crm.api.contracts.frappe.sendmail", return_value=queue) as sendmail,
			patch("crm.api.contracts.frappe.db.commit") as commit,
		):
			result = _issue_and_send_invitation(contract, signatory, commit=False)

		self.assertIs(result, queue)
		contract.save.assert_called_once_with(ignore_permissions=True)
		commit.assert_not_called()
		self.assertTrue(signatory.invite_token)
		self.assertTrue(sendmail.call_args.kwargs["now"])

	def test_contract_sms_delivery_is_logged_and_does_not_commit_caller_transaction(self):
		from frappe.core.doctype.sms_settings import sms_settings

		contract = SimpleNamespace(name="CONT-TEST-00001")
		signatory = SimpleNamespace(
			name="ROW-TEST-00001",
			signatory_role="Facility Signatory",
			signatory_phone="+254700000001",
		)
		delivery = SimpleNamespace(attempts=0, save=Mock())
		with (
			patch("crm.api.contracts._new_sms_delivery", return_value=delivery),
			patch("crm.api.contracts._sms_gateway_configured", return_value=True),
			patch.object(sms_settings, "send_sms") as send_sms,
			patch("crm.api.contracts.frappe.utils.now_datetime", return_value="2026-08-31 10:00:00"),
			patch("crm.api.contracts.frappe.db.commit") as commit,
		):
			status = _send_contract_sms(
				contract,
				signatory,
				"Invitation",
				"Please sign: https://example.test/sign",
				commit=False,
			)

		self.assertEqual(status, "Sent")
		self.assertEqual(delivery.status, "Sent")
		self.assertEqual(delivery.attempts, 1)
		send_sms.assert_called_once_with(
			["+254700000001"], "Please sign: https://example.test/sign", success_msg=False
		)
		commit.assert_not_called()

	def test_internal_approvers_receive_email_and_sms(self):
		contract = SimpleNamespace(name="CONT-TEST-00001", deal="DEAL-TEST-00001", network_slug="")
		onboarding = frappe._dict(
			{
				"network_approver_1": "network.approver@example.com",
				"network_approver_2": "",
				"tiberbu_approver": "tiberbu.approver@example.com",
			}
		)
		identity = {
			"full_name": "Contract Approver",
			"email": "approver@example.com",
			"phone": "+254700000001",
		}

		with (
			patch("crm.api.contracts.frappe.get_list", return_value=[onboarding]),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts._resolve_user_identity", return_value=identity),
			patch("crm.api.contracts.frappe.sendmail") as sendmail,
			patch("crm.api.contracts._send_contract_sms", return_value="Sent") as send_sms,
		):
			_notify_internal_approvers(contract.name, contract.deal)

		self.assertEqual(sendmail.call_count, 2)
		self.assertTrue(all(call.kwargs["now"] for call in sendmail.call_args_list))
		self.assertEqual(send_sms.call_count, 2)
		self.assertEqual(
			[call.args[2] for call in send_sms.call_args_list],
			["Approval", "Approval"],
		)

	def test_first_facility_signature_invites_every_remaining_signatory_together(self):
		facility = SimpleNamespace(
			signatory_role="Facility Signatory", status="Signed", invite_token="original"
		)
		witness = SimpleNamespace(signatory_role="Facility Witness", status="Pending", invite_token=None)
		network = SimpleNamespace(signatory_role="Network Signatory", status="Pending", invite_token=None)
		tiberbu = SimpleNamespace(signatory_role="Tiberbu Signatory", status="Pending", invite_token=None)
		contract = SimpleNamespace(
			name="CONT-TEST-00001",
			deal="DEAL-TEST-00001",
			signatories=[facility, witness, network, tiberbu],
		)

		def issue_invitation(_contract, row, commit):
			self.assertFalse(commit)
			row.invite_token = "issued-%s" % row.signatory_role

		with (
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts._issue_and_send_invitation", side_effect=issue_invitation) as issue,
			patch("crm.api.contracts._set_contract_state") as set_state,
			patch("crm.api.contracts._notify_internal_approvers"),
			patch("crm.api.contracts.log_deal_event") as log_event,
		):
			_transition(contract.name)
			_transition(contract.name)

		self.assertEqual(issue.call_count, 3)
		self.assertEqual([call.args[1] for call in issue.call_args_list], [witness, network, tiberbu])
		set_state.assert_called_once_with(contract, "Awaiting Remaining Signatures")
		log_event.assert_called_once()

	def test_signing_portal_returns_non_sensitive_progress_for_every_signatory(self):
		current = SimpleNamespace(signatory_name="Facility Signatory")
		contract = SimpleNamespace(
			contract_html="<p>Terms</p>",
			contract_date="2026-08-30",
			signatories=[
				SimpleNamespace(
					signatory_name="Facility Signatory",
					signatory_role="Facility Signatory",
					status="Signed",
				),
				SimpleNamespace(
					signatory_name="Tiberbu Signatory",
					signatory_role="Tiberbu Signatory",
					status="Pending",
				),
			],
		)

		with (
			patch("crm.api.contracts._check_contract_rate_limit"),
			patch("crm.api.contracts._load_signatory_by_token", return_value=(contract, current)),
			patch("crm.api.contracts._validate_signing"),
		):
			result = get_contract("session-token", "CONT-TEST-00001", "Tiberbu Signatory")

		self.assertEqual(
			result["signing_progress"],
			[
				{
					"name": "Facility Signatory",
					"role": "Facility Signatory",
					"status": "Signed",
				},
				{
					"name": "Tiberbu Signatory",
					"role": "Tiberbu Signatory",
					"status": "Awaiting signature",
				},
			],
		)
		self.assertNotIn("email", result["signing_progress"][0])

	def test_manual_contract_endpoint_keeps_its_existing_response_shape(self):
		with (
			patch("crm.api.contracts._check_crm_role") as check_role,
			patch(
				"crm.api.contracts._generate_contract",
				return_value={
					"contract": "CONT-TEST-00001",
					"invitation_queue": "Email Queue-TEST-00002",
				},
			) as generate_contract,
		):
			result = generate(
				deal="DEAL-TEST-00001",
				quote="QUO-TEST-00001",
				facility_signatory_name="Jane Signatory",
				facility_signatory_email="jane@example.com",
				facility_witness_name="John Witness",
				facility_witness_email="john@example.com",
			)

		self.assertEqual(result, {"contract": "CONT-TEST-00001"})
		check_role.assert_called_once()
		self.assertTrue(generate_contract.call_args.kwargs["commit"])

	def test_facility_signing_state_is_clear_about_pending_and_completed_signatures(self):
		self.assertEqual(_facility_signing_state(None), ("Not generated", None))
		self.assertEqual(
			_facility_signing_state(
				SimpleNamespace(status="Pending", invite_token="token", invite_expiry=None)
			),
			("Awaiting signature", None),
		)
		self.assertEqual(
			_facility_signing_state(SimpleNamespace(status="Signed", signed_at="2026-08-29 12:00:00")),
			("Signed", "2026-08-29 12:00:00"),
		)
		self.assertEqual(
			_facility_witness_signing_state(
				SimpleNamespace(status="Pending"),
				SimpleNamespace(status="Pending"),
			),
			("Waiting for facility signatory", None),
		)

	def test_facility_filter_matches_a_saved_multi_facility_submission(self):
		raw_json = json.dumps(
			{
				"pricing": [
					{"mfl_code": "10001", "facility_name": "Alpha Clinic", "keph_level": "Level 3"},
					{"mfl_code": "10002", "facility_name": "Beta Hospital", "keph_level": "Level 5"},
				]
			}
		)
		self.assertTrue(_submission_matches_facility_filter(raw_json, "Level 5", "beta"))
		self.assertFalse(_submission_matches_facility_filter(raw_json, "Level 4", "beta"))


class TestOptInSubmissionList(UnitTestCase):
	def test_submission_list_filters_and_paginates_by_saved_facility(self):
		def submission(name, facility_name, level):
			return frappe._dict(
				{
					"name": name,
					"status": "Processed",
					"network_slug": "test-network",
					"submitter_email": "jane@example.com",
					"submitted_at": "2026-08-29 10:00:00",
					"lead": None,
					"deal": None,
					"has_duplicate_mfl": 0,
					"error_log": None,
					"confirmation_email_queue": None,
					"confirmation_email_queued_at": None,
					"contract": None,
					"contract_invitation_email_queue": None,
					"contract_invitation_queued_at": None,
					"raw_json": json.dumps(
						{
							"pricing": [
								{
									"mfl_code": name,
									"facility_name": facility_name,
									"keph_level": level,
								}
							]
						}
					),
				}
			)

		with patch(
			"crm.api.optin.frappe.get_list",
			return_value=[
				submission("OIS-TEST-00001", "Alpha Clinic", "Level 3"),
				submission("OIS-TEST-00002", "Beta Hospital", "Level 5"),
			],
		):
			result = list_submissions(facility_level="Level 5", facility="beta")

		self.assertEqual(result["total"], 1)
		self.assertEqual([row["name"] for row in result["rows"]], ["OIS-TEST-00002"])
		self.assertEqual(result["rows"][0]["facility_name"], "Beta Hospital")
		self.assertEqual(result["rows"][0]["facility_level"], "Level 5")
		self.assertEqual(result["rows"][0]["facility_mfl_code"], "OIS-TEST-00002")

	def test_submission_list_includes_live_confirmation_email_status(self):
		submission = frappe._dict(
			{
				"name": "OIS-TEST-00001",
				"status": "Processed",
				"network_slug": "test-network",
				"submitter_email": "jane@example.com",
				"submitted_at": "2026-08-29 10:00:00",
				"lead": "LEAD-TEST-00001",
				"deal": "DEAL-TEST-00001",
				"has_duplicate_mfl": 0,
				"error_log": None,
				"confirmation_email_queue": "Email Queue-TEST-00001",
				"confirmation_email_queued_at": "2026-08-29 10:00:01",
				"contract": "CONT-TEST-00001",
				"contract_invitation_email_queue": "Email Queue-TEST-00002",
				"contract_invitation_queued_at": "2026-08-29 10:00:02",
			}
		)
		email_queues = [
			frappe._dict({"name": "Email Queue-TEST-00001", "status": "Sent"}),
			frappe._dict({"name": "Email Queue-TEST-00002", "status": "Sending"}),
		]
		contract = frappe._dict(
			{
				"name": "CONT-TEST-00001",
				"deal": submission.deal,
				"workflow_state": "Awaiting Facility Signature",
				"status": "Awaiting Signatures",
				"creation": "2026-08-29 10:00:02",
			}
		)
		facility_signatories = [
			frappe._dict(
				{
					"parent": contract.name,
					"signatory_role": "Facility Signatory",
					"status": "Pending",
					"signed_at": None,
					"invite_token": "token",
					"invite_expiry": None,
				}
			),
			frappe._dict(
				{
					"parent": contract.name,
					"signatory_role": "Facility Witness",
					"status": "Pending",
					"signed_at": None,
					"invite_token": None,
					"invite_expiry": None,
				}
			),
		]

		with patch(
			"crm.api.optin.frappe.get_list",
			side_effect=[
				[submission],
				[frappe._dict({"name": submission.name})],
				email_queues,
				[contract],
				facility_signatories,
			],
		):
			result = list_submissions()

		self.assertEqual(result["total"], 1)
		self.assertEqual(result["rows"][0]["confirmation_email_status"], "Sent")
		self.assertEqual(result["rows"][0]["contract_invitation_email_status"], "Sending")
		self.assertEqual(result["rows"][0]["facility_signing_status"], "Awaiting signature")
		self.assertEqual(
			result["rows"][0]["facility_witness_signing_status"],
			"Waiting for facility signatory",
		)
