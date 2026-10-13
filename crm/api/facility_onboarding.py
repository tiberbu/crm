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
from typing import Any

import frappe
import requests
from frappe import _
from frappe.utils.password import decrypt, encrypt
from frappe.utils.synchronization import filelock

from crm.api._email import OTP_QUEUE_REDACTION, schedule_email_queue_redaction
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
OTP_SUBJECT = "tiberbu Express facility onboarding verification code"
OTP_BRAND = "tiberbu Express"
_DECOY_DOMAINS = ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .'/-]{2,63}$")
PARTNER_ID_RE = re.compile(r"^\d{6}$")


def _text(value: Any) -> str:
	return frappe.utils.cstr(value or "").strip()


def _normalize_id_type(value: Any) -> str:
	return re.sub(r"[^a-z0-9]", "", _text(value).lower())


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
		frappe.throw(_("HFR integration is not enabled."), frappe.ConfigurationError)

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
		frappe.throw(_("Facility registry integration is not configured."), frappe.ConfigurationError)
	if not jwt:
		frappe.throw(_("Facility registry authentication is unavailable."), frappe.ConfigurationError)
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
	message = response.get("message") if isinstance(response, dict) else {}
	data = message if isinstance(message, dict) else response if isinstance(response, dict) else {}
	if isinstance(data.get("data"), dict):
		data = data["data"]
	rows = data.get("facilities") or (response.get("facilities") if isinstance(response, dict) else []) or []
	return [row for row in rows if isinstance(row, dict)]


def _facility_row(row: dict[str, Any]) -> dict[str, Any]:
	fid = _text(
		row.get("facility_id")
		or row.get("facility_fid")
		or row.get("hie_id")
		or row.get("registration_number")
	)
	mfl = _text(row.get("facility_code") or row.get("facility_mfl") or row.get("mfl_code"))
	return {
		"facility_id": fid,
		"mfl_code": mfl or fid,
		"facility_name": _text(row.get("facility_name")),
		"classification": _text(row.get("facility_level") or row.get("kephl_level") or row.get("category")),
		"facility_type": _text(row.get("facility_type")),
		"facility_category": _text(row.get("category") or row.get("facility_category")),
		"county": _text(row.get("county")),
		"sub_county": _text(row.get("sub_county")),
		"owner_type": _text(row.get("facility_owner_type") or row.get("owner_type")),
		"registration_number": _text(row.get("registration_number")),
	}


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
				queue = frappe.sendmail(
					recipients=[email],
					subject=OTP_SUBJECT,
					message=(
						"<p>Your %s facility onboarding code is <strong>%s</strong>.</p>"
						"<p>It expires in 10 minutes.</p>" % (OTP_BRAND, otp)
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
	delivery = session.get("delivery") or {}
	return {
		"channel": delivery.get("channel") or None,
		"masked_destination": delivery.get("masked_destination") or "",
		"status": delivery.get("status") or "sent",
		"expires_in": max(0, int(session.get("otp_expires_at") or 0) - now),
		"resend_after": max(0, OTP_RESEND_SECONDS - (now - int(session.get("otp_sent_at") or 0))),
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


# nosemgrep: guest-whitelisted-method -- generic identity responses, rate limiting, HFR ownership binding, and OTP verification prevent enumeration and unauthorised facility access.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def start_identity(identification_type: Any, identification_number: Any):
	"""Resolve facilities through HFR first, then the owner's contacts through Client Registry."""
	id_type = _text(identification_type)
	id_number = _text(identification_number)
	if not id_type or not ID_RE.fullmatch(id_number) or _rate_limited("start:%s" % _client_ip()):
		frappe.throw(
			_("We could not verify those details. Please check and try again."), frappe.ValidationError
		)
	# Evaluate both registries independently so one failure never masks the other
	# gate. Detailed outcomes are written only to protected onboarding evidence.
	hfr_failure = ""
	try:
		facilities = _hfr_facilities_for_owner(id_number)
	except Exception as exc:
		frappe.log_error(
			title="CRM facility onboarding HFR lookup", message="Lookup failed (%s)" % type(exc).__name__
		)
		facilities = []
		hfr_failure = "lookup failed"
	if not facilities and not hfr_failure:
		hfr_failure = "no facilities"

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
	gate_failures = []
	if cr_failure:
		gate_failures.append("CR/Afyangu: %s" % cr_failure)
	if hfr_failure:
		gate_failures.append("HFR: %s" % hfr_failure)
	lookup_valid = not gate_failures
	if not lookup_valid:
		person = {}
		facilities = []
	identity_hash = hashlib.sha256((id_type.lower() + "|" + id_number.lower()).encode()).hexdigest()
	now = int(time.time())
	payload = {
		"verified": False,
		"lookup_valid": lookup_valid,
		"id_type": id_type,
		"identity_hash": identity_hash,
		"person": {
			"first_name": _text(person.get("first_name")),
			"last_name": _text(person.get("last_name")),
			"email": contact_email,
			"phone": contact_phone,
		},
		"facilities": [_facility_row(row) for row in facilities],
		"otp_hash": _otp_hash(otp),
		"otp_attempts": 0,
		"otp_expires_at": now + OTP_TTL_SECONDS,
		"otp_sent_at": now,
		"resend_count": 0,
	}
	if lookup_valid:
		payload["delivery"] = _send_otp(payload["person"], otp)
	else:
		channel = _preferred_channel()
		payload["delivery"] = {
			"channel": channel,
			"masked_destination": _decoy_destination(identity_hash, channel),
			"status": "sent",
		}
	_save_session(token, payload)
	_evidence(
		"lookup",
		token,
		payload,
		outcome="ok" if lookup_valid else "failed",
		detail="; ".join(gate_failures) if gate_failures else "%d facilities" % len(payload["facilities"]),
	)
	if lookup_valid:
		_evidence(
			"otp_sent",
			token,
			payload,
			outcome="ok" if payload["delivery"]["status"] == "sent" else "failed",
			channel=payload["delivery"]["channel"] or "",
		)
	# Unknown IDs, missing facilities, and upstream failures return the same
	# challenge shape. Verification is the only point at which facility data is
	# released; only a masked destination and delivery state are shown before it.
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
	session = _session_or_error(token)
	now = int(time.time())
	if now - int(session.get("otp_sent_at") or 0) < OTP_RESEND_SECONDS:
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
	session = _session_or_error(token)
	if int(time.time()) > int(session.get("otp_expires_at") or 0):
		_evidence("otp_failed", token, session, outcome="failed", detail="expired", commit=True)
		frappe.throw(_("That code has expired. Please request a new one."), frappe.PermissionError)
	session["otp_attempts"] = int(session.get("otp_attempts") or 0) + 1
	if session["otp_attempts"] > OTP_MAX_ATTEMPTS or not hmac.compare_digest(
		session.get("otp_hash", ""), _otp_hash(_text(otp))
	):
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
	_save_session(token, session)
	_evidence("otp_verified", token, session, channel=(session.get("delivery") or {}).get("channel") or "")
	return {
		"success": True,
		"data": {"identity": _person_preview(session["person"]), "facilities": session["facilities"]},
	}


# nosemgrep: guest-whitelisted-method -- only public package metadata is returned after strict six-digit Network validation.
@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_catalog(partner_id: Any):
	partner = _public_network(_text(partner_id))
	if not partner:
		frappe.throw(
			_("That Partner ID is not available. Check the six digits and try again."), frappe.ValidationError
		)
	return {"success": True, "data": {"network": partner, "packages": _catalog_packages()}}


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


def _upsert_facility_membership(facility: dict[str, Any], network: str, person: dict[str, Any]):
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
	for row in facility_doc.memberships or []:
		if row.network == network and _text(row.contact_email).lower() == person["email"].lower():
			return facility_doc
	facility_doc.append(
		"memberships",
		{
			"network": network,
			"status": "Active",
			"contact_name": "%s %s" % (person.get("first_name", ""), person.get("last_name", "")),
			"contact_email": person["email"],
			"contact_phone": person.get("phone", ""),
		},
	)
	facility_doc.save(ignore_permissions=True)
	return facility_doc


# nosemgrep: guest-whitelisted-method -- submission requires a verified session, HFR-bound facility selection, valid Network, package, witness, and terms.
@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_onboarding(
	session_token: Any,
	partner_id: Any,
	selected_facility_ids: Any,
	package_item_code: Any,
	witness: Any,
	terms_accepted: Any = 0,
):
	token = _text(session_token)
	session = _session_or_error(token, verified=True)
	partner_id = _text(partner_id)
	partner = _public_network(partner_id)
	if not partner:
		frappe.throw(_("That Partner ID does not exist or is not available."), frappe.ValidationError)
	try:
		selected = (
			json.loads(selected_facility_ids)
			if isinstance(selected_facility_ids, str)
			else selected_facility_ids
		)
	except Exception:
		selected = []
	selected = {_text(value) for value in selected or [] if _text(value)}
	if not selected:
		frappe.throw(_("Select at least one facility to continue."), frappe.ValidationError)
	package = next((row for row in _token_packages() if row["item_code"] == _text(package_item_code)), None)
	if not package:
		frappe.throw(_("Select an available token package."), frappe.ValidationError)
	try:
		witness = json.loads(witness) if isinstance(witness, str) else witness
	except Exception:
		witness = {}
	if (
		not int(terms_accepted)
		or not _text(witness.get("name"))
		or not frappe.utils.validate_email_address(_text(witness.get("email")).lower())
	):
		frappe.throw(
			_("Accept the terms and add a valid facility witness before continuing."), frappe.ValidationError
		)
	facilities = [row for row in session["facilities"] if _text(row.get("facility_id")) in selected]
	if len(facilities) != len(selected):
		frappe.throw(
			_("One or more facilities are no longer available in this session."), frappe.ValidationError
		)

	with filelock("crm_onboarding_submit_%s" % evidence_ref(token)[:24], timeout=60):
		return _submit_selected_facilities(token, partner, package, witness, facilities)


def _submit_selected_facilities(token, partner, package, witness, facilities):
	"""Create or resume exactly one processed OIS per facility for this session."""
	from crm.api.optin import _process_submission

	# Re-read under the lock so a concurrent or repeated request sees earlier work.
	session = _session_or_error(token, verified=True)
	person = session["person"]
	submitted = session.setdefault("submitted", {})
	submissions = []
	for facility in facilities:
		facility_id = _text(facility.get("facility_id"))
		name = submitted.get(facility_id)
		is_new = not (name and frappe.db.exists("CRM Opt-In Submission", name))
		if is_new:
			_evidence(
				"terms_accepted",
				token,
				session,
				reference_doctype="CRM Opt-In Network",
				reference_name=partner["name"],
			)
			facility_doc = _upsert_facility_membership(facility, partner["name"], person)
			_evidence(
				"facility_selected",
				token,
				session,
				reference_doctype="CRM Pre-Qualified Facility",
				reference_name=facility_doc.name,
			)
			name = _create_submission(partner, package, witness, person, facility)
			submitted[facility_id] = name
			# Persist the mapping and the staged record before processing so a retry resumes it.
			_save_session(token, session)
			frappe.db.commit()  # nosemgrep: frappe-manual-commit
		status = frappe.db.get_value("CRM Opt-In Submission", name, "status")
		if status != "Processed":
			if status == "Failed":
				frappe.db.set_value("CRM Opt-In Submission", name, "status", "Pending")
			_process_submission(name)
			if frappe.db.get_value("CRM Opt-In Submission", name, "status") != "Processed":
				frappe.throw(
					_("We could not finish onboarding. Please contact support with reference {0}.").format(
						name
					)
				)
			is_new = True
		if is_new:
			_link_documents(token, session, name, facility, package)
		submissions.append(
			{"submission": name, "status": "Processed", "facility": _text(facility.get("facility_name"))}
		)
	return {"success": True, "data": {"submissions": submissions}}


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


def _create_submission(partner, package, witness, person, facility) -> str:
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
		"witness": {
			"name": _text(witness.get("name")),
			"email": _text(witness.get("email")).lower(),
			"phone": _text(witness.get("phone")),
		},
		"terms_accepted": 1,
		"tc_doc_name": _text(_setting("active_tc_document")) or "tiberbu Express Opt-In Terms",
		"tc_doc_hash": hashlib.sha256(
			("tiberbu-express:%s:%s" % (partner["name"], package["item_code"])).encode()
		).hexdigest(),
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
	submission = frappe.get_doc(
		{
			"doctype": "CRM Opt-In Submission",
			"naming_series": "OIS-.YYYY.-",
			"status": "Pending",
			"network_slug": partner["name"],
			"submitter_email": person["email"],
			"facility_signatory_name": payload["signatory"]["name"],
			"facility_signatory_email": person["email"],
			"facility_signatory_phone": person.get("phone", ""),
			"facility_witness_name": payload["witness"]["name"],
			"facility_witness_email": payload["witness"]["email"],
			"facility_witness_phone": payload["witness"]["phone"],
			"submitted_at": frappe.utils.now_datetime(),
			"raw_json": json.dumps(payload),
			"terms_acknowledgement": "authorised_signatory_acceptance",
		}
	)
	submission.flags.skip_auto_processing = True
	submission.insert(ignore_permissions=True)
	return submission.name
