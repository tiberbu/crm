"""OpenMeter Probe activities on the CRM Deal page (Metering tab).

The metering app answers through the `crm_metering_admin_*` hooks, so CRM does not
import it and works the same without it. That app keeps its own role checks: only
OpenMeter Admins may use these, and only the Administrator may reveal a site key.
"""

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, cstr

from crm.utils.facility_ids import owner_facility_candidates, record_facility_id

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
		fields=["name", "hfr_facility_id", "facility_name", "mfl_code"],
		order_by="idx asc",
	)
	return [
		{
			"row_name": row.name,
			"fid": cstr(row.hfr_facility_id).strip(),
			"facility_name": row.facility_name,
			"mfl_code": row.mfl_code,
		}
		for row in rows
	]


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=600)
def find_owner_facilities(deal: str, owner_id_number: str) -> dict:
	"""The owner's registry facilities, for staff to link a Facility ID from the Metering tab."""
	frappe.has_permission("CRM Deal", "read", deal, throw=True)
	_require_manage()
	return owner_facility_candidates(owner_id_number)


@frappe.whitelist(methods=["POST"])
def link_deal_facility(deal: str, row_name: str, hfr_facility_id: str, source: str = "manual", confirm_shared: int = 0):
	"""Link a Facility ID to one of the deal's facility rows, or report a conflict."""
	frappe.has_permission("CRM Deal", "read", deal, throw=True)
	_require_manage()
	if source not in ("hfr", "manual"):
		frappe.throw(_("Unknown link source."), frappe.ValidationError)
	row = frappe.db.get_value(
		"CRM Deal Facility",
		{"name": row_name, "parent": deal, "parenttype": "CRM Deal"},
		["name", "mfl_code"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Facility row not found."), frappe.ValidationError)
	result = record_facility_id(
		cstr(row.mfl_code).strip(),
		cstr(hfr_facility_id).strip(),
		source=source,
		actor=frappe.session.user,
		allow_shared=bool(cint(confirm_shared)),
		deal_row=row_name,
	)
	if result["status"] in ("linked", "already_linked"):
		return {"status": "linked", "fid": result["hfr_facility_id"]}
	if result["status"] == "invalid":
		frappe.throw(_("Enter a Facility ID like FID-00-12345-1."))
	if result["status"] == "different_fid":
		frappe.throw(_("This facility already has a different Facility ID. Change it on the network facility form."))
	return {"status": "in_use", "holders": result["holders"]}


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


def _require_manage():
	if not get_access()["can_manage"]:
		frappe.throw(_("Only OpenMeter Admins can use metering."), frappe.PermissionError)


def _known_facility(fid: str) -> bool:
	"""A deal facility or self-onboarded registry row carries this Facility ID."""
	return bool(
		frappe.db.exists("CRM Deal Facility", {"hfr_facility_id": fid, "parenttype": "CRM Deal"})
		or frappe.db.exists("CRM Pre-Qualified Facility", {"hfr_facility_id": fid})
	)


def _welcome_bonus_view(fid: str) -> dict:
	from crm.utils.token_bonus import WELCOME_BONUS, auto_dispense_enabled, bonus_settings, welcome_bonus_status

	status = welcome_bonus_status(fid)
	if status.get("source_doctype") == "User":
		status["source_label"] = frappe.utils.get_fullname(status.get("source_name"))
	return {**status, "configured_tokens": bonus_settings()[WELCOME_BONUS], "auto_dispense": auto_dispense_enabled()}


@frappe.whitelist(methods=["GET"])
def get_welcome_bonus(fid: str) -> dict:
	"""The facility's one-time welcome bonus: dispensed or not, and how many tokens it gives."""
	_require_manage()
	return _welcome_bonus_view(cstr(fid).strip())


@frappe.whitelist(methods=["POST"])
def dispense_welcome_bonus(fid: str) -> dict:
	"""Grant the welcome bonus now. A facility gets it once; later clicks and its first payment add nothing."""
	from crm.utils.token_bonus import WELCOME_BONUS, bonus_settings
	from crm.utils.token_bonus import dispense_welcome_bonus as dispense

	_require_manage()
	fid = cstr(fid).strip()
	if not fid:
		frappe.throw(_("This facility has no Facility ID."))
	if not _known_facility(fid):
		# The metering app would otherwise create an Active site for any string it is given.
		frappe.throw(_("No CRM facility has the Facility ID {0}.").format(fid))
	if bonus_settings()[WELCOME_BONUS] <= 0:
		frappe.throw(_("The first-purchase bonus is set to 0 tokens in Settings › Opt-In."))
	outcome = dispense(fid, "User", frappe.session.user)
	return {**_welcome_bonus_view(fid), "changed": bool(outcome.get("changed")), "reason": outcome.get("reason") or outcome.get("error")}
