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

try:
	import jwt
except ImportError:  # pragma: no cover - site configuration failure
	jwt = None

SESSION_TTL_SECONDS = 2 * 60 * 60
OTP_TTL_SECONDS = 10 * 60
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .'/-]{2,63}$")
PARTNER_ID_RE = re.compile(r"^\d{6}$")


def _text(value: Any) -> str:
	return frappe.utils.cstr(value or "").strip()


def _client_ip() -> str:
	try:
		request = getattr(frappe.local, "request", None)
		if request:
			return _text(request.headers.get("X-Forwarded-For", "").split(",")[0]) or _text(
				getattr(request, "remote_addr", "")
			) or "unknown"
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
		"facility_path": _text(_setting("facility_onboarding_hfr_facility_path"))
		or "/v1/hfr/fetch-facility",
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
	if jwt is None:
		frappe.throw(_("Facility registry authentication is unavailable."), frappe.ConfigurationError)
	return jwt.encode(
		{"key": config["username"], "exp": int(time.time()) + config["jwt_expiry"]},
		config["password"],
		algorithm="HS256",
	)


def _request(config: dict[str, Any], path: str, params: dict[str, Any]) -> Any:
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
		response.raise_for_status()
		return response.json()
	except requests.exceptions.Timeout:
		frappe.throw(_("The registry took too long to respond. Please try again."), frappe.ValidationError)
	except requests.exceptions.RequestException:
		frappe.log_error(frappe.get_traceback(), "CRM facility onboarding registry request")
		frappe.throw(_("The registry is temporarily unavailable. Please try again shortly."), frappe.ValidationError)
	except ValueError:
		frappe.log_error(frappe.get_traceback(), "CRM facility onboarding invalid registry response")
		frappe.throw(_("The registry returned an invalid response. Please try again shortly."), frappe.ValidationError)


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
	return rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None


def _hfr_facilities_for_owner(id_number: str) -> list[dict[str, Any]]:
	config = _onboarding_config()
	response = _request(config, config["owner_path"], {"owner_id_number": id_number})
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
	return "crm_facility_onboarding:%s" % hashlib.sha256(token.encode()).hexdigest()


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
		fields=["name", "slug", "display_name", "logo_url", "primary_colour", "contact_email", "footer_legal_name"],
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


@frappe.whitelist(allow_guest=True, methods=["POST"])
def start_identity(identification_type: Any, identification_number: Any):
	"""Resolve the person through Client Registry and facilities through HFR."""
	id_type = _text(identification_type)
	id_number = _text(identification_number)
	if not id_type or not ID_RE.fullmatch(id_number) or _rate_limited("start:%s" % _client_ip()):
		frappe.throw(_("We could not verify those details. Please check and try again."), frappe.ValidationError)
	try:
		person = _client_registry_person(id_type, id_number)
		facilities = _hfr_facilities_for_owner(id_number) if person else []
	except Exception:
		frappe.log_error(frappe.get_traceback(), "CRM facility onboarding identity lookup")
		person, facilities = None, []

	token = secrets.token_urlsafe(32)
	otp = "%06d" % secrets.randbelow(1_000_000)
	contact_email = _text(person.get("email")).lower() if person else ""
	contact_phone = _text(person.get("phone")) if person else ""
	lookup_valid = bool(person and facilities and contact_email)
	if not lookup_valid:
		person = {}
		facilities = []
	payload = {
		"verified": False,
		"lookup_valid": lookup_valid,
		"id_type": id_type,
		"identity_hash": hashlib.sha256((id_type.lower() + "|" + id_number.lower()).encode()).hexdigest(),
		"person": {
			"first_name": _text(person.get("first_name")),
			"last_name": _text(person.get("last_name")),
			"email": contact_email,
			"phone": contact_phone,
		},
		"facilities": [_facility_row(row) for row in facilities],
		"otp_hash": _otp_hash(otp),
		"otp_attempts": 0,
		"otp_expires_at": int(time.time()) + OTP_TTL_SECONDS,
		"otp_sent_at": int(time.time()),
	}
	_save_session(token, payload)
	if contact_email:
		frappe.sendmail(
			recipients=[contact_email],
			subject="tiberbu Express facility onboarding verification code",
			message=(
				"<p>Your tiberbu Express facility onboarding code is "
				"<strong>%s</strong>.</p><p>It expires in 10 minutes.</p>" % otp
			),
			delayed=False,
		)
	# Deliberately return the same challenge shape for unknown IDs, valid IDs,
	# missing facilities, and upstream failures. Verification is the only point
	# at which the facility list can be released.
	return {"success": True, "data": {"session_token": token, "challenge_started": True}}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def resend_otp(session_token: Any):
	session = _session_or_error(_text(session_token))
	if int(time.time()) - int(session.get("otp_sent_at") or 0) < OTP_RESEND_SECONDS:
		return {"success": True, "data": {"sent": True}}
	otp = "%06d" % secrets.randbelow(1_000_000)
	session.update({"otp_hash": _otp_hash(otp), "otp_attempts": 0, "otp_sent_at": int(time.time()), "otp_expires_at": int(time.time()) + OTP_TTL_SECONDS})
	_save_session(_text(session_token), session)
	if session.get("person", {}).get("email"):
		frappe.sendmail(
			recipients=[session["person"]["email"]],
			subject="tiberbu Express facility onboarding verification code",
		message="<p>Your new verification code is <strong>%s</strong>. It expires in 10 minutes.</p>" % otp,
			delayed=False,
		)
	return {"success": True, "data": {"sent": True}}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def verify_otp(session_token: Any, otp: Any):
	token = _text(session_token)
	session = _session_or_error(token)
	if int(time.time()) > int(session.get("otp_expires_at") or 0):
		frappe.throw(_("That code has expired. Please request a new one."), frappe.PermissionError)
	session["otp_attempts"] = int(session.get("otp_attempts") or 0) + 1
	if session["otp_attempts"] > OTP_MAX_ATTEMPTS or not hmac.compare_digest(session.get("otp_hash", ""), _otp_hash(_text(otp))):
		_save_session(token, session)
		frappe.throw(_("The verification code is incorrect or expired."), frappe.PermissionError)
	if not session.get("lookup_valid"):
		frappe.cache().delete_value(_session_key(token))
		frappe.throw(_("The verification code is incorrect or expired."), frappe.PermissionError)
	session["verified"] = True
	session["otp_hash"] = ""
	_save_session(token, session)
	return {"success": True, "data": {"identity": _person_preview(session["person"]), "facilities": session["facilities"]}}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_catalog(partner_id: Any):
	partner = _public_network(_text(partner_id))
	if not partner:
		frappe.throw(_("That Partner ID is not available. Check the six digits and try again."), frappe.ValidationError)
	return {"success": True, "data": {"network": partner, "packages": _token_packages()}}


def _upsert_facility_membership(facility: dict[str, Any], network: str, person: dict[str, Any]):
	mfl = _text(facility.get("mfl_code"))
	row = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": mfl}, "name")
	if row:
		facility_doc = frappe.get_doc("CRM Pre-Qualified Facility", row)
		facility_doc.facility_name = _text(facility.get("facility_name")) or facility_doc.facility_name
		facility_doc.keph_level = _text(facility.get("classification")) or facility_doc.keph_level or "Other"
	else:
		facility_doc = frappe.get_doc({"doctype": "CRM Pre-Qualified Facility", "mfl_code": mfl, "facility_name": _text(facility.get("facility_name")) or mfl, "organization": _text(facility.get("facility_name")) or mfl, "keph_level": _text(facility.get("classification")) or "Other"})
	for row in facility_doc.memberships or []:
		if row.network == network and _text(row.contact_email).lower() == person["email"].lower():
			return facility_doc
	facility_doc.append("memberships", {"network": network, "status": "Active", "contact_name": "%s %s" % (person.get("first_name", ""), person.get("last_name", "")), "contact_email": person["email"], "contact_phone": person.get("phone", "")})
	facility_doc.save(ignore_permissions=True)
	return facility_doc


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_onboarding(session_token: Any, partner_id: Any, selected_facility_ids: Any, package_item_code: Any, witness: Any, terms_accepted: Any = 0):
	token = _text(session_token)
	session = _session_or_error(token, verified=True)
	partner_id = _text(partner_id)
	partner = _public_network(partner_id)
	if not partner:
		frappe.throw(_("That Partner ID does not exist or is not available."), frappe.ValidationError)
	try:
		selected = json.loads(selected_facility_ids) if isinstance(selected_facility_ids, str) else selected_facility_ids
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
	if not int(terms_accepted) or not _text(witness.get("name")) or not frappe.utils.validate_email_address(_text(witness.get("email")).lower()):
		frappe.throw(_("Accept the terms and add a valid facility witness before continuing."), frappe.ValidationError)
	facilities = [row for row in session["facilities"] if _text(row.get("facility_id")) in selected]
	if len(facilities) != len(selected):
		frappe.throw(_("One or more facilities are no longer available in this session."), frappe.ValidationError)

	from crm.api.optin import _process_submission
	person = session["person"]
	for facility in facilities:
		_upsert_facility_membership(facility, partner["name"], person)
	price = float(package["price"])
	submissions = []
	for facility in facilities:
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
		frappe.db.commit()
		_process_submission(submission.name)
		if frappe.db.get_value("CRM Opt-In Submission", submission.name, "status") != "Processed":
			frappe.throw(
				_("We could not finish onboarding. Please contact support with reference {0}.").format(
					submission.name
				)
			)
		submissions.append(
			{
				"submission": submission.name,
				"status": "Processed",
				"facility": facility["facility_name"],
			}
		)
	frappe.cache().delete_value(_session_key(token))
	return {"success": True, "data": {"submissions": submissions}}
