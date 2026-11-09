from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import UnitTestCase

from crm.api.contracts import dispatch_contract


class TestContractEmailDispatch(UnitTestCase):
	def test_dispatch_sends_pdf_to_requested_recipient(self):
		contract = SimpleNamespace(name="CONT-TEST-DISPATCH", deal="DEAL-TEST-DISPATCH", status="Pending")
		queue = SimpleNamespace(name="Email Queue-TEST-DISPATCH")

		with (
			patch("crm.api.contracts._check_crm_role"),
			patch("crm.api.contracts.frappe.db.exists", return_value=True),
			patch("crm.api.contracts.frappe.get_doc", return_value=contract),
			patch("crm.api.contracts.frappe.get_print", return_value=b"%PDF-1.7"),
			patch("crm.api.contracts._network_for_contract", return_value=None),
			patch("crm.api.contracts._contract_email_subject_label", return_value="Afya Hospital"),
			patch("crm.api.contracts._log_contract_email", return_value="COMM-TEST-DISPATCH") as log_email,
			patch("crm.api.contracts.frappe.sendmail", return_value=queue) as sendmail,
			patch("crm.api.contracts.log_deal_event") as log_event,
		):
			result = dispatch_contract(
				"CONT-TEST-DISPATCH",
				"recipient@example.com",
				"Recipient",
			)

		self.assertEqual(
			result,
			{
				"status": "sent",
				"email": "recipient@example.com",
				"contract": "CONT-TEST-DISPATCH",
				"queue": "Email Queue-TEST-DISPATCH",
				"communication": "COMM-TEST-DISPATCH",
			},
		)
		attachment = sendmail.call_args.kwargs["attachments"][0]
		self.assertEqual(attachment["fname"], "CONT-TEST-DISPATCH.pdf")
		self.assertEqual(attachment["fcontent"], b"%PDF-1.7")
		self.assertEqual(sendmail.call_args.kwargs["recipients"], ["recipient@example.com"])
		self.assertEqual(sendmail.call_args.kwargs["communication"], "COMM-TEST-DISPATCH")
		self.assertEqual(sendmail.call_args.kwargs["reference_doctype"], "CRM Deal")
		self.assertEqual(sendmail.call_args.kwargs["reference_name"], "DEAL-TEST-DISPATCH")
		log_email.assert_called_once()
		log_event.assert_called_once_with(
			"DEAL-TEST-DISPATCH",
			"Contract CONT-TEST-DISPATCH dispatched to recipient@example.com",
		)
