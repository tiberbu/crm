"""Facility IDs (Health Facility Registry FIDs) for MFL codes.

Every CRM workflow shows a facility's Facility ID; records that only carry an MFL code read it
from the pre-qualified facility register, where HFR lookups and onboarding store it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import frappe
from frappe.utils import cstr, now_datetime

FACILITY_ID_RE = re.compile(r"FID-\d{2}-[\w-]+", re.IGNORECASE)
SYNC_STATUS = {"hfr": "HFR Verified", "manual": "Manual"}


def is_valid_facility_id(value) -> bool:
	"""True if the value looks like an HFR Facility ID (FID-00-12345-1)."""
	return bool(FACILITY_ID_RE.fullmatch(cstr(value).strip()))


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


def owner_facility_candidates(owner_id_number) -> dict:
	"""Look up an owner's facilities in the registry by ID number.

	Only rows carrying a valid Facility ID are usable. The registry is best-effort: any failure
	leaves the caller free to continue without a link.
	"""
	from crm.api.facility_onboarding import ID_RE, _hfr_facilities_for_owner

	number = cstr(owner_id_number).strip()
	if not ID_RE.fullmatch(number):
		return {"status": "invalid_id", "candidates": []}
	try:
		rows = _hfr_facilities_for_owner(number)
	except Exception:
		frappe.clear_messages()
		return {"status": "unavailable", "candidates": []}
	candidates = []
	seen = set()
	for row in rows or []:
		if not isinstance(row, dict):
			continue
		fid = cstr(row.get("facility_fid")).strip()
		if not is_valid_facility_id(fid):
			continue
		key = fid.casefold()
		if key in seen:
			continue
		seen.add(key)
		candidates.append(
			{
				"hfr_facility_id": fid,
				"facility_name": cstr(row.get("facility_name")),
				"facility_level": cstr(row.get("facility_level")) or cstr(row.get("kephl_level")),
				"facility_type": cstr(row.get("facility_type")),
			}
		)
	if not candidates:
		return {"status": "no_facilities", "candidates": []}
	return {"status": "ok", "candidates": candidates}


def facility_id_holders(fid, mfl_code=None) -> list[dict]:
	"""Records holding `fid` under a different MFL, compared case-insensitively.

	Express rows keep their FID in `mfl_code`, so those count as holders too. A blank `mfl_code`
	returns every holder.
	"""
	target = cstr(fid).strip().casefold()
	if not target:
		return []
	exclude = cstr(mfl_code).strip().casefold()
	holders = []
	seen = set()
	register = frappe.get_all(
		"CRM Pre-Qualified Facility",
		fields=["name", "mfl_code", "hfr_facility_id"],
		ignore_permissions=True,  # SYSTEM-INTERNAL: read-only holders check.
	)
	for row in register:
		mfl = cstr(row.mfl_code).strip().casefold()
		if exclude and mfl == exclude:
			continue
		if cstr(row.hfr_facility_id).strip().casefold() == target or mfl == target:
			key = ("CRM Pre-Qualified Facility", row.name)
			if key not in seen:
				seen.add(key)
				holders.append(
					{"doctype": "CRM Pre-Qualified Facility", "name": row.name, "mfl_code": cstr(row.mfl_code).strip()}
				)
	parenttype = {"CRM Lead Facility": "CRM Lead", "CRM Deal Facility": "CRM Deal"}
	for doctype in ("CRM Lead Facility", "CRM Deal Facility"):
		rows = frappe.get_all(
			doctype,
			filters={"hfr_facility_id": ["is", "set"], "parenttype": parenttype[doctype]},
			fields=["name", "parent", "mfl_code", "hfr_facility_id"],
			ignore_permissions=True,  # SYSTEM-INTERNAL: read-only holders check.
		)
		for row in rows:
			mfl = cstr(row.mfl_code).strip().casefold()
			if exclude and mfl == exclude:
				continue
			if cstr(row.hfr_facility_id).strip().casefold() == target:
				key = (doctype, row.parent)
				if key not in seen:
					seen.add(key)
					holders.append({"doctype": doctype, "name": row.parent, "mfl_code": cstr(row.mfl_code).strip()})
	return holders


def _fid_write_values(fid, sync_status) -> dict:
	values = {"hfr_facility_id": fid, "hfr_sync_status": sync_status}
	if sync_status == "HFR Verified":
		values["hfr_last_synced"] = now_datetime()
	return values


def fill_facility_rows(mfl_code, fid, *, sync_status, replace_fid=None) -> dict:
	"""Fill blank Facility IDs on the Lead and Deal rows of one MFL.

	A row already holding the same FID is left alone. A row holding `replace_fid` is updated; any
	other value is left alone and counted in `skipped`. Only updates — never appends a row and
	never writes `mfl_code`.
	"""
	mfl = cstr(mfl_code).strip()
	target = cstr(fid).strip()
	result = {"filled": 0, "skipped": 0, "deals": []}
	if not mfl or not target:
		return result
	replace = cstr(replace_fid).strip().casefold() if replace_fid else ""
	parenttype = {"CRM Lead Facility": "CRM Lead", "CRM Deal Facility": "CRM Deal"}
	for doctype in ("CRM Lead Facility", "CRM Deal Facility"):
		rows = frappe.get_all(
			doctype,
			filters={"mfl_code": mfl, "parenttype": parenttype[doctype]},
			fields=["name", "parent", "hfr_facility_id"],
			ignore_permissions=True,  # SYSTEM-INTERNAL: fill scoped to one MFL.
		)
		for row in rows:
			current = cstr(row.hfr_facility_id).strip()
			if current:
				if current.casefold() == target.casefold():
					continue
				if not (replace and current.casefold() == replace):
					result["skipped"] += 1
					continue
			frappe.db.set_value(doctype, row.name, _fid_write_values(target, sync_status), update_modified=False)
			result["filled"] += 1
			if doctype == "CRM Deal Facility":
				result["deals"].append(row.parent)
	return result


def record_facility_id(mfl_code, fid, *, source, actor, allow_shared=False, deal_row=None) -> dict:
	"""Record a Facility ID on the register and the matching rows. Never raises for business
	outcomes; the result carries `status`, `hfr_facility_id`, `filled`, `skipped`, `holders`.
	"""
	mfl = cstr(mfl_code).strip()
	target = cstr(fid).strip()
	status = SYNC_STATUS.get(source, "Manual")
	result = {"status": None, "hfr_facility_id": target, "filled": 0, "skipped": 0, "holders": []}
	if not is_valid_facility_id(target) or (not mfl and not deal_row):
		result["status"] = "invalid"
		return result
	if is_valid_facility_id(mfl) and mfl.casefold() != target.casefold():
		result["status"] = "different_fid"
		return result

	register = None
	if mfl:
		register = frappe.db.get_value(
			"CRM Pre-Qualified Facility", {"mfl_code": mfl}, "name", for_update=True
		)
	recorded = set()
	if mfl:
		if register:
			current = frappe.db.get_value("CRM Pre-Qualified Facility", register, "hfr_facility_id")
			if current:
				recorded.add(cstr(current).casefold())
		for doctype in ("CRM Lead Facility", "CRM Deal Facility"):
			rows = frappe.get_all(
				doctype,
				filters={"mfl_code": mfl},
				fields=["hfr_facility_id"],
				ignore_permissions=True,  # SYSTEM-INTERNAL: conflict check scoped to one MFL.
			)
			for row in rows:
				if row.hfr_facility_id:
					recorded.add(cstr(row.hfr_facility_id).casefold())
	if recorded - {target.casefold()}:
		result["status"] = "different_fid"
		return result

	if target.casefold() in recorded:
		if register:
			register_fid = cstr(frappe.db.get_value("CRM Pre-Qualified Facility", register, "hfr_facility_id")).strip()
			if not register_fid:
				frappe.db.set_value(
					"CRM Pre-Qualified Facility", register, _fid_write_values(target, status), update_modified=False
				)
		fill = fill_facility_rows(mfl, target, sync_status=status)
		result["status"] = "already_linked"
		result["filled"] = fill["filled"]
		result["skipped"] = fill["skipped"]
		return result

	holders = facility_id_holders(target, mfl)
	if holders and not allow_shared:
		result["status"] = "in_use"
		result["holders"] = holders
		return result

	if register:
		frappe.db.set_value(
			"CRM Pre-Qualified Facility", register, _fid_write_values(target, status), update_modified=False
		)
	fill = fill_facility_rows(mfl, target, sync_status=status) if mfl else {"filled": 0, "skipped": 0, "deals": []}
	if deal_row:
		row_values = frappe.db.get_value(
			"CRM Deal Facility", deal_row, ["mfl_code", "hfr_facility_id", "parent"], as_dict=True
		)
		if row_values and not cstr(row_values.mfl_code).strip():
			existing = cstr(row_values.hfr_facility_id).strip()
			if existing and existing.casefold() != target.casefold():
				result["status"] = "different_fid"
				return result
			frappe.db.set_value("CRM Deal Facility", deal_row, _fid_write_values(target, status), update_modified=False)
			fill["filled"] += 1
			fill["deals"].append(row_values.parent)

	try:
		label = "owner lookup" if source == "hfr" else "manual entry"
		from crm.api._timeline import log_deal_event

		for deal in fill["deals"]:
			log_deal_event(deal, "Facility ID %s linked to MFL %s by %s (%s)" % (target, mfl, actor, label))
		if not fill["deals"] and register:
			frappe.get_doc(
				{
					"doctype": "Comment",
					"comment_type": "Info",
					"reference_doctype": "CRM Pre-Qualified Facility",
					"reference_name": register,
					"content": "Facility ID %s linked to MFL %s by %s (%s)" % (target, mfl, actor, label),
				}
			).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="CRM facility ID link audit")

	result["status"] = "linked"
	result["filled"] = fill["filled"]
	result["skipped"] = fill["skipped"]
	result["holders"] = holders
	return result
