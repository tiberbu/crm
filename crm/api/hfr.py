from __future__ import annotations

import json
import time
from urllib.parse import quote

import frappe
import requests
from frappe import _

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
			json=params,
			headers={
				"Authorization": "Bearer %s" % token,
				"Content-Type": "application/json",
			},
			timeout=30,
		)
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
		"hfr_facility_id": f.get("facility_fid") or f.get("hie_id"),
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
		"open_whole_day": int(bool(f.get("open_whole_day", 0))),
		"open_weekends": int(bool(f.get("open_weekends", 0))),
		"open_public_holidays": int(bool(f.get("open_public_holiday", 0))),
		"open_late_night": int(bool(f.get("open_late_night", 0))),
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
			"fid": f.get("facility_fid") or f.get("hie_id"),
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
		"operational_status": "operational_status",
		"hfr_county": "hfr_county",
		"hfr_sub_county": "hfr_sub_county",
		"hfr_ward": "hfr_ward",
		"latitude": "latitude",
		"longitude": "longitude",
		"license_number": "license_number",
		"license_expiry": "license_expiry",
		"facility_standing": "facility_standing",
		"number_of_beds": "number_of_beds",
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
		["name", "hfr_facility_id"],
		as_dict=True,
	) if allowed else None
	if not facility and deals:
		deal_rows = frappe.get_all(
			"CRM Deal Facility",
			filters={"parent": ["in", deals], "mfl_code": mfl_code},
			fields=["hfr_facility_id"],
			limit=1,
			ignore_permissions=True,
		)
		if deal_rows:
			facility = frappe._dict(hfr_facility_id=deal_rows[0].get("hfr_facility_id"))
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
		return _get_external_provisioning_status(external_url, external_key, external_secret, facility.hfr_facility_id)

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
		if response.status_code == 400:
			body = _gateway_error(response)
			message = frappe.utils.cstr(body.get("message") or "")
			if "No Facility Setup found" in message:
				return {
					"configured": True,
					"status": "not_submitted",
					"progress": 0,
					"last_attempt": None,
					"service_units": None,
					"source": "external_setup",
					"message": _("HMIS setup has not started for this facility."),
				}
			if "Multiple Facility Setup" in message:
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
		response.raise_for_status()
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
