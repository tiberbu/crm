from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

from crm.finance.api import _get_customer_payment_context, _get_customer_payment_entry


class TestFinancePaymentMode(UnitTestCase):
	def _context(self, mode, account_type, account_company="Careverse HQ"):
		account = "Bank - CHQ" if account_type == "Bank" else "Cash - CHQ"
		with (
			patch("crm.finance.api.frappe.db.exists", return_value=True),
			patch(
				"crm.finance.api.frappe.db.get_value",
				side_effect=[
					"Cash" if mode == "Cash" else "Bank",
					account,
					frappe._dict(
						company=account_company,
						account_type=account_type,
						is_group=0,
						disabled=0,
					),
				],
			),
			patch(
				"erpnext.accounts.doctype.journal_entry.journal_entry.get_default_bank_cash_account",
				return_value=frappe._dict(account=account),
			) as resolver,
		):
			result = _get_customer_payment_context("Careverse HQ", mode)
		return result, resolver

	def test_bank_account_requires_both_native_transaction_references(self):
		context, resolver = self._context("Bank Transfer", "Bank")

		self.assertTrue(context["configured"])
		self.assertEqual(context["account"], "Bank - CHQ")
		self.assertEqual(context["account_type"], "Bank")
		self.assertTrue(context["requires_reference"])
		resolver.assert_called_once_with("Careverse HQ", mode_of_payment="Bank Transfer")

	def test_cash_account_does_not_require_bank_references(self):
		context, _resolver = self._context("Cash", "Cash")

		self.assertTrue(context["configured"])
		self.assertEqual(context["account_type"], "Cash")
		self.assertFalse(context["requires_reference"])

	def test_cash_mode_mapped_to_bank_returns_configuration_error(self):
		context, _resolver = self._context("Cash", "Bank")

		self.assertFalse(context["configured"])
		self.assertIn("Cash Mode of Payment is mapped to a Bank account", context["message"])

	def test_native_payment_entry_validation_accepts_cash_without_references(self):
		entry = frappe._dict(payment_type="Receive", paid_from="Debtors - CHQ", paid_to="Cash - CHQ")
		with patch(
			"erpnext.accounts.doctype.payment_entry.payment_entry.frappe.get_cached_value",
			return_value="Cash",
		):
			PaymentEntry.validate_transaction_reference(entry)

	def test_native_payment_entry_validation_requires_both_bank_references(self):
		entry = frappe._dict(payment_type="Receive", paid_from="Debtors - CHQ", paid_to="Bank - CHQ")
		with patch(
			"erpnext.accounts.doctype.payment_entry.payment_entry.frappe.get_cached_value",
			return_value="Bank",
		):
			with self.assertRaises(frappe.ValidationError):
				PaymentEntry.validate_transaction_reference(entry)

		entry.reference_no = "BANK-REF-1"
		entry.reference_date = "2026-10-12"
		with patch(
			"erpnext.accounts.doctype.payment_entry.payment_entry.frappe.get_cached_value",
			return_value="Bank",
		):
			PaymentEntry.validate_transaction_reference(entry)

	def test_account_mapped_to_another_company_returns_configuration_error(self):
		context, _resolver = self._context("Bank Transfer", "Bank", account_company="Other Company")

		self.assertFalse(context["configured"])
		self.assertIn("belonging to Careverse HQ", context["message"])

	def test_unconfigured_mode_has_recovery_message(self):
		with (
			patch("crm.finance.api.frappe.db.exists", return_value=True),
			patch("crm.finance.api.frappe.db.get_value", return_value=None),
			patch(
				"erpnext.accounts.doctype.journal_entry.journal_entry.get_default_bank_cash_account"
			) as resolver,
		):
			context = _get_customer_payment_context("Careverse HQ", "Bank Transfer")

		self.assertFalse(context["configured"])
		self.assertIn("no account configured", context["message"])
		resolver.assert_not_called()

	def test_payment_entry_mapper_contract_matches_erpnext_v15_and_v16(self):
		def map_v15(dt, dn, party_amount=None, bank_account=None, bank_amount=None, party_type=None, payment_type=None, reference_date=None, created_from_payment_request=False):
			return frappe._dict(paid_to=bank_account)

		def map_v16(dt, dn, party_amount=None, bank_account=None, bank_amount=None, party_type=None, payment_type=None, reference_date=None, created_from_payment_request=False):
			return frappe._dict(paid_to=bank_account)

		for mapper in (map_v15, map_v16):
			with patch(
				"erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
				new=mapper,
			):
				entry = _get_customer_payment_entry("SINV-1", 25, "Cash - CHQ")
				self.assertEqual(entry.paid_to, "Cash - CHQ")

	def test_selected_mode_account_overrides_invoice_mode_account_from_mapper(self):
		mapped_entry = frappe._dict(paid_to="Invoice Default - CHQ")
		with (
			patch(
				"erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
				return_value=mapped_entry,
			) as mapper,
			patch(
				"crm.finance.api.frappe.db.get_value",
				return_value=frappe._dict(account_currency="KES", account_type="Cash"),
			),
		):
			entry = _get_customer_payment_entry("SINV-1", 25, "Selected Cash - CHQ")

		self.assertEqual(entry.paid_to, "Selected Cash - CHQ")
		self.assertEqual(entry.paid_to_account_currency, "KES")
		self.assertEqual(entry.paid_to_account_type, "Cash")
		mapper.assert_called_once_with(
			"Sales Invoice", "SINV-1", party_amount=25, bank_account="Selected Cash - CHQ"
		)
