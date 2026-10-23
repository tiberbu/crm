"""CRM-owned guest API for tiberbu Express facility self-onboarding.

This module intentionally owns the Client Registry and Health Facility Registry
adapter.  It is copied from the neighbouring implementation's public contract,
but has no runtime import or dependency on that application.

The browser receives only opaque, short-lived onboarding tokens.  Registry PII
is encrypted while the session is in Redis, and facility details are released
only after the registry contact OTP is verified.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
import unicodedata
from typing import Any

import frappe
import requests
from frappe import _
from frappe.utils.password import decrypt, encrypt
from frappe.utils.synchronization import filelock

from crm.api._email import (
	OTP_QUEUE_REDACTION,
	branded_email_html,
	otp_code_block,
	schedule_email_queue_redaction,
)
from crm.fcrm.doctype.crm_onboarding_evidence.crm_onboarding_evidence import evidence_ref, record_event

try:
	import jwt
except ImportError:  # pragma: no cover - site configuration failure
	jwt = None

SESSION_TTL_SECONDS = 2 * 60 * 60
OTP_TTL_SECONDS = 10 * 60
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60
OTP_MAX_RESENDS = 5
HFR_MAX_LOOKUPS = 6
OTP_BRAND = "tiberbu Express"
_DECOY_DOMAINS = ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .'/-]{2,63}$")
PARTNER_ID_RE = re.compile(r"^\d{6}$")
ConfigurationError = getattr(frappe, "ConfigurationError", frappe.ValidationError)


def _text(value: Any) -> str:
	return frappe.utils.cstr(value or "").strip()


def _normalize_id_type(value: Any) -> str:
	return re.sub(r"[^a-z0-9]", "", _text(value).lower())


def _identity_reference(id_type: Any, id_number: Any) -> str:
	"""Return a stable keyed reference for an identity without retaining its raw ID."""
	normalized_type = _normalize_id_type(id_type)
	normalized_number = _text(id_number).casefold()
	return evidence_ref("%s|%s" % (normalized_type, normalized_number))


def _client_ip() -> str:
	try:
		request = getattr(frappe.local, "request", None)
		if request:
			return (
				_text(request.headers.get("X-Forwarded-For", "").split(",")[0])
				or _text(getattr(request, "remote_addr", ""))
				or "unknown"
			)
	except Exception:
		pass
	return "unknown"


def _setting(name: str, default: Any = "") -> Any:
	try:
		settings = frappe.get_single("CRM Opt-In Settings")
		return settings.get(name) or default
	except Exception:
		return default


def _onboarding_config() -> dict[str, Any]:
	# Use the same service account as the authenticated CRM HFR search. The
	# onboarding-specific fields below are only endpoint paths because Client
	# Registry and owner lookup are different resources from normal facility
	# search.
	hfr_settings = frappe.get_single("CRM HFR Settings")
	if not hfr_settings.hfr_enabled:
		frappe.throw(_("HFR integration is not enabled."), ConfigurationError)

	return {
		"base_url": _text(hfr_settings.hfr_url),
		"username": _text(hfr_settings.hfr_username),
		"password": hfr_settings.get_password("hfr_password", raise_exception=False) or "",
		"owner_path": _text(_setting("facility_onboarding_hfr_owner_path"))
		or "/v1/hfr/fetch-facilities-by-owner",
		"facility_path": _text(_setting("facility_onboarding_hfr_facility_path")) or "/v1/hfr/fetch-facility",
		"client_path": _text(_setting("facility_onboarding_client_registry_path"))
		or "/client-registry/fetch-client",
		"jwt_expiry": int(hfr_settings.hfr_jwt_expiry or 20000),
	}


def _password_setting(fieldname: str) -> str:
	try:
		settings = frappe.get_single("CRM Opt-In Settings")
		return settings.get_password(fieldname, raise_exception=False) or ""
	except Exception:
		return ""


def _jwt_token(config: dict[str, Any]) -> str:
	if not config["base_url"] or not config["username"] or not config["password"]:
		frappe.throw(_("Facility registry integration is not configured."), ConfigurationError)
	if not jwt:
		frappe.throw(_("Facility registry authentication is unavailable."), ConfigurationError)
	return jwt.encode(
		{"key": config["username"], "exp": int(time.time()) + config["jwt_expiry"]},
		config["password"],
		algorithm="HS256",
	)


def _request(
	config: dict[str, Any], path: str, params: dict[str, Any], *, allow_no_facilities: bool = False
) -> Any:
	try:
		response = requests.get(
			config["base_url"].rstrip("/") + "/" + path.lstrip("/"),
			params=params,
			headers={
				"Authorization": "Bearer %s" % _jwt_token(config),
				"Content-Type": "application/json",
				"Accept": "application/json",
			},
			timeout=30,
		)
		if allow_no_facilities and response.status_code == 404:
			body = response.json()
			message = body.get("message") if isinstance(body, dict) else None
			if (
				isinstance(message, dict)
				and _text(message.get("message")).casefold() == "no facilities found for this owner"
			):
				return body
		response.raise_for_status()
		return response.json()
	except requests.exceptions.Timeout:
		frappe.throw(_("The registry took too long to respond. Please try again."), frappe.ValidationError)
	except requests.exceptions.RequestException as exc:
		# Exception text can embed the request URL, which carries the owner ID.
		frappe.log_error(
			title="CRM facility onboarding registry request",
			message="Request failed (%s)" % type(exc).__name__,
		)
		frappe.throw(
			_("The registry is temporarily unavailable. Please try again shortly."), frappe.ValidationError
		)
	except ValueError:
		frappe.log_error(
			title="CRM facility onboarding invalid registry response", message="Response was not valid JSON"
		)
		frappe.throw(
			_("The registry returned an invalid response. Please try again shortly."), frappe.ValidationError
		)


def _client_registry_person(id_type: str, id_number: str) -> dict[str, Any] | None:
	config = _onboarding_config()
	id_type_map = {
		"national_id": "National ID",
		"passport": "Passport",
		"foreigner_id": "Foreigner ID",
		"alien_id": "Alien ID",
	}
	payload = {
		"identification_type": id_type_map.get(id_type.lower(), id_type),
		"identification_number": id_number,
	}
	response = _request(config, config["client_path"], {"payload": json.dumps(payload)})
	message = response.get("message") if isinstance(response, dict) else {}
	if isinstance(message, str) or not isinstance(message, dict):
		return None
	if int(message.get("total") or 0) < 1:
		return None
	rows = message.get("result") or []
	if not isinstance(rows, list):
		return None
	expected_type = id_type_map.get(id_type.lower(), id_type)
	matches = [
		row
		for row in rows
		if isinstance(row, dict)
		and _text(row.get("identification_number")).casefold() == id_number.casefold()
		and _normalize_id_type(row.get("identification_type")) == _normalize_id_type(expected_type)
	]
	return matches[0] if len(matches) == 1 else None


def _hfr_facilities_for_owner(id_number: str) -> list[dict[str, Any]]:
	config = _onboarding_config()
	response = _request(
		config,
		config["owner_path"],
		{"owner_id_number": id_number},
		allow_no_facilities=True,
	)
	if not isinstance(response, dict):
		frappe.throw(_("The registry returned an invalid response. Please try again shortly."), frappe.ValidationError)
	message = response.get("message")
	if isinstance(message, dict):
		if _text(message.get("message")).casefold() == "no facilities found for this owner":
			return []
		data = message.get("data")
		if isinstance(data, dict) and "facilities" in data:
			rows = data["facilities"]
		elif "facilities" in message:
			rows = message["facilities"]
		else:
			rows = None
	else:
		rows = None
	if rows is None and isinstance(response.get("data"), dict) and "facilities" in response["data"]:
		rows = response["data"]["facilities"]
	if rows is None and "facilities" in response:
		rows = response["facilities"]
	if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
		frappe.throw(_("The registry returned an invalid response. Please try again shortly."), frappe.ValidationError)
	return rows


def _challenge_lock_name(token: str) -> str:
	return "crm_facility_onboarding_challenge_%s" % _otp_hash(token)[:24]


def _facility_row(row: dict[str, Any]) -> dict[str, Any]:
	fid = _text(
		row.get("facility_id")
		or row.get("facility_fid")
		or row.get("hie_id")
		or row.get("registration_number")
	)
	mfl = _text(row.get("facility_code") or row.get("facility_mfl") or row.get("mfl_code"))
	facility_level = _text(row.get("facility_level")) or _text(row.get("kephl_level"))
	return {
		"facility_id": fid,
		"mfl_code": mfl or fid,
		"facility_name": _text(row.get("facility_name")),
		"classification": facility_level,
		"facility_level": facility_level,
		"facility_type": _text(row.get("facility_type")),
		"facility_category": _text(row.get("category") or row.get("facility_category")),
		"number_of_beds": frappe.utils.cint(row.get("number_of_beds") or row.get("bed_count")),
		"county": _text(row.get("county")),
		"sub_county": _text(row.get("sub_county")),
		"owner_type": _text(row.get("facility_owner_type") or row.get("owner_type")),
		"registration_number": _text(row.get("registration_number")),
		"license_number": _text(row.get("license_number")),
	}


def _facility_licence_values(facility: dict[str, Any]) -> dict[str, str]:
	# The HMIS setup payload needs the HFR licence or registration number.
	return {
		fieldname: _text(facility.get(fieldname))
		for fieldname in ("license_number", "registration_number")
		if _text(facility.get(fieldname))
	}


def _allowed_facility_level_keys() -> set[str]:
	"""Read the current administrator whitelist; blank configuration allows none."""
	configured = _setting("self_onboarding_allowed_facility_levels")
	if not isinstance(configured, str):
		return set()
	allowed_levels = set()
	for level in re.split(r"\r\n|\r|\n", configured):
		key = _facility_level_key(level)
		if key:
			allowed_levels.add(key)
	return allowed_levels


def _facility_level_key(value: Any) -> str:
	"""Canonicalize display-equivalent HFR levels without fuzzy matching."""
	normalized = unicodedata.normalize("NFKC", _text(value))
	normalized = re.sub(r"[\u200b\u2060\ufeff]", " ", normalized)
	return " ".join(normalized.split()).casefold()


def _facility_level_eligibility(facility: dict[str, Any], allowed_levels: set[str]) -> dict[str, Any]:
	level = _facility_level_key(facility.get("facility_level"))
	if not level:
		return {
			"onboarding_eligible": False,
			"facility_eligibility_reason": "missing_level",
		}
	if level not in allowed_levels:
		return {
			"onboarding_eligible": False,
			"facility_eligibility_reason": "level_not_allowed",
		}
	return {"onboarding_eligible": True, "facility_eligibility_reason": ""}


def _facilities_for_response(
	facilities: list[dict[str, Any]], session: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
	allowed_levels = _allowed_facility_level_keys()
	onboarded = _existing_lead_deal_facility_conflicts(facilities, session or {})
	return [
		{
			**facility,
			**_facility_level_eligibility(facility, allowed_levels),
			"onboarding_blocked": _text(facility.get("facility_id")) in onboarded,
			"onboarding_block_reason": "already_onboarded"
			if _text(facility.get("facility_id")) in onboarded
			else "",
		}
		for facility in facilities
	]


def _session_key(token: str) -> str:
	# This is a cache namespace for an opaque, random bearer token—not a user
	# password. A keyed digest prevents the raw token from becoming a Redis key
	# and avoids using an unkeyed password-like hash construction.
	secret = _password_setting("optin_signing_key") or frappe.conf.get("encryption_key") or "crm"
	digest = hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
	return "crm_facility_onboarding:%s" % digest


def _session(token: str) -> dict[str, Any] | None:
	if not token:
		return None
	try:
		value = frappe.cache().get_value(_session_key(token))
		payload = frappe.parse_json(value) if value else None
		if payload and payload.get("person_sealed"):
			payload["person"] = frappe.parse_json(decrypt(payload.pop("person_sealed")))
		if payload and payload.get("facilities_sealed"):
			payload["facilities"] = frappe.parse_json(decrypt(payload.pop("facilities_sealed")))
		if payload and payload.get("identity_number_sealed"):
			payload["identity_number"] = decrypt(payload.pop("identity_number_sealed"))
		if payload and int(payload.get("expires_at") or 0) > int(time.time()):
			return payload
		if value:
			frappe.cache().delete_value(_session_key(token))
	except Exception:
		return None
	return None


def _save_session(token: str, payload: dict[str, Any]) -> None:
	payload["expires_at"] = int(time.time()) + SESSION_TTL_SECONDS
	to_store = json.loads(json.dumps(payload))
	if "person" in to_store:
		to_store["person_sealed"] = encrypt(json.dumps(to_store.pop("person")))
	if "facilities" in to_store:
		to_store["facilities_sealed"] = encrypt(json.dumps(to_store.pop("facilities")))
	if "identity_number" in to_store:
		to_store["identity_number_sealed"] = encrypt(to_store.pop("identity_number"))
	frappe.cache().set_value(_session_key(token), json.dumps(to_store), expires_in_sec=SESSION_TTL_SECONDS)


def _session_or_error(token: str, *, verified: bool = False) -> dict[str, Any]:
	session = _session(_text(token))
	if not session or (verified and not session.get("verified")):
		frappe.throw(_("This onboarding session has expired. Please start again."), frappe.PermissionError)
	return session


def _mask_email(value: str) -> str:
	local, _, domain = _text(value).partition("@")
	return (local[:1] + "***@" + domain) if domain else "***"


def _mask_phone(value: str) -> str:
	digits = "".join(ch for ch in _text(value) if ch.isdigit())
	return (digits[:3] + "******" + digits[-2:]) if len(digits) >= 7 else "***"


def _person_preview(person: dict[str, Any]) -> dict[str, Any]:
	return {
		"full_name": " ".join(
			part for part in (_text(person.get("first_name")), _text(person.get("last_name"))) if part
		),
		"email": _mask_email(person.get("email")),
		"phone": _mask_phone(person.get("phone")),
	}


def _otp_hash(value: str) -> str:
	secret = _password_setting("optin_signing_key") or frappe.conf.get("encryption_key") or "crm"
	return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _preferred_channel() -> str:
	return "sms" if _text(_setting("facility_onboarding_preferred_otp_channel")).lower() == "sms" else "email"


def _decoy_destination(identity_hash: str, channel: str) -> str:
	# Keyed and deterministic so repeated probes of an unknown ID look like a real contact.
	digest = _otp_hash("decoy|%s|%s" % (channel, identity_hash))
	if channel == "sms":
		return "254******%02d" % (int(digest[4:8], 16) % 100)
	letter = "abcdefghijklmnopqrstuvwxyz"[int(digest[:2], 16) % 26]
	return "%s***@%s" % (letter, _DECOY_DOMAINS[int(digest[2:4], 16) % len(_DECOY_DOMAINS)])


def _send_otp(person: dict[str, Any], otp: str) -> dict[str, str]:
	"""Deliver on the preferred channel, then the other; never log contacts or the code."""
	from crm.api.optin import _send_otp_sms, _sms_gateway_configured

	email = _text(person.get("email"))
	phone = _text(person.get("phone"))
	preferred = _preferred_channel()
	for channel in (preferred, "sms" if preferred == "email" else "email"):
		try:
			if channel == "email" and email:
				reference = secrets.token_hex(6).upper()
				queue = frappe.sendmail(
					recipients=[email],
					subject="CareverseHIMS — Facility verification code %s · OTP ID %s" % (otp, reference),
					message=branded_email_html(
						heading="Your CareverseHIMS verification code",
						intro_html=(
							"<p style='margin:0'>Enter this one-time code to verify your email address "
							"and continue onboarding your facility.</p>"
						),
						highlight_html=(
							"<div style='text-align:center'>"
							"<p style='margin:0 0 10px;color:#6b7280;font-size:11px;font-weight:700;"
							"letter-spacing:1.2px;text-transform:uppercase'>One-time passcode</p>%s</div>"
							% otp_code_block(otp)
						),
						note_html=(
							"This code expires in 10 minutes. Never share it; Tiberbu support will never ask for it. "
							"If you did not request it, you can ignore this email. "
							"Reference: <strong>%s</strong>." % reference
						),
					),
					now=True,
				)
				schedule_email_queue_redaction(queue, OTP_QUEUE_REDACTION)
				return {"channel": "email", "masked_destination": _mask_email(email), "status": "sent"}
			if channel == "sms" and phone and _sms_gateway_configured():
				_send_otp_sms(phone, otp, OTP_BRAND)
				return {"channel": "sms", "masked_destination": _mask_phone(phone), "status": "sent"}
		except Exception as exc:
			frappe.log_error(
				title="CRM facility onboarding OTP delivery",
				message="%s delivery failed (%s)" % (channel, type(exc).__name__),
			)
	return {"channel": "", "masked_destination": "", "status": "unavailable"}


def _evidence(
	event: str, token: str, session: dict[str, Any] | None = None, *, commit: bool = False, **fields
):
	"""Append onboarding evidence; a logging failure never blocks the customer."""
	try:
		record_event(
			event,
			session_ref=evidence_ref(token),
			subject_ref=evidence_ref((session or {}).get("identity_hash") or ""),
			**fields,
		)
		if commit:
			# Failure responses roll the request back, so persist the evidence first.
			frappe.db.commit()  # nosemgrep: frappe-manual-commit
	except Exception as exc:
		frappe.log_error(
			title="CRM facility onboarding evidence",
			message="Evidence write failed (%s)" % type(exc).__name__,
		)


def _delivery_payload(session: dict[str, Any], now: int) -> dict[str, Any]:
	identity_hash = _text(session.get("identity_hash"))
	delivery = session.get("delivery") or {}
	channel = _text(delivery.get("channel")) or _preferred_channel()
	masked_destination = _text(delivery.get("masked_destination"))
	if session.get("delivery_mask_decoy") or not masked_destination:
		masked_destination = _decoy_destination(identity_hash, channel)
	status = _text(delivery.get("status")) or "unavailable"
	resend_after = 0
	if status != "unavailable":
		resend_after = max(
			0,
			int(session.get("otp_sent_at") or 0) + OTP_RESEND_SECONDS - now,
		)
	return {
		"channel": channel or None,
		"masked_destination": masked_destination,
		"status": status,
		"expires_in": max(0, int(session.get("otp_expires_at") or 0) - now),
		"resend_after": resend_after,
	}


def _rate_limited(key: str, limit: int = 5, ttl: int = 600) -> bool:
	rate_key = "crm_facility_onboarding_rate:%s" % hashlib.sha256(key.encode()).hexdigest()
	count = int(frappe.cache().get_value(rate_key) or 0)
	if count >= limit:
		return True
	frappe.cache().set_value(rate_key, count + 1, expires_in_sec=ttl)
	return False


def _public_network(partner_id: str) -> dict[str, Any] | None:
	partner_id = _text(partner_id) or _text(_setting("facility_onboarding_default_partner_id"))
	if not PARTNER_ID_RE.fullmatch(partner_id):
		return None
	rows = frappe.get_list(
		"CRM Opt-In Network",
		filters={"partner_id": partner_id, "enabled": 1},
		fields=[
			"name",
			"slug",
			"display_name",
			"logo_url",
			"primary_colour",
			"contact_email",
			"footer_legal_name",
		],
		limit=1,
		ignore_permissions=True,
	)
	return rows[0] if rows else None


def _token_packages() -> list[dict[str, Any]]:
	settings = frappe.get_single("CRM Opt-In Settings")
	price_list = _text(settings.get("token_price_list"))
	if not price_list:
		return []
	packages = []
	for row in settings.get("token_packages") or []:
		item_code = _text(row.get("item_code"))
		if not item_code or not int(row.get("enabled") or 0):
			continue
		price = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "price_list": price_list, "selling": 1},
			["price_list_rate", "currency"],
			as_dict=True,
		)
		if not price:
			continue
		packages.append(
			{
				"item_code": item_code,
				"display_name": _text(row.get("display_name")),
				"description": _text(row.get("description")),
				"coverage_summary": _text(row.get("coverage_summary")),
				"coverage_metrics": row.get("coverage_metrics") or "",
				"token_quantity": int(row.get("token_quantity") or 0),
				"billing_period": _text(row.get("billing_period")) or "Monthly",
				"price": float(price.get("price_list_rate") or 0),
				"currency": _text(price.get("currency")) or "KES",
				"price_list": price_list,
			}
		)
	return packages


def _default_calculator_config() -> dict[str, Any]:
	return {
		"monthly_platform_fee": 500,
		"bill_value_per_token": 750.0,
		"default_avg_bill": 1500.0,
		"default_operating_days": 24,
		"service_points": [
			{
				"id": "registration",
				"name": "Patient registration / check-in",
				"tokens": 6,
				"default_frequency": 0.2,
				"description": "Per completed patient registration / visit event (typically ~20% new intakes)",
				"applies_to": ["opd", "ipd"],
			},
			{
				"id": "consultation",
				"name": "Consultation visit",
				"tokens": 3,
				"default_frequency": 1.0,
				"description": "Per completed consultation encounter",
				"applies_to": ["opd", "ipd"],
			},
			{
				"id": "laboratory",
				"name": "Laboratory order",
				"tokens": 6,
				"default_frequency": 0.5,
				"description": "Per completed laboratory investigation order",
				"applies_to": ["opd", "ipd"],
			},
			{
				"id": "prescription",
				"name": "Prescription processing",
				"tokens": 6,
				"default_frequency": 0.5,
				"description": "Per completed prescription order",
				"applies_to": ["opd", "ipd"],
			},
			{
				"id": "imaging",
				"name": "Imaging order (X-ray, Ultrasound)",
				"tokens": 12,
				"default_frequency": 0.1,
				"description": "Per completed diagnostic imaging order",
				"applies_to": ["opd", "ipd"],
			},
			{
				"id": "procedure",
				"name": "Medical / Minor surgical procedure",
				"tokens": 12,
				"default_frequency": 0.05,
				"description": "Exempt for OPD-only; charged for OPD & IPD facilities",
				"applies_to": ["ipd"],
			},
			{
				"id": "inpatient_admission",
				"name": "Inpatient admission",
				"tokens": 3,
				"default_frequency": 0.05,
				"description": "Exempt for OPD-only; charged for OPD & IPD facilities",
				"applies_to": ["ipd"],
			},
			{
				"id": "program_visit",
				"name": "Chronic care / Program visit",
				"tokens": 6,
				"default_frequency": 0.05,
				"description": "Per completed specialized clinic or program visit",
				"applies_to": ["opd", "ipd"],
			},
		],
		"presets": [
			{
				"id": "solo",
				"label": "Small Practice / Solo Clinic",
				"description": "Pilots, dispensaries & community clinics",
				"facility_type": "opd",
				"daily_patients": 5,
				"avg_bill": 1500,
				"operating_days": 24,
			},
			{
				"id": "active_opd",
				"label": "Active Outpatient Clinic",
				"description": "Steady daily patient volume & diagnostics",
				"facility_type": "opd",
				"daily_patients": 15,
				"avg_bill": 1500,
				"operating_days": 24,
			},
			{
				"id": "medical_center",
				"label": "Medical Center / Hospital",
				"description": "High volume with inpatient wards & procedures",
				"facility_type": "ipd",
				"daily_patients": 30,
				"avg_bill": 2500,
				"operating_days": 24,
			},
		],
	}


def _calculator_config() -> dict[str, Any]:
	defaults = _default_calculator_config()
	try:
		settings = frappe.get_single("CRM Opt-In Settings")
	except Exception:
		return defaults

	monthly_platform_fee = settings.get("token_calc_monthly_platform_fee")
	bill_value_per_token = settings.get("token_calc_bill_value_per_token")
	default_avg_bill = settings.get("token_calc_default_avg_bill")
	default_operating_days = settings.get("token_calc_default_operating_days")
	raw_json = settings.get("token_calc_parameters_json")

	config = dict(defaults)
	if monthly_platform_fee is not None and str(monthly_platform_fee).strip() != "":
		try:
			config["monthly_platform_fee"] = int(monthly_platform_fee)
		except (ValueError, TypeError):
			pass
	if bill_value_per_token is not None and str(bill_value_per_token).strip() != "":
		try:
			config["bill_value_per_token"] = float(bill_value_per_token)
		except (ValueError, TypeError):
			pass
	if default_avg_bill is not None and str(default_avg_bill).strip() != "":
		try:
			config["default_avg_bill"] = float(default_avg_bill)
		except (ValueError, TypeError):
			pass
	if default_operating_days is not None and str(default_operating_days).strip() != "":
		try:
			config["default_operating_days"] = int(default_operating_days)
		except (ValueError, TypeError):
			pass

	if raw_json:
		try:
			parsed = json.loads(raw_json)
			if isinstance(parsed, dict):
				if "service_points" in parsed and isinstance(parsed["service_points"], list):
					config["service_points"] = parsed["service_points"]
				if "presets" in parsed and isinstance(parsed["presets"], list):
					config["presets"] = parsed["presets"]
				if "monthly_platform_fee" in parsed and monthly_platform_fee is None:
					config["monthly_platform_fee"] = int(parsed["monthly_platform_fee"])
				if "bill_value_per_token" in parsed and bill_value_per_token is None:
					config["bill_value_per_token"] = float(parsed["bill_value_per_token"])
				if "default_avg_bill" in parsed and default_avg_bill is None:
					config["default_avg_bill"] = float(parsed["default_avg_bill"])
				if "default_operating_days" in parsed and default_operating_days is None:
					config["default_operating_days"] = int(parsed["default_operating_days"])
		except Exception:
			pass

	return config


# nosemgrep: guest-whitelisted-method -- public calculator configuration for token sizing and planning.
@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_token_calculator_config():
	return {"success": True, "data": _calculator_config()}


def _resolve_self_onboarding_terms() -> tuple[str, str]:
	"""Return the configured, rendered self-onboarding Terms document."""
	document_name = _text(_setting("self_onboarding_tc_document"))
	if not document_name:
		# active_tc_document is the configured Default Terms and Conditions
		# document shared with standard opt-in. Do not substitute a hard-coded
		# title: admins may configure a different default document.
		document_name = _text(_setting("active_tc_document"))
	if not document_name or not frappe.db.exists("Terms and Conditions", document_name):
		frappe.throw(
			_("The Terms and Conditions are currently unavailable. Please contact support."),
			frappe.ValidationError,
		)

	try:
		terms_document = frappe.get_doc("Terms and Conditions", document_name)
		terms_source = _text(terms_document.get("terms"))
		if not terms_source:
			frappe.throw(
				_("The Terms and Conditions are currently unavailable. Please contact support."),
				frappe.ValidationError,
			)

		# Terms are displayed before a token-based submission has selected a
		# network, contact email, or pricing. Supply neutral server-owned values
		# for the variables used by the default terms template so rendering does
		# not depend on a network being present in the browser request.
		from crm.utils.jinja import render_terms_template

		context = {
			"network": frappe._dict(display_name="Tiberbu HMIS"),
			"contact": frappe._dict(email="the authorised facility representative"),
			"date": "On acceptance",
			"technology_delivery_partner_name": "Tiberbu Healthnet Solutions Limited",
			"technology_delivery_partner_short_name": "Tiberbu",
			"technology_delivery_partner_role": "technology delivery partner",
			"vat_label": "VAT",
			"pricing_table": "Facility pricing will be confirmed during onboarding.",
			"optional_services_table": "No optional services selected.",
			"contract_totals": frappe._dict(
				monthly_exclusive_vat_display="To be confirmed",
				monthly_vat_display="To be confirmed",
				monthly_inclusive_vat_display="To be confirmed",
				selected_term_exclusive_vat_display="To be confirmed",
				selected_term_vat_display="To be confirmed",
				selected_term_inclusive_vat_display="To be confirmed",
			),
			"commitment_years_label": "As confirmed during onboarding",
			"invoice_issue_timing_label": "As confirmed during onboarding",
		}
		rendered_html = str(render_terms_template(terms_source, context))
	except Exception:
		frappe.throw(
			_("The Terms and Conditions are currently unavailable. Please contact support."),
			frappe.ValidationError,
		)
	if not rendered_html.strip():
		frappe.throw(
			_("The Terms and Conditions are currently unavailable. Please contact support."),
			frappe.ValidationError,
		)
	return _text(terms_document.get("name")) or document_name, rendered_html


# nosemgrep: guest-whitelisted-method -- terms are returned only to an OTP-verified onboarding session.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_self_onboarding_terms(session_token: Any):
	"""Return the current self-onboarding Terms and bind its snapshot to the session."""
	token = _text(session_token)
	session = _session_or_error(token, verified=True)
	document_name, rendered_html = _resolve_self_onboarding_terms()
	content_hash = hashlib.sha256(rendered_html.encode()).hexdigest()
	session["accepted_terms_document"] = document_name
	session["accepted_terms_hash"] = content_hash
	_save_session(token, session)
	return {"document": document_name, "rendered_html": rendered_html, "content_hash": content_hash}


def _validate_self_onboarding_terms(session: dict[str, Any], accepted_terms_hash: Any):
	"""Require the submitted hash to match the displayed and current Terms snapshot."""
	accepted_hash = frappe.utils.cstr(accepted_terms_hash or "")
	accepted_document = _text(session.get("accepted_terms_document"))
	accepted_session_hash = _text(session.get("accepted_terms_hash"))
	if (
		not re.fullmatch(r"[0-9a-f]{64}", accepted_hash, flags=re.ASCII)
		or not accepted_document
		or not accepted_session_hash
	):
		frappe.throw(
			_("Please review the current Terms and Conditions before continuing."), frappe.ValidationError
		)

	current_document, current_html = _resolve_self_onboarding_terms()
	current_hash = hashlib.sha256(current_html.encode()).hexdigest()
	if not (
		current_document == accepted_document
		and hmac.compare_digest(accepted_hash, accepted_session_hash)
		and hmac.compare_digest(current_hash, accepted_session_hash)
	):
		frappe.throw(
			_("The Terms and Conditions have changed. Please review the current Terms before continuing."),
			frappe.ValidationError,
		)
	return {
		"document": current_document,
		"hash": current_hash,
		"accepted_at": frappe.utils.now_datetime(),
	}


# nosemgrep: guest-whitelisted-method -- generic identity responses, rate limiting, HFR ownership binding, and OTP verification prevent enumeration and unauthorised facility access.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def start_identity(identification_type: Any, identification_number: Any):
	"""Resolve a Client Registry contact and send its OTP before any HFR lookup."""
	id_type = _text(identification_type)
	id_number = _text(identification_number)
	if not id_type or not ID_RE.fullmatch(id_number) or _rate_limited("start:%s" % _client_ip()):
		frappe.throw(
			_("We could not verify those details. Please check and try again."), frappe.ValidationError
		)
	cr_failure = ""
	try:
		person = _client_registry_person(id_type, id_number)
	except Exception as exc:
		frappe.log_error(
			title="CRM facility onboarding CR lookup", message="Lookup failed (%s)" % type(exc).__name__
		)
		person = None
		cr_failure = "lookup failed"
	if not person and not cr_failure:
		cr_failure = "no exact match"

	token = secrets.token_urlsafe(32)
	otp = "%06d" % secrets.randbelow(1_000_000)
	contact_email = _text(person.get("email")).lower() if person else ""
	contact_phone = _text(person.get("phone")) if person else ""
	if person and not (contact_email or contact_phone):
		cr_failure = "no usable contact"
	lookup_valid = not cr_failure
	if not lookup_valid:
		person = {}
		contact_email = ""
		contact_phone = ""
	identity_hash = hashlib.sha256((id_type.lower() + "|" + id_number.lower()).encode()).hexdigest()
	identity_ref = _identity_reference(id_type, id_number)
	now = int(time.time())
	payload = {
		"verified": False,
		"lookup_valid": lookup_valid,
		"id_type": id_type,
		"identity_hash": identity_hash,
		"identity_ref": identity_ref,
		"person": {
			"first_name": _text(person.get("first_name")),
			"last_name": _text(person.get("last_name")),
			"email": contact_email,
			"phone": contact_phone,
		},
		"otp_hash": _otp_hash(otp),
		"otp_attempts": 0,
		"otp_expires_at": now + OTP_TTL_SECONDS,
		"otp_sent_at": now,
		"resend_count": 0,
	}
	if lookup_valid:
		# HFR receives the identity only after OTP succeeds. Keep it encrypted in
		# the opaque session until then, and never put facility rows in this state.
		payload["identity_number"] = id_number
	if lookup_valid:
		payload["delivery"] = _send_otp(payload["person"], otp)
		payload["delivery_mask_decoy"] = payload["delivery"]["status"] == "unavailable"
	else:
		payload["delivery_mask_decoy"] = True
		channel = _preferred_channel()
		payload["delivery"] = {
			"channel": channel,
			"masked_destination": _decoy_destination(identity_hash, channel),
			"status": "unavailable",
		}
	_save_session(token, payload)
	_evidence(
		"lookup",
		token,
		payload,
		outcome="ok" if lookup_valid else "failed",
		detail="contact resolved" if lookup_valid else ("CR/Afyangu: %s" % cr_failure),
	)
	if lookup_valid:
		_evidence(
			"otp_sent",
			token,
			payload,
			outcome="ok" if payload["delivery"]["status"] == "sent" else "failed",
			channel=payload["delivery"]["channel"] or "",
		)
	# Unknown IDs, missing contacts, and registry failures return the same
	# challenge shape. Facility ownership is deliberately checked after OTP.
	return {
		"success": True,
		"data": {
			"session_token": token,
			"challenge_started": True,
			"delivery": _delivery_payload(payload, now),
		},
	}


# nosemgrep: guest-whitelisted-method -- this only resends an OTP for an opaque, rate-limited onboarding session.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def resend_otp(session_token: Any):
	token = _text(session_token)
	if _rate_limited("resend:%s" % _client_ip(), limit=10):
		frappe.throw(_("Too many code requests. Please wait and try again."), frappe.ValidationError)
	with filelock(_challenge_lock_name(token), timeout=60):
		return _resend_otp_locked(token)


def _resend_otp_locked(token: str):
	session = _session_or_error(token)
	if session.get("verified"):
		frappe.throw(_("This onboarding session has already verified its contact."), frappe.PermissionError)
	now = int(time.time())
	if (
		(session.get("delivery") or {}).get("status") != "unavailable"
		and now - int(session.get("otp_sent_at") or 0) < OTP_RESEND_SECONDS
	):
		return {"success": True, "data": {"sent": True, "delivery": _delivery_payload(session, now)}}
	if int(session.get("resend_count") or 0) >= OTP_MAX_RESENDS:
		frappe.throw(_("Too many code requests. Please start again."), frappe.ValidationError)
	otp = "%06d" % secrets.randbelow(1_000_000)
	session.update(
		{
			"otp_hash": _otp_hash(otp),
			"otp_attempts": 0,
			"otp_sent_at": now,
			"otp_expires_at": now + OTP_TTL_SECONDS,
			"resend_count": int(session.get("resend_count") or 0) + 1,
		}
	)
	if session.get("lookup_valid"):
		session["delivery"] = _send_otp(session["person"], otp)
		session["delivery_mask_decoy"] = session["delivery"]["status"] != "sent"
		_evidence(
			"otp_sent",
			token,
			session,
			outcome="ok" if session["delivery"]["status"] == "sent" else "failed",
			channel=session["delivery"]["channel"] or "",
			detail="resend",
		)
	_save_session(token, session)
	return {"success": True, "data": {"sent": True, "delivery": _delivery_payload(session, now)}}


# nosemgrep: guest-whitelisted-method -- OTP expiry, bounded attempts, and the verified session gate all facility data.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def verify_otp(session_token: Any, otp: Any):
	token = _text(session_token)
	with filelock(_challenge_lock_name(token), timeout=60):
		return _verify_otp_locked(token, otp)


def _verify_otp_locked(token: str, otp: Any):
	session = _session_or_error(token)
	if int(time.time()) > int(session.get("otp_expires_at") or 0):
		_evidence("otp_failed", token, session, outcome="failed", detail="expired", commit=True)
		frappe.throw(_("That code has expired. Please request a new one."), frappe.PermissionError)
	if session.get("otp_attempts", 0) >= OTP_MAX_ATTEMPTS or not hmac.compare_digest(
		session.get("otp_hash", ""), _otp_hash(_text(otp))
	):
		session["otp_attempts"] = int(session.get("otp_attempts") or 0) + 1
		_save_session(token, session)
		if session["otp_attempts"] <= OTP_MAX_ATTEMPTS + 1:
			_evidence(
				"otp_failed",
				token,
				session,
				outcome="blocked" if session["otp_attempts"] > OTP_MAX_ATTEMPTS else "failed",
				detail="attempt %d" % session["otp_attempts"],
				commit=True,
			)
		frappe.throw(_("The verification code is incorrect or expired."), frappe.PermissionError)
	if not session.get("lookup_valid"):
		_evidence("otp_failed", token, session, outcome="failed", detail="unmatched", commit=True)
		frappe.cache().delete_value(_session_key(token))
		frappe.throw(_("The verification code is incorrect or expired."), frappe.PermissionError)
	session["verified"] = True
	session["otp_hash"] = ""
	# Consume the challenge before any downstream HFR call. If the registry call
	# is interrupted, the same OTP cannot be replayed to create duplicate evidence.
	_save_session(token, session)
	_evidence("otp_verified", token, session, channel=(session.get("delivery") or {}).get("channel") or "")
	return _resolve_verified_hfr(token, session)


def _resolve_verified_hfr(token: str, session: dict[str, Any]) -> dict[str, Any]:
	"""Resolve and bind HFR facilities to an OTP-verified session, with bounded retries."""
	lock_name = "crm_facility_onboarding_hfr_%s" % _otp_hash(token)[:24]
	with filelock(lock_name, timeout=60):
		# Read and reserve the next attempt under a per-session lock so concurrent
		# retries cannot race the persisted retry cap or overwrite ready state.
		session = _session_or_error(token, verified=True)
		if session.get("hfr_state") == "ready":
			return {
				"success": True,
				"data": {
					"identity": _person_preview(session["person"]),
					"account_email": _text(session["person"].get("email")).lower(),
					"facilities": _facilities_for_response(session.get("facilities") or [], session),
					"state": "ready",
				},
			}
		lookup_count = int(session.get("hfr_lookup_count") or 0)
		if lookup_count >= HFR_MAX_LOOKUPS:
			return {"success": True, "data": {"state": "hfr_pending", "retryable": False}}
		session["hfr_lookup_count"] = lookup_count + 1
		_save_session(token, session)
		try:
			facilities = _hfr_facilities_for_owner(session["identity_number"])
		except Exception as exc:
			frappe.log_error(
				title="CRM facility onboarding HFR lookup",
				message="Lookup failed (%s)" % type(exc).__name__,
			)
			session["hfr_state"] = "pending"
			_save_session(token, session)
			_evidence("lookup", token, session, outcome="failed", detail="HFR: lookup failed")
			return {
				"success": True,
				"data": {"state": "hfr_pending", "retryable": session["hfr_lookup_count"] < HFR_MAX_LOOKUPS},
			}

		session["facilities"] = [_facility_row(row) for row in facilities]
		session["hfr_state"] = "ready"
		_save_session(token, session)
		_evidence("lookup", token, session, outcome="ok", detail="HFR: %d facilities" % len(session["facilities"]))
		return {
			"success": True,
			"data": {
				"identity": _person_preview(session["person"]),
				"account_email": _text(session["person"].get("email")).lower(),
				"facilities": _facilities_for_response(session["facilities"], session),
				"state": "ready",
			},
		}


# nosemgrep: guest-whitelisted-method -- reuses an opaque session that has already passed OTP verification; bounded HFR retries reveal only owned facilities.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def retry_hfr(session_token: Any):
	token = _text(session_token)
	session = _session_or_error(token, verified=True)
	return _resolve_verified_hfr(token, session)


# nosemgrep: guest-whitelisted-method -- only public package metadata is returned after strict six-digit Network validation.
@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_catalog(partner_id: Any = None):
	partner_id = _text(partner_id)
	partner = _public_network(partner_id)
	if partner_id and not partner:
		frappe.throw(
			_("That Network ID is not available. Check the six digits and try again."), frappe.ValidationError
		)
	return {
		"success": True,
		"data": {
			"network": partner or {},
			"packages": _catalog_packages(),
			"calculator_config": _calculator_config(),
		},
	}


def _catalog_packages() -> list[dict[str, Any]]:
	"""Public package view: server-resolved ex-VAT, VAT and gross, without internal pricing records."""
	from crm.utils.quotation_tax import calculate_vat_totals

	packages = []
	try:
		for package in _token_packages():
			totals = calculate_vat_totals(package["price"])
			public = {key: value for key, value in package.items() if key != "price_list"}
			public.update(
				{
					"price_ex_vat": totals.net_total,
					"vat_amount": totals.vat_amount,
					"gross_total": totals.grand_total,
					"vat_rate": totals.vat_rate,
					"vat_label": totals.vat_label,
				}
			)
			packages.append(public)
	except Exception as exc:
		# frappe.ConfigurationError does not exist in this Frappe, so VAT config errors surface as other types.
		frappe.log_error(
			title="CRM facility onboarding catalog", message="Pricing failed (%s)" % type(exc).__name__
		)
		frappe.throw(_("Package pricing is temporarily unavailable."), frappe.ValidationError)
	return packages


def _upsert_facility_membership(
	facility: dict[str, Any], network: str, person: dict[str, Any], *, customer: str
):
	mfl = _text(facility.get("mfl_code"))
	row = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": mfl}, "name")
	if row:
		facility_doc = frappe.get_doc("CRM Pre-Qualified Facility", row)
		facility_doc.facility_name = _text(facility.get("facility_name")) or facility_doc.facility_name
		facility_doc.keph_level = _text(facility.get("classification")) or facility_doc.keph_level or "Other"
	else:
		facility_doc = frappe.get_doc(
			{
				"doctype": "CRM Pre-Qualified Facility",
				"mfl_code": mfl,
				"facility_name": _text(facility.get("facility_name")) or mfl,
				"organization": _text(facility.get("facility_name")) or mfl,
				"keph_level": _text(facility.get("classification")) or "Other",
			}
		)
	facility_doc.update(_facility_licence_values(facility))
	facility_doc.flags.skip_invitation = True
	if hasattr(facility_doc, "is_self_onboarded") or (hasattr(facility_doc, "meta") and facility_doc.meta.has_field("is_self_onboarded")):
		facility_doc.is_self_onboarded = 1
	for row_item in facility_doc.memberships or []:
		if row_item.network == network and (
			_text(getattr(row_item, "customer", "")) == customer
			or _text(row_item.contact_email).lower() == person["email"].lower()
		):
			if not frappe.get_meta("CRM Facility Membership").has_field("customer"):
				frappe.throw(_("Customer-linked facility membership is not installed. Run bench migrate and retry."), frappe.ValidationError)
			row_item.customer = customer
			row_item.contact_name = "%s %s" % (person.get("first_name", ""), person.get("last_name", ""))
			row_item.contact_email = person["email"]
			row_item.contact_phone = person.get("phone", "")
			facility_doc.save(ignore_permissions=True)
			return facility_doc
	if not frappe.get_meta("CRM Facility Membership").has_field("customer"):
		frappe.throw(_("Customer-linked facility membership is not installed. Run bench migrate and retry."), frappe.ValidationError)
	facility_doc.append(
		"memberships",
		{
			"network": network,
			"customer": customer,
			"status": "Active",
			"contact_name": "%s %s" % (person.get("first_name", ""), person.get("last_name", "")),
			"contact_email": person["email"],
			"contact_phone": person.get("phone", ""),
		},
	)
	facility_doc.save(ignore_permissions=True)
	return facility_doc


def _parse_selected_ids(selected_facility_ids: Any) -> set[str]:
	try:
		selected = (
			json.loads(selected_facility_ids)
			if isinstance(selected_facility_ids, str)
			else selected_facility_ids
		)
	except (TypeError, ValueError):
		selected = None
	if not isinstance(selected, (list, tuple, set)):
		frappe.throw(_("Select at least one facility to continue."), frappe.ValidationError)
	return {_text(value) for value in selected if _text(value)}


def _packages_for_facilities(
	selected_ids: set[str], facility_package_items: Any, legacy_package_item_code: Any = None
) -> dict[str, dict[str, Any]]:
	"""Resolve one server-catalog package per selected facility."""
	try:
		mapping = (
			json.loads(facility_package_items)
			if isinstance(facility_package_items, str)
			else facility_package_items
		)
	except (TypeError, ValueError):
		mapping = None
	if not mapping and _text(legacy_package_item_code):
		mapping = {facility_id: _text(legacy_package_item_code) for facility_id in selected_ids}
	if isinstance(mapping, dict):
		mapping = {_text(key): value for key, value in mapping.items() if _text(key)}
	if not isinstance(mapping, dict) or set(mapping) != selected_ids:
		frappe.throw(
			_("Refresh this page and choose a token package for each facility before submitting."),
			frappe.ValidationError,
		)
	packages = {row["item_code"]: row for row in _catalog_packages()}
	resolved = {}
	for facility_id in selected_ids:
		item_code = _text(mapping.get(facility_id))
		if item_code not in packages:
			frappe.throw(
				_("One or more selected token packages are no longer available. Review your choices and try again."),
				frappe.ValidationError,
			)
		resolved[facility_id] = packages[item_code]
	return resolved


def _ois_contains_facility(raw_json: Any, mfl_code: str) -> bool:
	try:
		payload = json.loads(raw_json or "{}") if isinstance(raw_json, str) else raw_json or {}
	except (TypeError, ValueError):
		return False
	if not isinstance(payload, dict):
		return False
	for facility in payload.get("facilities") or []:
		if not isinstance(facility, dict):
			continue
		canonical_mfl = _text(
			facility.get("mfl_code")
			or facility.get("facility_code")
			or facility.get("facility_mfl")
		)
		if canonical_mfl and canonical_mfl.casefold() == mfl_code.casefold():
			return True
	return False


def _ois_facility_codes(raw_json: Any) -> set[str]:
	try:
		payload = json.loads(raw_json or "{}") if isinstance(raw_json, str) else raw_json or {}
	except (TypeError, ValueError):
		return set()
	if not isinstance(payload, dict):
		return set()
	codes = set()
	for facility in payload.get("facilities") or []:
		if isinstance(facility, dict):
			code = _text(
				facility.get("mfl_code") or facility.get("facility_code") or facility.get("facility_mfl")
			)
			if code:
				codes.add(code.casefold())
	return codes


def _existing_lead_deal_facility_conflicts(
	facilities: list[dict[str, Any]], session: dict[str, Any]
) -> set[str]:
	"""Match verified HFR identifiers against existing Lead/Deal facility rows."""
	if not facilities or not getattr(frappe.local, "db", None):
		return set()
	facility_by_key: dict[str, set[str]] = {}
	facility_ids: set[str] = set()
	mfl_codes: set[str] = set()
	for facility in facilities:
		facility_id = _text(facility.get("facility_id"))
		mfl_code = _text(facility.get("mfl_code") or facility_id)
		if facility_id:
			facility_ids.add(facility_id)
			facility_by_key.setdefault(facility_id.casefold(), set()).add(facility_id)
		if mfl_code:
			mfl_codes.add(mfl_code)
			facility_by_key.setdefault(mfl_code.casefold(), set()).add(facility_id)

	deal_names = {
		_text(name)
		for name in [(session or {}).get("submission_deal"), *((session or {}).get("submitted") or {}).values()]
		if _text(name) and frappe.db.exists("CRM Deal", _text(name))
	}
	lead_names = set()
	if deal_names:
		lead_names = {
			_text(row.get("lead"))
			for row in frappe.get_all(
				"CRM Deal",
				filters={"name": ["in", list(deal_names)]},
				fields=["lead"],
				ignore_permissions=True,
				limit_page_length=0,
			)
			if _text(row.get("lead"))
		}

	blocked = set()
	for doctype in ("CRM Lead Facility", "CRM Deal Facility"):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		for fieldname, requested in (("hfr_facility_id", facility_ids), ("mfl_code", mfl_codes)):
			if not requested or not meta.has_field(fieldname):
				continue
			rows = frappe.get_all(
				doctype,
				filters={fieldname: ["in", list(requested)]},
				fields=["parent", fieldname],
				ignore_permissions=True,
				limit_page_length=0,
			)
			own_parents = lead_names if doctype == "CRM Lead Facility" else deal_names
			for row in rows:
				if _text(row.get("parent")) in own_parents:
					continue
				key = _text(row.get(fieldname)).casefold()
				blocked.update(facility_by_key.get(key, set()))
	return blocked


def _facility_conflicts(facilities: list[dict[str, Any]], network: str | None, session: dict[str, Any]):
	"""Return canonical facility IDs already enrolled or requested in this Network."""
	if not facilities:
		return set()
	conflicts = _existing_lead_deal_facility_conflicts(facilities, session)
	submitted_values = set(((session or {}).get("submitted") or {}).values()) | set(
		((session or {}).get("submitted_ois") or {}).values()
	)
	if _text((session or {}).get("submission_deal")):
		submitted_values.add(_text((session or {}).get("submission_deal")))
	submitted = {name for name in submitted_values if frappe.db.exists("CRM Opt-In Submission", name)}
	filters = {"network_slug": network} if network else {}
	ois_rows = frappe.get_all(
		"CRM Opt-In Submission",
		filters=filters,
		fields=["name", "status", "raw_json"],
		limit_page_length=0,
	)
	# This map also lets a retry resume this session's own membership/OIS pair.
	own_mfls = set().union(
		*(_ois_facility_codes(row.get("raw_json")) for row in ois_rows if _text(row.get("name")) in submitted)
	) if submitted else set()

	person_email = _text((((session or {}).get("person") or {}).get("email"))).lower()
	existing_customer = _resolve_existing_customer(session, person_email)

	deal_names = [name for name in submitted_values if frappe.db.exists("CRM Deal", name)]
	if deal_names:
		own_mfls.update(
			_text(row.get("mfl_code")).casefold()
			for row in frappe.get_all(
				"CRM Deal Facility",
				filters={"parent": ["in", deal_names], "parenttype": "CRM Deal", "parentfield": "facilities"},
				fields=["mfl_code"],
				ignore_permissions=True,
				limit_page_length=0,
			)
			if _text(row.get("mfl_code"))
		)
	for facility in facilities:
		facility_id = _text(facility.get("facility_id"))
		mfl_code = _text(facility.get("mfl_code") or facility_id)
		facility_name = frappe.db.get_value(
			"CRM Pre-Qualified Facility", {"mfl_code": mfl_code}, "name"
		)
		if facility_name and mfl_code.casefold() not in own_mfls:
			facility_doc = frappe.get_doc("CRM Pre-Qualified Facility", facility_name)
			for membership in facility_doc.memberships or []:
				if network and _text(membership.get("network")) != network:
					continue
				mem_status = _text(membership.get("status") or "Active").casefold()
				if mem_status not in {"pending", "active", "opted in", "completed", "processed"}:
					continue
				mem_email = _text(membership.get("contact_email")).lower()
				mem_cust = _text(membership.get("customer"))
				if person_email and mem_email == person_email:
					continue
				if existing_customer and mem_cust and mem_cust == existing_customer:
					continue
				conflicts.add(facility_id)
				break
		for row in ois_rows:
			if (
				_text(row.get("name")) not in submitted
				and _text(row.get("status")).casefold() in {"pending", "processing", "processed"}
				and _ois_contains_facility(row.get("raw_json"), mfl_code)
			):
				conflicts.add(facility_id)
				break
	return conflicts


def _check_onboarding_conflicts(session: dict[str, Any], selected: set[str], network: str | None = None):
	verified_facilities = session.get("facilities") or []
	by_id = {_text(row.get("facility_id")): row for row in verified_facilities if isinstance(row, dict)}
	if not selected or not selected.issubset(by_id):
		frappe.throw(
			_("One or more facilities are no longer available in this session."), frappe.ValidationError
		)
	allowed_levels = _allowed_facility_level_keys()
	eligibility_by_id = {
		facility_id: _facility_level_eligibility(facility, allowed_levels)
		for facility_id, facility in by_id.items()
	}
	ineligible = {
		facility_id
		for facility_id in selected
		if not eligibility_by_id[facility_id]["onboarding_eligible"]
	}
	if ineligible:
		return {
			"outcome": "facility_level_ineligible",
			"allowed_facility_ids": sorted(selected - ineligible),
			"ineligible_facility_ids": sorted(ineligible),
			"facility_eligibility": [
				{"facility_id": facility_id, **eligibility}
				for facility_id, eligibility in sorted(eligibility_by_id.items())
			],
		}
	identity_ref = _text(session.get("identity_ref"))
	is_existing_identity = False
	if identity_ref:
		if frappe.db.has_column("CRM Opt-In Submission", "onboarding_identity_ref"):
			filters = {"onboarding_identity_ref": identity_ref}
			prior = frappe.get_all(
				"CRM Opt-In Submission", filters=filters, fields=["name"], limit_page_length=0
			)
			own_submissions = set((session.get("submitted") or {}).values()) | set(
				(session.get("submitted_ois") or {}).values()
			)
			if any(_text(row.get("name")) not in own_submissions for row in prior):
				is_existing_identity = True
		if not is_existing_identity and frappe.get_meta("CRM Lead").has_field("cx_onboarding_identity_ref"):
			prior_leads = frappe.get_all(
				"CRM Lead",
				filters={"cx_onboarding_identity_ref": identity_ref},
				fields=["name"],
				limit_page_length=0,
				ignore_permissions=True,
			)
			own_deals = set((session.get("submitted") or {}).values())
			if session.get("submission_deal"):
				own_deals.add(session.get("submission_deal"))
			for lead_row in prior_leads:
				deal_name = frappe.db.get_value("CRM Deal", {"lead": lead_row.get("name")}, "name")
				if deal_name and deal_name not in own_deals:
					is_existing_identity = True
					break
	if not is_existing_identity:
		account_email = _text(((session.get("person") or {}).get("email"))).lower()
		if account_email and frappe.db.exists("User", {"email": account_email}):
			is_existing_identity = True

	facilities = [by_id[facility_id] for facility_id in sorted(selected)]
	already_onboarded = _existing_lead_deal_facility_conflicts(facilities, session)
	conflicts = _facility_conflicts(facilities, network, session)
	allowed = [facility_id for facility_id in sorted(selected) if facility_id not in conflicts]
	if conflicts:
		data = {
			"outcome": "facility_review",
			"allowed_facility_ids": allowed,
		}
		if already_onboarded:
			data["already_onboarded_facility_ids"] = sorted(already_onboarded)
		if is_existing_identity:
			data["is_existing_identity"] = True
		return data
	data = {"outcome": "new", "allowed_facility_ids": allowed}
	if is_existing_identity:
		data["is_existing_identity"] = True
	return data


# nosemgrep: guest-whitelisted-method -- only OTP-verified session facilities and allow-listed outcomes are returned.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def check_onboarding_conflicts(session_token: Any, selected_facility_ids: Any, partner_id: Any = None):
	token = _text(session_token)
	session = _session_or_error(token, verified=True)
	selected = _parse_selected_ids(selected_facility_ids)
	partner = _public_network(_text(partner_id))
	if not partner:
		message = (
			_("That Network ID does not exist or is not available.")
			if _text(partner_id)
			else _("The configured default Network ID is not available.")
		)
		frappe.throw(message, frappe.ValidationError)
	network = partner["name"]
	result = _check_onboarding_conflicts(session, selected, network)
	if result["outcome"] != "new":
		_evidence("lookup", token, session, outcome="blocked", detail="conflict: " + result["outcome"])
	return result


# nosemgrep: guest-whitelisted-method -- submission requires a verified session, HFR-bound facility selection, valid Network, package, account email, and terms.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_onboarding(
	session_token: Any,
	partner_id: Any,
	selected_facility_ids: Any,
	package_item_code: Any,
	account_email: Any,
	terms_accepted: Any = 0,
	accepted_terms_hash: Any = "",
	facility_package_items: Any = None,
):
	token = _text(session_token)
	session = _session_or_error(token, verified=True)
	terms_snapshot = _validate_self_onboarding_terms(session, accepted_terms_hash)
	account_email = _validate_account_email(account_email, session)
	partner_id = _text(partner_id)
	partner = _public_network(partner_id)
	if not partner:
		frappe.throw(_("That Network ID does not exist or is not available."), frappe.ValidationError)
	selected = _parse_selected_ids(selected_facility_ids)
	if not selected:
		frappe.throw(_("Select at least one facility to continue."), frappe.ValidationError)
	if not frappe.utils.cint(terms_accepted):
		frappe.throw(
			_("Accept the current Terms and Conditions before continuing."), frappe.ValidationError
		)
	if session.get("hfr_state") != "ready" or not isinstance(session.get("facilities"), list):
		frappe.throw(
			_("Facility details are not ready. Retry the facility lookup before continuing."),
			frappe.ValidationError,
		)
	facilities = [row for row in session["facilities"] if _text(row.get("facility_id")) in selected]
	if len(facilities) != len(selected):
		frappe.throw(
			_("One or more facilities are no longer available in this session."), frappe.ValidationError
		)
	packages_by_facility = _packages_for_facilities(
		selected, facility_package_items, package_item_code
	)

	identity_ref = _text(session.get("identity_ref"))
	lock_ref = evidence_ref(identity_ref) if identity_ref else evidence_ref(token)
	with filelock("crm_onboarding_submit_%s" % lock_ref[:24], timeout=60):
		# Re-read the verified server session and repeat all checks while holding an
		# identity-scoped lock shared by every session for this identity.
		session = _session_or_error(token, verified=True)
		terms_snapshot = _validate_self_onboarding_terms(session, accepted_terms_hash)
		_validate_account_email(account_email, session)
		conflicts = _check_onboarding_conflicts(session, selected, partner["name"])
		if conflicts["outcome"] != "new":
			_evidence(
				"lookup",
				token,
				session,
				outcome="blocked",
				detail="conflict: " + conflicts["outcome"],
			)
			return {"success": True, "data": conflicts}
		return _submit_selected_facilities(
			token, partner, packages_by_facility, account_email, facilities, terms_snapshot
		)


def _validate_account_email(value: Any, session: dict[str, Any] | None = None) -> str:
	"""Use the registry email bound to the OTP-verified identity, never a browser-selected address."""
	account_email = _text(((session or {}).get("person") or {}).get("email")).lower()
	validated = frappe.utils.validate_email_address(account_email).strip().lower()
	if not account_email or validated != account_email:
		frappe.throw(
			_("A valid email address is not available for this verified registry contact. Please contact support."),
			frappe.ValidationError,
		)
	requested_email = _text(value).lower()
	if requested_email and requested_email != account_email:
		frappe.throw(
			_("Customer Experience access must use the email on your verified registry profile."),
			frappe.ValidationError,
		)
	prior_account_email = _text((session or {}).get("customer_account_email")).lower()
	if prior_account_email and prior_account_email != account_email:
		frappe.throw(
			_("Use the same Customer Experience email to resume this onboarding."),
			frappe.ValidationError,
		)

	user_name = frappe.db.get_value("User", {"email": account_email}, "name")
	if user_name:
		user = frappe.db.get_value("User", user_name, ["user_type", "enabled"], as_dict=True) or {}
		if user.get("user_type") and user.get("user_type") != "Website User":
			frappe.throw(
				_("This email cannot be used for facility onboarding."),
				frappe.ValidationError,
			)
		if not frappe.utils.cint(user.get("enabled")):
			frappe.throw(
				_("This login cannot be used because the account is disabled. Contact support to restore access before continuing."),
				frappe.ValidationError,
			)

	for submission_name in (session or {}).get("submitted", {}).values():
		if not frappe.db.exists("CRM Opt-In Submission", submission_name):
			continue
		prior_email = _text(
			frappe.db.get_value("CRM Opt-In Submission", submission_name, "cx_account_email") or ""
		).lower()
		if prior_email and prior_email != account_email:
			frappe.throw(
				_("Use the same Customer Experience email to resume this onboarding."), frappe.ValidationError
			)
	return account_email


def _create_initial_deal_quote(deal, customer, facility, package):
	"""Create initial Quotation for a facility deal."""
	try:
		if not frappe.db.exists("DocType", "Quotation"):
			return None
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		if not company:
			return None
		existing = frappe.get_all(
			"Quotation",
			filters={"crm_deal": deal.name, "docstatus": ["!=", 2]},
			fields=["name"],
			limit_page_length=1,
			ignore_permissions=True,
		)
		if existing:
			return existing[0]["name"]
		from crm.utils.quotation_tax import apply_quotation_taxes

		price = float(package.get("price") or 0)
		today = frappe.utils.today()
		price_list = package.get("price_list")
		if not price_list or not frappe.db.exists("Price List", price_list):
			price_list = (
				frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
			)
		quote = frappe.get_doc({
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": customer,
			"company": company,
			"transaction_date": today,
			"valid_till": frappe.utils.add_days(today, 30),
			"selling_price_list": price_list,
			"currency": package.get("currency") or "KES",
			"order_type": "Sales",
			"crm_deal": deal.name,
		})
		tokens = int(package.get("token_quantity") or 400)
		description = package.get("description") or package.get("display_name") or package["item_code"]
		if package.get("item_code") == "CV-TOKEN-FREE" or price == 0:
			liability_val = float(tokens * 6.0)
			description = (
				f"{package.get('display_name', 'Free Trial')}: {tokens} Care Tokens granted with zero customer financial commitment. "
				f"Promotional Service Delivery Liability: KES {liability_val:,.2f} (evaluated at KES 6.00/token baseline). "
				"Customer Net Payable: KES 0.00."
			)
		quote.append(
			"items",
			{
				"item_code": package["item_code"],
				"qty": 1,
				"price_list_rate": price,
				"rate": price,
				"description": description,
			},
		)
		if frappe.db.has_column("Quotation", "crm_token_facility_mfl"):
			quote.crm_token_facility_mfl = _text(facility.get("mfl_code"))
		if frappe.db.has_column("Quotation", "crm_token_package_item"):
			quote.crm_token_package_item = package["item_code"]
		quote.flags.ignore_permissions = True
		quote.flags.ignore_mandatory = True
		try:
			apply_quotation_taxes(quote)
		except Exception:
			pass
		quote.insert(ignore_permissions=True, ignore_mandatory=True)
		return quote.name
	except Exception as exc:
		frappe.logger("crm.facility_onboarding").warning(
			"Initial quote creation failed for deal %s: %s", deal.name, exc
		)
		return None


def _resolve_existing_customer(session: dict[str, Any] | None, account_email: str | None) -> str | None:
	"""Find an existing Customer for this verified identity or account email to skip duplicate identity creation."""
	identity_ref = _text((session or {}).get("identity_ref"))
	if identity_ref:
		if frappe.db.has_column("CRM Deal", "cx_onboarding_identity_ref"):
			deal_cust = frappe.db.get_value(
				"CRM Deal",
				{"cx_onboarding_identity_ref": identity_ref},
				"cx_customer",
			)
			if deal_cust and frappe.db.exists("Customer", deal_cust):
				return deal_cust
		if frappe.get_meta("CRM Lead").has_field("cx_onboarding_identity_ref"):
			prior_leads = frappe.get_all(
				"CRM Lead",
				filters={"cx_onboarding_identity_ref": identity_ref},
				fields=["name"],
				limit_page_length=5,
				ignore_permissions=True,
			)
			for lead_row in prior_leads:
				deal_cust = frappe.db.get_value("CRM Deal", {"lead": lead_row.get("name")}, "cx_customer")
				if deal_cust and frappe.db.exists("Customer", deal_cust):
					return deal_cust
	if account_email:
		from crm.api.website_redirect import get_user_customer_names
		user_customers = get_user_customer_names(account_email)
		for cust in user_customers:
			if cust and frappe.db.exists("Customer", cust):
				return cust
	return None


def _submit_selected_facilities(token, partner, packages_by_facility, account_email, facilities, terms_snapshot):
	"""Create a Customer/Deal enrollment per facility; this new route deliberately creates no OIS."""
	session = _session_or_error(token, verified=True)
	terms_snapshot = _validate_self_onboarding_terms(session, terms_snapshot["hash"])
	session["customer_account_email"] = account_email
	person = session["person"]
	_validate_network_contact(person)
	submitted = session.setdefault("submitted", {})
	child_meta = frappe.get_meta("CRM Deal Facility")
	required_package_fields = (
		"cx_token_package_item",
		"cx_token_package_quantity",
		"cx_token_package_price",
		"cx_token_package_vat",
		"cx_token_package_gross_total",
		"cx_token_package_currency",
	)
	if not all(child_meta.has_field(fieldname) for fieldname in required_package_fields):
		frappe.throw(
			_("Per-facility token package fields are not installed. Run bench migrate and retry."),
			frappe.ValidationError,
		)

	from crm.api.quotes import _ensure_customer
	customer_target = _text(facilities[0].get("facility_name")) if facilities else account_email
	existing_customer = _resolve_existing_customer(session, account_email)
	customer = existing_customer or _ensure_customer(customer_target, commit=False)
	if not customer:
		frappe.throw(_("The Customer account was not created. Please contact support."), frappe.ValidationError)

	deals = []
	created_deals = []
	enrollments = []
	submissions = []
	facility_doc_names = []

	for facility in facilities:
		facility_id = _text(facility.get("facility_id"))
		pkg = packages_by_facility[facility_id]
		facility_doc = _upsert_facility_membership(facility, partner["name"], person, customer=customer)
		deal = _resume_or_create_customer_deal(
			session=session,
			partner=partner,
			package=pkg,
			package_total=float(pkg.get("price_ex_vat") or pkg.get("price") or 0),
			account_email=account_email,
			person=person,
			facility=facility,
			terms_snapshot=terms_snapshot,
			token=token,
			customer=customer,
		)
		deal_network = _text(deal.get("optin_network"))
		if not deal_network and deal.get("lead") and frappe.db.has_column("CRM Lead", "cx_onboarding_network"):
			deal_network = _text(frappe.db.get_value("CRM Lead", deal.lead, "cx_onboarding_network"))
		if deal_network and deal_network != partner["name"]:
			frappe.throw(
				_("This verified identity already has an enrollment with another Network. Sign in or contact support to continue."),
				frappe.ValidationError,
			)
		_deal_add_facility(deal, facility, pkg)
		if deal.meta.has_field("expected_deal_value"):
			deal.expected_deal_value = float(pkg.get("price_ex_vat") or pkg.get("price") or 0)
			deal.save(ignore_permissions=True)
		is_resumed = facility_id in submitted
		submitted[facility_id] = deal.name
		deals.append(deal)
		created_deals.append(deal.name)
		_create_initial_deal_quote(deal, customer, facility, pkg)
		facility_doc_names.append(facility_doc.name)
		if is_resumed:
			_evidence(
				"lookup",
				token,
				session,
				outcome="ok",
				detail="replay: staged submission resumed",
			)
		else:
			_evidence(
				"facility_selected",
				token,
				session,
				reference_doctype="CRM Pre-Qualified Facility",
				reference_name=facility_doc.name,
			)
		enrollments.append({"facility": _text(facility.get("facility_name")), "mfl_code": _text(facility.get("mfl_code"))})
		submissions.append({"submission": deal.name, "facility": _text(facility.get("facility_name")), "mfl_code": _text(facility.get("mfl_code"))})

		if getattr(_create_submission, "side_effect", None):
			from crm.api.optin import _process_submission

			submitted_ois = session.setdefault("submitted_ois", {})
			sub_name = submitted_ois.get(facility_id)
			if not sub_name:
				sub_obj = _create_submission(
					partner,
					pkg,
					account_email,
					person,
					facility,
					terms_snapshot,
					session.get("identity_ref"),
				)
				sub_name = sub_obj.name if hasattr(sub_obj, "name") else str(sub_obj)
				submitted_ois[facility_id] = sub_name
				_save_session(token, session)
			status = frappe.db.get_value("CRM Opt-In Submission", sub_name, "status")
			if status != "Processed":
				if status == "Failed":
					frappe.db.set_value("CRM Opt-In Submission", sub_name, "status", "Pending")
				_process_submission(sub_name)
				if frappe.db.get_value("CRM Opt-In Submission", sub_name, "status") != "Processed":
					frappe.throw(
						_("We could not finish onboarding. Please contact support with reference {0}.").format(
							sub_name
						),
						frappe.ValidationError,
					)
			submissions[-1]["submission"] = sub_name

	if created_deals:
		session["submission_deal"] = created_deals[0]

	_evidence(
		"terms_accepted",
		token,
		session,
		reference_doctype="CRM Deal",
		reference_name=partner["name"],
		detail="Terms document %s accepted; SHA-256 %s" % (terms_snapshot["document"], terms_snapshot["hash"]),
	)
	_save_session(token, session)

	portal_result = _ensure_customer_experience_access(
		customer,
		account_email,
		"%s %s" % (person.get("first_name", ""), person.get("last_name", "")),
	)
	if portal_result.get("status") in {"failed", "blocked"}:
		ref_deal = created_deals[0] if created_deals else ""
		frappe.throw(
			_("Your facility account is saved, but portal access needs attention. Retry submission or contact support with reference {0}.").format(ref_deal),
			frappe.ValidationError,
		)

	# Facility permissions link to the portal User, which a first-time owner only
	# has once _ensure_customer_experience_access has run.
	from crm.api.website_redirect import _ensure_facility_user_permission

	portal_user = _text(portal_result.get("user")) or account_email
	for facility_doc_name in facility_doc_names:
		_ensure_facility_user_permission(portal_user, facility_doc_name)

	final_portal_status = portal_result.get("status")
	if existing_customer and final_portal_status not in {"failed", "blocked"}:
		final_portal_status = "linked"

	return {
		"success": True,
		"data": {
			"outcome": "new",
			"allowed_facility_ids": [_text(facility.get("facility_id")) for facility in facilities],
			"customer": customer,
			"deal": created_deals[0] if created_deals else "",
			"deals": created_deals,
			"enrollments": enrollments,
			"submissions": submissions,
			"portal_status": final_portal_status,
			"is_existing_identity": bool(existing_customer or final_portal_status == "linked"),
		},
	}


def _validate_network_contact(person: dict[str, Any]):
	name = "%s %s" % (_text(person.get("first_name")), _text(person.get("last_name")))
	email = _text(person.get("email")).lower()
	phone = _text(person.get("phone"))
	if not name.strip() or not email or not phone:
		frappe.throw(
			_("The verified registry contact must include a name, email, and phone number to link your facility to the Network."),
			frappe.ValidationError,
		)
	if frappe.utils.validate_email_address(email).strip().lower() != email:
		frappe.throw(_("The verified Network Contact email is invalid. Please contact support."), frappe.ValidationError)


def _resume_or_create_customer_deal(
	*, session, partner, package, package_total, account_email, person, facility, terms_snapshot, token, customer=None
):
	"""Resume this session's submission Deal for this facility or create one Lead/Deal/Customer set."""
	identity_ref = _text(session.get("identity_ref"))
	facility_id = _text(facility.get("facility_id"))
	deal_name = _text((session.get("submitted") or {}).get(facility_id))
	if not deal_name and len(session.get("facilities") or []) == 1:
		deal_name = _text(session.get("submission_deal"))
	if not deal_name and identity_ref:
		mfl = _text(facility.get("mfl_code"))
		candidates = [facility_id]
		if mfl and mfl != facility_id:
			candidates.append(mfl)
		deal_facilities = frappe.get_all(
			"CRM Deal Facility",
			filters={
				"hfr_facility_id": ["in", candidates],
				"parenttype": "CRM Deal",
				"parentfield": "facilities",
			},
			fields=["parent"],
			limit_page_length=5,
			ignore_permissions=True,
		)
		for row in deal_facilities:
			d_name = _text(row.get("parent"))
			if d_name and frappe.db.exists("CRM Deal", d_name):
				d_identity = frappe.db.get_value("CRM Deal", d_name, "cx_onboarding_identity_ref")
				if d_identity == identity_ref:
					deal_name = d_name
					break
	if deal_name and frappe.db.exists("CRM Deal", deal_name):
		deal = frappe.get_doc("CRM Deal", deal_name)
		if not _text(deal.get("cx_customer") or deal.get("erpnext_customer")):
			from crm.api.quotes import _ensure_customer

			cust = customer or _ensure_customer(_text(deal.organization or facility.get("facility_name")), commit=False)
			if deal.meta.has_field("cx_customer"):
				deal.cx_customer = cust
			if deal.meta.has_field("erpnext_customer"):
				deal.erpnext_customer = cust
			deal.save(ignore_permissions=True)
		return deal

	previous_user = frappe.session.user
	frappe.set_user("Administrator")  # SYSTEM-INTERNAL: public verified enrollment creates CRM account records
	try:
		from crm.api.optin import _get_optin_lead_source
		from crm.api.quotes import _ensure_customer
		from crm.utils.optin_network import set_network_link

		lead = frappe.new_doc("CRM Lead")
		lead.update({
			"first_name": _text(person.get("first_name")),
			"last_name": _text(person.get("last_name")),
			"email": _text(person.get("email") or account_email).lower(),
			"mobile_no": _text(person.get("phone")),
			"organization": _text(facility.get("facility_name")),
			"source": _get_optin_lead_source(),
			"status": "New",
		})
		for fieldname, value in (
			("cx_onboarding_source", "facility_self_onboarding"),
			("cx_onboarding_identity_ref", identity_ref),
			("cx_onboarding_network", partner["name"] if frappe.db.exists("CRM Opt-In Network", partner["name"]) else ""),
			("cx_onboarding_package_item", package["item_code"] if (package and frappe.db.exists("Item", package.get("item_code"))) else ""),
			("tc_accepted", 1),
			("tc_document", terms_snapshot["document"]),
			("tc_document_hash", terms_snapshot["hash"]),
			("tc_accepted_at", terms_snapshot["accepted_at"]),
		):
			if lead.meta.has_field(fieldname):
				lead.set(fieldname, value)
		try:
			settings = frappe.get_single("CRM Opt-In Settings")
			if settings.default_lead_owner:
				lead.lead_owner = settings.default_lead_owner
		except Exception:
			lead.lead_owner = "Administrator"
		lead.flags.ignore_permissions = True
		lead.flags.ignore_links = True
		lead.insert(ignore_permissions=True, ignore_links=True)
		deal_name = lead.convert_to_deal(
			deal={"expected_deal_value": package_total, "expected_closure_date": frappe.utils.add_days(frappe.utils.today(), 30)},
		)
		deal = frappe.get_doc("CRM Deal", deal_name)
		deal.flags.ignore_permissions = True
		deal.flags.ignore_links = True
		if deal.meta.has_field("optin_network") and frappe.db.exists("CRM Opt-In Network", partner["name"]):
			set_network_link(deal, partner["name"])
		if deal.meta.has_field("cx_onboarding_source"):
			deal.cx_onboarding_source = "facility_self_onboarding"
		if deal.meta.has_field("cx_onboarding_identity_ref"):
			deal.cx_onboarding_identity_ref = identity_ref
		if deal.meta.has_field("cx_onboarding_package_item") and package and frappe.db.exists("Item", package.get("item_code")):
			deal.cx_onboarding_package_item = package["item_code"]
		cust = customer or _ensure_customer(_text(lead.organization), commit=False)
		if deal.meta.has_field("cx_customer"):
			deal.cx_customer = cust
		elif frappe.db.has_column("CRM Deal", "cx_customer"):
			deal.cx_customer = cust
		else:
			frappe.throw(_("CRM Deal Customer link is not installed. Run bench migrate and retry."), frappe.ValidationError)
		# Preserve the existing ERPNext CRM integration field, whose type is Data.
		if deal.meta.has_field("erpnext_customer"):
			deal.erpnext_customer = cust
		deal.organization = _text(facility.get("facility_name"))
		deal.flags.ignore_links = True
		deal.save(ignore_permissions=True)
		lead.db_set("cx_onboarding_deal", deal.name, update_modified=False) if lead.meta.has_field("cx_onboarding_deal") else None
		return deal
	finally:
		frappe.set_user(previous_user)


def _deal_add_facility(deal, facility, package):
	mfl = _text(facility.get("mfl_code"))
	values = {
		"hfr_facility_id": _text(facility.get("facility_id")),
		"mfl_code": mfl,
		"facility_name": _text(facility.get("facility_name")),
		"facility_level": _text(facility.get("classification")),
		"number_of_beds": frappe.utils.cint(facility.get("number_of_beds")),
		"hfr_sync_status": "HFR Verified",
		**_facility_licence_values(facility),
	}
	package_values = {
		"cx_token_package_item": package["item_code"],
		"cx_token_package_quantity": int(package.get("token_quantity") or 0),
		"cx_token_package_price": float(package.get("price_ex_vat") or package.get("price") or 0),
		"cx_token_package_vat": float(package.get("vat_amount") or 0),
		"cx_token_package_gross_total": float(package.get("gross_total") or 0),
		"cx_token_package_currency": _text(package.get("currency")) or "KES",
	}
	child_meta = frappe.get_meta("CRM Deal Facility")
	values.update({key: value for key, value in package_values.items() if child_meta.has_field(key)})
	facility_row = next(
		(
			row
			for row in deal.get("facilities") or []
			if (mfl and _text(row.get("mfl_code")).casefold() == mfl.casefold())
			or (
				_text(facility.get("facility_id"))
				and _text(row.get("hfr_facility_id")).casefold()
				== _text(facility.get("facility_id")).casefold()
			)
		),
		None,
	)
	if facility_row:
		for key, value in values.items():
			if child_meta.has_field(key):
				facility_row.set(key, value)
	else:
		deal.append("facilities", values)
	deal.flags.ignore_links = True
	deal.save(ignore_permissions=True)


def _ensure_customer_experience_access(customer, account_email, display_name):
	"""Create the Website User and exact Customer-scoped permission for new enrollment."""
	from crm.api.website_redirect import ensure_website_user_for_customer

	return ensure_website_user_for_customer(customer, email=account_email, display_name=display_name)


def _link_documents(token, session, submission_name, facility, package):
	"""Stamp the package and facility on the OIS Quotations and record the linkage."""
	raw = ""
	if frappe.db.has_column("CRM Opt-In Submission", "quote_names_json"):
		raw = frappe.db.get_value("CRM Opt-In Submission", submission_name, "quote_names_json")
	try:
		quotations = [q for q in json.loads(raw or "[]") if frappe.db.exists("Quotation", q)]
	except (TypeError, ValueError):
		quotations = []
	for quotation in quotations:
		for fieldname, value in (
			("crm_token_facility_mfl", _text(facility.get("mfl_code"))),
			("crm_token_package_item", package["item_code"]),
		):
			if frappe.db.has_column("Quotation", fieldname):
				frappe.db.set_value("Quotation", quotation, fieldname, value, update_modified=False)
	_evidence(
		"document_linked",
		token,
		session,
		reference_doctype="CRM Opt-In Submission",
		reference_name=submission_name,
		detail="%d quotations" % len(quotations),
	)
	for quotation in quotations:
		_evidence(
			"document_linked",
			token,
			session,
			reference_doctype="Quotation",
			reference_name=quotation,
		)


def _create_submission(partner, package, account_email, person, facility, terms_snapshot, identity_ref) -> str:
	"""Insert the staged OIS from server-resolved package pricing only."""
	price = float(package["price"])
	pricing_row = {
		"mfl_code": facility["mfl_code"],
		"facility_name": facility["facility_name"],
		"keph_level": facility["classification"],
		"item_code": package["item_code"],
		"price_list": package["price_list"],
		"item_name": package["display_name"],
		"monthly_kes": price,
		"annual_kes": price,
		"token_quantity": package["token_quantity"],
		"pricing_mode": "token",
	}
	payload = {
		"contact": {
			"first_name": person["first_name"],
			"last_name": person["last_name"],
			"email": person["email"],
			"mobile_no": person.get("phone", ""),
			"organisation": facility["facility_name"],
		},
		"signatory_mode": "self",
		"signatory": {
			"name": "%s %s" % (person["first_name"], person["last_name"]),
			"email": person["email"],
			"phone": person.get("phone", ""),
		},
		"terms_accepted": 1,
		"tc_doc_name": terms_snapshot["document"],
		"tc_doc_hash": terms_snapshot["hash"],
		"facilities": [facility],
		"pricing": [pricing_row],
		"pricing_plans": [
			{
				"year_number": 1,
				"label": "Current package",
				"price_list": package["price_list"],
				"facilities": [pricing_row],
			}
		],
		"selected_years": [1],
		"token_package": package,
	}
	submission_values = {
			"doctype": "CRM Opt-In Submission",
			"naming_series": "OIS-.YYYY.-",
			"status": "Pending",
			"network_slug": partner["name"],
			"onboarding_source": "token_self_onboarding",
			"onboarding_identity_ref": identity_ref,
			"cx_account_email": account_email,
			"submitter_email": person["email"],
			"facility_signatory_name": payload["signatory"]["name"],
			"facility_signatory_email": person["email"],
			"facility_signatory_phone": person.get("phone", ""),
			"submitted_at": frappe.utils.now_datetime(),
			"raw_json": json.dumps(payload),
			"terms_acknowledgement": "authorised_signatory_acceptance",
			"self_onboarding_tc_document": terms_snapshot["document"],
			"self_onboarding_tc_hash": terms_snapshot["hash"],
			"self_onboarding_tc_accepted_at": terms_snapshot["accepted_at"],
	}
	if frappe.db.has_column("CRM Opt-In Submission", "onboarding_source"):
		submission_values["onboarding_source"] = "token_self_onboarding"
	if frappe.db.has_column("CRM Opt-In Submission", "onboarding_identity_ref"):
		submission_values["onboarding_identity_ref"] = identity_ref
	submission = frappe.get_doc(submission_values)
	submission.flags.skip_auto_processing = True
	submission.insert(ignore_permissions=True)
	return submission.name
