from __future__ import annotations

import json
import hashlib
import hmac
import math
import re
import time
from urllib.parse import quote, urlparse

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit
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
			s.hfr_enabled and s.hfr_url and s.hfr_username and s.get_password("hfr_password", raise_exception=False)
		),
		"external_provisioning_url": s.get("external_provisioning_url") or "",
		"external_provisioning_key": s.get("external_provisioning_key") or "",
		"external_provisioning_secret_configured": bool(s.get_password("external_provisioning_secret", raise_exception=False)),
		"external_provisioning_configured": bool(
			s.get("external_provisioning_url")
			and s.get("external_provisioning_key")
			and s.get_password("external_provisioning_secret", raise_exception=False)
		),
		"provisioning_typical_minutes": _typical_setup_minutes(s),
		"external_provisioning_manual_review": frappe.utils.cint(s.get("external_provisioning_manual_review")),
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
	if "provisioning_typical_minutes" in settings:
		s.provisioning_typical_minutes = max(0, frappe.utils.cint(settings.get("provisioning_typical_minutes")))
	if "external_provisioning_manual_review" in settings:
		s.external_provisioning_manual_review = 1 if frappe.utils.cint(settings.get("external_provisioning_manual_review")) else 0
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


def _unique_facility_projection(rows, fields):
	"""Project only values that agree across all matching authorized facility rows."""
	projection = {}
	for fieldname in fields:
		values = {}
		for row in rows:
			value = row.get(fieldname)
			if value not in (None, ""):
				values.setdefault(frappe.utils.cstr(value).strip(), value)
		if len(values) == 1:
			projection[fieldname] = next(iter(values.values()))
	return projection


_DEFAULT_TYPICAL_SETUP_MINUTES = 60
# TA status strings are not an enumerated contract; match known wordings and treat
# any other non-error status on an existing setup record as deployment in progress.
_LIVE_STATUSES = {"deployed", "live", "active", "completed", "complete", "success", "successful", "ready", "provisioned"}
_ERROR_STATUSES = {"error", "failed", "failure", "cancelled", "canceled"}
_QUEUED_STATUSES = {"draft", "pending", "queued", "submitted", "scheduled", "awaiting deployment", "approved"}
_CONFIGURING_STATUSES = {"configuring", "setting up", "post deploy", "finalizing", "finalising"}
_JOURNEY_POLL_PHASES = {"preparing", "queued", "deploying", "configuring"}
_JOURNEY_STEP_INDEX = {"preparing": 0, "queued": 1, "deploying": 1, "configuring": 2, "live": 4}


def _auto_deploy_enabled(settings=None):
	"""CRM asks the setup service to deploy at once unless manual review is switched on."""
	return not frappe.utils.cint((settings or frappe.get_single(_DOCTYPE)).get("external_provisioning_manual_review"))


def _typical_setup_minutes(settings=None):
	"""Configured usual setup duration; 0 hides the typical estimate."""
	value = (settings or frappe.get_single(_DOCTYPE)).get("provisioning_typical_minutes")
	return _DEFAULT_TYPICAL_SETUP_MINUTES if value in (None, "") else max(0, frappe.utils.cint(value))


def _reported_setup_details(payload):
	"""Keep optional TA status fields the portal can show; ignore anything else."""
	aliases = {
		"site_url": ("site_url", "site", "site_name", "url", "domain"),
		"login_url": ("login_url",),
		"admin_username": ("admin_username", "admin_email", "username"),
		"eta_minutes": ("eta_minutes", "estimated_minutes_remaining", "minutes_remaining"),
		"estimated_completion": ("estimated_completion", "eta"),
		"started_at": ("started_at", "deployment_started", "deployment_started_at"),
		"deployed_on": ("deployed_on", "completed_at"),
		"setup_id": ("setup_id", "facility_setup"),
	}
	reported = {}
	for key, names in aliases.items():
		for name in names:
			value = payload.get(name)
			if isinstance(value, (int, float)) and not isinstance(value, bool) and key == "eta_minutes":
				reported[key] = value
				break
			if isinstance(value, str) and value.strip():
				reported[key] = value.strip()[:500]
				break
	# Setup service v2.x: the site address is under `target` and the owner
	# administrator sign-in under `login`.
	target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
	login = payload.get("login") if isinstance(payload.get("login"), dict) else None
	if "site_url" not in reported:
		# v2.0: login.url is the owner's sign-in address and target.frontend_url the
		# public site; target.url is the Frappe backend, so it is only the last resort.
		for value in ((login or {}).get("url"), target.get("frontend_url"), target.get("url")):
			if isinstance(value, str) and value.strip():
				reported["site_url"] = value.strip()[:500]
				break
	if login is not None:
		owner_login = _owner_login(login)
		reported["owner_login"] = owner_login
		if owner_login["email"]:
			reported["admin_username"] = owner_login["email"]
	# v2.0: `completion.fully_provisioned` is the authoritative "ready" flag.
	completion = payload.get("completion")
	if isinstance(completion, dict):
		reported["completion"] = {
			key: completion.get(key) is True
			for key in ("deployment_complete", "owner_user_complete", "fully_provisioned")
		}
	# v2.0: per-step deployment tracking. Only names and states are kept; step
	# error text can carry internal detail and stays with System Managers.
	steps = payload.get("steps")
	if isinstance(steps, list):
		reported["deploy_steps"] = [
			{
				"name": frappe.utils.cstr(step.get("name")).strip()[:120],
				"status": frappe.utils.cstr(step.get("status")).strip().casefold(),
			}
			for step in steps[:50]
			if isinstance(step, dict) and frappe.utils.cstr(step.get("name")).strip()
		]
	return reported


def _deploy_step_label(name):
	"""Plain wording for the setup service's deployment step names; unknown names pass through."""
	labels = {
		"role profiles": _("Preparing staff roles"),
		"company": _("Creating your facility"),
		"owner user (retry)": _("Creating your administrator account"),
		"warehouses": _("Setting up stores"),
		"practitioners": _("Adding practitioners"),
		"service units": _("Creating service units"),
		"laboratories": _("Setting up laboratories"),
		"service unit access": _("Granting service unit access"),
		"company settings": _("Applying facility settings"),
		"final configuration": _("Finishing configuration"),
		"api gateway credentials": _("Connecting the HMIS gateway"),
		"verification pass": _("Running final checks"),
	}
	return labels.get(" ".join(name.casefold().split()), name)


def _deploy_step(steps):
	"""Pick the failed, running or next deployment step from the reported step list."""
	steps = steps or []
	if not steps:
		return None
	for state, matches in (
		("failed", lambda value: value == "failed"),
		("running", lambda value: value == "running"),
		("pending", lambda value: value not in ("done", "skipped")),
	):
		index = next((i for i, step in enumerate(steps) if matches(step["status"])), None)
		if index is not None:
			name = steps[index]["name"]
			return {"index": index + 1, "total": len(steps), "name": name, "label": _deploy_step_label(name), "state": state}
	return None


def _is_owner_user_step(name):
	return frappe.utils.cstr(name).casefold().startswith("owner user")


_OWNER_LOGIN_READY = {"created", "activated", "skipped"}


def _owner_login(login):
	"""Summarize the setup service's owner sign-in block; the password itself never leaves here.

	Only whether a temporary password is on offer is kept. The password is read
	again, server to server, by `reveal_hmis_owner_password` when the owner asks.
	"""
	status = frappe.utils.cstr(login.get("status") or "").strip()
	password = login.get("password")
	return {
		"email": frappe.utils.cstr(login.get("email") or "").strip().lower()[:254] or None,
		"status": status.casefold() or None,
		"email_sent": bool(login.get("email_sent")),
		"password_available": isinstance(password, str) and bool(password),
	}


def _safe_site_url(value):
	"""Return an https URL with a host and no embedded credentials, or None."""
	value = frappe.utils.cstr(value or "").strip()
	if not value:
		return None
	if "://" not in value and re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(:\d+)?(/[^\s]*)?", value):
		value = "https://" + value
	parsed = urlparse(value)
	if parsed.scheme != "https" or not parsed.hostname or "@" in parsed.netloc or re.search(r"\s", value):
		return None
	return value.rstrip("/")


def _parse_status_time(value):
	try:
		return frappe.utils.get_datetime(value) if value else None
	except Exception:
		return None


def _format_minutes(minutes):
	minutes = max(1, int(minutes))
	if minutes < 60:
		return _("{0} min").format(minutes)
	hours, rest = divmod(minutes, 60)
	return _("{0} h {1} min").format(hours, rest) if rest else _("{0} h").format(hours)


def _journey_status_key(status):
	return " ".join(frappe.utils.cstr((status or {}).get("status") or "").replace("_", " ").replace("-", " ").casefold().split())


def _journey_phase(status):
	"""Map a raw CRM/TA status response to one customer-facing setup phase."""
	status = status or {}
	key = _journey_status_key(status)
	submission = (status.get("submission") or {}).get("state")
	if submission == "blocked":
		return "blocked"
	if submission == "error":
		return "needs_attention"
	if key in ("not linked", "not configured", "unavailable"):
		return key.replace(" ", "_")
	if key == "route not provisioned":
		return "not_configured"
	if key == "needs support" or key in _ERROR_STATUSES or status.get("has_error"):
		return "needs_attention"
	completion = (status.get("reported") or {}).get("completion")
	if completion is not None:
		# v2.0: ready only when both the deployment and the owner-login tracks are
		# complete; progress 100 or "Deployed" alone is not enough.
		if completion.get("fully_provisioned"):
			return "live"
		if key in _LIVE_STATUSES or completion.get("deployment_complete"):
			return "configuring"
	if key in _LIVE_STATUSES:
		# v2.x: the owner login is created asynchronously, so a deployed site is only
		# usable once it is Created/Activated (Skipped = no email was recorded). A
		# service without a login block keeps the older Deployed-means-live rule.
		owner_status = ((status.get("reported") or {}).get("owner_login") or {"status": "created"}).get("status")
		if owner_status == "failed":
			return "needs_attention"
		return "live" if owner_status in _OWNER_LOGIN_READY else "configuring"
	if key == "not submitted" or submission == "unknown":
		return "preparing"
	if key in _QUEUED_STATUSES or not key:
		return "queued"
	if key in _CONFIGURING_STATUSES:
		return "configuring"
	return "deploying"


def _journey_estimate(phase, status, typical_minutes, now):
	"""Pick the best-supported wait estimate: TA ETA, then progress, then typical time."""
	if phase not in _JOURNEY_POLL_PHASES:
		return None
	reported = status.get("reported") or {}
	eta = reported.get("eta_minutes")
	if isinstance(eta, (int, float)) and eta > 0:
		minutes = math.ceil(eta)
		return {"minutes": minutes, "source": "service", "overdue": False,
			"label": _("About {0} remaining, reported by the setup service").format(_format_minutes(minutes))}
	completion = _parse_status_time(reported.get("estimated_completion"))
	if completion and completion > now:
		minutes = math.ceil((completion - now).total_seconds() / 60)
		return {"minutes": minutes, "source": "service", "overdue": False,
			"label": _("About {0} remaining, reported by the setup service").format(_format_minutes(minutes))}
	started = _parse_status_time(reported.get("started_at") or status.get("last_attempt"))
	elapsed = (now - started).total_seconds() / 60 if started and started <= now else None
	progress = status.get("progress")
	if elapsed and isinstance(progress, (int, float)) and 0 < progress < 100:
		minutes = math.ceil(elapsed * (100 - progress) / progress)
		return {"minutes": minutes, "source": "progress", "overdue": False,
			"label": _("About {0} remaining, based on progress so far").format(_format_minutes(minutes))}
	if not typical_minutes:
		return None
	if elapsed is not None and elapsed >= typical_minutes:
		return {"minutes": None, "source": "typical", "overdue": True,
			"label": _("Taking longer than the usual {0}. This page keeps checking for you.").format(_format_minutes(typical_minutes))}
	minutes = math.ceil(typical_minutes - elapsed) if elapsed is not None else typical_minutes
	return {"minutes": minutes, "source": "typical", "overdue": False,
		"label": _("Usually ready within about {0}").format(_format_minutes(minutes))}


def _provisioning_journey(status, typical_minutes=_DEFAULT_TYPICAL_SETUP_MINUTES, admin_contact=None, now=None):
	"""Normalize status into the setup journey the facility portal renders.

	Pure: everything comes from the status response, settings and the verified
	admin contact. Site and sign-in details are shown only when TA reports them.
	"""
	status = status or {}
	now = now or frappe.utils.now_datetime()
	phase = _journey_phase(status)
	submission = status.get("submission") or {}
	reported = status.get("reported") or {}
	raw_status = frappe.utils.cstr(status.get("status") or "").strip()
	copy = {
		"preparing": (_("Preparing your HMIS setup request"),
			_("Your facility details are being sent to the HMIS setup service. This usually takes under a minute.")),
		"queued": (_("Setup request received"),
			_("The HMIS setup service has your facility details. Deployment starts once the implementation team releases it; this page updates automatically.")),
		"deploying": (_("Deploying your HMIS site"),
			_("Your HMIS site is being deployed. You can keep using the portal; this page updates automatically.")),
		"configuring": (_("Configuring your HMIS site"),
			_("Deployment is finished. Facility settings and your administrator account are being configured.")),
		"live": (_("Your HMIS site is ready"), _("Sign in with the facility administrator account below.")),
		# The blocker itself (missing fields) is shown once, in the submission panel.
		"blocked": (_("Setup needs information"),
			_("CRM has not sent your setup request because some required facility details are missing.")),
		"needs_attention": (_("Setup needs attention"), submission.get("message")
			or _("The implementation team needs to review the latest deployment attempt. Contact Network Support if this does not change.")),
		"unavailable": (status.get("error_title") or _("Status unavailable"), status.get("message")
			or _("The setup service could not return the latest status. Try again shortly.")),
		"not_linked": (_("HFR Facility ID needed"), status.get("message")
			or _("A verified HFR Facility ID is required before HMIS setup can start.")),
		"not_configured": (_("Setup tracking not connected"), status.get("message")
			or _("HMIS setup tracking has not been connected yet.")),
	}
	headline, detail = copy[phase]
	label = {
		"preparing": _("Preparing setup"),
		"queued": _("Request received"),
		"deploying": _("Deploying"),
		"configuring": _("Configuring"),
		"live": _("Live"),
		"blocked": _("Setup needs information"),
		"needs_attention": _("Needs attention"),
	}.get(phase)
	if phase == "queued" and _journey_status_key(status) == "approved":
		label = _("Approved")
		headline = _("Approved for deployment")
		detail = _("The implementation team has approved your setup. Deployment to your HMIS site starts next; this page checks again automatically.")
	elif phase == "queued" and (submission.get("deploy_queued") is False or status.get("deploy_not_queued")):
		# Auto-deploy was requested but the setup service could not queue it.
		detail = _("The HMIS setup service has your facility details, but deployment did not start automatically. The implementation team will start it; this page updates automatically.")
	elif phase == "queued" and status.get("auto_deploy"):
		detail = _("The HMIS setup service has your facility details. Deployment starts automatically within a few minutes; this page updates automatically.")
	if phase == "deploying" and raw_status and _journey_status_key(status) not in ("deploying", "in progress", "provisioning"):
		detail = _("The setup service reports “{0}”. This page updates automatically.").format(raw_status)
	owner_login = reported.get("owner_login") or {}
	owner_failed = (
		owner_login.get("status") == "failed"
		or status.get("owner_user_failed")
		or any(step["status"] == "failed" and _is_owner_user_step(step["name"]) for step in reported.get("deploy_steps") or [])
	)
	completion = reported.get("completion") or {}
	if phase == "configuring" and (_journey_status_key(status) in _LIVE_STATUSES or completion.get("deployment_complete")):
		headline = _("Creating your administrator account")
		detail = _("Your HMIS site is deployed. The administrator sign-in is being created; this page updates automatically.")
	if phase == "needs_attention" and not submission.get("state"):
		if owner_failed:
			headline = _("Administrator account needs attention")
			detail = _("The HMIS site could not create the administrator sign-in yet. The setup service retries it on the next deployment; contact Network Support if this does not change.")
		elif status.get("instance_blocked"):
			headline = _("HMIS server paused")
			detail = _("Deployment is on hold because the HMIS server for your facility is paused for maintenance. The implementation team restarts it once the server is back; contact Network Support if this does not change.")
		elif _journey_status_key(status) in ("cancelled", "canceled"):
			label = _("Cancelled")
			headline = _("Setup was cancelled")
			detail = _("The implementation team cancelled this HMIS setup. Contact Network Support to start it again.")

	# v2.0 step tracking: name the step that is running, or where deployment stopped.
	deploy_step = _deploy_step(reported.get("deploy_steps"))
	if deploy_step:
		if phase in ("deploying", "configuring") and deploy_step["state"] != "failed":
			deploy_step["text"] = _("Step {0} of {1} · {2}").format(deploy_step["index"], deploy_step["total"], deploy_step["label"])
		elif phase == "needs_attention" and deploy_step["state"] == "failed" and not submission.get("state"):
			deploy_step["text"] = _("Stopped at step {0} of {1} · {2}").format(deploy_step["index"], deploy_step["total"], deploy_step["label"])
		else:
			deploy_step = None

	steps = []
	if phase in _JOURNEY_STEP_INDEX or phase in ("blocked", "needs_attention"):
		labels = (
			("request", _("Setup request received")),
			("deploy", _("Deploying HMIS site")),
			("configure", _("Configuring facility and administrator")),
			("live", _("Ready to sign in")),
		)
		current = _JOURNEY_STEP_INDEX.get(phase)
		failed = None
		if phase in ("blocked", "needs_attention"):
			# A failure before TA holds a setup record is a request failure.
			if submission.get("state") in ("blocked", "error") or _journey_status_key(status) == "not submitted":
				failed = 0
			else:
				failed = 2 if owner_failed else 1
		for index, (key, step_label) in enumerate(labels):
			if failed is not None:
				state = "done" if index < failed else "error" if index == failed else "upcoming"
			else:
				state = "done" if index < current else "current" if index == current else "upcoming"
			steps.append({"key": key, "label": step_label, "state": state})

	progress = status.get("progress")
	progress = None if progress in (None, "") else max(0, min(100, round(frappe.utils.flt(progress))))
	if phase == "live":
		progress = 100
	elif not progress:
		# A 0% bar says nothing the steps do not.
		progress = None

	site = None
	if phase == "live":
		url = _safe_site_url(reported.get("site_url"))
		login_url = _safe_site_url(reported.get("login_url")) or url
		admin_email = reported.get("admin_username") or (admin_contact or {}).get("admin_email") or None
		password_step = _("First time signing in? Use the HMIS welcome email or “Forgot password” on the sign-in page to set your password.")
		password_on_offer = _owner_password_on_offer(owner_login)
		if owner_login.get("status") == "created":
			if owner_login.get("email_sent"):
				password_step = _("Use the password in the HMIS credentials email sent to {0}, or “Forgot password” on the sign-in page.").format(admin_email or _("your administrator"))
			elif password_on_offer:
				password_step = _("The credentials email could not be delivered. The facility administrator can view the temporary password once below. Change it after you first sign in.")
			else:
				password_step = _("The credentials email could not be delivered. Use “Forgot password” on the sign-in page, or contact Network Support if no reset email arrives.")
		elif owner_login.get("status") == "activated":
			password_step = _("This account already existed, so keep using its current password, or use “Forgot password” on the sign-in page.")
		instructions = [
			_("Open {0}").format(login_url) if login_url else _("Open the HMIS site link in the welcome email sent to your administrator."),
			_("Sign in with {0}").format(admin_email) if admin_email else _("Sign in with your facility administrator email."),
			password_step,
		]
		site = {"url": url, "login_url": login_url, "admin_email": admin_email, "instructions": instructions}
		if owner_login:
			# Whether the temporary password is on offer; who may view it is added per request.
			site["credentials"] = {
				"status": owner_login.get("status"),
				"email_sent": owner_login.get("email_sent"),
				"password_available": password_on_offer,
			}
		deployed_on = _parse_status_time(reported.get("deployed_on"))
		if deployed_on:
			site["live_since"] = _("Live since {0}").format("{0} {1}".format(deployed_on.day, deployed_on.strftime("%b %Y")))

	return {
		"phase": phase,
		"label": label,
		"headline": headline,
		"detail": detail,
		"steps": steps,
		"progress": progress,
		"estimate": _journey_estimate(phase, status, typical_minutes, now),
		"site": site,
		"deploy_step": deploy_step,
		"poll": phase in _JOURNEY_POLL_PHASES,
		# v2.0 asks for 30-60 s polling during deployment; waiting phases change slowly.
		"poll_after_seconds": (60 if phase in ("deploying", "configuring") else 300) if phase in _JOURNEY_POLL_PHASES else None,
		"checked_at": now.isoformat(timespec="seconds"),
	}


@frappe.whitelist(methods=["GET"])
def get_provisioning_status(mfl_code):
	"""Read deployment progress without creating or changing a setup record."""
	return _get_provisioning_status(mfl_code, ensure_missing_draft=False)


@frappe.whitelist(methods=["POST"])
def ensure_provisioning_draft(mfl_code):
	"""Ensure a draft exists: read TA status, POST only when no draft exists, then reload."""
	return _get_provisioning_status(mfl_code, ensure_missing_draft=True)


def provision_onboarded_facility(mfl_code, portal_user):
	"""Background job: start HMIS setup for a facility as soon as onboarding commits.

	Runs the same ensure command the Single Facility view sends, as the facility's
	new portal user, so portfolio authorization, the per-FID lock and payload
	validation are identical. Not whitelisted: only `submit_onboarding` enqueues it.
	"""
	previous_user = frappe.session.user
	try:
		frappe.set_user(portal_user)
		result = _get_provisioning_status(mfl_code, ensure_missing_draft=True)
		frappe.logger("crm.hmis_provisioning").info(
			"onboarding ensure mfl=%s status=%s submission=%s"
			% (mfl_code, result.get("status"), (result.get("submission") or {}).get("state"))
		)
		return {"status": result.get("status"), "phase": (result.get("journey") or {}).get("phase")}
	except Exception:
		# The facility view re-runs ensure on open, so a failed early start is recoverable.
		frappe.log_error(title="HMIS provisioning after onboarding", message="mfl=%s" % mfl_code)
	finally:
		frappe.set_user(previous_user)


def _get_provisioning_status(mfl_code, ensure_missing_draft):
	"""Resolve facility status and attach the customer-facing setup journey."""
	status = _resolve_provisioning_status(mfl_code, ensure_missing_draft)
	admin_contact = None
	if _journey_phase(status) == "live" and not (status.get("reported") or {}).get("admin_username"):
		admin_contact = _portal_admin_contact(mfl_code)
	status["journey"] = _provisioning_journey(status, _typical_setup_minutes(), admin_contact)
	credentials = (status["journey"].get("site") or {}).get("credentials")
	if credentials:
		owner_email = ((status.get("reported") or {}).get("owner_login") or {}).get("email")
		view = _credential_view(status.get("fid"), (status.get("reported") or {}).get("setup_id")) if credentials["password_available"] else None
		credentials["owner_email_masked"] = _mask_email(owner_email)
		credentials["viewed_on"] = frappe.utils.cstr(view.viewed_on) if view else None
		credentials["viewed_by_you"] = bool(view and view.viewed_by == frappe.session.user)
		credentials["can_view"] = bool(
			credentials["password_available"] and not view and owner_email and owner_email == _session_email()
		)
	return status


def _owner_password_on_offer(owner_login):
	"""The setup service offers a temporary password only while its credentials email is unconfirmed."""
	return bool(
		owner_login.get("status") == "created" and not owner_login.get("email_sent") and owner_login.get("password_available")
	)


def _session_email():
	user = frappe.session.user
	return frappe.utils.cstr(frappe.db.get_value("User", user, "email") or user).strip().lower()


def _mask_email(email):
	"""a***@d***.org: enough to recognise the inbox, not to read it."""
	email = frappe.utils.cstr(email or "").strip()
	if "@" not in email:
		return None
	local, _sep, domain = email.partition("@")
	host, dot, tld = domain.rpartition(".")
	return "%s***@%s***%s%s" % (local[:1], (host or domain)[:1], dot, tld if host else "")


_CREDENTIAL_VIEW_DOCTYPE = "CRM HMIS Credential View"


def _credential_view(fid, setup_id):
	"""The open one-time view of this FID's temporary password, if any. Re-armed rows do not count."""
	if not fid:
		return None
	rows = frappe.get_all(
		_CREDENTIAL_VIEW_DOCTYPE,
		filters={"fid": fid, "facility_setup": setup_id or ["is", "not set"], "status": "Viewed"},
		fields=["name", "viewed_by", "viewed_on"],
		order_by="viewed_on desc",
		limit_page_length=1,
		ignore_permissions=True,
	)
	return rows[0] if rows else None


def _fetch_owner_login(fid):
	"""Read the owner login block, password included, straight from the setup service.

	Server to server only. Nothing from this response is cached, stored or logged.
	"""
	credentials = _external_provisioning_credentials()
	if not credentials:
		return None
	base_url, api_key, api_secret = credentials
	try:
		response = requests.get(
			base_url + "/api/method/hmis_setup.api.external_provisioning.get_provision_status",
			params={"fid": fid},
			auth=(api_key, api_secret),
			headers={"Accept": "application/json", "X-Correlation-Id": frappe.generate_hash(length=16)},
			timeout=15,
		)
		if response.status_code != 200:
			return None
		login = _gateway_data(response).get("login")
	except (requests.exceptions.RequestException, ValueError, TypeError, AttributeError):
		return None
	return login if isinstance(login, dict) else None


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=5, seconds=3600)
def reveal_hmis_owner_password(mfl_code):
	"""Show the facility's temporary HMIS owner password once, to that owner only.

	The setup service returns a generated password while its credentials email is
	unconfirmed, because a new HMIS site may not be able to send mail yet. CRM never
	puts it in the polled status: it is fetched here on request, handed back in this
	one response, and recorded as viewed (who and when, never the password) before
	it is returned, so a second request is refused.
	"""
	status = _get_provisioning_status(mfl_code, ensure_missing_draft=False)
	journey = status.get("journey") or {}
	reported = status.get("reported") or {}
	owner_email = (reported.get("owner_login") or {}).get("email")
	if not owner_email or owner_email != _session_email():
		frappe.throw(_("Only the facility administrator can view the temporary HMIS password."), frappe.PermissionError)
	credentials = (journey.get("site") or {}).get("credentials") or {}
	if journey.get("phase") != "live" or not credentials.get("password_available"):
		frappe.throw(_("No temporary password is on offer for this HMIS site. Check the HMIS credentials email or use “Forgot password” on the sign-in page."))
	fid = status.get("fid")
	setup_id = reported.get("setup_id") or ""
	lock_key = hashlib.sha256(frappe.utils.cstr(fid).encode()).hexdigest()[:32]
	with filelock("crm_hmis_credential_view_%s" % lock_key, timeout=10):
		view = _credential_view(fid, setup_id)
		if view:
			frappe.throw(
				_("The temporary password was already viewed on {0}. Contact Network Support if it was lost.").format(
					frappe.utils.format_datetime(view.viewed_on)
				)
			)
		login = _fetch_owner_login(fid) or {}
		password = login.get("password")
		if (
			not (isinstance(password, str) and password)
			or login.get("email_sent")
			or frappe.utils.cstr(login.get("email")).strip().lower() != owner_email
		):
			frappe.throw(_("The temporary password is not available right now. Try again shortly, or use “Forgot password” on the sign-in page."))
		viewed_on = frappe.utils.now_datetime()
		frappe.get_doc({
			"doctype": _CREDENTIAL_VIEW_DOCTYPE,
			"status": "Viewed",
			"fid": fid,
			"facility": frappe.db.get_value("CRM Pre-Qualified Facility", {"hfr_facility_id": fid}, "name"),
			"facility_setup": setup_id,
			"owner_email": owner_email,
			"viewed_by": frappe.session.user,
			"viewed_on": viewed_on,
		}).insert(ignore_permissions=True)
		# Commit before the password leaves, so a concurrent or repeated request is refused.
		frappe.db.commit()
	return {"email": owner_email, "password": password, "viewed_on": frappe.utils.cstr(viewed_on)}


def _resolve_provisioning_status(mfl_code, ensure_missing_draft):
	"""Resolve an authorized facility and read status, optionally ensuring a draft."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to view facility implementation status."), frappe.PermissionError)

	from crm.api.website_redirect import get_user_customer_names, _portal_hfr_registry_by_mfl

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
		["name", "hfr_facility_id", "facility_name", "keph_level", "registration_number", "license_number", "hfr_county", "hfr_sub_county", "organization", "creation"],
		as_dict=True,
	) if allowed else None
	deal_facility = None
	if deals:
		deal_fields = [
			field for field in (
				"hfr_facility_id", "facility_name", "facility_level", "registration_number", "license_number", "organization",
				"hfr_county", "hfr_sub_county", "cx_token_package_item", "cx_token_package_quantity", "creation",
			) if frappe.get_meta("CRM Deal Facility").has_field(field)
		]
		deal_rows = frappe.get_all(
			"CRM Deal Facility",
			filters={"parent": ["in", deals], "mfl_code": mfl_code},
			fields=deal_fields,
			limit_page_length=0,
			ignore_permissions=True,
		)
		if deal_rows:
			deal_facility = frappe._dict(_unique_facility_projection(deal_rows, deal_fields))
			if not facility:
				facility = frappe._dict({**deal_facility, "mfl_code": mfl_code})
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
			limit_page_length=0,
			ignore_permissions=True,
		)
		if lead_rows:
			lead_projection = _unique_facility_projection(lead_rows, ["hfr_facility_id"])
			facility = frappe._dict({**lead_projection, "mfl_code": mfl_code})
	if not facility:
		frappe.throw(_("Facility not found in your portfolio."), frappe.PermissionError)

	if not facility.get("hfr_facility_id"):
		lead_organizations = frappe.get_all(
			"CRM Lead",
			filters={"name": ["in", leads]},
			fields=["organization"],
			limit_page_length=0,
			ignore_permissions=True,
		) if leads else []
		deal_organizations = frappe.get_all(
			"CRM Deal",
			filters={"name": ["in", deals]},
			fields=["organization"],
			limit_page_length=0,
			ignore_permissions=True,
		) if deals else []
		customer_organizations = frappe.get_all(
			"Customer",
			filters={"name": ["in", customers]},
			fields=["customer_name"],
			limit_page_length=0,
			ignore_permissions=True,
		) if customers else []
		registry_rows = _portal_hfr_registry_by_mfl(
			[mfl_code],
			[facility.get("organization")]
			+ [row.get("organization") for row in lead_organizations]
			+ [row.get("organization") for row in deal_organizations]
			+ [row.get("customer_name") for row in customer_organizations]
			+ customers,
		)
		registry_fids = {
			frappe.utils.cstr(row.get("hfr_facility_id") or "").strip()
			for row in registry_rows.values()
			if frappe.utils.cstr(row.get("hfr_facility_id") or "").strip()
		}
		if len(registry_fids) == 1:
			facility.hfr_facility_id = registry_fids.pop()

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
		if (
			ensure_missing_draft
			and (status.get("status") == "unavailable" or status.get("has_error"))
			and status.get("error_code") != "invalid_fid"
		):
			frappe.log_error(
				title="External HMIS provisioning status requires support",
				message="fid=%s correlation_id=%s\n%s"
				% (
					facility.hfr_facility_id,
					status.get("correlation_id") or "unknown",
					status.get("error_details") or status.get("message") or "No diagnostic response returned.",
				),
			)
		if ensure_missing_draft and status.get("status") == "not_submitted":
			source = _get_external_provisioning_source(facility, deal_facility, mfl_code, deals, customers)
			payload, missing_fields = _build_external_provisioning_payload(source)
			# Contract v2 D2: deployment starts without a manual release unless the
			# implementation team has switched manual review on in CRM HFR Settings.
			payload["auto_deploy"] = _auto_deploy_enabled(settings)
			metering = _apply_token_source(
				settings,
				payload,
				package_item=(deal_facility or {}).get("cx_token_package_item"),
				package_tokens=source.get("package_tokens"),
			)
			status = _auto_submit_external_provisioning(
				external_url,
				external_key,
				external_secret,
				facility.hfr_facility_id,
				status,
				payload,
				missing_fields,
				metering=metering,
			)
		status["fid"] = facility.hfr_facility_id
		status["auto_deploy"] = _auto_deploy_enabled(settings)
		# The TA status API includes its deployment log and last error on a 200
		# response. These can contain internal tracebacks, so only CRM System
		# Managers receive them through this customer-portfolio endpoint.
		if "System Manager" not in frappe.get_roles():
			status.pop("error_details", None)
			if isinstance(status.get("submission"), dict):
				status["submission"].pop("error_details", None)
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
	if not (base_url and path_template and settings.get("hfr_username") and settings.get_password("hfr_password", raise_exception=False)):
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
			"reported": _reported_setup_details(payload),
		}
	except requests.exceptions.RequestException as exc:
		return _provisioning_unavailable("network", None, correlation_id)
	except (ValueError, TypeError):
		return _provisioning_unavailable("response", None, correlation_id)


def _owner_user_failed(payload, reported):
	"""True when the setup service reports that the owner administrator login failed."""
	# The deploy flow's Owner User (retry) step prefixes its failure this way.
	if "[owner user]" in frappe.utils.cstr(payload.get("error") or "").casefold():
		return True
	# v2.0: Failed after every deployment step finished means the owner-user track failed.
	completion = reported.get("completion") or {}
	if (
		frappe.utils.cstr(payload.get("status")).casefold() == "failed"
		and completion.get("deployment_complete")
		and not completion.get("owner_user_complete")
	):
		return True
	return any(
		step["status"] == "failed" and _is_owner_user_step(step["name"]) for step in reported.get("deploy_steps") or []
	)


def _deploy_not_queued_key(fid):
	"""Cache key marking an FID whose auto-deploy request the setup service could not queue."""
	return "crm_external_provisioning_deploy_not_queued:%s" % hashlib.sha256(frappe.utils.cstr(fid).encode()).hexdigest()[:32]


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
	if not _is_valid_fid(fid):
		# The service answers a malformed FID with a 400 on every poll (v2.2 §5); it is a CRM data fix.
		return _external_provisioning_unavailable("invalid_fid", None)
	url = base_url + "/api/method/hmis_setup.api.external_provisioning.get_provision_status"
	correlation_id = frappe.generate_hash(length=16)
	try:
		response = requests.get(
			url,
			params={"fid": fid},
			auth=(api_key, api_secret),
			headers={"Accept": "application/json", "X-Correlation-Id": correlation_id},
			timeout=15,
		)
		response_correlation_id = response.headers.get("X-Correlation-Id") or correlation_id
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
					"correlation_id": response_correlation_id,
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
					"correlation_id": response_correlation_id,
					"message": _("More than one setup record uses this facility ID. Contact the implementation team."),
				}
			return _external_provisioning_unavailable(
				"bad_request", response.status_code, _external_error_details_for_response(response), response_correlation_id
			)
		if response.status_code in (401, 403):
			body = _gateway_error(response)
			failure = body.get("message", "").casefold()
			kind = "method_not_published" if "not whitelisted" in failure else "auth"
			return _external_provisioning_unavailable(
				kind, response.status_code, _external_error_details_for_response(response), response_correlation_id
			)
		if response.status_code == 404:
			body = _gateway_error(response)
			return _external_provisioning_unavailable(
				"method_not_published", response.status_code, _external_error_details_for_response(response), response_correlation_id
			)
		if response.status_code != 200:
			body = _gateway_error(response)
			return _external_provisioning_unavailable(
				"service", response.status_code, _external_error_details_for_response(response), response_correlation_id
			)
		payload = _gateway_data(response)
		status = frappe.utils.cstr(payload.get("status") or "Unknown")
		result = {
			"configured": True,
			"status": status,
			"progress": frappe.utils.flt(payload.get("progress")) if payload.get("progress") is not None else None,
			"last_attempt": frappe.utils.cstr(payload.get("last_attempt") or "") or None,
			"has_error": bool(payload.get("error")),
			"service_units": None,
			"service_units_count": None,
			"site_status": None,
			"source": "external_setup",
			"correlation_id": response_correlation_id,
			"message": _("Status synced from the HMIS setup service. Deployment is reviewed and started by the implementation team."),
			"service_units_message": _("The setup status API does not report configured service units."),
			"reported": _reported_setup_details(payload),
		}
		result["owner_user_failed"] = _owner_user_failed(payload, result["reported"])
		error_text = frappe.utils.cstr(payload.get("error") or "").casefold()
		# v2.0 blocks deployment while the target HMIS instance is not Active.
		result["instance_blocked"] = "blocked until the instance is set to active" in error_text
		if _journey_status_key(result) in _QUEUED_STATUSES and frappe.cache().get_value(_deploy_not_queued_key(fid)):
			result["deploy_not_queued"] = True
		if status.casefold() == "error" or payload.get("error"):
			error_details = _external_error_details(
				response.status_code,
				{"error": payload.get("error"), "log": payload.get("log")},
			)
			if "System Manager" in frappe.get_roles():
				result["error_details"] = error_details
		return result
	except requests.exceptions.RequestException:
		return _external_provisioning_unavailable("network", None, correlation_id=correlation_id)
	except (ValueError, TypeError):
		return _external_provisioning_unavailable("response", None, correlation_id=correlation_id)


def _get_external_provisioning_source(facility, deal_facility, mfl_code, deals, customers=None):
	"""Resolve only server-owned CRM data that can support a facility draft.

	The administrator is the accepted Opt-In signatory or, for a self-onboarded
	facility (which has no Opt-In), the OTP-verified owner on its membership. The
	TA maps licence to the HFR licence number or registration number, backfilled
	from the HFR registry by FID when onboarding did not store one. Billing is not
	part of the setup request (setup service v2.1); the metering system owns it.
	"""
	facility = frappe._dict(facility or {})
	deal_facility = frappe._dict(deal_facility or {})
	selected_package = None
	admin = _resolve_admin_contact(mfl_code, deals, customers)
	licence = facility.get("license_number") or facility.get("registration_number")
	if not licence and facility.get("hfr_facility_id"):
		licence = _backfill_licence_from_hfr(facility.get("hfr_facility_id"), mfl_code, deals)
	if deal_facility.get("cx_token_package_item"):
		selected_package = deal_facility
	return {
		"fid": facility.get("hfr_facility_id"),
		"licence": licence,
		"facility_name": facility.get("facility_name"),
		"facility_level": facility.get("keph_level") or facility.get("facility_level"),
		"county": facility.get("hfr_county"),
		"sub_county": facility.get("hfr_sub_county"),
		# Not sent to the setup service (v2.1 dropped billing fields); the metering
		# hooks still receive the package size.
		"package_tokens": (selected_package.get("cx_token_package_quantity") or 0) if selected_package else 0,
		**admin,
	}


def _resolve_admin_contact(mfl_code, deals, customers):
	"""Return the one verified HMIS administrator contact for a facility, or {}.

	The accepted Opt-In signatory wins; a self-onboarded facility (no Opt-In) uses
	its OTP-verified owner. CRM never chooses between conflicting contacts.
	"""
	admin = {}
	if deals:
		rows = frappe.get_all(
			"CRM Opt-In Submission",
			filters={"deal": ["in", deals], "status": "Processed"},
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
	if not any(admin.values()):
		admin = _self_onboarded_owner_admin(mfl_code, customers)
	return admin


def _portal_admin_contact(mfl_code):
	"""Admin contact for the signed-in portal user's facility, used for sign-in steps."""
	from crm.api.website_redirect import get_user_customer_names, get_user_deal_names

	user = frappe.session.user
	return _resolve_admin_contact(
		frappe.utils.cstr(mfl_code or "").strip(), get_user_deal_names(user), get_user_customer_names(user)
	)


def _self_onboarded_owner_admin(mfl_code, customers):
	"""Return the OTP-verified owner of a self-onboarded facility as its HMIS administrator.

	Self-onboarding records the registry contact that passed OTP on the facility
	membership. Only one unambiguous contact for the signed-in customer is used.
	"""
	if not customers:
		return {}
	facility_name = frappe.db.get_value(
		"CRM Pre-Qualified Facility", {"mfl_code": mfl_code, "is_self_onboarded": 1}, "name"
	)
	if not facility_name:
		return {}
	rows = frappe.get_all(
		"CRM Facility Membership",
		filters={"parent": facility_name, "customer": ["in", customers], "status": "Active"},
		fields=["contact_name", "contact_email", "contact_phone"],
		limit_page_length=0,
		ignore_permissions=True,
	)
	contacts = {
		(
			" ".join(frappe.utils.cstr(row.contact_name).split()),
			frappe.utils.cstr(row.contact_email).strip().lower(),
			frappe.utils.cstr(row.contact_phone).strip(),
		)
		for row in rows
	}
	if len(contacts) != 1:
		return {}
	name, email, phone = contacts.pop()
	return {"admin_name": name, "admin_email": email, "admin_mobile": phone}


def _backfill_licence_from_hfr(fid, mfl_code, deals):
	"""Fetch the HFR licence (or registration) number by FID and store it on the CRM facility."""
	if not frappe.db.get_single_value(_DOCTYPE, "hfr_enabled"):
		return None
	message_log = getattr(frappe.local, "message_log", None)
	message_count = len(message_log) if message_log is not None else 0
	try:
		detail = get_facility_detail(fid)
	except Exception:
		# The registry error is for support, not the customer viewing the facility.
		if message_log is not None:
			del message_log[message_count:]
		frappe.log_error(title="HMIS provisioning licence lookup", message="fid=%s" % fid)
		return None
	if frappe.utils.cstr(detail.get("hfr_facility_id")).strip() != frappe.utils.cstr(fid).strip():
		return None
	values = {
		fieldname: detail.get(fieldname)
		for fieldname in ("license_number", "registration_number")
		if detail.get(fieldname)
	}
	if not values:
		return None
	facility_name = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": mfl_code}, "name")
	if facility_name:
		frappe.db.set_value("CRM Pre-Qualified Facility", facility_name, values, update_modified=False)
	if deals:
		for row in frappe.get_all(
			"CRM Deal Facility",
			filters={"parent": ["in", deals], "mfl_code": mfl_code},
			pluck="name",
			ignore_permissions=True,
		):
			frappe.db.set_value("CRM Deal Facility", row, values, update_modified=False)
	return values.get("license_number") or values.get("registration_number")


# Setup service v2.1 contract: billing metering moved to the independent metering
# system, so tokens_awarded, token_expiry_date, billing_model and
# license_expiry_date are neither sent nor required.
_EXTERNAL_PROVISIONING_REQUIRED = ("fid", "licence", "admin_email", "admin_name", "admin_mobile")


def _is_valid_fid(fid):
	"""The setup service's FR code format, `^FID-\\d{2}-[\\w-]+$` (case-insensitive)."""
	return bool(re.fullmatch(r"FID-\d{2}-[\w-]+", frappe.utils.cstr(fid).strip(), flags=re.IGNORECASE))


def _build_external_provisioning_payload(source):
	"""Validate the exact TA-required payload without guessing missing policy data."""
	source = source or {}
	payload = {}
	for fieldname in _EXTERNAL_PROVISIONING_REQUIRED + ("facility_name", "facility_level", "county", "sub_county"):
		value = source.get(fieldname)
		if isinstance(value, str):
			value = value.strip()
			if fieldname == "admin_email":
				value = value.lower()
		if value not in (None, ""):
			payload[fieldname] = value

	missing = [fieldname for fieldname in _EXTERNAL_PROVISIONING_REQUIRED if fieldname not in payload]
	if payload.get("fid") and not _is_valid_fid(payload["fid"]):
		missing.append("valid fid")
	if payload.get("admin_email") and "@" not in frappe.utils.cstr(payload["admin_email"]):
		missing.append("valid admin_email")
	return payload, list(dict.fromkeys(missing))


def _apply_token_source(settings, payload, package_item=None, package_tokens=0):
	"""Set the HMIS token source on the payload and return the context the metering hooks receive.

	With OpenMeter as the token source (openmeter_mediator ADR-003), CRM grants the
	facility's tokens in OpenMeter under its FID and HMIS reads its balance there,
	and the setup service carries no token ledger (v2.1). A paid package is granted when its
	invoice is paid, never at provisioning, so the context defers it.
	"""
	context = {
		"fid": payload.get("fid"),
		"package_tokens": package_tokens or 0,
		# The metering app re-checks this item's catalog price before any initial grant.
		"package_item": frappe.utils.cstr(package_item or "").strip(),
		"token_source": "crm",
		"defer_package_grant": _is_paid_package(package_item),
	}
	if not settings.get("hmis_token_source_openmeter"):
		return context
	context["token_source"] = "openmeter"
	payload["token_source"] = "openmeter"
	payload["token_purchase_url"] = frappe.utils.cstr(settings.get("token_purchase_url") or "").strip() or frappe.utils.get_url(
		"/cx-portal"
	)
	return context


def _is_paid_package(package_item):
	"""True unless the facility's package is in the catalog at no charge (a free trial)."""
	from crm.api.facility_onboarding import _token_packages

	package_item = frappe.utils.cstr(package_item or "").strip()
	if not package_item:
		return True
	package = next((row for row in _token_packages() if row["item_code"] == package_item), None)
	return not package or frappe.utils.flt(package.get("price")) > 0


def _issue_metering_site_key(fid, context):
	"""Return the FID's metering site key from the crm_issue_hmis_metering_site_key hook.

	CRM does not import the metering app. The key only travels in the outbound
	request: it is never stored, cached, logged or returned to the portal.
	"""
	for method in frappe.get_hooks("crm_issue_hmis_metering_site_key"):
		try:
			key = frappe.get_attr(method)(fid=fid, context=dict(context))
		except Exception:
			frappe.log_error(
				title="HMIS metering site key could not be issued",
				message="fid=%s hook=%s\n%s" % (fid, method, frappe.get_traceback()),
			)
			continue
		if isinstance(key, str) and key.strip():
			return key.strip()
	return ""


def run_hmis_provisioning_submitted_hooks(fid, context=None):
	"""Background job: tell installed apps that the setup service accepted this FID's provisioning."""
	for method in frappe.get_hooks("crm_on_hmis_provisioning_submitted"):
		try:
			frappe.get_attr(method)(fid=fid, context=dict(context or {}))
		except Exception:
			frappe.log_error(
				title="HMIS provisioning-submitted hook failed",
				message="fid=%s hook=%s\n%s" % (fid, method, frappe.get_traceback()),
			)


_EXISTING_SITE_KEY_JOB = "crm-hmis-existing-site-key-delivery"


@frappe.whitelist(methods=["POST"])
def deliver_metering_site_keys():
	"""Queue metering site-key delivery to facilities whose HMIS site predates metering.

	New facilities get their key in the provisioning request. An existing site never
	sends that request again, so the setup service pushes the key to it in a signed
	`update_license` instead (openmeter_mediator OMM-38).
	"""
	frappe.only_for("System Manager")
	if not _external_provisioning_credentials():
		frappe.throw(_("Finish the external HMIS setup service credentials in CRM HFR Settings first."))
	if not frappe.get_hooks("crm_list_hmis_sites_needing_metering_key"):
		frappe.throw(_("No metering app is installed to issue site keys."))
	frappe.enqueue(
		"crm.api.hfr.run_existing_site_key_delivery",
		queue="long",
		timeout=3600,
		job_id=_EXISTING_SITE_KEY_JOB,
		deduplicate=True,
		enqueue_after_commit=True,
	)
	return {"job_id": _EXISTING_SITE_KEY_JOB}


def _external_provisioning_credentials():
	settings = frappe.get_single(_DOCTYPE)
	base_url = frappe.utils.cstr(settings.get("external_provisioning_url") or "").strip().rstrip("/")
	api_key = frappe.utils.cstr(settings.get("external_provisioning_key") or "").strip()
	api_secret = settings.get_password("external_provisioning_secret") if settings.get("external_provisioning_secret") else ""
	if base_url.startswith("https://") and api_key and api_secret:
		return base_url, api_key, api_secret
	return None


def run_existing_site_key_delivery():
	"""Background job: deliver a site key to every existing HMIS site that has none."""
	credentials = _external_provisioning_credentials()
	if not credentials:
		return {}
	fids = []
	for method in frappe.get_hooks("crm_list_hmis_sites_needing_metering_key"):
		try:
			fids.extend(frappe.get_attr(method)(context={"purpose": "existing_site"}) or [])
		except Exception:
			frappe.log_error(title="HMIS metering key list hook failed", message="hook=%s\n%s" % (method, frappe.get_traceback()))
	results = {"delivered": [], "skipped": [], "failed": []}
	for fid in dict.fromkeys(frappe.utils.cstr(fid).strip() for fid in fids if fid):
		try:
			outcome = _deliver_existing_site_key(*credentials, fid)
		except LockTimeoutError:
			outcome = {"state": "failed", "reason": "Another provisioning step for this facility is running."}
		frappe.db.commit()
		results[outcome["state"]].append({"fid": fid, "reason": outcome.get("reason")})
		if outcome["state"] == "failed":
			frappe.log_error(
				title="HMIS metering key not delivered: %s" % fid,
				message="%s\n%s" % (outcome.get("reason"), outcome.get("error_details") or ""),
			)
	frappe.logger("crm.hmis_provisioning").info(
		"existing-site key delivery delivered=%s skipped=%s failed=%s"
		% (len(results["delivered"]), len(results["skipped"]), len(results["failed"]))
	)
	return results


def _deliver_existing_site_key(base_url, api_key, api_secret, fid):
	"""Issue a key for one existing HMIS site and have the setup service push it there.

	Holds the provisioning lock for the FID, so it never races a new provisioning
	request. The key only travels in the outbound request, as in provisioning.
	"""
	lock_key = hashlib.sha256(frappe.utils.cstr(fid).encode()).hexdigest()[:32]
	with filelock("crm_external_provisioning_%s" % lock_key, timeout=60):
		status = _get_external_provisioning_status(base_url, api_key, api_secret, fid)
		state = status.get("status")
		if state == "not_submitted":
			return {"state": "skipped", "reason": "No HMIS site yet; provisioning will carry the key."}
		if not status.get("configured") or state in ("unavailable", "needs_support", "not_configured"):
			return {"state": "failed", "reason": "HMIS setup status unavailable (%s)." % state}

		site_key = _issue_metering_site_key(fid, {"fid": fid, "purpose": "existing_site", "token_source": "openmeter"})
		if not site_key:
			return {"state": "failed", "reason": "No site key was issued; see the metering app's error log entry."}

		url = base_url + "/api/method/hmis_setup.api.external_provisioning.update_metering_site_key"
		correlation_id = frappe.generate_hash(length=16)
		try:
			response = requests.post(
				url,
				auth=(api_key, api_secret),
				json={"fid": fid, "metering_site_key": site_key},
				headers={"Accept": "application/json", "Content-Type": "application/json", "X-Correlation-Id": correlation_id},
				timeout=60,
			)
		except requests.exceptions.RequestException:
			return {"state": "failed", "reason": "The setup service did not answer (correlation %s)." % correlation_id}
		if response.status_code not in (200, 202):
			reason = "The setup service refused the key (HTTP %s)." % response.status_code
			if response.status_code == 404:
				reason = "The setup service does not offer update_metering_site_key yet (HTTP 404)."
			return {"state": "failed", "reason": reason, "error_details": _external_error_details_for_response(response)}
		try:
			accepted = _gateway_data(response).get("accepted") is True
		except ValueError:
			accepted = False
		if not accepted:
			return {"state": "failed", "reason": "The setup service did not confirm the key (correlation %s)." % correlation_id}

	for method in frappe.get_hooks("crm_on_hmis_metering_site_key_delivered"):
		try:
			frappe.get_attr(method)(fid=fid, context={"fid": fid})
		except Exception:
			frappe.log_error(
				title="HMIS metering key delivered hook failed",
				message="fid=%s hook=%s\n%s" % (fid, method, frappe.get_traceback()),
			)
	return {"state": "delivered"}


def _auto_submit_external_provisioning(base_url, api_key, api_secret, fid, status, payload, missing_fields, metering=None):
	try:
		return _auto_submit_external_provisioning_impl(
			base_url, api_key, api_secret, fid, status, payload, missing_fields, metering=metering
		)
	except LockTimeoutError:
		status["submission"] = {
			"state": "unknown",
			"retryable": True,
			"retry_mode": "status_check",
			"message": _("Another request is checking or creating this setup. Refresh status shortly; CRM will check for an existing draft before any submission."),
		}
		return status


def _auto_submit_external_provisioning_impl(base_url, api_key, api_secret, fid, status, payload, missing_fields, metering=None):
	"""Create one draft after an authoritative missing-status check.

	The FID lock serializes portal retries. Before every POST we GET status again.
	An ambiguous result is reconciled by the next explicit ensure: retry POST only
	when that fresh status GET still confirms no draft. The TA endpoint has no
	idempotency support, so this is the strongest available duplicate control.
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
				"error_details": frappe.cache().get_value(attempt_key + ":error_details"),
			}
			return status
		# A fresh authoritative GET has already confirmed there is no draft. Do
		# not let a stale `unknown` or `accepted` cache entry suppress creation:
		# the caller explicitly requested ensure, so POST now and reconcile again.

		request_payload = payload
		if (metering or {}).get("token_source") == "openmeter":
			# Issued only once the fresh GET has confirmed no draft, so a key is not
			# rotated on every status refresh. The fingerprint above excludes it.
			site_key = _issue_metering_site_key(fid, metering)
			if not site_key:
				status["submission"] = {
					"state": "blocked",
					"retryable": False,
					"missing_fields": ["metering_site_key"],
					"message": _(
						"OpenMeter is the HMIS token source, but no metering site key could be issued for this facility. Check the OpenMeter Mediator app, then refresh."
					),
				}
				return status
			request_payload = {**payload, "metering_site_key": site_key}

		url = base_url.rstrip("/") + "/api/method/hmis_setup.api.external_provisioning.provision_facility"
		correlation_id = frappe.generate_hash(length=16)
		try:
			response = requests.post(
				url,
				auth=(api_key, api_secret),
				json=request_payload,
				headers={"Accept": "application/json", "Content-Type": "application/json", "X-Correlation-Id": correlation_id},
				timeout=60,
			)
		except requests.exceptions.RequestException:
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
			error_details = _external_error_details_for_response(response)
			submission_correlation_id = response.headers.get("X-Correlation-Id") or correlation_id
			frappe.log_error(
				title="External HMIS provisioning submission failed",
				message="http_status=%s correlation_id=%s\n%s"
				% (response.status_code, submission_correlation_id, error_details),
			)
			if response.status_code >= 500 or response.status_code in (408, 429) or _is_transient_rejection(body):
				state = "unknown"
				retryable = True
			else:
				frappe.cache().set_value(attempt_key, "rejected:%s" % payload_fingerprint, expires_in_sec=31536000)
				frappe.cache().set_value(attempt_key + ":error_details", error_details, expires_in_sec=31536000)
				state = "error"
				retryable = False
			status["submission"] = {
				"state": state,
				"retryable": retryable,
				"retry_mode": "status_check" if retryable else None,
				"message": _("The setup service could not reach the Health Facility Registry. CRM will check status and retry on the next refresh.")
				if _is_transient_rejection(body)
				else _external_submit_error(response.status_code, body),
				"error_details": error_details,
				"correlation_id": submission_correlation_id,
			}
			return status

		body = _gateway_data(response)
		if body.get("accepted") is not True:
			status["submission"] = {
				"state": "unknown",
				"retryable": True,
				"retry_mode": "status_check",
				"message": _("The deployment service returned an unclear response. CRM will check status before any retry."),
				"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
			}
			return status

		if frappe.get_hooks("crm_on_hmis_provisioning_submitted"):
			frappe.enqueue(
				"crm.api.hfr.run_hmis_provisioning_submitted_hooks",
				queue="short",
				enqueue_after_commit=True,
				fid=fid,
				context=dict(metering or {"fid": fid}),
			)

		idempotent = bool(body.get("idempotent"))
		deploy_queued = None
		if request_payload.get("auto_deploy") is True and idempotent:
			# v2.2 §4.5: a re-post never starts deployment, so a record still in Draft waits for a manual release.
			if _journey_status_key({"status": body.get("status")}) in _QUEUED_STATUSES:
				deploy_queued = False
				frappe.cache().set_value(_deploy_not_queued_key(fid), 1, expires_in_sec=7 * 24 * 3600)
		elif request_payload.get("auto_deploy") is True:
			# v2.0 still answers 200 when the deployment enqueue fails, with a WARNING message.
			warning = frappe.utils.cstr(body.get("message")).lstrip().upper().startswith("WARNING")
			if body.get("auto_deploy_queued") is False or warning:
				deploy_queued = False
				frappe.cache().set_value(_deploy_not_queued_key(fid), 1, expires_in_sec=7 * 24 * 3600)
				frappe.log_error(
					title="External HMIS auto-deploy not queued",
					message="fid=%s correlation_id=%s\n%s"
					% (fid, response.headers.get("X-Correlation-Id") or correlation_id, frappe.utils.cstr(body.get("message"))[:2000]),
				)
			elif body.get("auto_deploy_queued") is True:
				deploy_queued = True
		if deploy_queued is not False and not idempotent:
			# A new setup record replaces any earlier record whose deploy was not queued.
			frappe.cache().delete_value(_deploy_not_queued_key(fid))

		refreshed = _get_external_provisioning_status(base_url, api_key, api_secret, fid)
		if refreshed.get("status") == "not_submitted":
			refreshed.update({"status": body.get("status") or "Draft", "progress": 0})
		if deploy_queued is False and _journey_status_key(refreshed) in _QUEUED_STATUSES:
			refreshed["deploy_not_queued"] = True
		if idempotent:
			message = _("An HMIS setup record already exists for this facility. Its status has been refreshed.")
		elif deploy_queued is False:
			message = _("The HMIS setup request was sent, but deployment did not start automatically. The implementation team will start it.")
		elif request_payload.get("auto_deploy") is True:
			message = _("The HMIS setup request was sent and deployment starts automatically.")
		else:
			message = _("The HMIS setup draft was created. The implementation team will review it before deployment.")
		refreshed["submission"] = {
			# An FID that already had a setup record comes back as idempotent (v2.x).
			"state": "already_exists" if idempotent else "created",
			"retryable": False,
			"facility_setup": body.get("facility_setup"),
			"deploy_queued": deploy_queued,
			# The service's own message is operator-facing (it may name its admin UI or a WARNING).
			"message": message,
			"correlation_id": response.headers.get("X-Correlation-Id") or correlation_id,
		}
		return refreshed


def _is_transient_rejection(body):
	"""A validation-coded response that reports an outage, not bad facility details."""
	message = frappe.utils.cstr((body or {}).get("message") if isinstance(body, dict) else "").casefold()
	# v2.0 returns a registry HTTP failure as a 400; the same details succeed once it recovers.
	return "registry lookup failed" in message


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


def _external_error_details(status_code, body):
	"""Keep a bounded upstream error response for support, with credentials redacted."""
	sensitive_key = re.compile(r"password|secret|token|authorization|cookie|api[_-]?key|site[_-]?key|credential", re.I)
	secret_value = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
	site_key_value = re.compile(r"omk2\.[A-Za-z0-9._-]+")
	sensitive_text = re.compile(
		r'(?i)((?:"?)(?:password|secret|token|authorization|cookie|api[_-]?key|credential)(?:"?)\s*[:=]\s*"?)[^"\s,;&}]+'
	)

	def redact(value):
		if isinstance(value, dict):
			return {
				str(key): "[REDACTED]" if sensitive_key.search(str(key)) else redact(item)
				for key, item in value.items()
			}
		if isinstance(value, list):
			return [redact(item) for item in value[:50]]
		if isinstance(value, str):
			value = site_key_value.sub("[REDACTED]", secret_value.sub(r"\1[REDACTED]", value[:8000]))
			return sensitive_text.sub(r"\1[REDACTED]", value)
		return value

	details = {"http_status": int(status_code), "response": redact(body)}
	return json.dumps(details, ensure_ascii=False, indent=2, default=str)[:12000]


def _external_error_details_for_response(response):
	"""Serialize the complete upstream error response, including non-JSON bodies."""
	try:
		body = response.json()
	except (ValueError, TypeError):
		body = {"response_text": getattr(response, "text", "")}
	return _external_error_details(response.status_code, body)


def _external_provisioning_unavailable(kind, status_code, error_details=None, correlation_id=None):
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
	elif kind == "invalid_fid":
		error_code = "invalid_fid"
		error_title = _("This facility's HFR Facility ID is not in the expected format")
		message = _("The Facility ID must look like FID-XX-…. Ask your implementation team to correct it in CRM.")
		retryable = False
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
		"error_details": error_details,
		"correlation_id": correlation_id,
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
