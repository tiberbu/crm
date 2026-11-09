from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.finance.workflow import payment_entry_has_permission
from crm.finance.api import get_customer_payments
from crm.patches.v1_0.seed_finance_payment_workflow import (
	WORKFLOW_NAME,
	WORKFLOW_STATES,
	WORKFLOW_TRANSITIONS,
)


class TestFinancePaymentWorkflow(UnitTestCase):
	def test_seeded_approval_transition_disables_self_approval(self):
		approval = next(row for row in WORKFLOW_TRANSITIONS if row[1] == "Approve and Submit")
		request = next(row for row in WORKFLOW_TRANSITIONS if row[1] == "Submit for Approval")

		self.assertEqual(WORKFLOW_NAME, "CRM Payment Entry Approval")
		self.assertEqual(approval[3], "Accounts Manager")
		self.assertEqual(approval[4], 0)
		self.assertEqual(request[4], 1)
		self.assertEqual(len(WORKFLOW_STATES), 3)

	def test_site_has_migrated_payment_entry_workflow(self):
		if not frappe.db.exists("Workflow", WORKFLOW_NAME):
			self.skipTest("Run the CRM workflow migration patch on this site first")

		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
		approve = next(row for row in workflow.transitions if row.action == "Approve and Submit")
		self.assertEqual(workflow.document_type, "Payment Entry")
		self.assertEqual(workflow.is_active, 1)
		self.assertEqual(approve.allowed, "Accounts Manager")
		self.assertEqual(approve.allow_self_approval, 0)
		self.assertTrue(frappe.db.has_column("Payment Entry", "workflow_state"))

	def test_accounts_user_cannot_submit_payment_entry(self):
		doc = frappe._dict(name="ACC-PAY-TEST", is_new=lambda: False)
		with patch("crm.finance.workflow.frappe.get_roles", return_value=["Accounts User"]):
			self.assertFalse(payment_entry_has_permission(doc, "accounts.user@example.com", "submit"))

	def test_accounts_manager_submission_uses_native_workflow_transition(self):
		doc = frappe._dict(name="ACC-PAY-TEST", is_new=lambda: False)
		workflow = frappe._dict(states=[frappe._dict(state="Submitted", doc_status="1")])
		source_doc = frappe._dict(name=doc.name)
		transition = frappe._dict(next_state="Submitted")
		with (
			patch("crm.finance.workflow.frappe.get_roles", return_value=["Accounts Manager"]),
			patch("crm.finance.workflow.frappe.db.exists", return_value=True),
			patch("crm.finance.workflow.frappe.get_doc", return_value=source_doc),
			patch("frappe.model.workflow.get_workflow", return_value=workflow),
			patch("frappe.model.workflow.get_transitions", return_value=[transition]),
			patch("frappe.model.workflow.has_approval_access", return_value=True) as native_check,
		):
			self.assertTrue(payment_entry_has_permission(doc, "accounts.manager@example.com", "submit"))

		native_check.assert_called_once_with("accounts.manager@example.com", source_doc, transition)

	def test_self_approval_is_denied_by_native_workflow_check(self):
		doc = frappe._dict(name="ACC-PAY-TEST", is_new=lambda: False)
		workflow = frappe._dict(states=[frappe._dict(state="Submitted", doc_status="1")])
		source_doc = frappe._dict(name=doc.name)
		transition = frappe._dict(next_state="Submitted")
		with (
			patch("crm.finance.workflow.frappe.get_roles", return_value=["Accounts Manager"]),
			patch("crm.finance.workflow.frappe.db.exists", return_value=True),
			patch("crm.finance.workflow.frappe.get_doc", return_value=source_doc),
			patch("frappe.model.workflow.get_workflow", return_value=workflow),
			patch("frappe.model.workflow.get_transitions", return_value=[transition]),
			patch("frappe.model.workflow.has_approval_access", return_value=False) as native_check,
		):
			self.assertFalse(payment_entry_has_permission(doc, "accounts.manager@example.com", "submit"))

		native_check.assert_called_once_with("accounts.manager@example.com", source_doc, transition)

	def test_payment_list_includes_approval_state_and_pending_drafts(self):
		with (
			patch("crm.finance.api.frappe.get_roles", return_value=["Accounts User"]),
			patch("crm.finance.api._resolve_company", return_value="Careverse HQ"),
			patch("crm.finance.api._page_args", return_value=(0, 20)),
			patch("crm.finance.api.frappe.db.has_column", return_value=True),
			patch("crm.finance.api.erpnext_adapter.get_list", return_value=[]) as get_list,
		):
			get_customer_payments(company="Careverse HQ")

		kwargs = get_list.call_args.kwargs
		self.assertIn(["docstatus", "!=", 2], kwargs["filters"])
		self.assertIn("workflow_state", kwargs["fields"])
