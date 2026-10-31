"""OpenMeter Probe activities on the CRM Deal page (Metering tab).

The metering app answers through the `crm_metering_admin_*` hooks, so CRM does not
import it and works the same without it. That app keeps its own role checks: only
OpenMeter Admins may use these, and only the Administrator may reveal a site key.
"""

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cstr

NO_ACCESS = {"enabled": False, "can_manage": False, "can_reveal": False}


def _hook(name: str):
	methods = frappe.get_hooks(name)
	return frappe.get_attr(methods[-1]) if methods else None


def _require_hook(name: str):
	method = _hook(name)
	if not method:
		frappe.throw(_("No metering app is installed on this site."))
	return method


@frappe.whitelist(methods=["GET"])
def get_access() -> dict:
	"""Whether the Metering tab shows, and whether this user may reveal site keys."""
	method = _hook("crm_metering_admin_access")
	if not method:
		return NO_ACCESS
	try:
		result = method() or {}
	except Exception:
		frappe.log_error(title="Metering access unavailable", message=frappe.get_traceback())
		return NO_ACCESS
	return {
		"enabled": True,
		"can_manage": bool(result.get("can_manage")),
		"can_reveal": bool(result.get("can_reveal")),
	}


@frappe.whitelist(methods=["GET"])
def get_deal_facilities(deal: str) -> list[dict]:
	"""The deal's facilities, Facility ID first, for the Metering tab."""
	frappe.has_permission("CRM Deal", "read", deal, throw=True)
	if not get_access()["can_manage"]:
		frappe.throw(_("Only OpenMeter Admins can use metering."), frappe.PermissionError)
	rows = frappe.get_all(
		"CRM Deal Facility",
		filters={"parent": deal, "parenttype": "CRM Deal"},
		fields=["hfr_facility_id", "facility_name", "mfl_code"],
		order_by="idx asc",
	)
	return [
		{
			"fid": cstr(row.hfr_facility_id).strip(),
			"facility_name": row.facility_name,
			"mfl_code": row.mfl_code,
		}
		for row in rows
	]


@frappe.whitelist(methods=["GET"])
def get_facility(fid: str) -> dict:
	return _require_hook("crm_metering_admin_facility")(fid)


@frappe.whitelist(methods=["POST"])
def run_action(action: str, fid: str | None = None, params: str | dict | None = None):
	if isinstance(params, str):
		params = json.loads(params or "{}")
	return _require_hook("crm_metering_admin_action")(action, fid=fid, params=params or {})


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=5, seconds=10 * 60)
def reveal_key(fid: str, password: str) -> dict:
	"""The facility's full site key, for the Administrator to copy. The metering app re-checks the password."""
	return _require_hook("crm_metering_admin_reveal_key")(fid, password)
