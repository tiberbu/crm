from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.finance.api import _add_finance_employee_labels, mark_commission_paid, mark_rebate_paid
from crm.finance.payment_hooks import _maybe_create_rebate_voucher
from crm.finance.setup import ensure_network_payout_mappings


class TestFinancePayeeMapping(UnitTestCase):
	def test_rebate_paid_action_is_blocked_without_native_payout(self):
		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts Manager"]),
			patch("crm.finance.api.is_manager", return_value=True),
			patch("crm.finance.api.frappe.throw", side_effect=frappe.ValidationError) as throw,
			patch("crm.finance.api.frappe.get_doc") as get_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				mark_rebate_paid("REBATE-0001", "Careverse HQ")

		self.assertIn("native payable and payment flow", throw.call_args.args[0])
		get_doc.assert_not_called()

	def test_commission_paid_action_is_blocked_without_native_payout(self):
		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts Manager"]),
			patch("crm.finance.api.is_manager", return_value=True),
			patch("crm.finance.api.frappe.throw", side_effect=frappe.ValidationError) as throw,
			patch("crm.finance.api.frappe.get_doc") as get_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				mark_commission_paid("COMM-0001", "Careverse HQ")

		self.assertIn("payroll component and period", throw.call_args.args[0])
		get_doc.assert_not_called()

	def test_network_mappings_are_created_only_when_network_exists(self):
		with patch(
			"crm.finance.setup.frappe.db.exists",
			return_value=False,
		), patch("crm.finance.setup.create_custom_fields") as create_fields:
			self.assertFalse(ensure_network_payout_mappings())

		create_fields.assert_not_called()

	def test_network_rate_and_supplier_mappings_are_finance_scoped(self):
		with (
			patch("crm.finance.setup.frappe.db.exists", return_value=True),
			patch("crm.finance.setup.create_custom_fields") as create_fields,
			patch("crm.finance.setup.frappe.db.get_value", return_value=None),
			patch("crm.finance.setup.frappe.get_doc") as get_doc,
			patch("crm.finance.setup.frappe.db.has_column", return_value=True),
		):
			self.assertTrue(ensure_network_payout_mappings())

		fields = create_fields.call_args.args[0]["CRM Opt-In Network"]
		self.assertEqual([field["fieldname"] for field in fields], ["finance_rebate_structure", "finance_supplier"])
		self.assertEqual(fields[0]["options"], "CRM Rebate Structure")
		self.assertEqual(fields[1]["options"], "Supplier")
		self.assertEqual([field["permlevel"] for field in fields], [1, 1])
		self.assertEqual(get_doc.call_count, 2)
		permissions = [call.args[0] for call in get_doc.call_args_list]
		self.assertEqual([permission["permlevel"] for permission in permissions], [0, 1])
		self.assertEqual([permission["write"] for permission in permissions], [0, 1])
		self.assertTrue(all(permission["role"] == "Accounts Manager" for permission in permissions))

	def test_commission_payee_resolves_active_employee_for_current_company(self):
		rows = [frappe._dict(sales_person="seller@example.com")]
		with patch(
			"crm.finance.api.erpnext_adapter.get_list",
			return_value=[frappe._dict(name="EMP-001", user_id="seller@example.com", employee_name="Sales Seller", company="Careverse HQ", status="Active")],
		) as get_list:
			result = _add_finance_employee_labels(rows, "Careverse HQ")

		self.assertEqual(result[0].employee, "EMP-001")
		self.assertEqual(result[0].employee_name, "Sales Seller")
		self.assertTrue(result[0].employee_available)
		self.assertEqual(get_list.call_args.args[0], "Employee")
		self.assertIn(["company", "=", "Careverse HQ"], get_list.call_args.kwargs["filters"])
		self.assertIn(["user_id", "in", ["seller@example.com"]], get_list.call_args.kwargs["filters"])
		self.assertIn(["status", "=", "Active"], get_list.call_args.kwargs["filters"])

	def test_payroll_employee_from_another_company_is_not_linked(self):
		rows = [frappe._dict(sales_person="seller@example.com")]
		with patch(
			"crm.finance.api.erpnext_adapter.get_list",
			return_value=[frappe._dict(name="EMP-OTHER", user_id="seller@example.com", employee_name="Other Seller", company="Other Company", status="Active")],
		):
			result = _add_finance_employee_labels(rows, "Careverse HQ")

		self.assertFalse(result[0].employee_available)
		self.assertEqual(result[0].employee, "")
		self.assertEqual(result[0].employee_name, "No active Employee linked for this Company")

	def test_rebate_accrual_uses_network_rate_and_keeps_legacy_partner_optional(self):
		payment = frappe._dict(name="PAY-0001", paid_to_account_currency="KES")
		invoice = frappe._dict(name="SINV-0001", customer="CUST-001")
		ref = frappe._dict(allocated_amount=1000)
		created = frappe._dict(insert=lambda **kwargs: None)
		get_value = {
			("CRM Deal", "DEAL-0001", "optin_network"): "care-network",
			("CRM Opt-In Network", "care-network", "finance_rebate_structure"): "NETWORK-REBATE-10",
			("CRM Rebate Structure", "NETWORK-REBATE-10", "rebate_pct"): 10,
			("CRM Deal", "DEAL-0001", "lead"): "LEAD-0001",
			("CRM Lead", "LEAD-0001", "partner"): "LEGACY-PARTNER",
		}
		with (
			patch("crm.finance.payment_hooks.frappe.db.exists", return_value=False),
			patch("crm.finance.payment_hooks.frappe.db.has_column", return_value=True),
			patch("crm.finance.payment_hooks.frappe.db.get_value", side_effect=lambda *args, **kwargs: get_value[args]),
			patch("crm.finance.payment_hooks.frappe.get_doc", return_value=created) as get_doc,
			patch("crm.finance.payment_hooks.set_network_link") as set_network_link,
		):
			_maybe_create_rebate_voucher(payment, invoice, ref, "DEAL-0001")

		voucher = get_doc.call_args.args[0]
		self.assertEqual(voucher["rebate_structure"], "NETWORK-REBATE-10")
		self.assertEqual(voucher["rebate_amount"], 100)
		self.assertEqual(voucher["partner"], "LEGACY-PARTNER")
		set_network_link.assert_called_once_with(created, "care-network")
