from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.finance.api import (
	_add_finance_network_labels,
	get_rebate_vouchers,
	get_sales_commissions,
)


class TestFinancePartnerNetworkLinks(UnitTestCase):
	def _run_list(self, endpoint, doctype, record):
		calls = []

		def get_list(requested_doctype, filters=None, **kwargs):
			calls.append((requested_doctype, filters, kwargs))
			if requested_doctype == doctype:
				self.assertIn(["docstatus", "!=", 2], filters)
				self.assertIn("optin_network", kwargs["fields"])
				return [record]
			if requested_doctype == "CRM Opt-In Network":
				self.assertEqual(filters, {"name": ["in", ["care-network"]]})
				self.assertEqual(kwargs["fields"], ["name", "display_name"])
				return [frappe._dict(name="care-network", display_name="Care Network")]
			self.fail(f"Unexpected DocType query: {requested_doctype}")

		def erp_get_list(requested_doctype, filters, **kwargs):
			self.assertEqual(requested_doctype, "Payment Entry")
			self.assertIn(["company", "=", "Careverse HQ"], filters)
			self.assertIn(["name", "in", ["PAY-0001"]], filters)
			return [{"name": "PAY-0001"}]

		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User"]),
			patch("crm.finance.api._resolve_company", return_value="Careverse HQ") as resolve_company,
			patch("crm.finance.api.frappe.db.has_column", return_value=True),
			patch("crm.finance.api.frappe.get_list", side_effect=get_list),
			patch("crm.finance.api.erpnext_adapter.get_list", side_effect=erp_get_list) as erp_list,
		):
			rows = endpoint(company="Careverse HQ")

		resolve_company.assert_called_once_with("Careverse HQ")
		self.assertEqual(erp_list.call_count, 1)
		self.assertEqual(erp_list.call_args.kwargs["fields"], ["name"])
		self.assertEqual(len(calls), 2)
		return rows

	def test_rebate_list_uses_canonical_network_and_payment_company(self):
		rows = self._run_list(
			get_rebate_vouchers,
			"CRM Partner Rebate Voucher",
			frappe._dict(
				name="RBV-0001",
				partner="LEGACY-PARTNER",
				payment_reference="PAY-0001",
				optin_network="care-network",
			),
		)

		self.assertEqual(rows[0].network_label, "Care Network")
		self.assertEqual(rows[0].optin_network, "care-network")
		self.assertEqual(rows[0].company, "Careverse HQ")
		self.assertTrue(rows[0].network_available)

	def test_commission_list_uses_canonical_network_and_payment_company(self):
		rows = self._run_list(
			get_sales_commissions,
			"CRM Sales Commission",
			frappe._dict(
				name="COM-0001",
				payment_reference="PAY-0001",
				optin_network="care-network",
			),
		)

		self.assertEqual(rows[0].network_label, "Care Network")
		self.assertEqual(rows[0].optin_network, "care-network")
		self.assertEqual(rows[0].company, "Careverse HQ")
		self.assertTrue(rows[0].network_available)

	def test_missing_network_never_falls_back_to_legacy_partner(self):
		with patch("crm.finance.api.frappe.get_list", return_value=[]) as get_list:
			rows = [frappe._dict(partner="LEGACY-PARTNER", optin_network="missing-network")]
			result = _add_finance_network_labels(rows, "Careverse HQ")

		self.assertEqual(result[0].network_label, "")
		self.assertFalse(result[0].network_available)
		get_list.assert_called_once()
