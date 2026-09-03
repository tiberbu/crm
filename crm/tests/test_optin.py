import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, random_string, today

from crm.api.contracts import (
	_build_contract_document_html,
	_crm_app_url,
	_ensure_contract_signing_open,
	_ensure_pending_signatory,
	_facility_name_for_contract,
	_generate_contract,
	_generate_invitation_email_reference,
	_internal_reminder_item,
	_invitation_sent_recently,
	_issue_and_send_invitation,
	_network_signers,
	_notify_internal_approvers,
	_required_signatures_complete,
	_save_otp_state,
	_send_contract_sms,
	_send_fully_executed_contract,
	_send_internal_signatory_reminder,
	_tiberbu_signer,
	_tiberbu_signers,
	_transition,
	add_signatory,
	check_user_email,
	generate,
	get_contract,
	get_network_signatories,
	remove_signatory,
	request_otp,
	resend_invitation,
	send_internal_signatory_reminders,
	sync_configured_signatories,
	update_signatory,
)
from crm.api.optin import (
	_KEPH_MAP,
	_facility_email_subject_label,
	_facility_signing_state,
	_facility_witness_signing_state,
	_generate_contract_for_submission,
	_get_optin_deal_forecast_fields,
	_process_submission,
	_queue_confirmation_email,
	_submission_matches_facility_filter,
	get_pricing,
	list_submissions,
)
from crm.patches.v1_0.seed_negotiated_price_lists import PRICE_LISTS
from crm.setup.optin import ensure_internal_signatory_reminder_job
from crm.utils.jinja import render_current_terms_for_contract


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


class TestSignatoryUserLookup(UnitTestCase):
	def test_check_user_email_reports_enabled_account(self):
		with (
			patch("crm.api.contracts._check_crm_role"),
			patch(
				"crm.api.contracts.frappe.get_list",
				return_value=[frappe._dict({"email": "signer@example.com", "full_name": "A Signer"})],
			) as get_list,
		):
			result = check_user_email(" Signer@Example.com ")

		self.assertEqual(result, {"checked": True, "linked": True, "full_name": "A Signer"})
		self.assertEqual(
			get_list.call_args.kwargs["filters"],
			{"email": "signer@example.com", "enabled": 1},
		)

	def test_check_user_email_treats_missing_account_as_external(self):
		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_list", return_value=[]),
		):
			result = check_user_email("external@example.com")

		self.assertEqual(result, {"checked": True, "linked": False, "full_name": ""})

	def test_resend_suppresses_a_second_request_in_the_duplicate_window(self):
		row = SimpleNamespace(
			name="ROW-TEST-DEDUP",
			signatory_role="Network Signatory",
			signatory_name="Network Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
			invite_token="active-token",
			crm_last_invitation_sent_at=frappe.utils.now_datetime(),
		)
		contract = SimpleNamespace(
			name="CONT-TEST-DEDUP",
			deal="DEAL-TEST-DEDUP",
			signatories=[row],
		)

		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract) as get_doc,
			patch("crm.api.contracts._issue_and_send_invitation") as issue,
			patch("crm.api.contracts.log_deal_event") as log_event,
		):
			result = resend_invitation(contract.name, row.signatory_role, row.name)

		self.assertEqual(result, {"status": "already_sent", "email": row.signatory_email})
		issue.assert_not_called()
		self.assertTrue(get_doc.call_args.kwargs["for_update"])
		log_event.assert_called_once()

	def test_invitation_dedupe_window_accepts_old_invitation(self):
		row = SimpleNamespace(
			crm_last_invitation_sent_at=frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=-120)
		)
		self.assertFalse(_invitation_sent_recently(row))

	def test_internal_reminder_scheduler_is_registered_with_two_hour_cron(self):
		with (
			patch("crm.setup.optin.frappe.db.table_exists", return_value=True),
			patch(
				"frappe.core.doctype.scheduled_job_type.scheduled_job_type.insert_single_event"
			) as insert_event,
			patch("crm.setup.optin.frappe.db.commit"),
		):
			self.assertTrue(ensure_internal_signatory_reminder_job())

		insert_event.assert_called_once_with(
			"Cron",
			"crm.api.contracts.send_internal_signatory_reminders",
			"0 */2 * * *",
		)


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

	def test_facility_membership_price_list_overrides_network_default(self):
		facilities = [
			frappe._dict(
				{
					"mfl_code": "1001",
					"facility_name": "Network-priced Clinic",
					"keph_level": "Level 3",
					"price_list_override": "",
				}
			),
			frappe._dict(
				{
					"mfl_code": "1002",
					"facility_name": "Facility-negotiated Hospital",
					"keph_level": "Level 5",
					"price_list_override": "Negotiated Year 2",
				}
			),
		]

		def item_prices(_doctype, **kwargs):
			price_list = kwargs["filters"]["price_list"]
			return [frappe._dict({"price_list_rate": 100 if price_list == "Negotiated Year 1" else 200})]

		def tax_totals(value, tax_template=None):
			return SimpleNamespace(
				net_total=value,
				vat_amount=0,
				grand_total=value,
				template=tax_template or "VAT",
				vat_rate=16,
				vat_label="VAT",
			)

		with (
			patch("crm.api.optin._validate_signing_token"),
			patch("crm.api.optin._decode_deal_invitation", return_value=None),
			patch(
				"crm.api.optin._get_network_doc",
				return_value=frappe._dict({"price_list_override": "Negotiated Year 1"}),
			),
			patch(
				"crm.api.optin.frappe.get_single",
				return_value=frappe._dict({"default_price_list": "Negotiated Year 1"}),
			),
			patch("crm.api.optin.frappe.db.exists", return_value=True),
			patch("crm.api.optin._get_all_memberships", return_value=facilities),
			patch("crm.api.optin._get_quoted_facility_map", return_value={}),
			patch("crm.api.optin.frappe.get_list", side_effect=item_prices),
			patch("crm.api.optin.calculate_vat_totals", side_effect=tax_totals),
		):
			result = get_pricing(
				"token",
				"jane@example.com",
				"network-a",
				9999999999,
				["1001", "1002"],
			)

		self.assertEqual(
			[row["price_list"] for row in result["facilities"]],
			["Negotiated Year 1", "Negotiated Year 2"],
		)


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
			"Test Network — Opt-In confirmed · Reference OIS-TEST-00001",
		)
		self.assertEqual(sendmail.call_args.kwargs["reference_doctype"], "CRM Opt-In Submission")
		self.assertEqual(sendmail.call_args.kwargs["reference_name"], submission.name)
		self.assertTrue(sendmail.call_args.kwargs["now"])


class TestOptInTiberbuContacts(UnitTestCase):
	def test_settings_table_resolves_multiple_tiberbu_signers(self):
		settings = frappe._dict(
			{
				"tiberbu_contacts": [
					{"role": "Signatory", "full_name": "Signer One", "email": "ONE@example.com", "phone": ""},
					{
						"role": "Signatory",
						"full_name": "Signer One Duplicate",
						"email": "one@example.com",
						"phone": "+254700000001",
					},
					{
						"role": "Approver",
						"full_name": "Reviewer",
						"email": "reviewer@example.com",
						"phone": "+254700000002",
					},
				],
			}
		)
		with patch("crm.api.contracts._load_optin_settings_safely", return_value=settings):
			self.assertEqual(
				_tiberbu_signers(),
				[{"full_name": "Signer One", "email": "one@example.com", "phone": ""}],
			)

	def test_at_least_one_tiberbu_signer_satisfies_completion(self):
		def row(role, status):
			return SimpleNamespace(signatory_role=role, status=status)

		contract = SimpleNamespace(
			tiberbu_signing_requirement="At least one must sign",
			signatories=[
				row("Facility Signatory", "Signed"),
				row("Facility Witness", "Signed"),
				row("Network Signatory", "Signed"),
				row("Tiberbu Signatory", "Signed"),
				row("Tiberbu Signatory", "Pending"),
			],
		)
		self.assertTrue(_required_signatures_complete(contract))

	def test_signed_signatory_cannot_be_edited(self):
		row = SimpleNamespace(
			name="ROW-SIGNED",
			signatory_role="Tiberbu Signatory",
			signatory_name="Original",
			signatory_email="original@example.com",
			signatory_phone="",
			status="Signed",
			signature_data="data:image/png;base64,signed",
			signed_at="2026-09-01 10:00:00",
		)
		contract = SimpleNamespace(signatories=[row])
		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
		):
			with self.assertRaises(frappe.ValidationError) as raised:
				update_signatory(
					contract="CONT-SIGNED",
					role="Tiberbu Signatory",
					name="Changed",
					email="changed@example.com",
				)
		self.assertIn("cannot be edited", str(raised.exception).lower())

	def test_adding_signatory_reopens_stale_fully_executed_contract(self):
		class ContractDoc(SimpleNamespace):
			def append(self, _fieldname, values):
				self.signatories.append(SimpleNamespace(**values))

		contract = ContractDoc(
			name="CONT-STALE-00001",
			deal="DEAL-STALE-00001",
			status="Fully Executed",
			workflow_state="Fully Executed",
			executed_contract_sent_at="2026-09-01 10:00:00",
			signatories=[
				SimpleNamespace(signatory_role="Facility Signatory", status="Signed"),
			],
			save=Mock(),
		)
		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts.frappe.db.commit"),
			patch("crm.api.contracts.log_deal_event"),
			patch("crm.api.contracts._transition"),
		):
			result = add_signatory(
				contract.name,
				"Tiberbu Signatory",
				"New Reviewer",
				"new-reviewer@example.com",
			)

		self.assertEqual(result["status"], "added")
		self.assertEqual(contract.status, "Awaiting Signatures")
		self.assertEqual(contract.workflow_state, "Awaiting Remaining Signatures")
		self.assertIsNone(contract.executed_contract_sent_at)
		self.assertEqual(contract.signatories[-1].status, "Pending")

	def test_pending_signatory_can_repair_legacy_fully_executed_state(self):
		contract = SimpleNamespace(
			name="CONT-STALE-00002",
			deal="DEAL-STALE-00002",
			status="Fully Executed",
			workflow_state="Fully Executed",
			executed_contract_sent_at="2026-09-01 10:00:00",
			signatories=[
				SimpleNamespace(signatory_role="Facility Signatory", status="Signed"),
				SimpleNamespace(signatory_role="Tiberbu Signatory", status="Pending"),
			],
			save=Mock(),
		)

		with (
			patch("crm.api.contracts.frappe.db.commit"),
			patch("crm.api.contracts.log_deal_event"),
		):
			_ensure_contract_signing_open(contract)

		self.assertEqual(contract.status, "Awaiting Signatures")
		self.assertEqual(contract.workflow_state, "Awaiting Remaining Signatures")
		self.assertIsNone(contract.executed_contract_sent_at)
		contract.save.assert_called_once_with(ignore_permissions=True)

	def test_fully_executed_contract_with_no_pending_rows_stays_protected(self):
		contract = SimpleNamespace(
			name="CONT-EXECUTED-00002",
			deal="DEAL-EXECUTED-00002",
			status="Fully Executed",
			signatories=[
				SimpleNamespace(signatory_role="Facility Signatory", status="Signed"),
			],
		)

		with self.assertRaises(frappe.ValidationError) as raised:
			_ensure_contract_signing_open(contract)

		self.assertIn("already been fully executed", str(raised.exception).lower())

	def test_fully_executed_contract_pdf_is_sent_once_to_facility(self):
		facility = SimpleNamespace(
			signatory_role="Facility Signatory", signatory_email="facility@example.com"
		)
		contract = SimpleNamespace(
			name="CONT-EXECUTED",
			deal="DEAL-EXECUTED",
			signatories=[facility],
			executed_contract_sent_at=None,
			save=Mock(),
		)
		with (
			patch("crm.api.contracts.frappe.get_print", return_value=b"pdf"),
			patch("crm.api.contracts.frappe.sendmail") as sendmail,
			patch("crm.api.contracts._contract_email_subject_label", return_value="Example Facility"),
			patch("crm.api.contracts._network_for_contract", return_value=None),
			patch("crm.api.contracts.frappe.db.commit"),
		):
			self.assertTrue(_send_fully_executed_contract(contract))
			self.assertFalse(_send_fully_executed_contract(contract))
		self.assertEqual(sendmail.call_count, 1)
		self.assertEqual(sendmail.call_args.kwargs["recipients"], ["facility@example.com"])
		self.assertTrue(sendmail.call_args.kwargs["now"])
		self.assertEqual(sendmail.call_args.kwargs["attachments"][0]["fcontent"], b"pdf")

	def test_network_signers_collapse_duplicate_email_rows(self):
		rows = [
			frappe._dict({"full_name": "Network Reviewer", "email": "Reviewer@Example.com", "phone": ""}),
			frappe._dict({"full_name": "", "email": " reviewer@example.com ", "phone": "+254700000001"}),
			frappe._dict({"full_name": "Another Reviewer", "email": "other@example.com", "phone": ""}),
		]
		with (
			patch("crm.api.contracts.frappe.db.exists", return_value=True),
			patch("crm.api.contracts.frappe.get_list", return_value=rows),
		):
			result = _network_signers("network-a")

		self.assertEqual(
			result,
			[
				{"full_name": "Network Reviewer", "email": "reviewer@example.com", "phone": "+254700000001"},
				{"full_name": "Another Reviewer", "email": "other@example.com", "phone": ""},
			],
		)

	def test_quoting_page_resolves_the_global_tiberbu_contact(self):
		contact = {
			"full_name": "Tiberbu Signer",
			"email": "signer@tiberbu.example",
			"phone": "+254700000010",
		}
		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts._resolve_network_slug", return_value="network-a"),
			patch("crm.api.contracts._network_signers", return_value=[]),
			patch("crm.api.contracts._tiberbu_signer", return_value=contact),
		):
			result = get_network_signatories(deal="DEAL-TEST-00001")

		self.assertEqual(result["network_slug"], "network-a")
		self.assertEqual(
			result["signers"],
			[{**contact, "signer_role": "Tiberbu Signatory"}],
		)

	def test_tiberbu_signatory_contact_settings_are_used_without_a_user(self):
		settings = frappe._dict(
			{
				"tiberbu_signatory": "",
				"tiberbu_signatory_name": "Tiberbu Signer",
				"tiberbu_signatory_email": "Signer@tiberbu.example",
				"tiberbu_signatory_phone": "+254700000010",
			}
		)
		with patch("crm.api.contracts._load_optin_settings_safely", return_value=settings):
			self.assertEqual(
				_tiberbu_signer(),
				{
					"full_name": "Tiberbu Signer",
					"email": "signer@tiberbu.example",
					"phone": "+254700000010",
				},
			)

	def test_tiberbu_signatory_user_setting_remains_a_fallback(self):
		settings = frappe._dict(
			{
				"tiberbu_signatory": "tiberbu.user@example.com",
				"tiberbu_signatory_name": "",
				"tiberbu_signatory_email": "",
				"tiberbu_signatory_phone": "",
			}
		)
		identity = {
			"full_name": "Tiberbu User",
			"email": "tiberbu.user@example.com",
			"phone": "+254700000011",
		}
		with (
			patch("crm.api.contracts._load_optin_settings_safely", return_value=settings),
			patch("crm.api.contracts._resolve_user_identity", return_value=identity),
		):
			self.assertEqual(_tiberbu_signer(), identity)


class TestOptInTermsPrinting(UnitTestCase):
	def test_executed_contract_print_uses_immutable_snapshot(self):
		contract = frappe._dict(
			{
				"status": "Fully Executed",
				"contract_html": "<p>Current terms</p>",
				"contract_html_snapshot": "<p>Accepted terms</p>",
			}
		)
		with patch("crm.api.contracts._regenerate_contract_body") as regenerate:
			body = render_current_terms_for_contract(contract)

		self.assertEqual(str(body), "<p>Accepted terms</p>")
		regenerate.assert_not_called()

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
	def test_contract_generation_is_idempotent_for_an_existing_deal_contract(self):
		existing = frappe._dict({"name": "CONT-EXISTING-00001", "status": "Awaiting Signatures"})
		with (
			patch("crm.api.contracts._lock_deal_for_contract_generation") as lock_deal,
			patch("crm.api.contracts._existing_contract_for_deal", return_value=existing),
			patch(
				"crm.api.contracts._existing_contract_invitation_queue",
				return_value="Email Queue-EXISTING-00001",
			),
			patch("crm.api.contracts.frappe.new_doc") as new_doc,
		):
			result = _generate_contract(
				deal="DEAL-EXISTING-00001",
				quote="QUO-EXISTING-00001",
				facility_signatory_name="Facility Signatory",
				facility_signatory_email="facility@example.com",
				facility_witness_name="Facility Witness",
				facility_witness_email="witness@example.com",
			)

		self.assertEqual(
			result,
			{
				"contract": "CONT-EXISTING-00001",
				"invitation_queue": "Email Queue-EXISTING-00001",
				"already_exists": True,
			},
		)
		lock_deal.assert_called_once_with("DEAL-EXISTING-00001")
		new_doc.assert_not_called()

	def test_otp_accepts_legacy_blank_pending_status_only(self):
		blank = SimpleNamespace(status="")
		lowercase = SimpleNamespace(status="pending")
		_ensure_pending_signatory(blank)
		_ensure_pending_signatory(lowercase)
		self.assertEqual(blank.status, "Pending")
		self.assertEqual(lowercase.status, "Pending")

		with self.assertRaises(frappe.ValidationError) as signed_error:
			_ensure_pending_signatory(SimpleNamespace(status="Signed"))
		self.assertIn("already been completed", str(signed_error.exception))

		with self.assertRaises(frappe.ValidationError) as contradictory_error:
			_ensure_pending_signatory(SimpleNamespace(status="Pending", signature_data="data"))
		self.assertIn("already been completed", str(contradictory_error.exception))

		with self.assertRaises(frappe.ValidationError) as declined_error:
			_ensure_pending_signatory(SimpleNamespace(status="Declined"))
		self.assertIn("no longer active", str(declined_error.exception))

		with self.assertRaises(frappe.ValidationError) as unknown_error:
			_ensure_pending_signatory(SimpleNamespace(status="Legacy status"))
		self.assertIn("not ready yet", str(unknown_error.exception))

	def test_otp_save_failure_is_logged_and_safe_for_guest(self):
		contract = SimpleNamespace(save=Mock(side_effect=frappe.ValidationError("invalid legacy row")))
		with (
			patch("crm.api.contracts.frappe.db.rollback") as rollback,
			patch("crm.api.contracts.frappe.log_error") as log_error,
			patch("crm.api.contracts.frappe.get_traceback", return_value="traceback"),
		):
			with self.assertRaises(frappe.ValidationError) as raised:
				_save_otp_state(contract, "CONT-TEST-00004", "Facility Signatory")

		self.assertIn("couldn't prepare your verification code", str(raised.exception).lower())
		rollback.assert_called_once_with()
		log_error.assert_called_once()

	def test_otp_email_identifies_facility_and_request(self):
		contract = SimpleNamespace(name="CONT-TEST-00003", deal="DEAL-TEST-00003", save=Mock())
		signatory = SimpleNamespace(
			name="ROW-TEST-00003",
			signatory_name="Jane Signatory",
			signatory_email="jane@example.com",
			signatory_role="Facility Signatory",
			status="Pending",
			invite_token="invitation-token",
			invite_expiry=frappe.utils.add_days(frappe.utils.now_datetime(), 1),
		)
		cache = Mock()

		with (
			patch("crm.api.contracts._check_contract_rate_limit"),
			patch("crm.api.contracts._load_signatory_by_token", return_value=(contract, signatory)),
			patch("crm.api.contracts._validate_invite"),
			patch("crm.api.contracts.secrets.randbelow", return_value=234567),
			patch("crm.api.contracts._get_signing_key", return_value="test-key"),
			patch("crm.api.contracts._hmac_hex", return_value="otp-hash"),
			patch("crm.api.contracts.frappe.cache", return_value=cache),
			patch("crm.api.contracts._network_for_contract", return_value=None),
			patch("crm.api.contracts._contract_email_subject_label", return_value="MediCare Hospital"),
			patch("crm.api.contracts._generate_invitation_email_reference", return_value="OTP-ONE"),
			patch("crm.api.contracts.branded_email_html", return_value="otp-email") as render_email,
			patch("crm.api.contracts.otp_code_block", return_value="otp-block"),
			patch("crm.api.contracts.frappe.sendmail") as sendmail,
			patch("crm.api.contracts._send_contract_sms", return_value="Not Available"),
			patch("crm.api.contracts.frappe.db.commit"),
		):
			result = request_otp("CONT-TEST-00003", "Facility Signatory", "invitation-token")

		self.assertEqual(result, {"status": "sent", "sms_status": "Not Available"})
		subject = sendmail.call_args.kwargs["subject"]
		self.assertEqual(
			subject,
			"MediCare Hospital — Contract verification code · OTP ID OTP-ONE",
		)
		self.assertNotIn("234567", subject)
		self.assertTrue(sendmail.call_args.kwargs["now"])
		note_html = render_email.call_args.kwargs["note_html"]
		self.assertIn("OTP reference: <strong>OTP-ONE</strong>", note_html)

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
		contract = SimpleNamespace(
			name="CONT-TEST-00001", deal="DEAL-TEST-00001", network_slug="", save=Mock()
		)
		signatory = SimpleNamespace(
			signatory_role="Facility Signatory",
			signatory_name="Jane Signatory",
			signatory_email="jane@example.com",
		)
		queue = SimpleNamespace(name="Email Queue-TEST-00002")

		with (
			patch("crm.api.contracts._gen_token", return_value="invitation-token"),
			patch("crm.api.contracts._generate_invitation_email_reference", return_value="REF-ONE"),
			patch("crm.api.contracts._network_for_contract", return_value=None),
			patch("crm.api.contracts._facility_name_for_contract", return_value="MediCare Hospital"),
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
		self.assertEqual(
			sendmail.call_args.kwargs["subject"],
			"MediCare Hospital — Contract ready for signature · Invitation ID REF-ONE",
		)

	def test_intentional_reminder_invitation_is_marked_in_subject(self):
		contract = SimpleNamespace(
			name="CONT-TEST-00001", deal="DEAL-TEST-00001", network_slug="", save=Mock()
		)
		signatory = SimpleNamespace(
			signatory_role="Facility Signatory",
			signatory_name="Jane Signatory",
			signatory_email="jane@example.com",
		)
		queue = SimpleNamespace(name="Email Queue-TEST-00002")

		with (
			patch("crm.api.contracts._gen_token", return_value="reminder-token"),
			patch("crm.api.contracts._generate_invitation_email_reference", return_value="REF-REMINDER"),
			patch("crm.api.contracts._network_for_contract", return_value=None),
			patch("crm.api.contracts._facility_name_for_contract", return_value="MediCare Hospital"),
			patch("crm.api.contracts.branded_email_html", return_value="email"),
			patch("crm.api.contracts.frappe.sendmail", return_value=queue) as sendmail,
			patch("crm.api.contracts._send_contract_sms", return_value="Not Available"),
			patch("crm.api.contracts.frappe.db.commit"),
		):
			_issue_and_send_invitation(contract, signatory, commit=False, reminder=True)

		self.assertEqual(
			sendmail.call_args.kwargs["subject"],
			"[Reminder] MediCare Hospital — Contract ready for signature · Invitation ID REF-REMINDER",
		)
		self.assertTrue(sendmail.call_args.kwargs["now"])

	def test_resend_invitation_marks_follow_up_as_reminder(self):
		row = SimpleNamespace(
			name="ROW-TEST-00004",
			signatory_role="Network Signatory",
			signatory_name="Network Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
			invite_token="active-token",
		)
		contract = SimpleNamespace(
			name="CONT-TEST-00004",
			deal="DEAL-TEST-00004",
			signatories=[row],
		)

		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts._issue_and_send_invitation") as issue,
			patch("crm.api.contracts.log_deal_event"),
		):
			result = resend_invitation(contract.name, row.signatory_role, row.name)

		self.assertEqual(result, {"status": "sent", "email": "reviewer@example.com"})
		issue.assert_called_once_with(contract, row, reminder=True)

	def test_resending_invitation_changes_inbox_identifier(self):
		contract = SimpleNamespace(
			name="CONT-TEST-00001", deal="DEAL-TEST-00001", network_slug="", save=Mock()
		)
		signatory = SimpleNamespace(
			signatory_role="Facility Signatory",
			signatory_name="Jane Signatory",
			signatory_email="jane@example.com",
		)
		queue = SimpleNamespace(name="Email Queue-TEST-00002")

		with (
			patch("crm.api.contracts._gen_token", side_effect=["invitation-token-1", "invitation-token-2"]),
			patch(
				"crm.api.contracts._generate_invitation_email_reference", side_effect=["REF-ONE", "REF-TWO"]
			),
			patch("crm.api.contracts._network_for_contract", return_value=None),
			patch("crm.api.contracts._facility_name_for_contract", return_value="MediCare Hospital"),
			patch("crm.api.contracts.branded_email_html", return_value="email"),
			patch("crm.api.contracts.frappe.sendmail", return_value=queue) as sendmail,
			patch("crm.api.contracts.frappe.db.commit"),
		):
			_issue_and_send_invitation(contract, signatory, commit=False)
			_issue_and_send_invitation(contract, signatory, commit=False)

		subjects = [call.kwargs["subject"] for call in sendmail.call_args_list]
		self.assertEqual(len(subjects), 2)
		self.assertEqual(len(set(subjects)), 2)
		self.assertIn("Invitation ID REF-ONE", subjects[0])
		self.assertIn("Invitation ID REF-TWO", subjects[1])
		self.assertTrue(all("MediCare Hospital" in subject for subject in subjects))

	def test_invitation_email_reference_is_random_and_nonempty(self):
		first = _generate_invitation_email_reference()
		second = _generate_invitation_email_reference()
		self.assertEqual(len(first), 12)
		self.assertTrue(first.isalnum())
		self.assertNotEqual(first, second)

	def test_facility_email_subject_label_prioritizes_unique_facility_names(self):
		self.assertEqual(
			_facility_email_subject_label(
				[
					{"facility_name": "MediCare Hospital"},
					{"facility_name": "Riverside Clinic"},
					{"facility_name": "MediCare Hospital"},
				]
			),
			"MediCare Hospital + 1 more facilities",
		)
		self.assertEqual(
			_facility_email_subject_label([{"facility_name": "  Mobile\nClinic  "}]),
			"Mobile Clinic",
		)

	def test_facility_subject_label_uses_latest_optin_payload(self):
		contract = SimpleNamespace(name="CONT-TEST-00001", deal="DEAL-TEST-00001")
		submission = {
			"raw_json": json.dumps(
				{
					"pricing": [
						{"facility_name": "MediCare Hospital"},
						{"facility_name": "Riverside Clinic"},
						{"facility_name": "MediCare Hospital"},
					]
				}
			)
		}
		with patch("crm.api.contracts.frappe.get_list", return_value=[submission]):
			self.assertEqual(
				_facility_name_for_contract(contract),
				"MediCare Hospital + 1 more facilities",
			)

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

	def test_tiberbu_approver_contact_does_not_require_a_user(self):
		contract = SimpleNamespace(name="CONT-TEST-00002", deal="DEAL-TEST-00002", network_slug="")
		onboarding = frappe._dict(
			{
				"name": "ONB-TEST-00002",
				"network_approver_1": "",
				"network_approver_2": "",
				"tiberbu_approver": "",
				"tiberbu_approver_name": "Tiberbu Reviewer",
				"tiberbu_approver_email": "reviewer@tiberbu.example",
				"tiberbu_approver_phone": "+254700000002",
			}
		)
		with (
			patch("crm.api.contracts.frappe.get_list", return_value=[onboarding]),
			patch("crm.api.contracts.frappe.get_single", return_value=frappe._dict()),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts.frappe.sendmail") as sendmail,
			patch("crm.api.contracts._send_contract_sms", return_value="Sent") as send_sms,
		):
			_notify_internal_approvers(contract.name, contract.deal)

		sendmail.assert_called_once_with(
			recipients=["reviewer@tiberbu.example"],
			subject="CareverseHIMS — Contract approval required · CONT-TEST-00002",
			message=sendmail.call_args.kwargs["message"],
			now=True,
		)
		send_sms.assert_called_once()
		self.assertEqual(send_sms.call_args.args[2], "Approval")
		self.assertEqual(send_sms.call_args.args[1].signatory_name, "Tiberbu Reviewer")
		self.assertEqual(send_sms.call_args.args[1].signatory_phone, "+254700000002")

	def test_unsigned_cosignatory_can_be_removed_from_current_contract(self):
		row = SimpleNamespace(
			name="ROW-NETWORK-00001",
			signatory_role="Network Signatory",
			signatory_name="Network Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
			signature_data=None,
			signed_at=None,
		)
		contract = SimpleNamespace(
			name="CONT-TEST-00005",
			deal="DEAL-TEST-00005",
			excluded_signatories="",
			signatories=[row],
			remove=Mock(),
			save=Mock(),
		)

		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts.log_deal_event") as log_event,
			patch("crm.api.contracts._transition") as transition,
			patch("crm.api.contracts.frappe.db.commit"),
		):
			result = remove_signatory(
				contract.name,
				"Network Signatory",
				row.name,
			)

		self.assertEqual(
			result,
			{"status": "removed", "role": "Network Signatory", "email": "reviewer@example.com"},
		)
		contract.remove.assert_called_once_with(row)
		contract.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(
			json.loads(contract.excluded_signatories),
			[{"role": "Network Signatory", "email": "reviewer@example.com"}],
		)
		transition.assert_called_once_with(contract.name)
		self.assertIn("removed from contract", log_event.call_args.args[1])

	def test_duplicate_unsigned_rows_can_be_removed_one_at_a_time(self):
		class ContractDoc(SimpleNamespace):
			def remove(self, row):
				self.signatories.remove(row)

		rows = [
			SimpleNamespace(
				name="ROW-DUPLICATE-00001",
				signatory_role="Network Signatory",
				signatory_name="Duplicate Reviewer",
				signatory_email="duplicate@example.com",
				status="Pending",
				signature_data=None,
				signed_at=None,
			),
			SimpleNamespace(
				name="ROW-DUPLICATE-00002",
				signatory_role="Network Signatory",
				signatory_name="Duplicate Reviewer",
				signatory_email="duplicate@example.com",
				status="Pending",
				signature_data=None,
				signed_at=None,
			),
		]
		contract = ContractDoc(
			name="CONT-TEST-DUPLICATES",
			deal="DEAL-TEST-DUPLICATES",
			excluded_signatories="",
			signatories=rows,
			save=Mock(),
		)
		first_row, second_row = rows

		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts.log_deal_event"),
			patch("crm.api.contracts._transition"),
			patch("crm.api.contracts.frappe.db.commit"),
		):
			remove_signatory(contract.name, "Network Signatory", first_row.name)
			self.assertEqual([row.name for row in contract.signatories], [second_row.name])
			remove_signatory(contract.name, "Network Signatory", second_row.name)

		self.assertEqual(contract.signatories, [])
		self.assertEqual(
			json.loads(contract.excluded_signatories),
			[{"role": "Network Signatory", "email": "duplicate@example.com"}],
		)

	def test_sync_does_not_resurrect_a_removed_configured_signatory(self):
		contract = SimpleNamespace(
			name="CONT-TEST-EXCLUSION",
			network_slug="network-a",
			excluded_signatories=json.dumps([{"role": "Network Signatory", "email": "reviewer@example.com"}]),
			signatories=[],
			append=Mock(),
			save=Mock(),
		)
		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch(
				"crm.api.contracts._network_signers",
				return_value=[
					{
						"full_name": "Network Reviewer",
						"email": "reviewer@example.com",
						"phone": "",
					}
				],
			),
			patch("crm.api.contracts._tiberbu_signers", return_value=[]),
			patch("crm.api.contracts.frappe.db.commit"),
			patch("crm.api.contracts._transition"),
		):
			result = sync_configured_signatories(contract.name)

		self.assertEqual(result["added"], 0)
		self.assertEqual(result["updated"], 0)
		contract.append.assert_not_called()
		contract.save.assert_not_called()

	def test_signed_cosignatory_cannot_be_removed_even_with_pending_status(self):
		row = SimpleNamespace(
			name="ROW-TIBERBU-00001",
			signatory_role="Tiberbu Signatory",
			signatory_name="Tiberbu Reviewer",
			signatory_email="reviewer@tiberbu.example",
			status="Pending",
			signature_data="captured-signature",
			signed_at=None,
		)
		contract = SimpleNamespace(
			name="CONT-TEST-00006",
			deal="DEAL-TEST-00006",
			signatories=[row],
			remove=Mock(),
			save=Mock(),
		)

		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
		):
			with self.assertRaises(frappe.ValidationError) as raised:
				remove_signatory(contract.name, "Tiberbu Signatory", row.name)

		self.assertIn("already signed", str(raised.exception).lower())
		contract.remove.assert_not_called()
		contract.save.assert_not_called()

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
			patch("crm.api.contracts.frappe.get_doc", return_value=contract) as get_doc,
			patch("crm.api.contracts._issue_and_send_invitation", side_effect=issue_invitation) as issue,
			patch("crm.api.contracts._set_contract_state") as set_state,
			patch("crm.api.contracts._notify_internal_approvers"),
			patch("crm.api.contracts.log_deal_event") as log_event,
		):
			_transition(contract.name)
			_transition(contract.name)

		self.assertEqual(issue.call_count, 3)
		self.assertEqual(get_doc.call_count, 2)
		self.assertTrue(all(call.kwargs.get("for_update") for call in get_doc.call_args_list))
		self.assertEqual([call.args[1] for call in issue.call_args_list], [witness, network, tiberbu])
		set_state.assert_called_once_with(contract, "Awaiting Remaining Signatures")
		log_event.assert_called_once()

	def test_crm_user_cosignatory_gets_login_action_without_public_invitation(self):
		facility = SimpleNamespace(
			signatory_role="Facility Signatory", status="Signed", invite_token="original"
		)
		internal = SimpleNamespace(
			name="ROW-INTERNAL-00001",
			signatory_role="Network Signatory",
			signatory_name="Network Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
			invite_token=None,
		)
		contract = SimpleNamespace(
			name="CONT-TEST-00003",
			deal="DEAL-TEST-00003",
			signatories=[facility, internal],
		)
		with (
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts._is_internal_crm_signatory", return_value=True),
			patch("crm.api.contracts._mark_internal_action_available") as mark_action,
			patch("crm.api.contracts._issue_and_send_invitation") as issue,
			patch("crm.api.contracts._set_contract_state") as set_state,
			patch("crm.api.contracts.log_deal_event"),
		):
			_transition(contract.name)

		issue.assert_not_called()
		mark_action.assert_called_once_with(contract, internal)
		set_state.assert_called_once_with(contract, "Awaiting Remaining Signatures")

	def test_internal_signatory_reminder_is_facility_named_and_logged(self):
		contract = SimpleNamespace(name="CONT-TEST-00004", deal="DEAL-TEST-00004")
		row = SimpleNamespace(
			name="ROW-INTERNAL-00002",
			signatory_role="Tiberbu Signatory",
			signatory_name="Tiberbu Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
			crm_last_reminder_at=None,
		)
		with (
			patch("crm.api.contracts._is_internal_crm_signatory", return_value=True),
			patch("crm.api.contracts._contract_email_subject_label", return_value="Test Hospital"),
			patch("crm.api.contracts.frappe.sendmail") as sendmail,
			patch("crm.api.contracts.frappe.db.has_column", return_value=True),
			patch("crm.api.contracts.frappe.db.set_value") as set_value,
			patch("crm.api.contracts.log_deal_event") as log_event,
		):
			result = _send_internal_signatory_reminder(contract, row)

		self.assertTrue(result)
		sendmail.assert_called_once()
		self.assertEqual(
			sendmail.call_args.kwargs["subject"], "[Action needed] Pending contract approvals (1)"
		)
		self.assertTrue(sendmail.call_args.kwargs["now"])
		self.assertIn("Open pending approvals", sendmail.call_args.kwargs["message"])
		self.assertIn("/crm/opt-in-submissions?pending_my_action=1", sendmail.call_args.kwargs["message"])
		set_value.assert_called_once()
		log_event.assert_called_once()

	def test_internal_signatory_reminder_is_generic_and_uses_crm_mount(self):
		contract = SimpleNamespace(name="CONT-TEST-00004B", deal="DEAL-TEST-00004B")
		row = SimpleNamespace(
			name="ROW-INTERNAL-00002B",
			signatory_role="Tiberbu Signatory",
			signatory_name="Tiberbu Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
		)
		with (
			patch("crm.api.contracts._is_internal_crm_signatory", return_value=True),
			patch("crm.api.contracts._contract_email_subject_label", return_value="Nairobi Area Branch Hospital"),
			patch("crm.api.contracts.frappe.utils.get_url", return_value="https://crm.example"),
			patch("crm.api.contracts.frappe.sendmail") as sendmail,
			patch("crm.api.contracts.frappe.db.has_column", return_value=False),
			patch("crm.api.contracts.log_deal_event"),
		):
			result = _send_internal_signatory_reminder(
				contract,
				row,
				network={"display_name": "National Medical Facilities of Kenya"},
			)

		self.assertTrue(result)
		message = sendmail.call_args.kwargs["message"]
		self.assertIn("https://crm.example/crm/opt-in-submissions?pending_my_action=1", message)
		self.assertIn("CareverseHIMS", message)
		self.assertNotIn("National Medical Facilities of Kenya", message)
		self.assertNotIn("Nairobi Area Branch Hospital", sendmail.call_args.kwargs["subject"])

	def test_crm_app_url_does_not_duplicate_existing_mount(self):
		with patch("crm.api.contracts.frappe.utils.get_url", return_value="https://crm.example/crm"):
			self.assertEqual(
				_crm_app_url("/crm/opt-in-submissions?pending_my_action=1"),
				"https://crm.example/crm/opt-in-submissions?pending_my_action=1",
			)

	def test_internal_signatory_reminder_groups_pending_workload(self):
		first_contract = SimpleNamespace(name="CONT-TEST-00005", deal="DEAL-TEST-00005")
		second_contract = SimpleNamespace(name="CONT-TEST-00006", deal="DEAL-TEST-00006")
		first_row = SimpleNamespace(
			name="ROW-INTERNAL-00003",
			signatory_role="Network Signatory",
			signatory_name="Tiberbu Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
		)
		second_row = SimpleNamespace(
			name="ROW-INTERNAL-00004",
			signatory_role="Tiberbu Signatory",
			signatory_name="Tiberbu Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
		)
		first_item = _internal_reminder_item(first_contract, first_row)
		second_item = _internal_reminder_item(second_contract, second_row)
		first_item["facility_label"] = "Aga Khan Hospital"
		second_item["facility_label"] = "Lifecare Hospital"

		with (
			patch("crm.api.contracts._is_internal_crm_signatory", return_value=True),
			patch("crm.api.contracts.frappe.sendmail") as sendmail,
			patch("crm.api.contracts.frappe.db.has_column", return_value=True),
			patch("crm.api.contracts.frappe.db.set_value") as set_value,
			patch("crm.api.contracts.log_deal_event") as log_event,
		):
			result = _send_internal_signatory_reminder(
				first_contract,
				first_row,
				pending_items=[first_item, second_item],
			)

		self.assertTrue(result)
		sendmail.assert_called_once()
		self.assertEqual(
			sendmail.call_args.kwargs["subject"], "[Action needed] Pending contract approvals (2)"
		)
		self.assertNotIn("Aga Khan Hospital", sendmail.call_args.kwargs["subject"])
		self.assertIn("Aga Khan Hospital", sendmail.call_args.kwargs["message"])
		self.assertIn("Lifecare Hospital", sendmail.call_args.kwargs["message"])
		self.assertIn("/crm/opt-in-submissions?pending_my_action=1", sendmail.call_args.kwargs["message"])
		self.assertTrue(sendmail.call_args.kwargs["now"])
		self.assertEqual(set_value.call_count, 2)
		self.assertEqual(log_event.call_count, 2)

	def test_internal_reminder_scheduler_groups_same_user_and_skips_external_rows(self):
		facility = SimpleNamespace(signatory_role="Facility Signatory", status="Signed")
		internal = SimpleNamespace(
			name="ROW-INTERNAL-00005",
			signatory_role="Network Signatory",
			signatory_name="CRM Reviewer",
			signatory_email="reviewer@example.com",
			status="Pending",
			crm_last_reminder_at=None,
		)
		external = SimpleNamespace(
			name="ROW-EXTERNAL-00001",
			signatory_role="Tiberbu Signatory",
			signatory_name="External Reviewer",
			signatory_email="external@example.com",
			status="Pending",
			crm_last_reminder_at=None,
		)
		first = SimpleNamespace(
			name="CONT-TEST-00007", deal="DEAL-TEST-00007", signatories=[facility, internal]
		)
		second = SimpleNamespace(
			name="CONT-TEST-00008", deal="DEAL-TEST-00008", signatories=[facility, internal]
		)
		external_contract = SimpleNamespace(
			name="CONT-TEST-00009", deal="DEAL-TEST-00009", signatories=[facility, external]
		)

		with (
			patch(
				"crm.api.contracts.frappe.get_list",
				return_value=[
					frappe._dict({"name": first.name}),
					frappe._dict({"name": second.name}),
					frappe._dict({"name": external_contract.name}),
				],
			),
			patch("crm.api.contracts.frappe.get_doc", side_effect=[first, second, external_contract]),
			patch(
				"crm.api.contracts._network_for_contract",
				side_effect=[{"name": "network-a"}, {"name": "network-b"}, None],
			),
			patch(
				"crm.api.contracts._is_internal_crm_signatory",
				side_effect=lambda row: row.signatory_email == "reviewer@example.com",
			),
			patch("crm.api.contracts._send_internal_signatory_reminder", return_value=True) as send,
			patch("crm.api.contracts.frappe.db.commit"),
		):
			result = send_internal_signatory_reminders()

		self.assertEqual(result, {"sent": 1, "skipped": 0})
		send.assert_called_once()
		self.assertEqual(len(send.call_args.kwargs["pending_items"]), 2)

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
		contract_signatories = [
			frappe._dict(
				{
					"parent": contract.name,
					"signatory_name": "Facility signer",
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
					"signatory_name": "Facility witness",
					"signatory_role": "Facility Witness",
					"status": "Pending",
					"signed_at": None,
					"invite_token": None,
					"invite_expiry": None,
				}
			),
			frappe._dict(
				{
					"parent": contract.name,
					"signatory_name": "Network signer",
					"signatory_role": "Network Signatory",
					"status": "Pending",
					"signed_at": None,
					"invite_token": None,
					"invite_expiry": None,
				}
			),
			frappe._dict(
				{
					"parent": contract.name,
					"signatory_name": "Tiberbu signer",
					"signatory_role": "Tiberbu Signatory",
					"status": "Signed",
					"signed_at": "2026-08-29 11:00:00",
					"invite_token": "tiberbu-token",
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
				contract_signatories,
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
		self.assertEqual(
			result["rows"][0]["network_signatories"],
			[
				{
					"name": "Network signer",
					"status": "Waiting for facility signatory",
					"signed_at": None,
				}
			],
		)
		self.assertEqual(
			result["rows"][0]["tiberbu_signatory"],
			{
				"name": "Tiberbu signer",
				"status": "Signed",
				"signed_at": "2026-08-29 11:00:00",
			},
		)
