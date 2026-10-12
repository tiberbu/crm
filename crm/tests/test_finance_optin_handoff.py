import json
from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from crm.automation.optin_billing import handoff_facility_signed, process_due_optin_billing


class TestFinanceOptInHandoff(UnitTestCase):
	def _submission(self, schedules):
		return SimpleNamespace(
			name="OIS-0001",
			status="Processed",
			contract="CONT-0001",
			deal="DEAL-0001",
			billing_schedule_json=json.dumps(schedules),
			save=lambda **kwargs: None,
	)

	def _quotation(self):
		return SimpleNamespace(
			name="SAL-QTN-0001",
			docstatus=1,
			party_name="CUSTOMER-1",
			company="Careverse HQ",
			currency="KES",
			selling_price_list="Standard Selling",
			items=[],
			flags=SimpleNamespace(),
		)

	def test_signature_network_creates_q1_order_and_invoice_on_signed_date(self):
		submission = self._submission(
			[
				{
					"year_number": 1,
					"quarter_number": 1,
					"billing_key": "OIS-0001-Y1-Q1",
					"invoice_issue_timing": "contract_signature",
					"invoice_schedule_configured": True,
					"status": "Scheduled",
				}
			]
		)
		quotation = self._quotation()

		def get_doc(doctype, name=None):
			return submission if doctype == "CRM Opt-In Submission" else quotation

		with (
			patch("crm.automation.optin_billing.frappe.db.exists", return_value=True),
			patch("crm.automation.optin_billing.frappe.db.savepoint"),
			patch("crm.automation.optin_billing.frappe.get_list", return_value=[SimpleNamespace(name=submission.name)]),
			patch("crm.automation.optin_billing.frappe.get_doc", side_effect=get_doc),
			patch("crm.automation.optin_billing._quote_for_schedule", return_value=quotation.name),
			patch("crm.automation.optin_billing._mark_deal_won"),
			patch("crm.automation.optin_billing._create_order_and_invoice", return_value=("SAL-ORD-0001", "SAL-INV-0001")) as create_billing,
		):
			result = handoff_facility_signed(submission.contract, "2026-10-12")

		self.assertTrue(result["ok"])
		self.assertEqual(result["sales_order"], "SAL-ORD-0001")
		self.assertEqual(result["sales_invoice"], "SAL-INV-0001")
		self.assertTrue(result["invoice_created"])
		self.assertEqual(create_billing.call_args.args[3].isoformat(), "2026-10-12")
		self.assertTrue(create_billing.call_args.kwargs["create_invoice"])
		self.assertEqual(quotation.company, "Careverse HQ")

	def test_scheduled_network_creates_order_at_signature_without_invoice(self):
		submission = self._submission(
			[
				{
					"year_number": 1,
					"quarter_number": 1,
					"billing_key": "OIS-0001-Y1-Q1",
					"invoice_issue_timing": "submission_offset",
					"invoice_schedule_configured": True,
					"invoice_date": "2026-11-12",
					"status": "Scheduled",
				}
			]
		)
		quotation = self._quotation()

		def get_doc(doctype, name=None):
			return submission if doctype == "CRM Opt-In Submission" else quotation

		with (
			patch("crm.automation.optin_billing.frappe.db.exists", return_value=True),
			patch("crm.automation.optin_billing.frappe.db.savepoint"),
			patch("crm.automation.optin_billing.frappe.get_list", return_value=[SimpleNamespace(name=submission.name)]),
			patch("crm.automation.optin_billing.frappe.get_doc", side_effect=get_doc),
			patch("crm.automation.optin_billing._quote_for_schedule", return_value=quotation.name),
			patch("crm.automation.optin_billing._mark_deal_won"),
			patch("crm.automation.optin_billing._create_order_and_invoice", return_value=("SAL-ORD-0001", "")) as create_billing,
		):
			result = handoff_facility_signed(submission.contract, "2026-10-12")

		self.assertTrue(result["ok"])
		self.assertEqual(result["sales_order"], "SAL-ORD-0001")
		self.assertEqual(result["sales_invoice"], "")
		self.assertFalse(result["invoice_created"])
		self.assertFalse(create_billing.call_args.kwargs["create_invoice"])
		self.assertEqual(json.loads(submission.billing_schedule_json)[0]["invoice_date"], "2026-11-12")

	def test_due_schedule_waits_for_execution_and_uses_saved_invoice_date(self):
		submission = self._submission(
			[
				{
					"year_number": 1,
					"quarter_number": 1,
					"billing_key": "OIS-0001-Y1-Q1",
					"invoice_issue_timing": "submission_offset",
					"invoice_schedule_configured": True,
					"invoice_date": "2026-10-10",
					"status": "Scheduled",
				}
			]
		)
		quotation = self._quotation()

		def get_value(doctype, name, fieldname, **kwargs):
			if fieldname == "status":
				return "Fully Executed"
			return name

		def get_doc(doctype, name=None):
			return submission if doctype == "CRM Opt-In Submission" else quotation

		with (
			patch("crm.automation.optin_billing.frappe.db.exists", return_value=True),
			patch("crm.automation.optin_billing.frappe.db.has_column", return_value=True),
			patch("crm.automation.optin_billing.frappe.db.get_value", side_effect=get_value),
			patch("crm.automation.optin_billing.frappe.db.savepoint"),
			patch("crm.automation.optin_billing.frappe.db.commit"),
			patch("crm.automation.optin_billing.frappe.get_list", return_value=[submission]),
			patch("crm.automation.optin_billing.frappe.get_doc", side_effect=get_doc),
			patch("crm.automation.optin_billing._quote_for_schedule", return_value=quotation.name),
			patch("crm.automation.optin_billing._create_order_and_invoice", return_value=("SAL-ORD-0001", "SAL-INV-0001")) as create_billing,
			patch("crm.automation.optin_billing.nowdate", return_value="2026-10-12"),
		):
			result = process_due_optin_billing()

		self.assertEqual(result, {"processed": 1, "skipped": 0, "failed": 0})
		self.assertEqual(create_billing.call_args.args[3].isoformat(), "2026-10-10")
		updated_schedule = json.loads(submission.billing_schedule_json)[0]
		self.assertEqual(updated_schedule["sales_order"], "SAL-ORD-0001")
		self.assertEqual(updated_schedule["sales_invoice"], "SAL-INV-0001")
		self.assertEqual(updated_schedule["invoice_due_date"], "2026-11-09")

	def test_handoff_retry_returns_existing_order_without_duplicate_creation(self):
		submission = self._submission(
			[
				{
					"year_number": 1,
					"quarter_number": 1,
					"billing_key": "OIS-0001-Y1-Q1",
					"invoice_issue_timing": "contract_signature",
					"invoice_schedule_configured": True,
					"sales_order": "SAL-ORD-0001",
					"sales_invoice": "SAL-INV-0001",
				}
			]
		)

		with (
			patch("crm.automation.optin_billing.frappe.db.exists", return_value=True),
			patch("crm.automation.optin_billing.frappe.get_list", return_value=[SimpleNamespace(name=submission.name)]),
			patch("crm.automation.optin_billing.frappe.get_doc", return_value=submission),
			patch("crm.automation.optin_billing._quote_for_schedule", return_value="SAL-QTN-0001"),
			patch("crm.automation.optin_billing._mark_deal_won"),
			patch("crm.automation.optin_billing._create_order_and_invoice") as create_billing,
		):
			result = handoff_facility_signed(submission.contract, "2026-10-12")

		self.assertTrue(result["ok"])
		self.assertEqual(result["sales_order"], "SAL-ORD-0001")
		self.assertEqual(result["sales_invoice"], "SAL-INV-0001")
		self.assertTrue(result["invoice_created"])
		create_billing.assert_not_called()
