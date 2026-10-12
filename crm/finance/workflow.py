"""Permission extensions for finance workflows.

The Payment Entry approval decision stays in Frappe Workflow. This hook closes
the native Submit permission shortcut by allowing submit only when the active
workflow exposes a submitted-state transition to this user and the built-in
Frappe self-approval check accepts it.
"""

from __future__ import annotations

import frappe


def payment_entry_has_permission(doc, user=None, permission_type=None):
	"""Restrict Payment Entry submit to a valid Accounts Manager workflow action."""
	if permission_type != "submit" or not doc:
		return None

	user = user or frappe.session.user
	if user == "Administrator":
		# Frappe Workflow treats Administrator as its explicit system override.
		return None

	if "Accounts Manager" not in frappe.get_roles(user):
		return False

	if doc.is_new() or not doc.name:
		return False

	from frappe.model.workflow import get_transitions, get_workflow, has_approval_access

	if not frappe.db.exists(
		"Workflow", {"document_type": "Payment Entry", "is_active": 1}
	):
		return False

	workflow = get_workflow("Payment Entry")
	source_doc = frappe.get_doc("Payment Entry", doc.name)
	transitions = get_transitions(source_doc, workflow)
	submitted_states = {
		state.state for state in workflow.states if str(state.doc_status) == "1"
	}

	return any(
		transition.next_state in submitted_states
		and has_approval_access(user, source_doc, transition)
		for transition in transitions
	)
