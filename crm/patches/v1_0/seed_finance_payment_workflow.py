"""Seed the Accounts User → Accounts Manager Payment Entry workflow."""

from __future__ import annotations

import frappe


WORKFLOW_NAME = "CRM Payment Entry Approval"

WORKFLOW_STATES = (
	("Draft", "0", "Accounts User", "Info"),
	("Pending Approval", "0", "Accounts Manager", "Warning"),
	("Submitted", "1", "Accounts Manager", "Success"),
)

WORKFLOW_TRANSITIONS = (
	("Draft", "Submit for Approval", "Pending Approval", "Accounts User", 1),
	("Draft", "Submit for Approval", "Pending Approval", "Accounts Manager", 1),
	("Pending Approval", "Approve and Submit", "Submitted", "Accounts Manager", 0),
)


def _ensure_link_records():
	for state, _doc_status, _allow_edit, style in WORKFLOW_STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{
					"doctype": "Workflow State",
					"workflow_state_name": state,
					"style": style,
				}
			).insert(ignore_permissions=True)

	for _state, action, _next_state, _role, _allow_self_approval in WORKFLOW_TRANSITIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)


def _workflow_doc():
	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		return frappe.get_doc("Workflow", WORKFLOW_NAME)
	return frappe.new_doc("Workflow")


def execute():
	"""Create or refresh the CRM Payment Entry approval workflow on migrate."""
	if not frappe.db.exists("DocType", "Payment Entry"):
		return
	if not frappe.db.exists("Role", "Accounts User") or not frappe.db.exists("Role", "Accounts Manager"):
		return

	_ensure_link_records()
	workflow = _workflow_doc()
	workflow.workflow_name = WORKFLOW_NAME
	workflow.document_type = "Payment Entry"
	workflow.is_active = 1
	workflow.override_status = 0
	workflow.send_email_alert = 0
	workflow.workflow_state_field = "workflow_state"
	workflow.set("states", [])
	workflow.set("transitions", [])

	for state, doc_status, allow_edit, _style in WORKFLOW_STATES:
		workflow.append(
			"states",
			{
				"state": state,
				"doc_status": doc_status,
				"allow_edit": allow_edit,
				"update_field": "workflow_state",
				"update_value": state,
			},
		)

	for state, action, next_state, role, allow_self_approval in WORKFLOW_TRANSITIONS:
		workflow.append(
			"transitions",
			{
				"state": state,
				"action": action,
				"next_state": next_state,
				"allowed": role,
				# Frappe Workflow enforces this on apply_workflow; keep explicit
				# zero because the DocType default permits self-approval.
				"allow_self_approval": allow_self_approval,
			},
		)

	if workflow.is_new():
		workflow.insert(ignore_permissions=True)
	else:
		workflow.save(ignore_permissions=True)
