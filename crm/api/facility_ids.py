"""Facility IDs for desk screens whose records carry only MFL codes (quotes, opt-in submissions)."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from crm.utils.facility_ids import facility_ids_by_mfl

MAX_CODES = 500


@frappe.whitelist(methods=["GET", "POST"])
def get_facility_ids(mfl_codes: Any) -> dict[str, str]:
	"""Map MFL codes to Facility IDs for signed-in CRM staff."""
	if frappe.session.user == "Guest" or frappe.get_cached_value("User", frappe.session.user, "user_type") != "System User":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if isinstance(mfl_codes, str):
		mfl_codes = json.loads(mfl_codes or "[]")
	if not isinstance(mfl_codes, list) or len(mfl_codes) > MAX_CODES:
		frappe.throw(_("Send up to %s MFL codes as a list.") % MAX_CODES, frappe.ValidationError)
	return facility_ids_by_mfl(mfl_codes)
