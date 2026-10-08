"""Shared authorization for the Finance Cockpit.

The cockpit is an accounting workspace, not a general CRM reporting surface.
Keep the policy in one small module so the page, API, route guard, and frontend
all fail closed in the same way.
"""

from __future__ import annotations

import frappe
from frappe import _


ACCOUNTING_ROLES = frozenset({"Accounts User", "Accounts Manager"})


def roles_for_user(user=None) -> set[str]:
	"""Return the complete role set, denying access if role resolution fails."""
	try:
		user = user or frappe.session.user
		return set(frappe.get_roles(user))
	except Exception:
		return set()


def has_access(user=None, roles=None) -> bool:
	"""Administrator is the recovery account; all other access is Accounts-based."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(ACCOUNTING_ROLES & (set(roles) if roles is not None else roles_for_user(user)))


def require_access(user=None, roles=None):
	"""Raise a stable, user-facing permission error for non-accounting users."""
	if not has_access(user=user, roles=roles):
		frappe.throw(
			_("Finance Cockpit requires the Accounts User or Accounts Manager role."),
			frappe.PermissionError,
		)


def is_manager(user=None, roles=None) -> bool:
	"""Return whether the user may perform manager-level cockpit actions."""
	user = user or frappe.session.user
	return user == "Administrator" or "Accounts Manager" in (
		set(roles) if roles is not None else roles_for_user(user)
	)
