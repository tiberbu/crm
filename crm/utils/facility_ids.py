"""Facility IDs (Health Facility Registry FIDs) for MFL codes.

Every CRM workflow shows a facility's Facility ID; records that only carry an MFL code read it
from the pre-qualified facility register, where HFR lookups and onboarding store it.
"""

from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe.utils import cstr


def facility_ids_by_mfl(mfl_codes: Iterable) -> dict[str, str]:
	"""Map each known MFL code to its Facility ID; codes without one are left out."""
	codes = sorted({cstr(code).strip() for code in mfl_codes or [] if cstr(code).strip()})
	if not codes:
		return {}
	rows = frappe.get_all(
		"CRM Pre-Qualified Facility",
		filters={"mfl_code": ["in", codes], "hfr_facility_id": ["is", "set"]},
		fields=["mfl_code", "hfr_facility_id"],
		ignore_permissions=True,  # SYSTEM-INTERNAL: callers have already scoped the MFL codes.
	)
	return {cstr(row.mfl_code).strip(): cstr(row.hfr_facility_id).strip() for row in rows}
