from unittest import TestCase
from unittest.mock import patch

import frappe

from crm.finance.payment_hooks import on_payment_entry_submit


class TestFinancePaymentHook(TestCase):
	def setUp(self):
		frappe.flags.crm_finance_payment_warnings = {}

	def tearDown(self):
		frappe.flags.pop("crm_finance_payment_warnings", None)

	def test_crm_accrual_failure_does_not_fail_native_payment_submit(self):
		payment = frappe._dict(
			name="PE-TEST-001",
			payment_type="Receive",
			references=[
				frappe._dict(
					reference_doctype="Sales Invoice",
					reference_name="SINV-TEST-001",
					allocated_amount=100,
				)
			],
		)
		invoice = frappe._dict(name="SINV-TEST-001")
		with (
			patch("crm.finance.payment_hooks.frappe.get_doc", return_value=invoice),
			patch("crm.finance.payment_hooks.frappe.db.get_value", return_value="DEAL-TEST-001"),
			patch(
				"crm.finance.payment_hooks._maybe_create_rebate_voucher",
				side_effect=RuntimeError("missing rebate setup"),
			),
			patch("crm.finance.payment_hooks._maybe_create_commission"),
			patch(
				"crm.finance.payment_hooks.frappe.log_error",
				return_value=frappe._dict(name="ERROR-LOG-001"),
			) as log_error,
			patch("crm.finance.payment_hooks.frappe.msgprint") as msgprint,
		):
			self.assertIsNone(on_payment_entry_submit(payment, "on_submit"))

		self.assertEqual(log_error.call_args.kwargs["reference_name"], payment.name)
		warnings = frappe.flags.crm_finance_payment_warnings[payment.name]
		self.assertEqual(len(warnings), 1)
		self.assertIn("Payment Entry was submitted", warnings[0])
		self.assertIn("ERROR-LOG-001", warnings[0])
		msgprint.assert_called_once()

	def test_receive_with_non_invoice_reference_reports_unsupported_crm_scope(self):
		payment = frappe._dict(
			name="PE-TEST-002",
			payment_type="Receive",
			references=[
				frappe._dict(reference_doctype="Sales Order", reference_name="SO-TEST-001")
			],
		)
		with (
			patch("crm.finance.payment_hooks._maybe_create_rebate_voucher") as rebate,
			patch("crm.finance.payment_hooks._maybe_create_commission") as commission,
			patch("crm.finance.payment_hooks.frappe.msgprint") as msgprint,
		):
			on_payment_entry_submit(payment, "on_submit")

		rebate.assert_not_called()
		commission.assert_not_called()
		self.assertIn("only for receipts allocated to Sales Invoices", msgprint.call_args.args[0])
