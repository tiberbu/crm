from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.finance.api import (
	_add_finance_employee_labels,
	get_finance_rule_options,
	mark_commission_paid,
	mark_rebate_paid,
	save_network_rebate_settings,
)
from crm.finance.payment_hooks import (
	_invoice_facility_bases,
	_maybe_create_commission,
	_maybe_create_rebate_voucher,
)
from crm.finance.setup import ensure_network_payout_mappings, ensure_optin_supplier_attribution_fields


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

	def test_optin_supplier_fields_are_copyable_through_billing_documents(self):
		with (
			patch("crm.finance.setup.frappe.db.exists", return_value=True),
			patch("crm.finance.setup.create_custom_fields") as create_fields,
			patch("crm.finance.setup.frappe.db.has_column", return_value=True),
		):
			self.assertTrue(ensure_optin_supplier_attribution_fields())

		definitions = create_fields.call_args.args[0]
		self.assertEqual(set(definitions), {"Quotation Item", "Sales Order Item", "Sales Invoice Item"})
		for fields in definitions.values():
			by_name = {field["fieldname"]: field for field in fields}
			self.assertEqual(by_name["crm_rebate_supplier"]["no_copy"], 0)
			self.assertEqual(by_name["crm_optin_facility_mfl_code"]["no_copy"], 0)

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
			("CRM Opt-In Network", "care-network", "finance_supplier"): "SUPPLIER-01",
			("CRM Rebate Structure", "NETWORK-REBATE-10", "rebate_pct"): 10,
			("CRM Deal", "DEAL-0001", "lead"): "LEAD-0001",
			("CRM Lead", "LEAD-0001", "partner"): "LEGACY-PARTNER",
		}
		with (
			patch("crm.finance.payment_hooks.frappe.db.exists", side_effect=lambda *args, **kwargs: args[0] == "Supplier"),
			patch("crm.finance.payment_hooks.frappe.db.has_column", return_value=True),
			patch("crm.finance.payment_hooks.frappe.db.get_value", side_effect=lambda *args, **kwargs: get_value[args]),
			patch("crm.finance.payment_hooks.frappe.get_doc", return_value=created) as get_doc,
			patch("crm.finance.payment_hooks.set_network_link") as set_network_link,
		):
			_maybe_create_rebate_voucher(payment, invoice, ref, "DEAL-0001")

		voucher = get_doc.call_args.args[0]
		self.assertEqual(voucher["rebate_structure"], "NETWORK-REBATE-10")
		self.assertEqual(voucher["rebate_amount"], 100)
		self.assertEqual(voucher["payee_supplier"], "SUPPLIER-01")
		self.assertEqual(voucher["calculation_basis"], 1000)
		self.assertEqual(voucher["partner"], "LEGACY-PARTNER")
		set_network_link.assert_called_once_with(created, "care-network")

	def test_invoice_allocation_is_split_proportionally_over_facility_supplier_lines(self):
		invoice = frappe._dict(
			items=[
				frappe._dict(
					crm_optin_facility_mfl_code="111",
					facility_name="Clinic One",
					crm_rebate_supplier="SUPPLIER-01",
					base_net_amount=300,
				),
				frappe._dict(
					crm_optin_facility_mfl_code="222",
					facility_name="Clinic Two",
					crm_rebate_supplier="SUPPLIER-02",
					base_net_amount=200,
				),
			]
		)

		bases = _invoice_facility_bases(invoice, 1000)

		self.assertEqual([row.basis for row in bases], [600, 400])
		self.assertEqual(sum(row.basis for row in bases), 1000)
		self.assertEqual([row.supplier for row in bases], ["SUPPLIER-01", "SUPPLIER-02"])

	def test_facility_supplier_overrides_network_fallback(self):
		payment = frappe._dict(name="PAY-0001", paid_to_account_currency="KES")
		invoice = frappe._dict(
			name="SINV-0001", customer="CUST-001", currency="KES",
			items=[frappe._dict(crm_optin_facility_mfl_code="111", facility_name="Clinic", crm_rebate_supplier="FACILITY-SUPPLIER", net_amount=1000)],
		)
		ref = frappe._dict(allocated_amount=1000)
		created = frappe._dict(insert=lambda **kwargs: None)
		get_value = {
			("CRM Deal", "DEAL-0001", "optin_network"): "care-network",
			("CRM Opt-In Network", "care-network", "finance_rebate_structure"): "NETWORK-RULE",
			("CRM Opt-In Network", "care-network", "finance_supplier"): "NETWORK-SUPPLIER",
			("CRM Rebate Structure", "NETWORK-RULE", "rebate_pct"): 5,
			("CRM Deal", "DEAL-0001", "lead"): "",
		}
		with (
			patch("crm.finance.payment_hooks.frappe.db.exists", side_effect=lambda doctype, *args, **kwargs: doctype == "Supplier"),
			patch("crm.finance.payment_hooks.frappe.db.has_column", return_value=True),
			patch("crm.finance.payment_hooks.frappe.db.get_value", side_effect=lambda *args, **kwargs: get_value[args]),
			patch("crm.finance.payment_hooks.frappe.get_doc", return_value=created) as get_doc,
			patch("crm.finance.payment_hooks.set_network_link"),
		):
			_maybe_create_rebate_voucher(payment, invoice, ref, "DEAL-0001")

		voucher = get_doc.call_args.args[0]
		self.assertEqual(voucher["payee_supplier"], "FACILITY-SUPPLIER")
		self.assertEqual(voucher["rebate_amount"], 50)

	def test_commission_uses_unique_employee_rule_and_snapshots_rate_and_basis(self):
		payment = frappe._dict(name="PAY-0001", paid_to_account_currency="KES")
		invoice = frappe._dict(name="SINV-0001", customer="CUST-001", company="Careverse HQ", currency="KES")
		ref = frappe._dict(allocated_amount=2500)
		created = frappe._dict(insert=lambda **kwargs: None)
		with (
			patch("crm.finance.payment_hooks.frappe.db.get_value", side_effect=["seller@example.com", frappe._dict(name="RATE-1", commission_pct=4), "care-network"]),
			patch("crm.finance.payment_hooks.frappe.db.has_column", return_value=True),
			patch(
				"crm.finance.payment_hooks.frappe.get_all",
				return_value=[frappe._dict(name="EMP-001", user_id="seller@example.com", company="Careverse HQ")],
			) as get_all,
			patch(
				"crm.finance.payment_hooks.frappe.db.exists",
				side_effect=lambda doctype, *args, **kwargs: doctype == "DocType" and args[0] == "Employee",
			),
			patch("crm.finance.payment_hooks.frappe.get_doc", return_value=created) as get_doc,
			patch("crm.finance.payment_hooks.set_network_link"),
		):
			_maybe_create_commission(payment, invoice, ref, "DEAL-0001")

		self.assertEqual(get_all.call_args.args[0], "Employee")
		commission = get_doc.call_args.args[0]
		self.assertEqual(commission["employee"], "EMP-001")
		self.assertEqual(commission["commission_pct"], 4)
		self.assertEqual(commission["calculation_basis"], 2500)
		self.assertEqual(commission["commission_amount"], 100)

	def test_rule_options_are_limited_to_accounts_managers(self):
		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User"]),
			patch("crm.finance.api._is_admin", return_value=False),
			patch("crm.finance.api.frappe.throw", side_effect=frappe.PermissionError),
		):
			with self.assertRaises(frappe.PermissionError):
				get_finance_rule_options()

	def test_rebate_rate_rejects_values_outside_percentage_range(self):
		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts Manager"]),
			patch("crm.finance.api.frappe.db.exists", return_value=True),
			patch("crm.finance.api.frappe.throw", side_effect=frappe.ValidationError) as throw,
		):
			with self.assertRaises(frappe.ValidationError):
				save_network_rebate_settings("care-network", 100.01)

		self.assertIn("between 0 and 100", throw.call_args.args[0])
