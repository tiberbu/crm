from __future__ import annotations

import json
import hashlib
import hmac
import re
import time
from datetime import date
from urllib.parse import quote

import frappe
import requests
from frappe import _
from frappe.utils.file_lock import LockTimeoutError
from frappe.utils.synchronization import filelock

try:
	import jwt as pyjwt
except ImportError:
	pyjwt = None

_DOCTYPE = "CRM HFR Settings"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_settings():
	s = frappe.get_single(_DOCTYPE)
	if not s.hfr_enabled:
		frappe.throw(_("HFR integration is not enabled."), frappe.PermissionError)
	return s


def _generate_jwt(s):
	if pyjwt is None:
		frappe.throw(_("PyJWT is not installed. Run: pip install PyJWT"))
	password = s.get_password("hfr_password") or ""
	expiry = int(s.hfr_jwt_expiry or 20000)
	payload = {"key": s.hfr_username, "exp": int(time.time()) + expiry}
	return pyjwt.encode(payload, password, algorithm="HS256")


def _hfr_request(url, params):
	s = _get_settings()
	token = _generate_jwt(s)
	try:
		resp = requests.get(
			url,
			params=params,
			headers={
				"Authorization": "Bearer %s" % token,
				"Content-Type": "application/json",
				"Accept": "application/json",
			},
			timeout=30,
		)
		if resp.status_code == 400:
			try:
				body = resp.json()
			except ValueError:
				body = {}
			message = frappe.utils.cstr(body.get("message") if isinstance(body, dict) else "")
			if "organization with the" in message.casefold() and "not found" in message.casefold():
				return {"message": []}
		resp.raise_for_status()
	except requests.exceptions.Timeout:
		frappe.throw(_("HFR request timed out. Please try again."))
	except requests.exceptions.RequestException as exc:
		frappe.throw(_("HFR request failed: %s") % str(exc))
	return resp.json()


def _build_hfr_url(s):
	return "%s%s" % (s.hfr_url.rstrip("/"), s.hfr_fetch_path)


def _normalise_facility_list(data):
	"""Extract a list of facility dicts from varied HFR response shapes."""
	msg = data.get("message") or data.get("data") or []
	if isinstance(msg, dict):
		# Some endpoints wrap in {facilities: [...]}
		msg = msg.get("facilities") or msg.get("data") or [msg]
	if not isinstance(msg, list):
		msg = []
	return msg


def _map_facility_to_org_fields(f):
	"""Map a raw HFR facility dict to CRM Organization fieldnames."""
	county = f.get("county") or ""
	territory = None
	if county:
		territory = frappe.db.exists("CRM Territory", {"territory_name": county})

	return {
		"organization_name": f.get("facility_name"),
		# This field is used by the deployment API, whose tracking key is the
		# facility_fid. A generic HIE id is not interchangeable with a deployment FID.
		"hfr_facility_id": f.get("facility_fid"),
		"mfl_code": f.get("facility_mfl") or f.get("facility_code"),
		"facility_type": f.get("facility_type"),
		"facility_category": f.get("category"),
		"facility_level": f.get("kephl_level"),
		"facility_owner": f.get("facility_owner"),
		"facility_owner_type": f.get("facility_owner_type"),
		"regulatory_body": f.get("regulatory_body"),
		"registration_number": f.get("registration_number"),
		"board_registration_number": f.get("board_registration_number"),
		"operational_status": f.get("operational_status"),
		"kra_pin": f.get("kra_pin"),
		"hfr_county": county,
		"hfr_sub_county": f.get("sub_county"),
		"hfr_constituency": f.get("constituency"),
		"hfr_ward": f.get("ward"),
		"latitude": f.get("latitude"),
		"longitude": f.get("longitude"),
		"license_number": f.get("license_number"),
		"license_type": f.get("license_type"),
		"license_expiry": f.get("license_expiry"),
		"facility_standing": f.get("standing"),
		"open_whole_day": int(bool(f.get("open_whole_day"))) if "open_whole_day" in f else None,
		"open_weekends": int(bool(f.get("open_weekends"))) if "open_weekends" in f else None,
		"open_public_holidays": int(bool(f.get("open_public_holiday"))) if "open_public_holiday" in f else None,
		"open_late_night": int(bool(f.get("open_late_night"))) if "open_late_night" in f else None,
		"number_of_beds": f.get("number_of_beds"),
		"number_of_cots": f.get("number_of_cots"),
		"territory": territory,
		"hfr_sync_status": "HFR Verified",
	}


# ---------------------------------------------------------------------------
# Public whitelisted API
# ---------------------------------------------------------------------------


@frappe.whitelist()
def search_facility(query, search_by="mfl_code"):
	"""Return a list of HFR facility candidates matching query.

	The UAT HIE endpoint supports lookup by: mfl_code, registration_number,
	license_number, facility_fid. Free-text name search is not supported.
	"""
	param_map = {
		"mfl_code": "facility-code",
		"registration_number": "registration-number",
		"license_number": "license-number",
		"facility_fid": "facility-fid",
	}
	# Keep aliases accepted by older clients while making the registry identifiers explicit.
	param_map["fid"] = param_map["facility_fid"]
	if search_by not in param_map:
		frappe.throw(_("Invalid search_by value."))

	s = _get_settings()
	url = _build_hfr_url(s)
	data = _hfr_request(url, {param_map[search_by]: query})
	facilities = _normalise_facility_list(data)

	return [
		{
			# ``fid`` is retained for older clients, but it must remain the
			# deployment FID. A generic HIE identifier is not interchangeable.
			"fid": f.get("facility_fid"),
			"facility_fid": f.get("facility_fid"),
			"hie_id": f.get("hie_id"),
			"name": f.get("facility_name"),
			"mfl_code": f.get("facility_mfl") or f.get("facility_code"),
			"level": f.get("kephl_level"),
			"category": f.get("category"),
			"county": f.get("county"),
			"owner_type": f.get("facility_owner_type"),
			"operational_status": f.get("operational_status"),
		}
		for f in facilities
		if f.get("facility_fid") or f.get("hie_id")
	]


@frappe.whitelist()
def get_facility_detail(fid):
	"""Return HFR fields keyed to CRM Organization fieldnames for a given FID."""
	s = _get_settings()
	url = _build_hfr_url(s)
	data = _hfr_request(url, {"facility-fid": fid})
	facilities = _normalise_facility_list(data)
	f = facilities[0] if facilities else {}
	return _map_facility_to_org_fields(f)


@frappe.whitelist()
def resync_facility_row(doctype, docname, row_name):
	"""Fetch latest HFR data for a facility child row and overwrite all HFR-managed fields."""
	_allowed = ("CRM Organization", "CRM Lead", "CRM Deal")
	if doctype not in _allowed:
		frappe.throw(_("Invalid doctype."))

	parent = frappe.get_doc(doctype, docname)
	row = next((r for r in (parent.facilities or []) if r.name == row_name), None)
	if not row:
		frappe.throw(_("Facility row not found."))
	if not row.hfr_facility_id:
		frappe.throw(_("This facility row has no HFR Facility ID."))

	hfr_data = get_facility_detail(row.hfr_facility_id)

	_field_map = {
		"facility_name": "organization_name",
		"mfl_code": "mfl_code",
		"facility_type": "facility_type",
		"facility_category": "facility_category",
		"facility_level": "facility_level",
		"facility_owner": "facility_owner",
		"facility_owner_type": "facility_owner_type",
		"regulatory_body": "regulatory_body",
		"registration_number": "registration_number",
		"board_registration_number": "board_registration_number",
		"operational_status": "operational_status",
		"kra_pin": "kra_pin",
		"hfr_county": "hfr_county",
		"hfr_sub_county": "hfr_sub_county",
		"hfr_constituency": "hfr_constituency",
		"hfr_ward": "hfr_ward",
		"latitude": "latitude",
		"longitude": "longitude",
		"license_number": "license_number",
		"license_type": "license_type",
		"license_expiry": "license_expiry",
		"facility_standing": "facility_standing",
		"number_of_beds": "number_of_beds",
		"number_of_cots": "number_of_cots",
		"open_whole_day": "open_whole_day",
		"open_weekends": "open_weekends",
		"open_public_holidays": "open_public_holidays",
		"open_late_night": "open_late_night",
	}
	for row_field, data_field in _field_map.items():
		val = hfr_data.get(data_field)
		if val is not None:
			row.set(row_field, val)

	row.hfr_sync_status = "HFR Verified"
	row.hfr_last_synced = frappe.utils.now_datetime()
	parent.save()

	return {"updated_row": row_name, "hfr_facility_id": row.hfr_facility_id}


@frappe.whitelist()
def get_hfr_settings():
	"""Return non-sensitive HFR settings for the frontend."""
	s = frappe.get_single(_DOCTYPE)
	response = {"hfr_enabled": s.hfr_enabled}
	if not frappe.has_permission(_DOCTYPE, "read"):
		return response
	response.update({
		"hfr_enabled": s.hfr_enabled,
		"hfr_url": s.hfr_url,
		"hfr_fetch_path": s.hfr_fetch_path,
		"hfr_username": s.hfr_username,
		"hfr_jwt_expiry": s.hfr_jwt_expiry,
		"provisioning_submit_path": s.get("provisioning_submit_path") or "/v1/hmis/provisioning/facilities",
		"provisioning_status_path": s.get("provisioning_status_path")
			or "/v1/hmis/provisioning/facilities/{fid}/status",
		"provisioning_status_configured": bool(
			s.hfr_enabled and s.hfr_url and s.hfr_username and s.get_password("hfr_password")
		),
		"external_provisioning_url": s.get("external_provisioning_url") or "",
		"external_provisioning_key": s.get("external_provisioning_key") or "",
		"external_provisioning_secret_configured": bool(s.get_password("external_provisioning_secret")),
		"external_provisioning_configured": bool(
			s.get("external_provisioning_url")
			and s.get("external_provisioning_key")
			and s.get_password("external_provisioning_secret")
		),
	})
	return response


@frappe.whitelist(methods=["POST"])
def update_hfr_settings(settings):
	"""Persist HFR settings. Password only updated when provided."""
	frappe.only_for("System Manager")
	if isinstance(settings, str):
		settings = json.loads(settings)

	s = frappe.get_single(_DOCTYPE)
	s.hfr_enabled = settings.get("hfr_enabled", 0)
	s.hfr_url = settings.get("hfr_url") or ""
	s.hfr_fetch_path = settings.get("hfr_fetch_path") or "/v1/hfr/facilities"
	s.hfr_username = settings.get("hfr_username") or ""
	s.hfr_jwt_expiry = int(settings.get("hfr_jwt_expiry") or 20000)
	if settings.get("hfr_password"):
		s.hfr_password = settings["hfr_password"]
	s.provisioning_submit_path = settings.get("provisioning_submit_path") or "/v1/hmis/provisioning/facilities"
	s.provisioning_status_path = settings.get("provisioning_status_path") or "/v1/hmis/provisioning/facilities/{fid}/status"
	s.external_provisioning_url = frappe.utils.cstr(settings.get("external_provisioning_url") or "").strip().rstrip("/")
	s.external_provisioning_key = frappe.utils.cstr(settings.get("external_provisioning_key") or "").strip()
	if settings.get("external_provisioning_secret"):
		s.external_provisioning_secret = settings["external_provisioning_secret"]
	s.save()
	return {"success": True}


def _merge_facility_hfr_fallback(primary, fallback):
	"""Fill blank portal facility fields from its matching Deal Facility row."""
	primary = frappe._dict(primary or {})
	fallback = frappe._dict(fallback or {})
	for fieldname in (
		"hfr_facility_id", "facility_name", "facility_level", "registration_number",
		"license_number", "hfr_county", "hfr_sub_county",
	):
		if not primary.get(fieldname) and fallback.get(fieldname):
			primary[fieldname] = fallback[fieldname]
	return primary


@frappe.whitelist(methods=["GET", "POST"])
def get_provisioning_status(mfl_code):
	"""Return deployment progress for a facility in the signed-in user's portfolio.

	The route is called through the configured HIE API gateway with the existing
	Bearer JWT. Its documented status payload does not include service-unit
	inventory, so that field stays unavailable until the gateway contract provides it.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to view facility implementation status."), frappe.PermissionError)

	from crm.api.website_redirect import get_user_customer_names

	customers = get_user_customer_names(user)
	from crm.api.website_redirect import get_user_deal_names, get_user_lead_names

	deals = get_user_deal_names(user)
	leads = get_user_lead_names(user)
	mfl_code = frappe.utils.cstr(mfl_code or "").strip()
	if not mfl_code or not (customers or deals or leads):
		frappe.throw(_("Facility not found in your portfolio."), frappe.PermissionError)

	allowed = frappe.get_all(
		"CRM Facility Membership",
		filters={"customer": ["in", customers]},
		fields=["parent"],
		pluck="parent",
		ignore_permissions=True,
		limit_page_length=0,
	)
	facility = frappe.db.get_value(
		"CRM Pre-Qualified Facility",
		{"name": ["in", allowed], "mfl_code": mfl_code},
		["name", "hfr_facility_id", "facility_name", "keph_level", "registration_number", "license_number", "hfr_county", "hfr_sub_county"],
		as_dict=True,
	) if allowed else None
	deal_facility = None
	if deals:
		deal_fields = [
			field for field in (
				"hfr_facility_id", "facility_name", "facility_level", "registration_number", "license_number",
				"hfr_county", "hfr_sub_county", "cx_token_package_item", "cx_token_package_quantity",
			) if frappe.get_meta("CRM Deal Facility").has_field(field)
		]
		deal_rows = frappe.get_all(
			"CRM Deal Facility",
			filters={"parent": ["in", deals], "mfl_code": mfl_code},
			fields=deal_fields,
			limit=1,
			ignore_permissions=True,
		)
		if deal_rows:
			deal_facility = frappe._dict(deal_rows[0])
			if not facility:
				facility = frappe._dict(deal_rows[0])
			else:
				# The portal projects HFR values from the Deal Facility when the
				# linked Pre-Qualified Facility is incomplete. Apply the same
				# fallback here so status lookup uses the exact same deployment FID.
				facility = _merge_facility_hfr_fallback(facility, deal_facility)
	if not facility and leads:
		lead_rows = frappe.get_all(
			"CRM Lead Facility",
			filters={"parent": ["in", leads], "mfl_code": mfl_code},
			fields=["hfr_facility_id"],
			limit=1,
			ignore_permissions=True,
		)
		if lead_rows:
			facility = frappe._dict(hfr_facility_id=lead_rows[0].get("hfr_facility_id"))
	if not facility:
		frappe.throw(_("Facility not found in your portfolio."), frappe.PermissionError)

	if not facility.get("hfr_facility_id"):
		return {
			"configured": False,
			"status": "not_linked",
			"progress": None,
			"last_attempt": None,
			"service_units": None,
			"source": "hie_gateway",
			"message": _("An HFR Facility ID is required to look up HMIS implementation status."),
		}

	settings = frappe.get_single(_DOCTYPE)
	external_url = frappe.utils.cstr(settings.get("external_provisioning_url") or "").strip().rstrip("/")
	external_key = frappe.utils.cstr(settings.get("external_provisioning_key") or "").strip()
	external_secret = settings.get_password("external_provisioning_secret") if settings.get("external_provisioning_secret") else ""
	external_is_partial = bool(external_url or external_key or external_secret)
	if external_is_partial:
		if not (external_url and external_key and external_secret):
			return {
				"configured": False,
				"status": "not_configured",
				"progress": None,
				"last_attempt": None,
				"service_units": None,
				"source": "external_setup",
				"message": _("External HMIS setup access is incomplete. Ask your administrator to finish the service credentials."),
			}
		status = _get_external_provisioning_status(external_url, external_key, external_secret, facility.hfr_facility_id)
		if status.get("status") == "not_submitted":
			source = _get_external_provisioning_source(facility, deal_facility, mfl_code, deals)
			payload, missing_fields = _build_external_provisioning_payload(source)
			status = _auto_submit_external_provisioning(
				external_url,
				external_key,
				external_secret,
				facility.hfr_facility_id,
				status,
				payload,
				missing_fields,
			)
		return status

	if not settings.hfr_enabled:
		return {
			"configured": False,
			"status": "not_configured",
			"progress": None,
			"last_attempt": None,
			"service_units": None,
			"source": "hie_gateway",
			"message": _("HIE registry and implementation tracking are not configured yet."),
		}
	base_url = frappe.utils.cstr(settings.get("hfr_url") or "").strip().rstrip("/")
	path_template = frappe.utils.cstr(
		settings.get("provisioning_status_path") or "/v1/hmis/provisioning/facilities/{fid}/status"
	).strip()
	if not (base_url and path_template and settings.get("hfr_username") and settings.get_password("hfr_password")):
		return {
			"configured": False,
			"status": "not_configured",
			"progress": None,
			"last_attempt": None,
			"service_units": None,
			"source": "hie_gateway",
			"message": _("HMIS deployment tracking has not been connected yet."),
		}
	if not path_template.startswith("/") or path_template.startswith("//") or "://" in path_template or "{fid}" not in path_template:
		frappe.throw(_("Provisioning API path must be a relative path on the HIE gateway."), frappe.ValidationError)

	path = path_template.replace("{fid}", quote(frappe.utils.cstr(facility.hfr_facility_id), safe=""))
	url = base_url + path
	correlation_id = frappe.generate_hash(length=16)
	try:
		response = requests.get(
			url,
			headers={
				"Accept": "application/json",
				"Authorization": "Bearer %s" % _generate_jwt(settings),
				"X-Correlation-Id": correlation_id,
			},
			timeout=15,
		)
		if response.status_code == 404:
			body = _gateway_error(response)
			code = body.get("code") or ""
			if code == "FACILITY_SETUP_NOT_FOUND" or "No Facility Setup" in frappe.utils.cstr(body.get("message")):
				return {
					"configured": True,
					"status": "not_submitted",
					"progress": 0,
					"last_attempt": None,
					"service_units": None,
					"source": "hie_gateway",
					"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
					"message": _("HMIS setup has not started for this facility."),
				}
			return {
				"configured": True,
				"status": "route_not_provisioned",
				"progress": None,
				"last_attempt": None,
				"service_units": None,
				"source": "hie_gateway",
				"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
				"message": _("HIE implementation tracking is not available yet. Try again later."),
			}
		if response.status_code in (401, 403):
			return _provisioning_unavailable("auth", response.status_code, correlation_id)
		if response.status_code == 409:
			return {
				"configured": True,
				"status": "needs_support",
				"progress": None,
				"last_attempt": None,
				"service_units": None,
				"source": "hie_gateway",
				"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
				"message": _("HMIS status needs support review. Contact your implementation team."),
			}
		if response.status_code == 400:
			return {
				"configured": True,
				"status": "unavailable",
				"progress": None,
				"last_attempt": None,
				"service_units": None,
				"source": "hie_gateway",
				"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
				"message": _("The HMIS status request could not be processed. Contact support if this continues."),
			}
		response.raise_for_status()
		payload = _gateway_data(response)
		unit_rows = payload.get("service_units", payload.get("configured_service_units"))
		if isinstance(unit_rows, list):
			unit_names = [
				frappe.utils.cstr(
					row.get("service_unit_name") or row.get("name") or row.get("service_unit") or ""
					if isinstance(row, dict)
					else row
				).strip()
				for row in unit_rows
			]
			unit_names = [name for name in unit_names if name][:50]
			unit_count = payload.get("service_unit_count", len(unit_names))
		elif isinstance(unit_rows, (int, float)):
			unit_names = []
			unit_count = max(0, int(unit_rows))
		else:
			unit_names = []
			unit_count = None
		return {
			"configured": True,
			"status": frappe.utils.cstr(payload.get("status") or "Unknown"),
			"progress": frappe.utils.flt(payload.get("progress")) if payload.get("progress") is not None else None,
			"last_attempt": frappe.utils.cstr(payload.get("last_attempt") or "") or None,
			"message": _("Deployment status is synced from the HMIS setup service."),
			"service_units": unit_names,
			"source": "hie_gateway",
			"service_units_count": unit_count,
			"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
			"service_units_message": None if unit_count is not None else _("The HMIS setup status API does not report configured service units."),
			"site_status": frappe.utils.cstr(payload.get("site_status") or payload.get("site_url_status") or "") or None,
			"has_error": bool(payload.get("error")),
		}
	except requests.exceptions.RequestException as exc:
		return _provisioning_unavailable("network", None, correlation_id)
	except (ValueError, TypeError):
		frappe.log_error(title="HMIS provisioning response invalid", message="The HIE response was not valid JSON.")
		return _provisioning_unavailable("response", None, correlation_id)


def _get_external_provisioning_status(base_url, api_key, api_secret, fid):
	"""Read status directly from the setup service when its service account is configured."""
	base_url = base_url.rstrip("/")
	if not base_url.startswith("https://"):
		return {
			"configured": False,
			"status": "not_configured",
			"progress": None,
			"last_attempt": None,
			"service_units": None,
			"source": "external_setup",
			"message": _("External HMIS setup must use a secure HTTPS address."),
		}
	url = base_url + "/api/method/hmis_setup.api.external_provisioning.get_provision_status"
	try:
		response = requests.get(url, params={"fid": fid}, auth=(api_key, api_secret), headers={"Accept": "application/json"}, timeout=15)
		# Frappe maps ValidationError to HTTP 417; the setup service uses that
		# for the documented "no Facility Setup found" and duplicate responses.
		# Older/gateway implementations may return the same validation errors as 400.
		if response.status_code in (400, 417):
			body = _gateway_error(response)
			message = frappe.utils.cstr(body.get("message") or "")
			message_lower = message.casefold()
			if "no facility setup found" in message_lower:
				return {
					"configured": True,
					"status": "not_submitted",
					"progress": 0,
					"last_attempt": None,
					"service_units": None,
					"source": "external_setup",
					"message": _("HMIS setup has not started for this facility."),
				}
			if "multiple facility setup" in message_lower:
				return {
					"configured": True,
					"status": "needs_support",
					"progress": None,
					"last_attempt": None,
					"service_units": None,
					"source": "external_setup",
					"message": _("More than one setup record uses this facility ID. Contact the implementation team."),
				}
			return _external_provisioning_unavailable("bad_request", response.status_code)
		if response.status_code in (401, 403):
			failure = _gateway_error(response).get("message", "").casefold()
			kind = "method_not_published" if "not whitelisted" in failure else "auth"
			return _external_provisioning_unavailable(kind, response.status_code)
		if response.status_code == 404:
			return _external_provisioning_unavailable("method_not_published", response.status_code)
		if response.status_code != 200:
			return _external_provisioning_unavailable("service", response.status_code)
		payload = _gateway_data(response)
		status = frappe.utils.cstr(payload.get("status") or "Unknown")
		return {
			"configured": True,
			"status": status,
			"progress": frappe.utils.flt(payload.get("progress")) if payload.get("progress") is not None else None,
			"last_attempt": frappe.utils.cstr(payload.get("last_attempt") or "") or None,
			"has_error": bool(payload.get("error")),
			"service_units": None,
			"service_units_count": None,
			"site_status": None,
			"source": "external_setup",
			"message": _("Status synced from the HMIS setup service. Deployment is reviewed and started by the implementation team."),
			"service_units_message": _("The setup status API does not report configured service units."),
		}
	except requests.exceptions.RequestException:
		return _external_provisioning_unavailable("network", None)
	except (ValueError, TypeError):
		return _external_provisioning_unavailable("response", None)


def _get_external_provisioning_source(facility, deal_facility, mfl_code, deals):
	"""Resolve only server-owned CRM data that can support a facility draft.

	The accepted Opt-In signatory is the only approved administrator source. The
	TA maps licence to the HFR licence number or registration number. Billing
	model and expiry policy remain unresolved in the provisioning PRD.
	"""
	facility = frappe._dict(facility or {})
	deal_facility = frappe._dict(deal_facility or {})
	admin = {}
	purchased_package = None
	if deals:
		won_deals = frappe.get_all(
			"CRM Deal",
			filters={"name": ["in", deals], "status": "Won"},
			pluck="name",
			limit_page_length=0,
			ignore_permissions=True,
		)
		if won_deals:
			deal_meta = frappe.get_meta("CRM Deal Facility")
			package_fields = ["parent"] + [
				field for field in ("cx_token_package_item", "cx_token_package_quantity") if deal_meta.has_field(field)
			]
			package_rows = frappe.get_all(
				"CRM Deal Facility",
				filters={"parent": ["in", won_deals], "mfl_code": mfl_code},
				fields=package_fields,
				limit_page_length=0,
				ignore_permissions=True,
			)
			if len(package_rows) == 1 and package_rows[0].get("cx_token_package_item"):
				invoice_filters = {
					"crm_token_facility_mfl": mfl_code,
					"crm_token_package_item": package_rows[0]["cx_token_package_item"],
					"docstatus": 1,
					"outstanding_amount": 0,
				}
				if frappe.db.has_column("Sales Invoice", "crm_token_facility_mfl") and frappe.db.has_column("Sales Invoice", "crm_token_package_item"):
					if frappe.db.exists("Sales Invoice", invoice_filters):
						purchased_package = package_rows[0]
		admin_deals = [purchased_package.get("parent")] if purchased_package else deals
		rows = frappe.get_all(
			"CRM Opt-In Submission",
			filters={"deal": ["in", admin_deals], "status": "Processed"},
			fields=["name", "deal", "raw_json", "facility_signatory_name", "facility_signatory_email", "facility_signatory_phone"],
			limit_page_length=0,
			ignore_permissions=True,
		)
		matches = []
		for row in rows:
			try:
				data = json.loads(row.get("raw_json") or "{}")
			except (TypeError, ValueError):
				continue
			facilities = data.get("facilities") or data.get("pricing") or []
			if any(
				isinstance(item, dict)
				and frappe.utils.cstr(item.get("mfl_code") or "").strip().casefold() == mfl_code.casefold()
				for item in facilities
			):
				matches.append(row)
		if len(matches) == 1:
			admin = {
				"admin_name": matches[0].get("facility_signatory_name"),
				"admin_email": matches[0].get("facility_signatory_email"),
				"admin_mobile": matches[0].get("facility_signatory_phone"),
			}
	return {
		"fid": facility.get("hfr_facility_id"),
		"licence": facility.get("license_number") or facility.get("registration_number"),
		"facility_name": facility.get("facility_name"),
		"facility_level": facility.get("keph_level") or facility.get("facility_level"),
		"county": facility.get("hfr_county"),
		"sub_county": facility.get("hfr_sub_county"),
		"tokens_awarded": purchased_package.get("cx_token_package_quantity") if purchased_package else None,
		**admin,
		# Billing model and expiry sources remain unresolved in PRD §12.
		"deal_won_package_purchase_verified": bool(purchased_package),
	}


def _build_external_provisioning_payload(source):
	"""Validate the exact TA-required payload without guessing missing policy data."""
	source = source or {}
	payload = {}
	for fieldname in (
		"fid",
		"licence",
		"tokens_awarded",
		"token_expiry_date",
		"admin_email",
		"admin_name",
		"billing_model",
		"admin_mobile",
	):
		value = source.get(fieldname)
		if isinstance(value, str):
			value = value.strip()
			if fieldname == "admin_email":
				value = value.lower()
		if value not in (None, ""):
			payload[fieldname] = value
	if source.get("billing_model") == "License" and source.get("license_expiry_date"):
		payload["license_expiry_date"] = source["license_expiry_date"]
	for fieldname in ("facility_name", "facility_level", "county", "sub_county"):
		value = source.get(fieldname)
		if isinstance(value, str):
			value = value.strip()
		if value not in (None, ""):
			payload[fieldname] = value

	missing = [
		fieldname
		for fieldname in (
			"fid",
			"licence",
			"tokens_awarded",
			"token_expiry_date",
			"admin_email",
			"admin_name",
			"billing_model",
			"admin_mobile",
		)
		if fieldname not in payload
	]
	if source.get("deal_won_package_purchase_verified") is not True:
		missing.append("won deal with purchased facility package")
	if payload.get("billing_model") == "License" and not payload.get("license_expiry_date"):
		missing.append("license_expiry_date")

	if payload.get("fid") and not re.fullmatch(r"FID-\d{2}-[\w-]+", frappe.utils.cstr(payload["fid"]), flags=re.IGNORECASE):
		missing.append("valid fid")
	if payload.get("admin_email") and "@" not in frappe.utils.cstr(payload["admin_email"]):
		missing.append("valid admin_email")
	if payload.get("billing_model") and payload["billing_model"] not in ("License", "Token"):
		missing.append("valid billing_model")
	for date_field in ("token_expiry_date", "license_expiry_date"):
		if payload.get(date_field):
			try:
				if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", frappe.utils.cstr(payload[date_field])):
					raise ValueError
				date.fromisoformat(frappe.utils.cstr(payload[date_field]))
			except ValueError:
				missing.append("valid " + date_field)
	if "tokens_awarded" in payload:
		try:
			payload["tokens_awarded"] = int(payload["tokens_awarded"])
			if payload["tokens_awarded"] < 0:
				missing.append("non-negative tokens_awarded")
		except (TypeError, ValueError):
			missing.append("integer tokens_awarded")
	return payload, list(dict.fromkeys(missing))


def _auto_submit_external_provisioning(base_url, api_key, api_secret, fid, status, payload, missing_fields):
	try:
		return _auto_submit_external_provisioning_impl(
			base_url, api_key, api_secret, fid, status, payload, missing_fields
		)
	except LockTimeoutError:
		status["submission"] = {
			"state": "unknown",
			"retryable": True,
			"retry_mode": "status_check",
			"message": _("Another request is checking or creating this setup. Refresh status shortly; CRM will check for an existing draft before any submission."),
		}
		return status


def _auto_submit_external_provisioning_impl(base_url, api_key, api_secret, fid, status, payload, missing_fields):
	"""Create one draft after an authoritative missing-status check.

	The FID lock serializes portal retries. Before every POST we GET status again;
	ambiguous POST outcomes are remembered and never automatically reposted because
	the TA endpoint does not implement idempotency. A retry after an ambiguous result
	means status-check only. Support must verify the upstream record before clearing
	the cached attempt state to permit a new POST.
	"""
	if missing_fields:
		status["submission"] = {
			"state": "blocked",
			"retryable": False,
			"missing_fields": missing_fields,
			"message": _(
				"Automatic setup could not start because approved CRM values are missing for: {0}. Update the facility contract/package and verified administrator details, then refresh."
			).format(", ".join(missing_fields)),
		}
		return status

	lock_key = hashlib.sha256(frappe.utils.cstr(fid).encode()).hexdigest()[:32]
	attempt_key = "crm_external_provisioning_attempt:%s" % lock_key
	# This is a keyed request identity for cache deduplication, not password storage.
	# HMAC also prevents payload contact details from being recoverable from the cache.
	encryption_key = frappe.conf.get("encryption_key")
	if not encryption_key:
		frappe.throw(_("The site encryption key is required to protect provisioning retry state."))
	canonical_request = json.dumps(
		{"payload": payload, "api_key": api_key}, sort_keys=True, separators=(",", ":")
	)
	payload_fingerprint = hmac.new(
		frappe.utils.cstr(encryption_key).encode(), canonical_request.encode(), hashlib.sha512
	).hexdigest()
	with filelock("crm_external_provisioning_%s" % lock_key, timeout=60):
		current = _get_external_provisioning_status(base_url, api_key, api_secret, fid)
		if current.get("status") != "not_submitted":
			current["submission"] = {
				"state": "already_exists",
				"retryable": False,
				"message": _("An HMIS setup record already exists. Its status has been refreshed."),
			}
			return current

		attempt = frappe.cache().get_value(attempt_key)
		if attempt == "rejected:%s" % payload_fingerprint:
			status["submission"] = {
				"state": "error",
				"retryable": False,
				"message": _("The deployment service rejected these same facility details. Correct the contract or administrator data before refreshing."),
			}
			return status
		if attempt in ("posting", "unknown", "accepted"):
			status["submission"] = {
				"state": "unknown",
				"retryable": True,
				"retry_mode": "status_check",
				"message": _(
					"The prior submission may have reached the deployment service. CRM checked again and found no visible draft, so it will not risk creating a duplicate. Ask support to verify the FID before retrying."
				),
			}
			return status

		frappe.cache().set_value(attempt_key, "posting", expires_in_sec=31536000)
		url = base_url.rstrip("/") + "/api/method/hmis_setup.api.external_provisioning.provision_facility"
		correlation_id = frappe.generate_hash(length=16)
		try:
			response = requests.post(
				url,
				auth=(api_key, api_secret),
				json=payload,
				headers={"Accept": "application/json", "Content-Type": "application/json", "X-Correlation-Id": correlation_id},
				timeout=60,
			)
		except requests.exceptions.RequestException:
			frappe.cache().set_value(attempt_key, "unknown", expires_in_sec=31536000)
			status["submission"] = {
				"state": "unknown",
				"retryable": True,
				"retry_mode": "status_check",
				"message": _("The deployment service did not confirm the request. CRM will check status before any retry to avoid duplicate drafts."),
				"correlation_id": correlation_id,
			}
			return status

		if response.status_code not in (200, 202):
			body = _gateway_error(response)
			if response.status_code >= 500 or response.status_code in (408, 429):
				frappe.cache().set_value(attempt_key, "unknown", expires_in_sec=31536000)
				state = "unknown"
				retryable = True
			else:
				frappe.cache().set_value(attempt_key, "rejected:%s" % payload_fingerprint, expires_in_sec=31536000)
				state = "error"
				retryable = False
			status["submission"] = {
				"state": state,
				"retryable": retryable,
				"retry_mode": "status_check" if retryable else None,
				"message": _external_submit_error(response.status_code, body),
				"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
			}
			return status

		body = _gateway_data(response)
		if body.get("accepted") is not True:
			frappe.cache().set_value(attempt_key, "unknown", expires_in_sec=31536000)
			status["submission"] = {
				"state": "unknown",
				"retryable": True,
				"retry_mode": "status_check",
				"message": _("The deployment service returned an unclear response. CRM will check status before any retry."),
				"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
			}
			return status

		frappe.cache().set_value(attempt_key, "accepted", expires_in_sec=31536000)
		refreshed = _get_external_provisioning_status(base_url, api_key, api_secret, fid)
		if refreshed.get("status") == "not_submitted":
			refreshed.update({"status": body.get("status") or "Draft", "progress": 0})
		refreshed["submission"] = {
			"state": "created",
			"retryable": False,
			"facility_setup": body.get("facility_setup"),
			"message": body.get("message") or _("The HMIS setup draft was created and status has been refreshed."),
			"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
		}
		return refreshed


def _external_submit_error(status_code, body):
	"""Map TA submission errors to safe, actionable portal copy."""
	if status_code in (401, 403):
		return _("The deployment service denied setup submission. Ask your administrator to check the service account permissions.")
	if status_code in (400, 417):
		message = body.get("message") if isinstance(body, dict) else None
		if isinstance(message, str):
			message = " ".join(message.split())
			# TA validation errors identify missing or invalid fields. Return those
			# concise messages; suppress tracebacks and internal server details.
			if (
				message
				and len(message) <= 300
				and "traceback" not in message.casefold()
				and "file \"" not in message.casefold()
				and not any(char in message for char in "{}[]")
			):
				return _("The deployment service rejected the facility details: {0}").format(message)
		return _("The deployment service rejected the facility details. Review the required contract and facility fields, then retry.")
	if status_code == 404:
		return _("The deployment submission method is not available on the service. Ask your administrator to check the endpoint configuration.")
	if status_code == 429:
		return _("The deployment service is rate limiting requests. Wait briefly and refresh to retry safely.")
	if status_code >= 500:
		return _("The deployment service could not confirm setup creation. CRM will check status before retrying.")
	return _("The deployment service rejected the request. Contact support with the status code {0}.").format(status_code)


def _external_provisioning_unavailable(kind, status_code):
	if kind == "method_not_published":
		error_code = "method_not_published"
		error_title = _("Connected, but status access is not enabled")
		message = _(
			"The deployment service responded, but has not enabled its status method for this portal yet. Contact your implementation team."
		)
		retryable = False
	elif kind == "auth":
		error_code = "access_denied"
		error_title = _("The deployment service denied status access")
		message = _(
			"The deployment service is reachable, but the configured service account cannot read this status. Contact your administrator."
		)
		retryable = False
	elif kind == "network":
		error_code = "network_error"
		error_title = _("Could not reach the deployment service")
		message = _("Check your connection and try refreshing the status.")
		retryable = True
	elif kind == "bad_request":
		error_code = "status_request_rejected"
		error_title = _("The deployment service could not find a clear status")
		message = _("Ask your implementation team to check this facility’s setup record.")
		retryable = False
	else:
		error_code = "service_error"
		error_title = _("The deployment service could not return status")
		message = _("Try refreshing shortly. Your billing and facility records are unaffected.")
		retryable = True
	frappe.log_error(
		title="External HMIS provisioning API unavailable",
		message="kind=%s status=%s" % (kind, status_code or "unknown"),
	)
	return {
		"configured": True,
		"status": "unavailable",
		"progress": None,
		"last_attempt": None,
		"service_units": None,
		"source": "external_setup",
		"error_code": error_code,
		"error_title": error_title,
		"retryable": retryable,
		"connection_reached": kind in ("method_not_published", "auth", "bad_request"),
		"message": message,
	}


def _gateway_data(response):
	"""Unwrap common HIE/APISIX and Frappe response envelopes."""
	body = response.json()
	if not isinstance(body, dict):
		return {}
	data = body.get("data")
	if isinstance(data, dict):
		return data
	message = body.get("message")
	if isinstance(message, dict):
		return message.get("data") if isinstance(message.get("data"), dict) else message
	return body


def _gateway_error(response):
	try:
		body = response.json()
		error = body.get("error") if isinstance(body, dict) else None
		if isinstance(error, dict):
			return error
		message = body.get("message") if isinstance(body, dict) else None
		if not isinstance(message, str) and isinstance(body, dict):
			message = body.get("exception") or body.get("exc")
		return {"message": message if isinstance(message, str) else ""}
	except (ValueError, TypeError):
		return {}


def _provisioning_unavailable(kind, status_code, correlation_id=None):
	"""Return a safe portal state while the HIE provisioning API is unavailable."""
	if kind == "auth":
		error_code = "access_denied"
		error_title = _("The HIE gateway denied status access")
		message = _(
			"The gateway responded, but did not authorize this status request. Contact your support team."
		)
		retryable = False
	else:
		error_code = "network_error" if kind == "network" else "service_error"
		error_title = _("Could not refresh implementation status")
		message = _("Try refreshing shortly. Your billing and facility records are unaffected.")
		retryable = True
	frappe.log_error(
		title="HMIS provisioning API unavailable",
		message="kind=%s status=%s correlation_id=%s" % (kind, status_code or "unknown", correlation_id or "unknown"),
	)
	return {
		"configured": True,
		"status": "unavailable",
		"progress": None,
		"last_attempt": None,
		"service_units": None,
		"source": "hie_gateway",
		"error_code": error_code,
		"error_title": error_title,
		"retryable": retryable,
		"connection_reached": kind == "auth",
		"correlation_id": correlation_id,
		"message": message,
	}
