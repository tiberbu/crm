import json
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, random_string, today

from crm.api.optin import _get_optin_deal_forecast_fields, _process_submission


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
