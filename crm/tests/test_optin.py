import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, random_string, today

from crm.api.optin import (
	_get_optin_deal_forecast_fields,
	_process_submission,
	_queue_confirmation_email,
	list_submissions,
)


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

		try:
			# Empty canonical pricing fails after the Lead, Contact, and Organisation
			# would have been created. They must all be rolled back together.
			with patch("crm.api.optin.frappe.log_error"):
				self.assertFalse(_process_submission(submission.name))

			submission.reload()
			self.assertEqual(submission.status, "Failed")
			self.assertEqual(frappe.session.user, original_user)
			self.assertFalse(frappe.db.exists("CRM Lead", {"email": email}))
			self.assertFalse(
				frappe.db.exists("CRM Organization", {"organization_name": organization})
			)
			self.assertFalse(frappe.db.exists("Contact Email", {"email_id": email}))
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
		self.assertFalse(sendmail.call_args.kwargs["now"])


class TestOptInSubmissionList(UnitTestCase):
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
			}
		)
		email_queue = frappe._dict({"name": "Email Queue-TEST-00001", "status": "Sent"})

		with patch(
			"crm.api.optin.frappe.get_list",
			side_effect=[[submission], [email_queue], [frappe._dict({"name": submission.name})]],
		):
			result = list_submissions()

		self.assertEqual(result["total"], 1)
		self.assertEqual(result["rows"][0]["confirmation_email_status"], "Sent")
