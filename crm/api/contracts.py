"""
crm/api/contracts.py — CRM Contract Signing State Machine

Story:  cs-s1-2
BRD:    BRD_Contract_Signing.docx
ADR:    ADR_Contract_Signing.docx

Security model:
- generate / download_pdf / resend_invitation require Sales Manager or System Manager.
- Public endpoints (request_otp, verify_otp, get_contract, sign) are guest-accessible.
- Identity chain: random invitation token (stored on the signatory row) → 6-digit OTP
  → random signing-session token (stored on the row). All tokens are opaque, high-entropy
  secrets generated with frappe.generate_hash(); none are derived from the request, so a
  token can be regenerated at will and rotating the signing key never invalidates them.
- hmac.compare_digest() is used for ALL token/OTP comparisons — never ==.

Rules enforced:
- frappe.get_list() for every SELECT — no frappe.db.sql() SELECTs, no frappe.get_all().
- ignore_permissions=True only on system/scheduler paths — marked # SYSTEM-INTERNAL.
- No f-strings in log/error messages — % formatting only.
- All transactional email renders through crm.api._email.branded_email_html.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

import frappe
from frappe import _

from crm.api._email import branded_email_html, internal_signatory_reminder_html, otp_code_block
from crm.api._timeline import log_deal_event
from crm.utils.optin_network import set_network_link
from crm.utils.price_list_history import contract_snapshot, set_snapshot, snapshot

_OTP_EXPIRY_SECONDS = 600  # 10 minutes
_SIGN_EXPIRY_SECONDS = 7200  # 2 hours
_INVITE_EXPIRY_SECONDS = 604800  # 7 days
_MAX_OTP_ATTEMPTS = 3
_TOKEN_LENGTH = 48
_INVITATION_DEDUPE_SECONDS = 60


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_signing_key():
	"""Return the optin_signing_key; auto-generates if absent. Used only for OTP hashing."""
	settings = frappe.get_single("CRM Opt-In Settings")
	key = settings.get_password("optin_signing_key", raise_exception=False)
	if not key:
		from crm.setup.optin import ensure_signing_key

		ensure_signing_key()
		settings = frappe.get_single("CRM Opt-In Settings")
		key = settings.get_password("optin_signing_key", raise_exception=False)
	if not key:
		frappe.throw("Contract signing key not configured.", frappe.ConfigurationError)
	return key


def _hmac_hex(secret, message):
	"""Return HMAC-SHA256 hex digest of message under secret (both str)."""
	return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def _gen_token():
	"""Return an opaque, high-entropy, URL-safe token."""
	return frappe.generate_hash(length=_TOKEN_LENGTH)


def _generate_invitation_email_reference():
	"""Return a non-secret identifier for one invitation email issuance.

	This is deliberately independent from the signing token. It changes whenever
	an invitation is resent and cannot be used to open the signing portal.
	"""
	return frappe.generate_hash(length=12).upper()


def _facility_name_for_contract(contract_doc):
	"""Return a concise facility label for a contract email subject.

	Opt-In submissions keep their canonical facility list in ``raw_json``. Read
	the latest submission for the contract's deal so this remains backward
	compatible with contracts created before a dedicated facility field existed.
	"""
	deal = frappe.utils.cstr(getattr(contract_doc, "deal", "") or "").strip()
	if not deal:
		return ""
	try:
		rows = frappe.get_list(
			"CRM Opt-In Submission",
			filters={"deal": deal},
			fields=["raw_json"],
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
		if not rows:
			return ""
		payload = json.loads(rows[0].get("raw_json") or "{}")
		facilities = payload.get("pricing") or payload.get("facilities") or []
		names = []
		for facility in facilities:
			if not isinstance(facility, dict):
				continue
			name = frappe.utils.cstr(facility.get("facility_name") or "").strip()
			if name and name not in names:
				names.append(name)
		if len(names) == 1:
			return names[0]
		if names:
			return "%s + %s more facilities" % (names[0], len(names) - 1)
	except Exception:
		pass
	return ""


def _contract_email_subject_label(contract_doc):
	"""Return a safe, human-readable label for contract email subjects."""
	label = _facility_name_for_contract(contract_doc) or "CareverseHIMS"
	# Subject values are plain text; line breaks from user-supplied facility names
	# must not be allowed to alter MIME headers.
	return frappe.utils.cstr(label).replace("\r", " ").replace("\n", " ").strip() or "CareverseHIMS"


def _network_for_contract(contract_doc):
	"""Resolve the branded-email network dict for a contract, or None. Never raises."""
	slug = frappe.utils.cstr(
		getattr(contract_doc, "optin_network", "") or getattr(contract_doc, "network_slug", "") or ""
	).strip()
	if not slug:
		return None
	try:
		from crm.api.optin import _get_network_doc

		return _get_network_doc(slug)
	except Exception:
		return None


def _resolve_network_slug(deal):
	"""Best-effort: find the opt-in network slug for a deal via its submission. Never raises."""
	try:
		fields = ["network_slug"]
		if frappe.db.has_column("CRM Opt-In Submission", "optin_network"):
			fields.append("optin_network")
		rows = frappe.get_list(
			"CRM Opt-In Submission",
			filters={"deal": deal},
			fields=fields,
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
		if rows:
			return frappe.utils.cstr(
				rows[0].get("optin_network") or rows[0].get("network_slug") or ""
			).strip()
	except Exception:
		pass
	return ""


def _resolve_user_identity(user, fallback_name="", fallback_email="", fallback_phone=""):
	"""Resolve a User link to {full_name, email, phone}, preferring live User values.

	Phone is optional for backward compatibility with existing settings and users.
	"""
	name = frappe.utils.cstr(fallback_name or "").strip()
	email = frappe.utils.cstr(fallback_email or "").strip().lower()
	phone = frappe.utils.cstr(fallback_phone or "").strip()
	user = frappe.utils.cstr(user or "").strip()
	if user:
		try:
			u = frappe.db.get_value("User", user, ["full_name", "email", "mobile_no"], as_dict=True)
			if u:
				name = frappe.utils.cstr(u.full_name or name).strip()
				email = frappe.utils.cstr(u.email or email).strip().lower()
				phone = frappe.utils.cstr(u.mobile_no or phone).strip()
		except Exception:
			pass
	return {"full_name": name, "email": email, "phone": phone}


def _crm_user_exists(email):
	"""Return whether an email belongs to an enabled CRM User.

	The explicit identity check is important for mocked/older Frappe list
	responses: a non-empty result alone must never route an external signatory to
	the internal CRM path.
	"""
	email = frappe.utils.cstr(email or "").strip().lower()
	if not email:
		return False
	try:
		rows = frappe.get_list(
			"User",
			filters={"email": email, "enabled": 1},
			fields=["name", "email"],
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL: route notification safely
		)
		return any(
			frappe.utils.cstr(row.get("email") or row.get("name") or "").strip().lower() == email
			for row in rows
		)
	except Exception:
		return False


_APPROVER_SLOTS = ("network_approver_1", "network_approver_2", "tiberbu_approver")
_TIBERBU_APPROVER_CONTACT_FIELDS = (
	"tiberbu_approver_name",
	"tiberbu_approver_email",
	"tiberbu_approver_phone",
)
_APPROVER_ROLE_TO_SLOT = {
	"Network Approver 1": "network_approver_1",
	"Network Approver 2": "network_approver_2",
	"Tiberbu Approver": "tiberbu_approver",
}


def _identity_from_fields(source, prefix="tiberbu_approver"):
	"""Read a name/email/phone contact triplet from a document-like object."""
	source = source or {}
	return {
		"full_name": frappe.utils.cstr(source.get("%s_name" % prefix) or "").strip(),
		"email": frappe.utils.cstr(source.get("%s_email" % prefix) or "").strip().lower(),
		"phone": frappe.utils.cstr(source.get("%s_phone" % prefix) or "").strip(),
	}


def _merge_identity(primary, fallback):
	return {
		key: frappe.utils.cstr(primary.get(key) or fallback.get(key) or "").strip()
		for key in ("full_name", "email", "phone")
	}


def _load_optin_settings_safely():
	try:
		return frappe.get_single("CRM Opt-In Settings")
	except Exception:
		return None


def _approver_identity(slot, onboarding_row=None, settings=None):
	"""Resolve an approver from a User or a contact triplet.

	Network approvers remain backward-compatible User links. Tiberbu approvers can
	be external contacts (name/email/phone), with per-request values taking
	precedence over the global Opt-In Settings default and the legacy User link.
	"""
	onboarding_row = onboarding_row or {}
	if slot != "tiberbu_approver":
		return _resolve_user_identity(onboarding_row.get(slot))

	contact_identity = _identity_from_fields(onboarding_row)
	if settings is None:
		settings = _load_optin_settings_safely()
	settings_identity = _identity_from_fields(settings)
	legacy_value = frappe.utils.cstr(onboarding_row.get(slot) or "").strip()
	legacy_identity = _resolve_user_identity(
		legacy_value,
		fallback_email=legacy_value if "@" in legacy_value else "",
	)
	return _merge_identity(_merge_identity(contact_identity, settings_identity), legacy_identity)


def _onboarding_approver_row(deal_name):
	"""Load approver fields without breaking sites before the new contact fields migrate."""
	if not deal_name:
		return frappe._dict()
	base_fields = ["name", *_APPROVER_SLOTS]
	fields = [*base_fields, *_TIBERBU_APPROVER_CONTACT_FIELDS]
	try:
		rows = frappe.get_list(
			"CRM Onboarding Request",
			filters={"deal": deal_name},
			fields=fields,
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
	except Exception:
		rows = frappe.get_list(
			"CRM Onboarding Request",
			filters={"deal": deal_name},
			fields=base_fields,
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
	return frappe._dict(rows[0]) if rows else frappe._dict()


def _network_signers(network_slug):
	"""Configured co-signatories for a network → [{full_name, email, phone}]. Network
	signers are external people keyed by email (name + email, no Frappe User). A
	network's name IS its slug (autoname field:slug)."""
	network_slug = frappe.utils.cstr(network_slug or "").strip()
	if not network_slug or not frappe.db.exists("CRM Opt-In Network", network_slug):
		return []
	rows = frappe.get_list(
		"CRM Network Signer",
		filters={
			"parent": network_slug,
			"parenttype": "CRM Opt-In Network",
			"parentfield": "network_signers",
		},
		fields=["full_name", "email", "phone"],
		order_by="idx asc",
		ignore_permissions=True,  # SYSTEM-INTERNAL
	)
	# A legacy import (or two concurrent edits before the email uniqueness check)
	# can leave the child table with the same signer more than once. Treat email as
	# the stable identity here so one configured person cannot receive two contract
	# invitations in the same generation wave. Keep the first display name and fill
	# any missing contact details from a later duplicate row.
	signers_by_email = {}
	for r in rows:
		email = frappe.utils.cstr(r.get("email") or "").strip().lower()
		if not email:
			continue
		current = {
			"full_name": frappe.utils.cstr(r.get("full_name") or "").strip(),
			"email": email,
			"phone": frappe.utils.cstr(r.get("phone") or "").strip(),
		}
		existing = signers_by_email.get(email)
		if existing:
			existing["full_name"] = existing["full_name"] or current["full_name"]
			existing["phone"] = existing["phone"] or current["phone"]
		else:
			current["full_name"] = current["full_name"] or email
			signers_by_email[email] = current
	return list(signers_by_email.values())


def _tiberbu_signer():
	"""Return the configured global Tiberbu contract signer, including external contacts.

	The contact triplet is the preferred source so a signer does not need a CRM User
	account. The existing ``tiberbu_signatory`` User link remains a fallback for
	backward compatibility, including its live email and mobile number.
	"""
	settings = _load_optin_settings_safely()
	if not settings:
		return None

	contact = _identity_from_fields(settings, prefix="tiberbu_signatory")
	legacy_user = frappe.utils.cstr(settings.get("tiberbu_signatory") or "").strip()
	legacy = _resolve_user_identity(legacy_user)
	identity = _merge_identity(contact, legacy)
	if not identity["email"]:
		return None
	identity["full_name"] = identity["full_name"] or identity["email"]
	return identity


def _tiberbu_contact_rows(settings=None):
	"""Return configured Tiberbu contact rows when the child table is available."""
	settings = settings or _load_optin_settings_safely()
	if not settings:
		return []
	rows = (
		settings.get("tiberbu_contacts")
		if hasattr(settings, "get")
		else getattr(settings, "tiberbu_contacts", None)
	)
	return list(rows or [])


def _tiberbu_contacts(role, settings=None):
	"""Resolve configured Tiberbu contacts for a role, deduped by email."""
	role = frappe.utils.cstr(role or "").strip().lower()
	contacts = []
	for row in _tiberbu_contact_rows(settings):
		row_role = (
			frappe.utils.cstr(row.get("role") if hasattr(row, "get") else getattr(row, "role", ""))
			.strip()
			.lower()
		)
		if row_role != role:
			continue
		identity = {
			"full_name": frappe.utils.cstr(
				row.get("full_name") if hasattr(row, "get") else getattr(row, "full_name", "")
			).strip(),
			"email": frappe.utils.cstr(row.get("email") if hasattr(row, "get") else getattr(row, "email", ""))
			.strip()
			.lower(),
			"phone": frappe.utils.cstr(
				row.get("phone") if hasattr(row, "get") else getattr(row, "phone", "")
			).strip(),
		}
		if not identity["email"]:
			continue
		identity["full_name"] = identity["full_name"] or identity["email"]
		if not any(existing["email"] == identity["email"] for existing in contacts):
			contacts.append(identity)
	return contacts


def _tiberbu_signers(settings=None):
	"""Return all configured Tiberbu signers, with the legacy signer as fallback."""
	contacts = _tiberbu_contacts("signatory", settings)
	if contacts:
		return contacts
	legacy = _tiberbu_signer()
	return [legacy] if legacy else []


def _tiberbu_approvers(settings=None):
	"""Return all configured Tiberbu approvers plus the legacy contact if distinct."""
	contacts = _tiberbu_contacts("approver", settings)
	legacy = _identity_from_fields(settings or _load_optin_settings_safely())
	if legacy.get("email") and not any(row["email"] == legacy["email"] for row in contacts):
		legacy["full_name"] = legacy["full_name"] or legacy["email"]
		contacts.append(legacy)
	return contacts


def _tiberbu_signing_requirement(settings=None):
	"""Return the normalized requirement snapshot used by a newly generated contract."""
	settings = settings or _load_optin_settings_safely()
	value = settings.get("tiberbu_signing_requirement") if settings and hasattr(settings, "get") else ""
	return (
		"At least one must sign"
		if frappe.utils.cstr(value).strip().lower()
		in (
			"at least one",
			"at least one must sign",
			"any",
		)
		else "All must sign"
	)


def _lock_deal_for_contract_generation(deal):
	"""Serialize contract generation requests for the same deal."""
	try:
		frappe.db.get_value("CRM Deal", deal, "name", for_update=True)
	except Exception:
		# Keep legacy/custom sites working if CRM Deal is not available while the
		# caller is already validating the deal through another integration path.
		pass


def _existing_contract_for_deal(deal):
	"""Return the latest non-cancelled contract for a deal, if one exists."""
	try:
		rows = frappe.get_list(
			"CRM Contract",
			filters={"deal": deal, "status": ["!=", "Cancelled"]},
			fields=["name", "status"],
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL: idempotency guard
		)
		return rows[0] if rows else None
	except Exception:
		return None


def _existing_contract_invitation_queue(contract_name):
	"""Find a tracked invitation queue for an already-generated contract."""
	try:
		rows = frappe.get_list(
			"CRM Opt-In Submission",
			filters={"contract": contract_name},
			fields=["contract_invitation_email_queue"],
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL: idempotent retry lookup
		)
		return frappe.utils.cstr(rows[0].get("contract_invitation_email_queue") or "") if rows else ""
	except Exception:
		return ""


def _facility_witness_from_deal(deal):
	"""Facility witness captured on the deal's latest opt-in submission."""
	deal = frappe.utils.cstr(deal or "").strip()
	if not deal:
		return {"name": "", "email": "", "phone": ""}
	rows = frappe.get_list(
		"CRM Opt-In Submission",
		filters={"deal": deal},
		fields=["facility_witness_name", "facility_witness_email", "facility_witness_phone"],
		order_by="creation desc",
		limit=1,
		ignore_permissions=True,  # SYSTEM-INTERNAL
	)
	if rows:
		return {
			"name": frappe.utils.cstr(rows[0].get("facility_witness_name") or "").strip(),
			"email": frappe.utils.cstr(rows[0].get("facility_witness_email") or "").strip().lower(),
			"phone": frappe.utils.cstr(rows[0].get("facility_witness_phone") or "").strip(),
		}
	return {"name": "", "email": "", "phone": ""}


def _check_contract_rate_limit(limit=10, window=60):
	"""IP-based rate limit for guest contract signing endpoints (10 req/min/IP)."""
	request = getattr(frappe.local, "request", None)
	ip = request.environ.get("REMOTE_ADDR", "unknown") if request else "cli"
	cache_key = "contract_rl:%s" % ip
	count = frappe.cache().get_value(cache_key) or 0
	if int(count) >= limit:
		frappe.throw(_("Too many requests. Please wait before trying again."), frappe.PermissionError)
	frappe.cache().set_value(cache_key, int(count) + 1, expires_in_sec=window)


def _check_crm_role():
	"""Raise PermissionError if the current user lacks Sales Manager or System Manager."""
	user = frappe.session.user
	roles = frappe.get_roles(user)
	if "Sales Manager" not in roles and "System Manager" not in roles and user != "Administrator":
		frappe.throw(_("Not permitted."), frappe.PermissionError)


def _get_signatory_row(contract_doc, role, row_name=None):
	"""Return the signatory child row for role, or None.

	A role can legitimately repeat on one contract — a network with several
	configured signers yields several "Network Signatory" rows. When row_name
	(the child docname) is given, the exact row is returned so operations never
	hit the wrong person; without it, the first row for the role is returned
	(correct for the singular roles: facility signatory/witness).
	"""
	rows = [r for r in (contract_doc.signatories or []) if r.signatory_role == role]
	if row_name:
		for r in rows:
			if r.name == row_name:
				return r
		return None
	return rows[0] if rows else None


def _load_signatory(contract, role, row_name=None, for_update=False):
	"""Load the contract doc and the signatory row for role. Raise if either is missing."""
	contract_doc = frappe.get_doc("CRM Contract", contract, for_update=for_update)
	signatory_row = _get_signatory_row(contract_doc, role, row_name)
	if not signatory_row:
		frappe.throw(_("Signatory role not found in this contract."), frappe.DoesNotExistError)
	return contract_doc, signatory_row


def _load_signatory_by_token(contract, role, token, token_field):
	"""Resolve a signatory row for the guest signing flow by matching its token.

	Roles that repeat (multiple Network Signatory rows) each carry a unique
	invite/signing token, so the token — not the role — identifies the person.
	Falls back to the first role row when no token matches, so the downstream
	token validator raises the usual "invalid/expired link" error unchanged.
	"""
	contract_doc = frappe.get_doc("CRM Contract", contract)
	rows = [r for r in (contract_doc.signatories or []) if r.signatory_role == role]
	if not rows:
		frappe.throw(_("Signatory role not found in this contract."), frappe.DoesNotExistError)
	token = frappe.utils.cstr(token or "")
	if token:
		for r in rows:
			stored = frappe.utils.cstr(r.get(token_field) or "")
			if stored and hmac.compare_digest(stored, token):
				return contract_doc, r
	return contract_doc, rows[0]


def _invalidate_signature(row):
	"""Void a captured signature and its signing artefacts.

	Used when an edit means the signature no longer belongs to the current
	person/terms, so the audit trail never shows a signature for a signing event
	that no longer holds. Clears the signature image, IP, timestamp, the consumed
	OTP and any live signing session. Invite handling is left to the caller.
	"""
	row.signature_data = None
	row.signature_ip = None
	row.signed_at = None
	row.otp_hash = None
	row.otp_expiry = None
	row.otp_used = 0
	row.signing_token = None
	row.signing_expiry = None


def _validate_invite(signatory_row, token):
	"""Raise AuthenticationError unless token matches the stored, unexpired invite token."""
	stored = frappe.utils.cstr(signatory_row.invite_token or "")
	if (
		not stored
		or not signatory_row.invite_expiry
		or frappe.utils.now_datetime() > signatory_row.invite_expiry
	):
		frappe.throw(_("This signing link has expired."), frappe.AuthenticationError)
	if not hmac.compare_digest(stored, frappe.utils.cstr(token)):
		frappe.throw(_("Invalid signing link."), frappe.AuthenticationError)


def _save_otp_state(contract_doc, contract, role):
	"""Persist a newly issued OTP without exposing framework errors to guests.

	A contract save validates the complete parent and all child signatory rows, so
	a legacy contract with stale data can fail even though the signer only asked
	for a code. Keep the diagnostic traceback in Error Log, roll back the partial
	transaction, and return one actionable message to the public portal.
	"""
	try:
		contract_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			frappe.get_traceback(),
			"contracts.request_otp: unable to save OTP state for %s / %s" % (contract, role),
		)
		frappe.throw(
			_(
				"We couldn't prepare your verification code. Please try again. "
				"If the problem continues, ask the contract issuer to send a fresh link."
			),
			frappe.ValidationError,
		)


def _ensure_pending_signatory(signatory_row):
	"""Normalize legacy pending values before issuing the first OTP.

	Older contracts can contain an empty or differently-cased value because the
	child-table default was introduced after those rows were created. Treat only
	those equivalent pending values as recoverable; a completed or declined row
	must never be reopened by a public link.
	"""
	# A captured signature is stronger evidence than a stale Select value. This
	# prevents a contradictory Pending row from being reopened by a public link.
	if getattr(signatory_row, "signature_data", None) or getattr(signatory_row, "signed_at", None):
		signatory_row.status = "Signed"
		frappe.throw(_("This signing slot has already been completed."), frappe.ValidationError)

	status = " ".join(frappe.utils.cstr(signatory_row.status or "").strip().lower().split())
	if not status or status == "pending":
		signatory_row.status = "Pending"
		return
	if status in ("signed", "completed", "complete", "fully signed"):
		message = _("This signing slot has already been completed.")
	elif status in ("declined", "rejected", "cancelled", "canceled"):
		message = _(
			"This signing invitation is no longer active. Ask the contract issuer to send a new link."
		)
	else:
		message = _(
			"This signing invitation is not ready yet. Ask the contract issuer to review the contract."
		)
	frappe.throw(
		message,
		frappe.ValidationError,
	)


def _validate_signing(signatory_row, token):
	"""Raise AuthenticationError unless token matches the stored, unexpired signing token."""
	stored = frappe.utils.cstr(signatory_row.signing_token or "")
	if (
		not stored
		or not signatory_row.signing_expiry
		or frappe.utils.now_datetime() > signatory_row.signing_expiry
	):
		frappe.throw(_("Session expired. Please request a new code."), frappe.AuthenticationError)
	if not hmac.compare_digest(stored, frappe.utils.cstr(token)):
		frappe.throw(_("Verification failed."), frappe.AuthenticationError)


def _signing_progress(contract_doc):
	"""Return the minimal, recipient-safe contract signing progress.

	Every authenticated signatory may see who is required to execute the same
	contract and which signatures are complete. Email addresses, invitation
	tokens, OTPs, IPs and signature images remain private.
	"""
	progress = []
	for row in contract_doc.signatories or []:
		status = frappe.utils.cstr(row.status or "Pending")
		progress.append(
			{
				"name": frappe.utils.cstr(row.signatory_name or ""),
				"role": frappe.utils.cstr(row.signatory_role or ""),
				"status": "Signed" if status == "Signed" else "Awaiting signature",
			}
		)
	return progress


def _current_user_signatory(contract_name, role=""):
	"""Resolve the pending contract signer for the logged-in CRM user.

		Authenticated CRM users do not need a second email OTP: the Frappe session,
	the contract read permission, and the email-to-signatory match together prove
	the identity. Public invitation links continue to use the existing token + OTP
	path and are not changed by this helper.
	"""
	user = frappe.utils.cstr(frappe.session.user or "").strip()
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to review and sign this contract."), frappe.AuthenticationError)
	if not frappe.has_permission("CRM Contract", "read", contract_name):
		frappe.throw(_("You do not have access to this network's contract."), frappe.PermissionError)
	identity = frappe.db.get_value("User", user, ["email", "full_name"], as_dict=True) or frappe._dict()
	email = frappe.utils.cstr(identity.get("email") or user).strip().lower()
	doc = frappe.get_doc("CRM Contract", contract_name)
	requested_role = frappe.utils.cstr(role or "").strip()
	rows = [
		row
		for row in (doc.signatories or [])
		if row.signatory_role in _COUNTERPARTY_ROLES
		and (not requested_role or row.signatory_role == requested_role)
		and frappe.utils.cstr(row.signatory_email or "").strip().lower() == email
	]
	row = next(
		(
			candidate
			for candidate in rows
			if " ".join(frappe.utils.cstr(candidate.status or "").lower().split())
			in ("", "pending", "awaiting", "awaiting signature", "awaiting signatures", "invited", "sent")
		),
		rows[0] if rows else None,
	)
	# Counterparty invitations are released only after the facility signatory
	# completes. Keep the same ordering for the authenticated CRM branch so a
	# user-permission match cannot bypass the contract state machine.
	if row and row.signatory_role in _COUNTERPARTY_ROLES:
		facility = _get_signatory_row(doc, "Facility Signatory")
		facility_status = " ".join(frappe.utils.cstr(getattr(facility, "status", "") or "").lower().split())
		if facility_status not in ("signed", "completed", "complete", "fully signed"):
			row = None
	return doc, row, email, frappe.utils.cstr(identity.get("full_name") or "").strip()


def _attempts_cache_key(contract, role, row_name=""):
	# row_name disambiguates repeated roles (multiple Network Signatory rows) so
	# each signatory has its own brute-force counter rather than a shared one.
	return "contract_otp_attempts:%s:%s:%s" % (contract, role, row_name or "")


def _signing_link(contract_name, role, token):
	"""Build the guest signing-portal URL for an invitation token."""
	return frappe.utils.get_url(
		"/sign-contract?contract=%s&role=%s&token=%s" % (contract_name, role.replace(" ", "+"), token)
	)


def _sms_gateway_configured():
	"""Return whether Frappe has an SMS gateway configured."""
	try:
		return bool(frappe.db.get_single_value("SMS Settings", "sms_gateway_url"))
	except Exception:
		return False


def _new_sms_delivery(contract, signatory_row, purpose):
	"""Create a delivery audit row without making SMS availability transactional."""
	try:
		delivery = frappe.new_doc("CRM Contract SMS Delivery")
		delivery.contract = contract.name
		delivery.signatory_row = signatory_row.name
		delivery.signatory_role = frappe.utils.cstr(signatory_row.signatory_role)
		delivery.purpose = purpose
		delivery.recipient_phone = frappe.utils.cstr(
			getattr(signatory_row, "signatory_phone", "") or ""
		).strip()
		delivery.status = "Pending"
		delivery.attempts = 0
		delivery.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
		return delivery
	except Exception:
		# A site upgrading from an older CRM build may not have synced the new
		# DocType yet. Never prevent the contractual email from being delivered.
		frappe.log_error(
			frappe.get_traceback(),
			"contracts: unable to create SMS delivery audit row for %s" % contract.name,
		)
		return None


def _send_contract_sms(contract, signatory_row, purpose, message, delivery=None, commit=True):
	"""Send one contract SMS and persist a retryable, non-secret delivery status."""
	delivery = delivery or _new_sms_delivery(contract, signatory_row, purpose)
	phone = frappe.utils.cstr(getattr(signatory_row, "signatory_phone", "") or "").strip()
	if delivery:
		delivery.recipient_phone = phone
		delivery.attempts = frappe.utils.cint(delivery.attempts) + 1
		delivery.last_attempt_at = frappe.utils.now_datetime()

	if not phone or not _sms_gateway_configured():
		status = "Not Available"
		error = "No mobile number or SMS gateway is configured."
		if delivery:
			delivery.status = status
			delivery.last_error = error
			delivery.save(ignore_permissions=True)  # SYSTEM-INTERNAL
			if commit:
				frappe.db.commit()
		return status

	try:
		from frappe.core.doctype.sms_settings.sms_settings import send_sms

		send_sms([phone], message, success_msg=False)
		status = "Sent"
		if delivery:
			delivery.status = status
			delivery.sent_at = frappe.utils.now_datetime()
			delivery.last_error = ""
	except Exception as error:
		status = "Failed"
		if delivery:
			delivery.status = status
			delivery.last_error = frappe.utils.cstr(error)[:2000]
		frappe.log_error(
			frappe.get_traceback(),
			"contracts: SMS %s failed for %s / %s"
			% (purpose.lower(), contract.name, signatory_row.signatory_role),
		)

	if delivery:
		delivery.save(ignore_permissions=True)  # SYSTEM-INTERNAL
		if commit:
			frappe.db.commit()
	return status


def _invitation_sms_message(network, signatory_row, link):
	"""Build a concise mobile-friendly invitation message."""
	brand = frappe.utils.cstr((network or {}).get("display_name") or "CareverseHIMS")
	return (
		"%s: %s, please review and sign your contract: %s "
		"Your identity will be verified with an OTP. Link expires in 7 days."
		% (brand, frappe.utils.cstr(getattr(signatory_row, "signatory_name", "") or "Signatory"), link)
	)


def _otp_sms_message(network, signatory_row, otp):
	brand = frappe.utils.cstr((network or {}).get("display_name") or "CareverseHIMS")
	return "%s: your contract signing code is %s. It expires in 10 minutes." % (brand, otp)


def _invitation_sent_recently(signatory_row, now=None):
	"""Return whether this row received an invitation in the duplicate window."""
	last_sent = getattr(signatory_row, "crm_last_invitation_sent_at", None)
	if not last_sent:
		return False
	now = now or frappe.utils.now_datetime()
	try:
		age = (now - frappe.utils.get_datetime(last_sent)).total_seconds()
		return 0 <= age < _INVITATION_DEDUPE_SECONDS
	except (TypeError, ValueError):
		return False


def _mark_invitation_sent(signatory_row, sent_at=None, commit=True):
	"""Persist the latest successful invitation timestamp when the field exists."""
	sent_at = sent_at or frappe.utils.now_datetime()
	has_field = False
	try:
		has_field = frappe.db.has_column("CRM Contract Signatory", "crm_last_invitation_sent_at")
		if getattr(signatory_row, "name", None) and has_field:
			frappe.db.set_value(
				"CRM Contract Signatory",
				signatory_row.name,
				"crm_last_invitation_sent_at",
				sent_at,
				update_modified=False,
			)
	except Exception:
		pass
	if has_field or not getattr(signatory_row, "meta", None):
		signatory_row.crm_last_invitation_sent_at = sent_at
	if commit:
		frappe.db.commit()


def _issue_and_send_invitation(contract_doc, signatory_row, commit=True, reminder=False):
	"""
	Mint a fresh invitation token on the signatory row, persist it, and email the
	signatory a branded invitation with a Sign CTA. The caller is responsible for
	having a saved contract_doc; this saves its token write and, by default,
	commits it.

	commit=False keeps the token, contract, and queued invitation in the caller's
	transaction. This is used by the synchronous Opt-In pipeline so a failed
	submission cannot leave a contract or signing link behind.

	Contract invitations always use immediate delivery. This avoids a completed
	signing step being held behind a background Email Queue worker.

	`reminder=True` is reserved for an intentional follow-up from the CRM UI
	(Resend link or a signatory edit that requires a fresh link). It keeps the
	message distinct in inboxes without changing automatic invitation delivery.
	"""
	# CRM users sign from the authenticated Quote/Opt-In view.  Never mint or
	# deliver a public invitation (email or SMS) for this branch, including when
	# an executive explicitly presses Resend.
	if _is_internal_crm_signatory(signatory_row):
		_mark_internal_action_available(contract_doc, signatory_row)
		return None
	token = _gen_token()
	signatory_row.invite_token = token
	signatory_row.invite_expiry = frappe.utils.add_to_date(
		frappe.utils.now_datetime(), seconds=_INVITE_EXPIRY_SECONDS
	)
	contract_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL

	role = frappe.utils.cstr(signatory_row.signatory_role)
	link = _signing_link(contract_doc.name, role, token)
	network = _network_for_contract(contract_doc)
	name = frappe.utils.escape_html(frappe.utils.cstr(signatory_row.signatory_name))
	invitation_reference = _generate_invitation_email_reference()
	facility_subject = _contract_email_subject_label(contract_doc)

	queue = None
	email_sent = False
	try:
		subject_prefix = "[Reminder] " if reminder else ""
		queue = frappe.sendmail(
			recipients=[signatory_row.signatory_email],
			subject="%s%s — Contract ready for signature · Invitation ID %s"
			% (subject_prefix, facility_subject, invitation_reference),
			message=branded_email_html(
				network,
				heading="Contract ready for your signature",
				intro_html=(
					"<p style='margin:0 0 6px'>Dear %s,</p>"
					"<p style='margin:0'>You have been asked to review and sign a "
					"CareverseHIMS contract. Use the button below to open the secure "
					"signing portal — you'll confirm your identity with a one-time code.</p>" % name
				),
				cta_label="Review & Sign Contract",
				cta_url=link,
				note_html=(
					"This link expires in 7 days and is unique to you — please don't share it. "
					"Invitation reference: <strong>%s</strong>." % invitation_reference
				),
			),
			now=True,
		)
		email_sent = True
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"contracts._issue_and_send_invitation: email failed for %s / %s" % (contract_doc.name, role),
		)
	if email_sent:
		# Keep the marker in the same transaction as the rotated token. Committing
		# the token before the marker would leave a race where a second resend could
		# acquire the row lock in between and send another email.
		_mark_invitation_sent(signatory_row, commit=False)

	sms_status = _send_contract_sms(
		contract_doc,
		signatory_row,
		"Invitation",
		_invitation_sms_message(network, signatory_row, link),
		commit=False,
	)
	if commit:
		# now=True mail is dispatched by Frappe's after-commit callback. Commit only
		# after the token, dedupe marker, and SMS audit row are all persisted.
		frappe.db.commit()
	# Keep the historical return value (Email Queue document) intact for callers,
	# while exposing the latest SMS status to new callers.
	if queue is not None:
		try:
			queue.sms_status = sms_status
		except Exception:
			pass
	return queue


# ---------------------------------------------------------------------------
# State machine — private, not whitelisted
# ---------------------------------------------------------------------------


_COUNTERPARTY_ROLES = ("Network Signatory", "Tiberbu Signatory")
_POST_FACILITY_SIGNATORY_ROLES = ("Facility Witness", *_COUNTERPARTY_ROLES)
_INTERNAL_REMINDER_INTERVAL_SECONDS = 2 * 60 * 60


def _is_internal_crm_signatory(signatory_row):
	"""Return whether a counterparty signer should act inside the CRM session."""
	return bool(
		signatory_row
		and signatory_row.signatory_role in _COUNTERPARTY_ROLES
		and _crm_user_exists(getattr(signatory_row, "signatory_email", ""))
	)


def _mark_internal_action_available(contract, signatory_row):
	"""Record the first internal action hand-off without emitting an invitation."""
	if getattr(signatory_row, "crm_internal_action_notified_at", None):
		return False
	now = frappe.utils.now_datetime()
	has_field = False
	try:
		has_field = frappe.db.has_column("CRM Contract Signatory", "crm_internal_action_notified_at")
		if getattr(signatory_row, "name", None) and has_field:
			frappe.db.set_value(
				"CRM Contract Signatory",
				signatory_row.name,
				"crm_internal_action_notified_at",
				now,
				update_modified=False,
			)
	except Exception:
		pass
	if has_field or not getattr(signatory_row, "meta", None):
		signatory_row.crm_internal_action_notified_at = now
	log_deal_event(
		contract.deal,
		"CRM %s %s is ready to sign contract %s — login action required"
		% (
			frappe.utils.cstr(signatory_row.signatory_role),
			frappe.utils.cstr(signatory_row.signatory_name or signatory_row.signatory_email),
			contract.name,
		),
	)
	return True


def _transition(contract_name):
	"""
	Advance the contract workflow after a signatory signs. The Facility Signatory
	is the sole prerequisite. Once that person has signed, every remaining party
	(the Facility Witness, all Network Signatories, and the Tiberbu Signatory)
	receives an independent invitation in one transaction and may sign in any
	order. Each invite_token guard makes the operation idempotent.

	All signatories must still sign before the contract becomes Fully Executed.
	"""
	# Signing requests can arrive twice (double-clicks, browser retries, or two
	# open tabs). Serialize the invitation wave on the contract row, then reload
	# the latest child-table state. Without this lock two requests can both observe
	# empty invite_token values, rotate the same links, and send duplicate emails;
	# the first link then appears expired as soon as the second request commits.
	contract = frappe.get_doc("CRM Contract", contract_name, for_update=True)
	sigs = list(contract.signatories or [])
	if not sigs:
		return

	fac_sig = _get_signatory_row(contract, "Facility Signatory")
	fac_sig_signed = bool(fac_sig) and fac_sig.status == "Signed"

	# The first facility signature unlocks all remaining signatories at once.
	# commit=False keeps every token write and every now=True mail callback in a
	# single invitation wave. _set_contract_state commits it once below, so a
	# partially-issued wave cannot be delivered ahead of the rest.
	if fac_sig_signed:
		invited_any = False
		internal_action_any = False
		for row in sigs:
			if (
				row.signatory_role in _POST_FACILITY_SIGNATORY_ROLES
				and row.status == "Pending"
				and not row.invite_token
			):
				if _is_internal_crm_signatory(row):
					_mark_internal_action_available(contract, row)
					internal_action_any = True
					continue
				_issue_and_send_invitation(contract, row, commit=False)
				invited_any = True
		if invited_any or internal_action_any:
			_set_contract_state(contract, "Awaiting Remaining Signatures")
			if invited_any:
				log_deal_event(
					contract.deal,
					"Facility signatory signed contract %s — all external remaining "
					"signatories invited together (7-day links)" % contract.name,
				)

	# Done: all mandatory parties have signed. Tiberbu rows may be configured as
	# "At Least One" while facility, witness, and network rows remain mandatory.
	if _required_signatures_complete(contract):
		_set_contract_state(contract, "Fully Executed", status="Fully Executed")
		_send_fully_executed_contract(contract)
		# Internal approvers are notified only after every external signatory has
		# completed the contract. The notifier sends both immediate email and SMS.
		_notify_internal_approvers(contract.name, contract.deal)
		log_deal_event(
			contract.deal,
			"All parties signed contract %s — fully executed" % contract.name,
		)


def _internal_reminder_due(signatory_row, now=None):
	"""Return true when a two-hour CRM action reminder is due."""
	last_sent = getattr(signatory_row, "crm_last_reminder_at", None)
	if not last_sent:
		return True
	now = now or frappe.utils.now_datetime()
	try:
		return (
			now - frappe.utils.get_datetime(last_sent)
		).total_seconds() >= _INTERNAL_REMINDER_INTERVAL_SECONDS
	except (TypeError, ValueError):
		return True


def _send_internal_signatory_reminder(contract, signatory_row, network=None):
	"""Send one login-only reminder and record it on the linked Deal timeline."""
	email = frappe.utils.cstr(getattr(signatory_row, "signatory_email", "") or "").strip()
	if not email or not _is_internal_crm_signatory(signatory_row):
		return False
	action_url = frappe.utils.get_url("/opt-in-submissions?pending_my_action=1")
	facility_label = _contract_email_subject_label(contract)
	name = frappe.utils.cstr(getattr(signatory_row, "signatory_name", "") or email).strip()
	role = frappe.utils.cstr(getattr(signatory_row, "signatory_role", "") or "Signatory").strip()
	subject = "[Action needed] %s — Pending contract approval" % facility_label
	try:
		frappe.sendmail(
			recipients=[email],
			subject=subject,
			message=internal_signatory_reminder_html(
				network,
				signatory_name=name,
				role=role,
				facility_label=facility_label,
				action_url=action_url,
			),
			now=True,
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"contracts._send_internal_signatory_reminder: email failed for %s / %s" % (email, contract.name),
		)
		return False

	now = frappe.utils.now_datetime()
	has_field = False
	try:
		has_field = frappe.db.has_column("CRM Contract Signatory", "crm_last_reminder_at")
		if getattr(signatory_row, "name", None) and has_field:
			frappe.db.set_value(
				"CRM Contract Signatory",
				signatory_row.name,
				"crm_last_reminder_at",
				now,
				update_modified=False,
			)
	except Exception:
		pass
	if has_field or not getattr(signatory_row, "meta", None):
		signatory_row.crm_last_reminder_at = now
	log_deal_event(
		contract.deal,
		"Two-hour CRM action reminder sent to %s (%s) for contract %s" % (name, role, contract.name),
	)
	return True


def send_internal_signatory_reminders():
	"""Remind CRM-user signatories every two hours until they sign.

	This is a system scheduler entry.  It never sends a public contract link or
	OTP; the email points to the permission-scoped pending-action list instead.
	External signatories and all existing public invitation behavior are excluded.
	"""
	try:
		contracts = frappe.get_list(
			"CRM Contract",
			fields=["name"],
			filters={"status": ["in", ["Awaiting Remaining Signatures", "Pending", "Awaiting Signatures"]]},
			limit_page_length=0,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
	except Exception:
		return {"sent": 0, "skipped": 0}

	sent = skipped = 0
	now = frappe.utils.now_datetime()
	for summary in contracts:
		try:
			contract = frappe.get_doc("CRM Contract", summary.name)
			facility = _get_signatory_row(contract, "Facility Signatory")
			if not facility or facility.status != "Signed":
				continue
			network = _network_for_contract(contract)
			for row in contract.signatories or []:
				if (
					row.signatory_role not in _COUNTERPARTY_ROLES
					or row.status != "Pending"
					or not _is_internal_crm_signatory(row)
					or not _internal_reminder_due(row, now)
				):
					continue
				if _send_internal_signatory_reminder(contract, row, network):
					sent += 1
				else:
					skipped += 1
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"contracts.send_internal_signatory_reminders: contract failed %s" % summary.name,
			)
			skipped += 1
	try:
		frappe.db.commit()
	except Exception:
		pass
	return {"sent": sent, "skipped": skipped}


def _required_signatures_complete(contract):
	"""Evaluate completion using the requirement snapshot stored on the contract."""
	rows = list(contract.signatories or [])
	if not rows:
		return False
	mandatory = [row for row in rows if row.signatory_role != "Tiberbu Signatory"]
	if not all(row.status == "Signed" for row in mandatory):
		return False
	tiberbu = [row for row in rows if row.signatory_role == "Tiberbu Signatory"]
	if not tiberbu:
		return True
	requirement = (
		frappe.utils.cstr(getattr(contract, "tiberbu_signing_requirement", "All") or "All").strip().lower()
	)
	if requirement in ("at least one", "at least one must sign", "any"):
		return any(row.status == "Signed" for row in tiberbu)
	return all(row.status == "Signed" for row in tiberbu)


def _contract_has_field(contract, fieldname):
	"""Return whether a contract document supports an optional compatibility field."""
	meta = getattr(contract, "meta", None)
	if meta is not None:
		try:
			return bool(meta.has_field(fieldname))
		except Exception:
			pass
	return hasattr(contract, fieldname)


def _signatory_key(role, email):
	"""Return the stable role/email key used for per-contract exclusions."""
	return "::".join(
		(
			frappe.utils.cstr(role or "").strip().lower(),
			frappe.utils.cstr(email or "").strip().lower(),
		)
	)


def _excluded_signatory_keys(contract):
	"""Read normalized per-contract signatory exclusions safely."""
	if not _contract_has_field(contract, "excluded_signatories"):
		return set()
	raw = getattr(contract, "excluded_signatories", None)
	if not raw:
		return set()
	try:
		entries = json.loads(raw) if isinstance(raw, str) else raw
	except (TypeError, ValueError):
		return set()
	if not isinstance(entries, list):
		return set()
	return {
		_signatory_key(entry.get("role"), entry.get("email"))
		for entry in entries
		if isinstance(entry, dict) and entry.get("role") and entry.get("email")
	}


def _set_excluded_signatory(contract, role, email, excluded=True):
	"""Add or remove one role/email exclusion without affecting source settings."""
	if not _contract_has_field(contract, "excluded_signatories"):
		return False
	key = _signatory_key(role, email)
	if not key or key == "::":
		return False
	entries = []
	raw = getattr(contract, "excluded_signatories", None)
	if raw:
		try:
			parsed = json.loads(raw) if isinstance(raw, str) else raw
		except (TypeError, ValueError):
			parsed = []
		if isinstance(parsed, list):
			entries = [
				entry
				for entry in parsed
				if isinstance(entry, dict) and entry.get("role") and entry.get("email")
			]

	filtered = [entry for entry in entries if _signatory_key(entry.get("role"), entry.get("email")) != key]
	if excluded:
		filtered.append(
			{
				"role": frappe.utils.cstr(role or "").strip(),
				"email": frappe.utils.cstr(email or "").strip().lower(),
			}
		)
	contract.excluded_signatories = json.dumps(filtered, separators=(",", ":"))
	return True


def _reopen_stale_fully_executed_contract(contract):
	"""Reopen a completed contract when a new unsigned row was added.

	Adding a co-signatory after execution is supported from the quotation page.
	The child row correctly starts as ``Pending``, but older versions left the
	parent status at ``Fully Executed``. That contradictory state blocked the new
	person at the first OTP request. Treat the pending row as a new execution
	version: restore the normal signing status and clear the one-shot delivery
	marker so the updated fully executed PDF can be sent after the new row signs.

	Only an actually incomplete contract is changed; a genuinely completed
	contract remains protected by ``_ensure_contract_signing_open``.
	"""
	if getattr(contract, "status", "") != "Fully Executed":
		return False
	rows = list(contract.signatories or [])
	if not rows or all(row.status == "Signed" for row in rows):
		return False

	contract.status = "Awaiting Signatures"
	contract.workflow_state = "Awaiting Remaining Signatures"
	if hasattr(contract, "executed_contract_sent_at"):
		contract.executed_contract_sent_at = None
	return True


def _ensure_contract_signing_open(contract):
	"""Reject new signing actions after the contract has been completed.

	Repair the legacy state where an unsigned co-signatory was appended after the
	contract was marked fully executed. This keeps existing pending links usable
	without weakening the guard for genuinely completed contracts.
	"""
	if getattr(contract, "status", "") == "Fully Executed":
		if _reopen_stale_fully_executed_contract(contract):
			contract.save(ignore_permissions=True)  # SYSTEM-INTERNAL
			frappe.db.commit()
			log_deal_event(
				contract.deal,
				"Contract %s reopened because it has an unsigned signatory row" % contract.name,
			)
			return
		frappe.throw(
			_("This contract has already been fully executed."),
			frappe.ValidationError,
		)


def _send_fully_executed_contract(contract):
	"""Send the CRM Contract Standard PDF to the facility exactly once."""
	if getattr(contract, "executed_contract_sent_at", None):
		return False
	# Re-acquire the contract row lock after the state transition commit. This
	# closes the race where two final signature requests could otherwise both see
	# an empty sent marker and deliver the executed PDF twice.
	try:
		if frappe.db.get_value("CRM Contract", contract.name, "executed_contract_sent_at", for_update=True):
			return False
	except Exception:
		# Older sites may not have the marker column until migrate; the local guard
		# and the idempotent transition still preserve legacy behavior.
		pass
	facility = _get_signatory_row(contract, "Facility Signatory")
	recipient = frappe.utils.cstr(getattr(facility, "signatory_email", "") or "").strip().lower()
	if not recipient:
		frappe.log_error(
			"Fully executed contract %s has no facility recipient." % contract.name,
			"contracts._send_fully_executed_contract: recipient missing",
		)
		return False
	try:
		try:
			pdf_bytes = frappe.get_print(
				"CRM Contract",
				contract.name,
				print_format="CRM Contract Standard",
				as_pdf=True,
				no_letterhead=1,
			)
		except Exception:
			# Keep legacy sites working if the custom Print Format has not migrated yet.
			from frappe.utils.pdf import get_pdf

			pdf_bytes = get_pdf(_build_contract_document_html(contract))
		facility_label = _contract_email_subject_label(contract)
		frappe.sendmail(
			recipients=[recipient],
			subject="%s — Fully executed contract" % facility_label,
			message=branded_email_html(
				_network_for_contract(contract),
				heading="Your fully executed contract",
				intro_html=(
					"<p style='margin:0'>All required signatories have completed the "
					"<strong>%s</strong> agreement. The signed PDF is attached for your records.</p>"
					% frappe.utils.escape_html(facility_label)
				),
			),
			attachments=[{"fname": "%s-fully-executed.pdf" % contract.name, "fcontent": pdf_bytes}],
			reference_doctype="CRM Contract",
			reference_name=contract.name,
			now=True,
		)
		contract.executed_contract_sent_at = frappe.utils.now_datetime()
		contract.save(ignore_permissions=True)  # SYSTEM-INTERNAL
		frappe.db.commit()
		return True
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"contracts._send_fully_executed_contract: delivery failed for %s" % contract.name,
		)
		return False


def _set_contract_state(contract, workflow_state, status=None):
	"""Persist workflow_state (and optionally status) on a contract. SYSTEM-INTERNAL."""
	contract.workflow_state = workflow_state
	if status:
		contract.status = status
	contract.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()


def _notify_internal_approvers(contract_name, deal_name):
	"""
	Fetch network approvers and the Tiberbu approval contact from the CRM
	Onboarding Request linked to the deal. Network approvers remain User links for
	backward compatibility; the Tiberbu approver may be a name/email/phone contact
	with no CRM User account. Per-request Tiberbu contact fields override the
	global Opt-In Settings default, which in turn overrides the legacy User link.
	Send a branded approval-request email and SMS to each approver found. Email is
	still delivered immediately; SMS availability is recorded independently.
	"""
	onboarding_row = _onboarding_approver_row(deal_name)
	settings = _load_optin_settings_safely()
	approver_slots = []
	for slot in _APPROVER_SLOTS:
		if slot != "tiberbu_approver" and not onboarding_row.get(slot):
			continue
		identity = _approver_identity(slot, onboarding_row, settings)
		if identity.get("email") or identity.get("phone"):
			approver_slots.append((slot, identity))
	legacy_tiberbu_emails = {
		identity.get("email")
		for slot, identity in approver_slots
		if slot == "tiberbu_approver" and identity.get("email")
	}
	for index, identity in enumerate(_tiberbu_approvers(settings), 1):
		if identity.get("email") in legacy_tiberbu_emails:
			continue
		if identity.get("email") or identity.get("phone"):
			approver_slots.append(("tiberbu_approver_%s" % index, identity))

	# NOTE: approver fields live only on CRM Onboarding Request (plus the global
	# Tiberbu contact in Opt-In Settings), not on CRM Deal. If no approver is
	# configured, log a warning and return — do not query nonexistent Deal columns.
	if not approver_slots:
		frappe.log_error(
			"No CRM Onboarding Request linked to deal %s; cannot notify internal approvers "
			"for contract %s." % (deal_name, contract_name),
			"contracts._notify_internal_approvers: no onboarding request",
		)
		return

	network = None
	contract_doc = None
	try:
		contract_doc = frappe.get_doc("CRM Contract", contract_name)
		network = _network_for_contract(contract_doc)
	except Exception:
		pass

	crm_url = frappe.utils.get_url("/crm/deals/%s" % deal_name) if deal_name else frappe.utils.get_url()
	pending_url = frappe.utils.get_url("/opt-in-submissions?pending_my_action=1")

	for approver_slot, identity in approver_slots:
		approver_email = identity.get("email", "")
		approver_name = identity.get("full_name", "") or approver_email or approver_slot
		approver_role = approver_slot.replace("_", " ").title()
		is_crm_user = _crm_user_exists(approver_email)
		action_url = pending_url if is_crm_user else crm_url
		if is_crm_user:
			approval_intro = (
				"<p style='margin:0 0 6px'>Hello,</p>"
				"<p style='margin:0'>All contract signatories have signed "
				"<strong>%s</strong>. Sign in to CRM to review your pending approval.</p>"
			)
		else:
			approval_intro = (
				"<p style='margin:0 0 6px'>Hello,</p>"
				"<p style='margin:0'>All contract signatories have signed contract "
				"<strong>%s</strong>. It now requires your internal approval before it "
				"can be executed.</p>"
			)
		approval_intro = approval_intro % frappe.utils.escape_html(contract_name)
		if approver_email:
			try:
				frappe.sendmail(
					recipients=[approver_email],
					subject=(
						"%s — Contract approval required · %s"
						% (_contract_email_subject_label(contract_doc), contract_name)
					),
					message=branded_email_html(
						network,
						heading="Contract awaiting your approval",
						intro_html=approval_intro,
						cta_label="Sign in to review" if is_crm_user else "Open in CRM",
						cta_url=action_url,
					),
					now=True,
				)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					"contracts._notify_internal_approvers: email failed for approver %s on %s"
					% (approver_email, contract_name),
				)

		# Keep the approver reference in the audit row so a failed SMS can be
		# retried after the user's mobile number or gateway is corrected. The row is
		# intentionally not a Contract Signatory child row.
		if contract_doc:
			approver_reference = "%s:%s" % (
				frappe.utils.cstr(onboarding_row.get("name") or "settings"),
				approver_slot,
			)
			approver_row = frappe._dict(
				{
					"name": approver_reference,
					"signatory_name": approver_name,
					"signatory_role": approver_role,
					"signatory_phone": identity.get("phone", ""),
				}
			)
			_send_contract_sms(
				contract_doc,
				approver_row,
				"Approval",
				_approval_sms_message(network, contract_name, approver_name, action_url),
			)


def _approval_sms_message(network, contract_name, approver_name, crm_url):
	"""Build a concise SMS for an internal contract approver."""
	brand = frappe.utils.cstr((network or {}).get("display_name") or "CareverseHIMS")
	return "%s: %s, contract %s is ready for your approval. Open CRM: %s" % (
		brand,
		approver_name,
		contract_name,
		crm_url,
	)


def _approval_identity_for_delivery(contract_doc, delivery):
	"""Resolve a retry recipient from current onboarding/settings data."""
	role = frappe.utils.cstr(delivery.signatory_role or "").strip()
	slot = _APPROVER_ROLE_TO_SLOT.get(role)
	if slot:
		identity = _approver_identity(
			slot,
			_onboarding_approver_row(contract_doc.deal),
			_load_optin_settings_safely(),
		)
	elif role.startswith("Tiberbu Approver"):
		try:
			index = int(role.rsplit(" ", 1)[-1]) - 1
		except (TypeError, ValueError):
			index = 0
		contacts = _tiberbu_approvers(_load_optin_settings_safely())
		identity = contacts[index] if 0 <= index < len(contacts) else {}
	else:
		identity = _resolve_user_identity(
			delivery.signatory_row,
			fallback_phone=delivery.recipient_phone,
		)
	if not identity.get("phone"):
		identity["phone"] = frappe.utils.cstr(delivery.recipient_phone or "").strip()
	return identity


# ---------------------------------------------------------------------------
# Whitelisted API — CRM users only
# ---------------------------------------------------------------------------


@frappe.whitelist()
def check_user_email(email: Any = ""):
	"""Report whether an email belongs to an enabled Frappe User.

	The Quote page uses this before adding a Tiberbu signatory so an executive can
	see which signing path will be used. Keep the lookup aligned with
	``_crm_user_exists``: disabled accounts are treated as external signers. Only
	the account's display name is returned; no user profile data is exposed.

	Requires: Sales Manager, System Manager, or Administrator.
	"""
	_check_crm_role()
	email = frappe.utils.cstr(email or "").strip().lower()
	if not email:
		return {"checked": False, "linked": False, "full_name": ""}

	rows = frappe.get_list(
		"User",
		filters={"email": email, "enabled": 1},
		fields=["email", "full_name"],
		limit=1,
	)
	user = rows[0] if rows else None
	return {
		"checked": True,
		"linked": bool(user),
		"full_name": frappe.utils.cstr(user.get("full_name") or "") if user else "",
	}


@frappe.whitelist()
def get_network_signatories(deal: Any = "", network_slug: Any = ""):
	"""
	Resolve the co-signatories that will be seeded onto a contract: every
	Network Signatory configured on the deal's network plus all configured Tiberbu
	Signatories. Powers the auto-populate on the Quote/Contracting page.

	Requires: Sales Manager or System Manager role.
	Returns: {network_slug, signers: [{full_name, email, phone, signer_role}],
	approvers: [{full_name, email, phone, contact_role}]}
	"""
	_check_crm_role()

	deal = frappe.utils.cstr(deal).strip()
	network_slug = frappe.utils.cstr(network_slug).strip()
	if not network_slug and deal:
		network_slug = _resolve_network_slug(deal) or ""

	signers = [dict(s, signer_role="Network Signatory") for s in _network_signers(network_slug)]
	signers.extend(dict(s, signer_role="Tiberbu Signatory") for s in _tiberbu_signers())

	return {
		"network_slug": network_slug,
		"signers": signers,
		"approvers": [dict(contact, contact_role="Tiberbu Approver") for contact in _tiberbu_approvers()],
		"tiberbu_signing_requirement": _tiberbu_signing_requirement(),
	}


@frappe.whitelist()
def sync_configured_signatories(contract: Any):
	"""Synchronize current network/Tiberbu contacts onto an unsigned contract.

	Signed rows are never changed. New or changed unsigned rows are persisted and
	then passed through the normal transition so invitations are sent only when the
	facility signature has unlocked the remaining parties.
	"""
	_check_crm_role()
	contract_name = frappe.utils.cstr(contract).strip()
	if not contract_name:
		frappe.throw(_("Contract is required."), frappe.ValidationError)
	doc = frappe.get_doc("CRM Contract", contract_name)
	configured = [dict(row, signer_role="Network Signatory") for row in _network_signers(doc.network_slug)]
	tiberbu_configured = _tiberbu_signers()
	configured.extend(dict(row, signer_role="Tiberbu Signatory") for row in tiberbu_configured)
	tiberbu_pending = [
		row
		for row in (doc.signatories or [])
		if row.signatory_role == "Tiberbu Signatory" and row.status != "Signed"
	]
	added = updated = skipped_signed = 0
	for identity in configured:
		role = identity["signer_role"]
		email = identity["email"]
		row = next(
			(
				candidate
				for candidate in (doc.signatories or [])
				if candidate.signatory_role == role
				and frappe.utils.cstr(candidate.signatory_email or "").strip().lower() == email
			),
			None,
		)
		# A removal is scoped to this contract. Check it before the legacy Tiberbu
		# re-key fallback so a removed identity can never be resurrected by sync.
		if not row and _signatory_key(role, email) in _excluded_signatory_keys(doc):
			continue
		# A single unsigned Tiberbu row is the safe legacy equivalent of a changed
		# settings contact email. Re-key it in place instead of leaving a stale
		# pending row that would block the all-signers rule.
		if (
			not row
			and role == "Tiberbu Signatory"
			and len(tiberbu_configured) == 1
			and len(tiberbu_pending) == 1
		):
			row = tiberbu_pending[0]
		if row:
			changed = (
				frappe.utils.cstr(row.signatory_email or "").strip().lower() != email
				or frappe.utils.cstr(row.signatory_name or "").strip() != identity["full_name"]
				or frappe.utils.cstr(row.signatory_phone or "").strip() != identity.get("phone", "")
			)
			if not changed:
				continue
			if (
				row.status == "Signed"
				or getattr(row, "signature_data", None)
				or getattr(row, "signed_at", None)
			):
				skipped_signed += 1
				continue
			row.signatory_name = identity["full_name"]
			if frappe.utils.cstr(row.signatory_email or "").strip().lower() != email:
				row.signatory_email = email
				row.invite_token = None
				row.invite_expiry = None
				row.signing_token = None
				row.signing_expiry = None
			row.signatory_phone = identity.get("phone", "")
			updated += 1
			continue
		doc.append(
			"signatories",
			{
				"signatory_name": identity["full_name"],
				"signatory_email": email,
				"signatory_phone": identity.get("phone", ""),
				"signatory_role": role,
				"status": "Pending",
				"is_witness": 0,
			},
		)
		added += 1
	if added or updated:
		reopened = _reopen_stale_fully_executed_contract(doc)
		doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
		frappe.db.commit()
		_transition(contract_name)
		if reopened:
			log_deal_event(
				doc.deal,
				"Contract %s reopened after configured signatory changes" % contract_name,
			)
	if added or updated or skipped_signed:
		log_deal_event(
			doc.deal,
			"Configured signatories synced on contract %s (added %s, updated %s, signed rows skipped %s)"
			% (contract_name, added, updated, skipped_signed),
		)
	return {"status": "synced", "added": added, "updated": updated, "skipped_signed": skipped_signed}


def _generate_contract(
	deal,
	quote,
	facility_signatory_name,
	facility_signatory_email,
	facility_witness_name,
	facility_witness_email,
	network_approver_1="",
	network_approver_2="",
	tiberbu_approver="",
	commit=True,
	facility_signatory_phone="",
	facility_witness_phone="",
):
	"""
	Create a CRM Contract for a deal, render contract HTML from active T&C, and
	seed all signatory rows: Facility Signatory, Facility Witness, every configured
	Network Signatory, and all configured Tiberbu Signatories. Only the Facility Signatory
	is invited immediately; the rest are invited by the state machine in order
	(see _transition). network_approver_* params are legacy no-ops — the network /
	tiberbu co-signatories now come from configuration.

	commit=False keeps creation and the facility-signatory invitation within the
	caller's database transaction. The public generate() API uses commit=True,
	preserving the existing CRM-executive workflow.

	Returns: {contract: <name>, invitation_queue: <Email Queue name or "">}
	"""
	deal = frappe.utils.cstr(deal).strip()
	quote = frappe.utils.cstr(quote).strip()
	facility_signatory_name = frappe.utils.cstr(facility_signatory_name).strip()
	facility_signatory_email = frappe.utils.cstr(facility_signatory_email).strip().lower()
	facility_witness_name = frappe.utils.cstr(facility_witness_name).strip()
	facility_witness_email = frappe.utils.cstr(facility_witness_email).strip().lower()
	facility_signatory_phone = frappe.utils.cstr(facility_signatory_phone or "").strip()
	facility_witness_phone = frappe.utils.cstr(facility_witness_phone or "").strip()

	if not deal:
		frappe.throw(_("Deal is required to generate a contract."))

	# A double-click, two browser tabs, or a retried HTTP request must not create
	# two contracts (and therefore two facility invitations) for one deal. The
	# deal lock makes the check-and-create sequence atomic for callers using this
	# endpoint; returning the existing record makes retries safe and predictable.
	_lock_deal_for_contract_generation(deal)
	existing_contract = _existing_contract_for_deal(deal)
	if existing_contract:
		return {
			"contract": existing_contract.name,
			"invitation_queue": _existing_contract_invitation_queue(existing_contract.name),
			"already_exists": True,
		}

	# Witness falls back to what the facility captured on their opt-in submission,
	# so the exec need not re-key it.
	if not facility_witness_email or not facility_witness_name:
		ois_witness = _facility_witness_from_deal(deal)
		facility_witness_name = facility_witness_name or ois_witness["name"]
		facility_witness_email = facility_witness_email or ois_witness["email"]
		facility_witness_phone = facility_witness_phone or ois_witness.get("phone", "")

	if not facility_signatory_email or not facility_witness_email:
		frappe.throw(_("Signatory and witness email addresses are required."))

	# Render contract HTML from active T&C template
	contract_html = ""
	tc_document = ""
	tc_document_hash = ""

	try:
		settings = frappe.get_single("CRM Opt-In Settings")
		tc_name = settings.active_tc_document
		if tc_name:
			tc_doc = frappe.get_doc("Terms and Conditions", tc_name)
			# The T&C template needs the full network/contact/pricing context the
			# customer accepted; a minimal {deal, date} context raises UndefinedError
			# ('network' is undefined) and leaves contract_html empty.
			from crm.api.optin import build_tc_context_for_deal

			context = build_tc_context_for_deal(deal) or {}
			context.setdefault("deal", deal)
			context.setdefault("quote", quote)
			context.setdefault("facility_signatory_name", facility_signatory_name)
			context.setdefault("date", frappe.utils.format_date(frappe.utils.today()))
			contract_html = frappe.render_template(tc_doc.terms or "", context)
			tc_document = tc_name
			tc_document_hash = hashlib.sha256(contract_html.encode()).hexdigest()
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"contracts.generate: T&C render failed for deal %s" % deal,
		)

	# Create the CRM Contract document
	contract = frappe.new_doc("CRM Contract")
	contract.naming_series = "CONT-"
	contract.deal = deal
	contract.quote = quote or None
	contract.contract_date = frappe.utils.today()
	contract.status = "Awaiting Signatures"
	contract.workflow_state = "Awaiting Facility Signature"
	contract.contract_html = contract_html
	contract.tc_document = tc_document
	contract.tc_document_hash = tc_document_hash
	network_slug = _resolve_network_slug(deal)
	contract.network_slug = network_slug
	set_network_link(contract, network_slug)
	# Preserve the commercial provenance alongside the executed contract. The
	# quotation is the source of truth; legacy quotes without the optional fields
	# degrade to a truthful current-only snapshot.
	price_snapshot = {}
	if quote and frappe.db.exists("Quotation", quote):
		try:
			price_snapshot = snapshot(frappe.get_doc("Quotation", quote))
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"contracts.generate: price-list snapshot failed for %s" % deal,
			)
	set_snapshot(contract, price_snapshot)

	# Row 1: Facility Signatory (invited immediately below).
	contract.append(
		"signatories",
		{
			"signatory_name": facility_signatory_name,
			"signatory_email": facility_signatory_email,
			"signatory_phone": facility_signatory_phone,
			"signatory_role": "Facility Signatory",
			"status": "Pending",
			"is_witness": 0,
		},
	)

	# Row 2: Facility Witness (invited with every remaining party once the
	# facility signatory has signed).
	contract.append(
		"signatories",
		{
			"signatory_name": facility_witness_name,
			"signatory_email": facility_witness_email,
			"signatory_phone": facility_witness_phone,
			"signatory_role": "Facility Witness",
			"status": "Pending",
			"is_witness": 1,
			"witnessing_for": facility_signatory_name,
		},
	)

	# Rows 3..N: network co-signatories from the network configuration. They are
	# invited with every other remaining party after the facility signatory signs.
	for signer in _network_signers(network_slug):
		contract.append(
			"signatories",
			{
				"signatory_name": signer["full_name"] or signer["email"],
				"signatory_email": signer["email"],
				"signatory_phone": signer.get("phone", ""),
				"signatory_role": "Network Signatory",
				"status": "Pending",
				"is_witness": 0,
			},
		)

	# Rows N+1..M: all configured Tiberbu co-signatories.
	settings = _load_optin_settings_safely()
	contract.tiberbu_signing_requirement = _tiberbu_signing_requirement(settings)
	for tb in _tiberbu_signers(settings):
		contract.append(
			"signatories",
			{
				"signatory_name": tb["full_name"] or tb["email"],
				"signatory_email": tb["email"],
				"signatory_phone": tb.get("phone", ""),
				"signatory_role": "Tiberbu Signatory",
				"status": "Pending",
				"is_witness": 0,
			},
		)

	contract.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	if commit:
		frappe.db.commit()

	# Send invitation to the Facility Signatory immediately
	signatory_row = _get_signatory_row(contract, "Facility Signatory")
	invitation_queue = None
	if signatory_row:
		invitation_queue = _issue_and_send_invitation(contract, signatory_row, commit=commit)

	log_deal_event(
		deal,
		"Contract %s generated — signing invitation sent to %s" % (contract.name, facility_signatory_email),
	)
	return {
		"contract": contract.name,
		"invitation_queue": invitation_queue.name if invitation_queue else "",
	}


@frappe.whitelist()
def generate(
	deal: Any,
	quote: Any,
	facility_signatory_name: Any,
	facility_signatory_email: Any,
	facility_witness_name: Any,
	facility_witness_email: Any,
	network_approver_1: Any = "",
	network_approver_2: Any = "",
	tiberbu_approver: Any = "",
	facility_signatory_phone: Any = "",
	facility_witness_phone: Any = "",
):
	"""
	Create and send a contract from the CRM Deal page.

	Requires: Sales Manager or System Manager role.
	Returns: {contract: <name>}.
	"""
	_check_crm_role()
	result = _generate_contract(
		deal=deal,
		quote=quote,
		facility_signatory_name=facility_signatory_name,
		facility_signatory_email=facility_signatory_email,
		facility_witness_name=facility_witness_name,
		facility_witness_email=facility_witness_email,
		facility_signatory_phone=facility_signatory_phone,
		facility_witness_phone=facility_witness_phone,
		network_approver_1=network_approver_1,
		network_approver_2=network_approver_2,
		tiberbu_approver=tiberbu_approver,
		commit=True,
	)
	return {"contract": result["contract"]}


@frappe.whitelist()
def resend_invitation(contract: Any, role: Any, row_name: Any = None):
	"""
	Regenerate the invitation link for a still-pending signatory and re-send the
	branded invitation email. Requires: Sales Manager or System Manager role.

	row_name (the signatory child docname) targets the exact row when a role
	repeats (multiple Network Signatory rows); omit it for the singular roles.

	Returns: {status: "sent", email: <signatory_email>}
	"""
	_check_crm_role()

	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()
	row_name = frappe.utils.cstr(row_name).strip() or None

	# Lock the parent while checking and rotating the token. A browser retry that
	# arrives while the first resend is committing must observe its timestamp and
	# be suppressed instead of sending a second link.
	contract_doc, signatory_row = _load_signatory(contract, role, row_name, for_update=True)

	if signatory_row.status != "Pending":
		_ensure_pending_signatory(signatory_row)

	if _is_internal_crm_signatory(signatory_row):
		_mark_internal_action_available(contract_doc, signatory_row)
		return {"status": "crm_login_required", "email": signatory_row.signatory_email}

	if _invitation_sent_recently(signatory_row):
		log_deal_event(
			contract_doc.deal,
			"Duplicate signing-link resend suppressed for %s on contract %s"
			% (signatory_row.signatory_email, contract),
		)
		return {"status": "already_sent", "email": signatory_row.signatory_email}

	# Before the facility signatory completes, remaining signatories have no invite
	# token and cannot be resent. After that point they are invited together.
	if not signatory_row.invite_token:
		frappe.throw(
			_(
				"This signatory hasn't been invited yet — all remaining signatories "
				"are invited automatically after the facility signatory signs."
			),
			frappe.ValidationError,
		)

	_issue_and_send_invitation(contract_doc, signatory_row, reminder=True)

	log_deal_event(
		contract_doc.deal,
		"Signing invitation for %s re-sent to %s (contract %s)"
		% (role, signatory_row.signatory_email, contract),
	)
	return {"status": "sent", "email": signatory_row.signatory_email}


@frappe.whitelist()
def retry_sms_delivery(notification: Any):
	"""Retry a failed contract SMS without rotating an invitation email link.

	OTP SMS retries are intentionally performed by the signatory's existing
	"request a new code" action: the server never stores a recoverable OTP. This
	endpoint retries invitation and approval delivery and is safe to expose to CRM
	managers as an idempotent operational action.
	"""
	_check_crm_role()
	notification = frappe.utils.cstr(notification).strip()
	if not notification:
		frappe.throw(_("An SMS delivery record is required."), frappe.ValidationError)
	delivery = frappe.get_doc("CRM Contract SMS Delivery", notification)
	if delivery.purpose not in ("Invitation", "Approval"):
		frappe.throw(
			_("OTP SMS cannot be retried from CRM. Ask the signatory to request a new code."),
			frappe.ValidationError,
		)
	if delivery.status not in ("Failed", "Not Available"):
		frappe.throw(_("This SMS does not need a retry."), frappe.ValidationError)

	contract_doc = frappe.get_doc("CRM Contract", delivery.contract)
	if delivery.purpose == "Approval":
		identity = _approval_identity_for_delivery(contract_doc, delivery)
		if not identity.get("phone"):
			frappe.throw(_("This approver SMS has no recipient reference."), frappe.ValidationError)
		role = frappe.utils.cstr(delivery.signatory_role or "Contract Approver").strip()
		approver_row = frappe._dict(
			{
				"name": frappe.utils.cstr(delivery.signatory_row or "").strip(),
				"signatory_name": identity.get("full_name") or identity.get("email") or role,
				"signatory_role": role,
				"signatory_phone": identity.get("phone", ""),
			}
		)
		crm_url = (
			frappe.utils.get_url("/crm/deals/%s" % contract_doc.deal)
			if contract_doc.deal
			else frappe.utils.get_url()
		)
		status = _send_contract_sms(
			contract_doc,
			approver_row,
			"Approval",
			_approval_sms_message(
				_network_for_contract(contract_doc),
				contract_doc.name,
				identity.get("full_name") or identity.get("email") or role,
				crm_url,
			),
			delivery=delivery,
		)
		return {"status": status, "notification": delivery.name}

	signatory_row = next(
		(row for row in contract_doc.signatories or [] if row.name == delivery.signatory_row),
		None,
	)
	if not signatory_row or signatory_row.status != "Pending" or not signatory_row.invite_token:
		frappe.throw(_("This signing invitation is no longer active."), frappe.ValidationError)

	link = _signing_link(contract_doc.name, signatory_row.signatory_role, signatory_row.invite_token)
	status = _send_contract_sms(
		contract_doc,
		signatory_row,
		"Invitation",
		_invitation_sms_message(_network_for_contract(contract_doc), signatory_row, link),
		delivery=delivery,
	)
	return {"status": status, "notification": delivery.name}


@frappe.whitelist()
def get_sms_delivery_status(contract: Any):
	"""Return safe SMS delivery status for a contract's CRM signatory panel."""
	_check_crm_role()
	contract = frappe.utils.cstr(contract).strip()
	if not contract:
		return []
	return frappe.get_list(
		"CRM Contract SMS Delivery",
		filters={"contract": contract},
		fields=[
			"name",
			"signatory_row",
			"signatory_role",
			"purpose",
			"status",
			"attempts",
			"last_attempt_at",
			"sent_at",
			"last_error",
		],
		order_by="modified desc",
		limit_page_length=100,
	)


@frappe.whitelist()
def update_signatory(
	contract: Any,
	role: Any,
	name: Any,
	email: Any,
	row_name: Any = None,
	phone: Any = "",
):
	"""
	Update the name/email of a signatory. Requires: Sales Manager or System
	Manager role.

	row_name (the signatory child docname) targets the exact row when a role
	repeats (multiple Network Signatory rows) — without it a repeated role would
	resolve to the first row and could invalidate the wrong person's signature.
	Omit it for the singular roles (facility signatory/witness, Tiberbu).

	Pending and Declined rows are editable. A captured signature is immutable: a
	signed row cannot be edited or replaced, even if the source settings change.
	If an unsigned row had an outstanding invite and its email changes, a fresh
	signing link is issued and the old link is invalidated.

	Returns: {status: "updated", email, resent: bool}
	"""
	_check_crm_role()

	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()
	name = frappe.utils.cstr(name).strip()
	email = frappe.utils.cstr(email).strip().lower()
	phone = frappe.utils.cstr(phone or "").strip()
	row_name = frappe.utils.cstr(row_name).strip() or None

	if not name or not email:
		frappe.throw(_("Signatory name and email are required."))

	contract_doc, signatory_row = _load_signatory(contract, role, row_name, for_update=True)

	if (
		signatory_row.status == "Signed"
		or getattr(signatory_row, "signature_data", None)
		or getattr(signatory_row, "signed_at", None)
	):
		frappe.throw(
			_("This signatory has already signed and cannot be edited."),
			frappe.ValidationError,
		)
	email_changed = frappe.utils.cstr(signatory_row.signatory_email or "").strip().lower() != email

	signatory_row.signatory_name = name
	signatory_row.signatory_email = email
	signatory_row.signatory_phone = phone

	# A corrected non-Pending row (Declined, or a just-invalidated Signed one)
	# returns to Pending so it re-enters the signing flow.
	if signatory_row.status != "Pending":
		signatory_row.status = "Pending"
	# The facility witness attests to the facility signatory's signing event.
	if role == "Facility Signatory":
		witness = _get_signatory_row(contract_doc, "Facility Witness")
		if witness:
			# Keep the "witnessing_for" label in sync when the principal is renamed.
			witness.witnessing_for = name

	# Re-issue a fresh link when the address changed on an already-invited row,
	# preserving the signed audit trail. Re-issuing mints a new token (invalidating
	# the stale link), emails it, saves, and commits.
	already_invited = bool(signatory_row.invite_token)
	resent = False
	if email_changed and already_invited:
		_issue_and_send_invitation(contract_doc, signatory_row, reminder=True)
		resent = True
	else:
		contract_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
		frappe.db.commit()

	log_deal_event(
		contract_doc.deal,
		"Signatory %s updated on contract %s%s"
		% (role, contract, (" — new invitation sent to %s" % email) if resent else ""),
	)
	return {"status": "updated", "email": email, "resent": resent}


@frappe.whitelist()
def add_signatory(contract: Any, role: Any, name: Any, email: Any, phone: Any = ""):
	"""
	Add a Network/Tiberbu co-signatory row to a contract that is missing it —
	e.g. a contract generated before co-signatories were wired, or where the
	network/Tiberbu configuration changed after generation.
	Requires: Sales Manager or System Manager role.

	The new row is Pending and un-invited: it is invited automatically once the
	facility signatory has signed (see _transition), or the exec can Resend.
	Both roles are deduped on email so the same person is not added twice; multiple
	Tiberbu signatories are supported by the settings table.

	Returns: {status: "added", role, email}
	"""
	_check_crm_role()

	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()
	name = frappe.utils.cstr(name).strip()
	email = frappe.utils.cstr(email).strip().lower()
	phone = frappe.utils.cstr(phone or "").strip()

	if role not in _COUNTERPARTY_ROLES:
		frappe.throw(_("Only Network and Tiberbu co-signatories can be added here."))
	if not name or not email:
		frappe.throw(_("Signatory name and email are required."))

	contract_doc = frappe.get_doc("CRM Contract", contract)

	for row in contract_doc.signatories or []:
		if row.signatory_role != role:
			continue
		if frappe.utils.cstr(row.signatory_email or "").strip().lower() == email:
			frappe.throw(_("This co-signatory is already on the contract."))

	contract_doc.append(
		"signatories",
		{
			"signatory_name": name,
			"signatory_email": email,
			"signatory_phone": phone,
			"signatory_role": role,
			"status": "Pending",
			"is_witness": 0,
		},
	)
	_set_excluded_signatory(contract_doc, role, email, excluded=False)
	_reopened = _reopen_stale_fully_executed_contract(contract_doc)
	contract_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()

	log_deal_event(
		contract_doc.deal,
		"Co-signatory %s (%s) added to contract %s" % (role, email, contract),
	)
	if _reopened:
		log_deal_event(
			contract_doc.deal,
			"Contract %s reopened after adding an unsigned co-signatory" % contract,
		)

	# If the facility signatory has already signed (the common legacy case — the
	# contract predates co-signing), the new counterparty would otherwise sit
	# Pending and un-invited forever, because invitations are only issued from
	# _transition on a signature event. _transition is ordered + idempotent
	# (guards on invite_token) so it safely invites the new row now if it is due.
	_transition(contract)

	return {"status": "added", "role": role, "email": email}


@frappe.whitelist()
def remove_signatory(contract: Any, role: Any, row_name: Any = None):
	"""Remove an unsigned Network/Tiberbu co-signatory from one contract.

	The configured network or global Tiberbu signer is deliberately left in its
	source configuration so future contracts retain that contact. Removing the
	contract row invalidates its invitation and OTP state because the old row (and
	its tokens) no longer belongs to the signing workflow. A captured signature is
	never removable; use the existing signed-row replacement flow instead.
	"""
	_check_crm_role()

	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()
	row_name = frappe.utils.cstr(row_name).strip() or None

	if role not in _COUNTERPARTY_ROLES:
		frappe.throw(
			_("Only Network and Tiberbu co-signatories can be removed here."),
			frappe.ValidationError,
		)
	if not row_name:
		frappe.throw(
			_("The exact signatory row is required."),
			frappe.ValidationError,
		)

	contract_doc, signatory_row = _load_signatory(contract, role, row_name)
	status = " ".join(frappe.utils.cstr(signatory_row.status or "").lower().split())
	if (
		status in ("signed", "completed", "complete", "fully signed")
		or getattr(signatory_row, "signature_data", None)
		or getattr(signatory_row, "signed_at", None)
	):
		frappe.throw(
			_("This signatory has already signed and cannot be removed."),
			frappe.ValidationError,
		)

	removed_email = frappe.utils.cstr(signatory_row.signatory_email or "").strip().lower()
	removed_name = frappe.utils.cstr(signatory_row.signatory_name or "").strip()
	contract_doc.remove(signatory_row)
	_set_excluded_signatory(contract_doc, role, removed_email)
	contract_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	log_deal_event(
		contract_doc.deal,
		"Co-signatory %s (%s) removed from contract %s before signing"
		% (role, removed_email or removed_name, contract),
	)
	frappe.db.commit()

	# Removing the last pending party can make a contract fully executable. Reuse
	# the normal idempotent transition so state and approval notifications remain
	# consistent with a real signature event.
	_transition(contract)

	return {"status": "removed", "role": role, "email": removed_email}


def _sync_network_signer_on_contract(contract, name, email, phone, original_email):
	"""Reflect a network-config signer change onto a live contract's Network
	Signatory row. Reuses the whitelisted row operations so the Signed-row
	invalidation + re-invite semantics (see update_signatory) are identical:
	edit the matching row (found by its original email, or by the new email when
	the row was already renamed) or add a new Pending row when the contract has
	none for that person yet.

	The new email is matched as a fallback so a rename to an address already on
	the contract updates that row rather than making add_signatory throw
	"already on the contract" (which would strand the just-committed config change).
	"""
	contract_doc = frappe.get_doc("CRM Contract", contract)
	old_match = frappe.utils.cstr(original_email or email).strip().lower()
	new_match = frappe.utils.cstr(email).strip().lower()
	net_rows = [r for r in (contract_doc.signatories or []) if r.signatory_role == "Network Signatory"]
	row = next(
		(r for r in net_rows if frappe.utils.cstr(r.signatory_email or "").strip().lower() == old_match),
		None,
	) or next(
		(r for r in net_rows if frappe.utils.cstr(r.signatory_email or "").strip().lower() == new_match),
		None,
	)
	if row:
		update_signatory(
			contract=contract,
			role="Network Signatory",
			name=name,
			email=email,
			phone=phone,
			row_name=row.name,
		)
		return "updated"
	add_signatory(contract=contract, role="Network Signatory", name=name, email=email, phone=phone)
	return "added"


@frappe.whitelist()
def save_network_signer(
	network_slug: Any,
	name: Any,
	email: Any,
	original_email: Any = "",
	contract: Any = "",
	phone: Any = "",
):
	"""
	Add, edit, or replace a Network Signatory in the NETWORK CONFIGURATION —
	the source of truth (CRM Opt-In Network.network_signers), so the change
	persists for every future contract for that network. Network signers are
	external people keyed by name + email (no Frappe User). When `contract` is
	given the change is also synced onto that live contract (see
	_sync_network_signer_on_contract). Requires: Sales Manager or System Manager.

	- original_email set → the matching config row is updated/replaced.
	- original_email blank → a new signer is appended (deduped by email).

	This is the Network counterpart to the per-contract add_signatory. Tiberbu
	contacts are deliberately NOT handled here — they are managed in the CRM
	Opt-In Settings table and must never be overwritten from a single deal, so
	Tiberbu add/edit stays per-contract via add_signatory / update_signatory.

	Returns: {status, network_slug, email, contract_synced}
	"""
	_check_crm_role()

	network_slug = frappe.utils.cstr(network_slug).strip()
	name = frappe.utils.cstr(name).strip()
	email = frappe.utils.cstr(email).strip().lower()
	phone = frappe.utils.cstr(phone or "").strip()
	original_email = frappe.utils.cstr(original_email).strip().lower()
	contract = frappe.utils.cstr(contract).strip()

	if not network_slug or not frappe.db.exists("CRM Opt-In Network", network_slug):
		frappe.throw(_("Unknown opt-in network for this deal — cannot save a network signer."))
	if not name or not email:
		frappe.throw(_("Signer name and email are required."))

	net = frappe.get_doc("CRM Opt-In Network", network_slug)
	rows = net.network_signers or []

	# When editing, match the config row by its original email. If the signer
	# isn't in the config yet (e.g. it lives only on the contract), we append it —
	# the whole point is to write it back — rather than error out.
	target = None
	if original_email:
		target = next(
			(r for r in rows if frappe.utils.cstr(r.email or "").strip().lower() == original_email),
			None,
		)

	# The new email must not collide with a DIFFERENT existing signer row.
	for r in rows:
		if r is target:
			continue
		if frappe.utils.cstr(r.email or "").strip().lower() == email:
			frappe.throw(_("A network signer with this email already exists."))

	# Validate the live contract before saving the network source of truth. A signed
	# contract row is immutable; failing first avoids a settings/contract split.
	if contract and frappe.db.exists("CRM Contract", contract):
		live = frappe.get_doc("CRM Contract", contract)
		old_email = original_email or email
		live_row = next(
			(
				row
				for row in (live.signatories or [])
				if row.signatory_role == "Network Signatory"
				and frappe.utils.cstr(row.signatory_email or "").strip().lower() == old_email
			),
			None,
		)
		live_changed = live_row and (
			frappe.utils.cstr(live_row.signatory_name or "").strip() != name
			or frappe.utils.cstr(live_row.signatory_email or "").strip().lower() != email
			or frappe.utils.cstr(live_row.signatory_phone or "").strip() != phone
		)
		if (
			live_row
			and live_changed
			and (
				live_row.status == "Signed"
				or getattr(live_row, "signature_data", None)
				or getattr(live_row, "signed_at", None)
			)
		):
			frappe.throw(
				_("This network signatory has already signed and cannot be edited."),
				frappe.ValidationError,
			)

	if target:
		target.full_name = name
		target.email = email
		target.phone = phone
	else:
		net.append("network_signers", {"full_name": name, "email": email, "phone": phone})

	net.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()

	contract_synced = ""
	if contract and frappe.db.exists("CRM Contract", contract):
		contract_synced = _sync_network_signer_on_contract(contract, name, email, phone, original_email)
		log_deal_event(
			frappe.get_value("CRM Contract", contract, "deal"),
			"Network signer %s saved to network %s config and %s on contract %s"
			% (email, network_slug, contract_synced, contract),
		)

	return {
		"status": "saved",
		"network_slug": network_slug,
		"email": email,
		"contract_synced": contract_synced,
	}


@frappe.whitelist()
def download_pdf(contract: Any):
	"""
	Return a base64-encoded PDF of the FULL executed contract:
	  1. The signed Terms & Conditions body.
	  2. A signature block — each signatory's name, role, rendered signature
	     image, timestamp and IP (or a wet-ink line where unsigned/printing).
	  3. An appended "Certificate of Completion" audit page (parties, per-signatory
	     timestamps/IPs, T&C integrity hash, execution status).

	Requires: Sales Manager or System Manager role.
	Returns: {pdf_b64: <base64 string>}
	"""
	_check_crm_role()

	contract = frappe.utils.cstr(contract).strip()
	if not frappe.db.exists("CRM Contract", contract):
		frappe.throw(_("Contract not found."), frappe.DoesNotExistError)

	contract_doc = frappe.get_doc("CRM Contract", contract)
	html = _build_contract_document_html(contract_doc)

	try:
		from frappe.utils.pdf import get_pdf

		pdf_bytes = get_pdf(html)
		return {"pdf_b64": base64.b64encode(pdf_bytes).decode("utf-8")}
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"contracts.download_pdf: PDF generation failed for %s" % contract,
		)
		frappe.throw(_("PDF generation failed."))


@frappe.whitelist()
def get_authenticated_signing_context(contract: Any, role: Any = ""):
	"""Return whether the current CRM user can sign a counterparty row.

	This is intentionally a small probe used by the Quote page. It never returns
	invite tokens or OTP state and returns ``action_required=False`` when the
	logged-in user is not one of the contract's Network/Tiberbu signatories.
	"""
	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()
	if not contract:
		frappe.throw(_("Contract is required."), frappe.ValidationError)
	doc, row, email, full_name = _current_user_signatory(contract, role)
	status = " ".join(frappe.utils.cstr(getattr(row, "status", "") or "").lower().split()) if row else ""
	action_required = bool(row) and status in (
		"",
		"pending",
		"awaiting",
		"awaiting signature",
		"awaiting signatures",
		"invited",
		"sent",
	)
	return {
		"contract": doc.name,
		"action_required": action_required,
		"role": frappe.utils.cstr(getattr(row, "signatory_role", "") or "") if row else "",
		"signatory_name": frappe.utils.cstr(getattr(row, "signatory_name", "") or "") if row else "",
		"email": email,
		"full_name": full_name,
		"signing_progress": _signing_progress(doc),
	}


@frappe.whitelist()
def get_authenticated_contract(contract: Any, role: Any):
	"""Return the contract body for a matching logged-in signer."""
	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()
	doc, row, _email, _full_name = _current_user_signatory(contract, role)
	if not row:
		frappe.throw(_("You are not assigned to sign this contract."), frappe.PermissionError)
	_ensure_pending_signatory(row)
	_ensure_contract_signing_open(doc)
	return {
		"contract_html": frappe.utils.cstr(doc.contract_html or ""),
		"signatory_name": frappe.utils.cstr(row.signatory_name or ""),
		"signatory_role": frappe.utils.cstr(row.signatory_role or ""),
		"contract_date": frappe.utils.cstr(doc.contract_date or ""),
		"signing_progress": _signing_progress(doc),
		"price_list_summary": _recipient_safe_price_snapshot(_contract_price_snapshot(doc)),
	}


@frappe.whitelist()
def sign_authenticated(contract: Any, role: Any, signature_b64: Any):
	"""Capture a signature from a matching, logged-in Network/Tiberbu signer.

	No email OTP is requested on this branch because the user has already proved
	identity through the CRM session and network-scoped User Permission. The
	public invitation endpoint remains token + OTP protected.
	"""
	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()
	signature_b64 = frappe.utils.cstr(signature_b64 or "").strip()
	if not signature_b64:
		frappe.throw(_("Draw your signature before submitting."), frappe.ValidationError)
	doc, row, _email, _full_name = _current_user_signatory(contract, role)
	if not row:
		frappe.throw(_("You are not assigned to sign this contract."), frappe.PermissionError)
	_ensure_contract_signing_open(doc)
	_ensure_pending_signatory(row)
	remote_addr = ""
	try:
		remote_addr = frappe.local.request.environ.get("REMOTE_ADDR", "")
	except AttributeError:
		pass
	row.signature_data = signature_b64
	row.signed_at = frappe.utils.now_datetime()
	row.signature_ip = remote_addr
	row.status = "Signed"
	doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()
	_transition(doc.name)
	log_deal_event(
		doc.deal,
		"%s signed contract %s from the CRM" % (row.signatory_role, doc.name),
	)
	return {"status": "signed", "contract": doc.name, "role": row.signatory_role}


def _build_contract_document_html(contract_doc):
	"""Assemble the full print-ready executed-contract HTML (terms + signatures
	+ certificate). Kept side-effect-free so it is safe to call for preview/PDF."""
	brand = _network_branding(contract_doc)
	accent = brand["accent"]

	# 1. Contract body. Always render the selected Terms document at print time so
	#    an authorised Terms & Conditions edit is visible in the next PDF. The saved
	#    snapshot and hash remain the immutable acceptance evidence in the audit page.
	body = _regenerate_contract_body(contract_doc)
	if not body:
		body = frappe.utils.cstr(contract_doc.contract_html or "").strip()
	if not body:
		body = (
			"<p style='color:#991b1b'>The terms for this contract are unavailable. "
			"Please contact the issuer for the executed copy.</p>"
		)

	date_str = frappe.utils.format_date(contract_doc.contract_date) if contract_doc.contract_date else ""
	signatures = _render_signature_block(contract_doc, accent)
	certificate = _render_certificate_page(contract_doc, accent, date_str, brand)

	# Centered, branded masthead: network logo (falls back to a wordmark), the
	# network name, the agreement title, reference/date, and the issuer contact.
	logo_html = (
		"<img class='doc-logo' src='%s' alt='%s'/>"
		% (frappe.utils.escape_html(brand["logo"]), frappe.utils.escape_html(brand["display_name"]))
		if brand["logo"]
		else ""
	)
	contact_html = (
		"<div class='doc-contact'>%s</div>" % frappe.utils.escape_html(brand["contact_email"])
		if brand["contact_email"]
		else ""
	)
	footer_html = (
		"<div class='doc-footer'>%s</div>" % frappe.utils.escape_html(brand["footer_legal_name"])
		if brand["footer_legal_name"]
		else ""
	)
	price_history = _render_price_list_history(contract_doc)

	return """<!doctype html>
<html><head><meta charset="utf-8"><style>
  @page {{ margin: 22mm 18mm; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          color: #1f2937; font-size: 12px; line-height: 1.55; }}
  h1, h2, h3 {{ color: #111827; }}
  .doc-header {{ text-align: center; border-bottom: 3px solid {accent};
          padding-bottom: 16px; margin-bottom: 24px; }}
  .doc-logo {{ max-height: 64px; max-width: 220px; margin: 0 auto 12px; display: block; }}
  .doc-header .brand {{ font-size: 12px; letter-spacing: .12em; text-transform: uppercase;
          color: {accent}; font-weight: 700; }}
  .doc-header h1 {{ margin: 6px 0 4px; font-size: 22px; }}
  .doc-meta {{ color: #6b7280; font-size: 11px; }}
  .doc-contact {{ color: {accent}; font-size: 11px; margin-top: 5px; font-weight: 600; }}
  .doc-footer {{ margin-top: 30px; padding-top: 12px; border-top: 1px solid #e5e7eb;
          text-align: center; color: #9ca3af; font-size: 10px; }}
  .price-history {{ margin: 0 0 22px; padding: 12px 14px; border: 1px solid #dbe3ef;
          border-left: 4px solid {accent}; border-radius: 7px; background: #f8fafc; }}
  .price-history h2 {{ margin: 0 0 8px; font-size: 13px; }}
  .price-kv {{ margin: 3px 0; font-size: 11px; }}
  .price-kv b {{ display: inline-block; min-width: 135px; color: #6b7280; font-weight: 600; }}
  .price-history table {{ width: 100%; border-collapse: collapse; margin-top: 9px; }}
  .price-history th, .price-history td {{ padding: 5px 6px; border-bottom: 1px solid #e5e7eb;
          text-align: left; font-size: 10px; vertical-align: top; }}
  .price-history th {{ color: #6b7280; text-transform: uppercase; letter-spacing: .04em; }}
  .contract-body {{ margin-bottom: 8px; text-align: justify; }}
  .sig-section {{ margin-top: 28px; padding-top: 14px; border-top: 1px solid #e5e7eb; }}
  .sig-section h2 {{ font-size: 14px; margin-bottom: 12px; text-align: center; }}
  .sig-card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 14px;
          margin-bottom: 12px; page-break-inside: avoid; text-align: center; }}
  .sig-role {{ font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
          color: {accent}; font-weight: 700; }}
  .sig-name {{ font-size: 14px; font-weight: 600; margin: 2px 0; }}
  .sig-img {{ height: 64px; margin: 6px auto; display: block; }}
  .sig-line {{ border-bottom: 1px solid #9ca3af; width: 260px; height: 40px; margin: 6px auto; }}
  .sig-meta {{ color: #6b7280; font-size: 10px; }}
  .cert-page {{ page-break-before: always; padding-top: 6px; }}
  .cert-title {{ text-align: center; margin-bottom: 4px; }}
  .cert-title .brand {{ color: {accent}; font-weight: 700; letter-spacing: .12em;
          text-transform: uppercase; font-size: 11px; }}
  .cert-title h2 {{ font-size: 18px; margin: 4px 0; }}
  table.cert {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  table.cert th, table.cert td {{ text-align: left; padding: 7px 8px; font-size: 11px;
          border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
  table.cert th {{ color: #6b7280; text-transform: uppercase; font-size: 9px; letter-spacing: .05em; }}
  .cert-kv {{ margin: 3px 0; font-size: 11px; }}
  .cert-kv b {{ display: inline-block; min-width: 130px; color: #6b7280; font-weight: 600; }}
  .hash {{ font-family: monospace; font-size: 10px; word-break: break-all; color: #374151; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 10px;
          font-weight: 700; background: {accent}; color: #fff; }}
</style></head><body>
  <div class="doc-header">
    {logo}
    <div class="brand">{network}</div>
    <h1>CareverseHIMS Subscription Agreement</h1>
    <div class="doc-meta">{ref}{date_bit}</div>
    {contact}
  </div>
  {price_history}
  <div class="contract-body">{body}</div>
  {signatures}
  {footer}
  {certificate}
</body></html>""".format(
		accent=accent,
		logo=logo_html,
		network=frappe.utils.escape_html(brand["display_name"]),
		ref=frappe.utils.escape_html(contract_doc.name),
		date_bit=(" &middot; " + frappe.utils.escape_html(date_str)) if date_str else "",
		contact=contact_html,
		footer=footer_html,
		price_history=price_history,
		body=body,
		signatures=signatures,
		certificate=certificate,
	)


def _contract_price_snapshot(contract_doc):
	"""Resolve the stored contract price snapshot, with a legacy quote fallback."""
	quote = None
	if getattr(contract_doc, "quote", None):
		try:
			quote = frappe.get_doc("Quotation", contract_doc.quote)
		except Exception:
			quote = None
	return contract_snapshot(contract_doc, quote)


def _render_price_list_history(contract_doc):
	"""Render an auditable, read-only price-list summary for contract/PDF output."""
	data = _contract_price_snapshot(contract_doc)
	initial = frappe.utils.cstr(data.get("initial") or "").strip()
	negotiated = frappe.utils.cstr(data.get("negotiated") or "").strip()
	history = data.get("history") or []
	if not initial and not negotiated and not history:
		return ""

	rows = []
	for event in history:
		at = frappe.utils.cstr(event.get("at") or "")
		try:
			at = frappe.utils.format_datetime(at) if at else ""
		except Exception:
			pass
		change = (
			"%s → %s" % (event.get("from") or "—", event.get("to") or "—")
			if event.get("from")
			else event.get("to") or "—"
		)
		rows.append(
			"<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
			% (
				frappe.utils.escape_html(frappe.utils.cstr(event.get("event") or "Price list")),
				frappe.utils.escape_html(frappe.utils.cstr(change)),
				frappe.utils.escape_html(at or "—"),
				frappe.utils.escape_html(frappe.utils.cstr(event.get("by") or "System")),
			)
		)
	return """<section class='price-history'>
  <h2>Price list history</h2>
  <div class='price-kv'><b>Initial price list</b> {initial}</div>
  <div class='price-kv'><b>Negotiated price list</b> {negotiated}</div>
  <table><thead><tr><th>Event</th><th>Price list</th><th>Recorded</th><th>Changed by</th></tr></thead>
  <tbody>{rows}</tbody></table>
</section>""".format(
		initial=frappe.utils.escape_html(initial or "—"),
		negotiated=frappe.utils.escape_html(negotiated or "—"),
		rows="".join(rows),
	)


def _recipient_safe_price_snapshot(data):
	"""Remove internal actor metadata before returning pricing to a signer."""
	return {
		"initial": data.get("initial") or "",
		"negotiated": data.get("negotiated") or "",
		"history": [
			{
				"event": event.get("event") or "Price list",
				"from": event.get("from") or "",
				"to": event.get("to") or "",
				"at": event.get("at") or "",
			}
			for event in data.get("history") or []
			if isinstance(event, dict) and event.get("to")
		],
	}


def _regenerate_contract_body(contract_doc):
	"""Render the contract's current selected Terms document for a print/PDF."""
	tc_name = contract_doc.tc_document
	if not tc_name and frappe.db.exists("CRM Opt-In Settings", "CRM Opt-In Settings"):
		tc_name = frappe.get_single("CRM Opt-In Settings").active_tc_document
	if not tc_name or not frappe.db.exists("Terms and Conditions", tc_name):
		return ""
	try:
		tc_doc = frappe.get_doc("Terms and Conditions", tc_name)
		signatory = _get_signatory_row(contract_doc, "Facility Signatory")
		# Reuse the accepted network/contact/pricing context (see build_tc_context_for_deal);
		# without it the template raises 'network is undefined' and yields empty terms.
		from crm.api.optin import build_tc_context_for_deal

		context = build_tc_context_for_deal(contract_doc.deal) or {}
		context.setdefault("deal", contract_doc.deal)
		context.setdefault("quote", contract_doc.quote)
		context.setdefault("facility_signatory_name", signatory.signatory_name if signatory else "")
		context.setdefault(
			"date", frappe.utils.format_date(contract_doc.contract_date or frappe.utils.today())
		)
		return frappe.render_template(tc_doc.terms or "", context)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"contracts.download_pdf: T&C re-render failed for %s" % contract_doc.name,
		)
		return ""


def _render_signature_block(contract_doc, accent):
	"""One card per signatory: rendered signature image + audit line, or a wet-ink
	line for signatories still pending (so a printed copy can be hand-signed)."""
	cards = []
	for s in contract_doc.signatories or []:
		role = frappe.utils.escape_html(s.signatory_role or "")
		name = frappe.utils.escape_html(s.signatory_name or "")
		if s.status == "Signed" and s.signature_data:
			mark = "<img class='sig-img' src='%s' alt='signature'/>" % frappe.utils.cstr(s.signature_data)
			when = frappe.utils.format_datetime(s.signed_at) if s.signed_at else ""
			meta = "Signed electronically"
			if when:
				meta += " on %s" % frappe.utils.escape_html(when)
			if s.signature_ip:
				meta += " &middot; IP %s" % frappe.utils.escape_html(frappe.utils.cstr(s.signature_ip))
		else:
			mark = "<div class='sig-line'></div>"
			meta = "Awaiting signature"
		cards.append(
			"<div class='sig-card'><div class='sig-role'>%s</div>"
			"<div class='sig-name'>%s</div>%s<div class='sig-meta'>%s</div></div>" % (role, name, mark, meta)
		)
	return "<div class='sig-section'><h2>Signatures</h2>%s</div>" % "".join(cards)


def _render_certificate_page(contract_doc, accent, date_str, brand=None):
	"""DocuSign-style Certificate of Completion appended as a separate page."""
	brand = brand or _network_branding(contract_doc)
	rows = []
	for s in contract_doc.signatories or []:
		when = frappe.utils.format_datetime(s.signed_at) if s.signed_at else "—"
		ip = frappe.utils.escape_html(frappe.utils.cstr(s.signature_ip or "—"))
		rows.append(
			"<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
			% (
				frappe.utils.escape_html(s.signatory_name or ""),
				frappe.utils.escape_html(s.signatory_role or ""),
				frappe.utils.escape_html(s.status or ""),
				frappe.utils.escape_html(when),
				ip,
			)
		)
	executed = getattr(contract_doc, "status", "") == "Fully Executed" or _required_signatures_complete(
		contract_doc
	)
	status_label = (
		"Fully Executed"
		if executed
		else frappe.utils.cstr(contract_doc.workflow_state or contract_doc.status or "In Progress")
	)
	tc_hash = frappe.utils.escape_html(frappe.utils.cstr(contract_doc.tc_document_hash or "—"))

	contact_line = (
		"<div class='cert-kv'><b>Issuer Contact</b> %s</div>"
		% frappe.utils.escape_html(brand["contact_email"])
		if brand.get("contact_email")
		else ""
	)

	return """<div class="cert-page">
    <div class="cert-title"><div class="brand">{network}</div>
      <h2>Certificate of Completion</h2></div>
    <div class="cert-kv"><b>Contract</b> {ref}</div>
    <div class="cert-kv"><b>Contract Date</b> {date}</div>
    <div class="cert-kv"><b>Deal</b> {deal}</div>
    {contact}
    <div class="cert-kv"><b>Status</b> <span class="badge">{status}</span></div>
    <table class="cert"><thead><tr>
      <th>Signatory</th><th>Role</th><th>Status</th><th>Signed At</th><th>IP Address</th>
    </tr></thead><tbody>{rows}</tbody></table>
	<div class="cert-kv" style="margin-top:18px"><b>Accepted T&amp;C Snapshot Integrity</b></div>
    <div class="hash">{hash}</div>
  </div>""".format(
		network=frappe.utils.escape_html(brand["display_name"]),
		ref=frappe.utils.escape_html(contract_doc.name),
		date=frappe.utils.escape_html(date_str or "—"),
		deal=frappe.utils.escape_html(frappe.utils.cstr(contract_doc.deal or "—")),
		contact=contact_line,
		status=frappe.utils.escape_html(status_label),
		rows="".join(rows) or "<tr><td colspan='5'>No signatories.</td></tr>",
		hash=tc_hash,
	)


def _network_branding(contract_doc):
	"""Resolve the network masthead for a contract: accent colour, display name,
	logo URL, issuer contact e-mail and legal footer. Falls back through the deal's
	latest opt-in submission for legacy contracts with no network_slug, and to the
	Tiberbu wordmark/red when nothing is configured."""
	import re

	from crm.api.optin import _get_network_doc

	slug = frappe.utils.cstr(contract_doc.network_slug or "").strip()
	if not slug and contract_doc.deal:
		subs = frappe.get_list(
			"CRM Opt-In Submission",
			filters={"deal": contract_doc.deal},
			fields=["network_slug"],
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
		if subs:
			slug = frappe.utils.cstr(subs[0].network_slug or "").strip()

	doc = _get_network_doc(slug) if slug else None

	accent = frappe.utils.cstr((doc.get("primary_colour") if doc else "") or "").strip()
	if not re.match(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", accent):
		accent = "#bc1823"

	display = frappe.utils.cstr((doc.get("display_name") if doc else "") or "").strip() or "CareverseHIMS"

	logo = frappe.utils.cstr((doc.get("logo_url") if doc else "") or "").strip()
	if logo and not logo.startswith("http"):
		logo = frappe.utils.get_url(logo)

	return {
		"accent": accent,
		"display_name": display,
		"logo": logo,
		"contact_email": frappe.utils.cstr((doc.get("contact_email") if doc else "") or "").strip(),
		"footer_legal_name": frappe.utils.cstr((doc.get("footer_legal_name") if doc else "") or "").strip(),
	}


# ---------------------------------------------------------------------------
# Whitelisted API — guest-accessible (signing portal)
# ---------------------------------------------------------------------------


# nosemgrep: guest-whitelisted-method -- HMAC invitation validation and per-IP rate limit are enforced below.
@frappe.whitelist(allow_guest=True)
def request_otp(contract: Any, role: Any, token: Any):
	"""
	Validate the invitation token, generate a 6-digit OTP, store its HMAC on the
	signatory row, and email it to the signatory.

	Returns: {status: "sent", sms_status: "Sent"|"Failed"|"Not Available"}
	"""
	_check_contract_rate_limit()
	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()

	contract_doc, signatory_row = _load_signatory_by_token(contract, role, token, "invite_token")
	_validate_invite(signatory_row, token)
	_ensure_contract_signing_open(contract_doc)

	_ensure_pending_signatory(signatory_row)

	# Generate 6-digit OTP with a cryptographically-secure RNG (this is an auth factor)
	otp = str(secrets.randbelow(900000) + 100000)
	key = _get_signing_key()
	signatory_row.otp_hash = _hmac_hex(key, otp)
	signatory_row.otp_expiry = frappe.utils.add_to_date(
		frappe.utils.now_datetime(), seconds=_OTP_EXPIRY_SECONDS
	)
	signatory_row.otp_used = 0
	_save_otp_state(contract_doc, contract, role)

	# Reset attempt counter in Redis (keyed per-row so co-signatories sharing a
	# role each get their own counter)
	frappe.cache().set_value(
		_attempts_cache_key(contract, role, signatory_row.name),
		0,
		expires_in_sec=_OTP_EXPIRY_SECONDS + 120,
	)

	# Send branded OTP email. Keep the facility and a fresh, non-secret reference
	# in the subject so repeated code requests are easy to distinguish in an inbox.
	network = _network_for_contract(contract_doc)
	otp_reference = _generate_invitation_email_reference()
	facility_subject = _contract_email_subject_label(contract_doc)
	try:
		frappe.sendmail(
			recipients=[signatory_row.signatory_email],
			subject="%s — Contract verification code · OTP ID %s" % (facility_subject, otp_reference),
			message=branded_email_html(
				network,
				heading="Verify your identity",
				intro_html=(
					"<p style='margin:0 0 6px'>Dear %s,</p>"
					"<p style='margin:0'>Use the code below to sign your CareverseHIMS "
					"contract.</p>"
					% frappe.utils.escape_html(frappe.utils.cstr(signatory_row.signatory_name))
				),
				highlight_html=otp_code_block(otp, network),
				note_html=(
					"This code expires in 10 minutes. Do not share it with anyone. "
					"OTP reference: <strong>%s</strong>." % otp_reference
				),
			),
			now=True,
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"contracts.request_otp: OTP email failed for %s / %s" % (contract, role),
		)

	sms_status = _send_contract_sms(
		contract_doc,
		signatory_row,
		"OTP",
		_otp_sms_message(network, signatory_row, otp),
	)
	return {"status": "sent", "sms_status": sms_status}


# nosemgrep: guest-whitelisted-method -- HMAC invitation validation and per-IP rate limit are enforced below.
@frappe.whitelist(allow_guest=True)
def verify_otp(contract: Any, role: Any, token: Any, otp: Any):
	"""
	Validate the 6-digit OTP against the stored HMAC.
	On success: clear otp_hash, issue a short-lived signing-session token.

	Returns: {signing_token, expiry, signatory_name, signatory_role}
	The contract HTML is fetched separately via get_contract once the session token
	is issued, so it is intentionally not returned here.

	All failures raise frappe.AuthenticationError with a generic message.
	"""
	_check_contract_rate_limit()
	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()
	otp = frappe.utils.cstr(otp).strip()

	contract_doc, signatory_row = _load_signatory_by_token(contract, role, token, "invite_token")
	_validate_invite(signatory_row, token)
	_ensure_contract_signing_open(contract_doc)

	if signatory_row.status != "Pending":
		frappe.throw(_("Verification failed."), frappe.AuthenticationError)

	# Check OTP expiry / reuse. otp_used blocks a consumed code even if a stale
	# otp_hash lingers; a fresh request_otp resets it to 0.
	if (
		not signatory_row.otp_hash
		or frappe.utils.cint(signatory_row.otp_used)
		or not signatory_row.otp_expiry
		or frappe.utils.now_datetime() > signatory_row.otp_expiry
	):
		frappe.throw(_("Verification failed."), frappe.AuthenticationError)

	# Check attempt count from Redis (per-row so shared-role co-signatories don't
	# share a brute-force counter)
	attempts_key = _attempts_cache_key(contract, role, signatory_row.name)
	attempts = int(frappe.cache().get_value(attempts_key) or 0)
	if attempts >= _MAX_OTP_ATTEMPTS:
		frappe.throw(_("Verification failed."), frappe.AuthenticationError)

	# Increment attempts before validating (prevents brute-force via timing)
	frappe.cache().set_value(
		attempts_key,
		attempts + 1,
		expires_in_sec=_OTP_EXPIRY_SECONDS + 120,
	)

	# Validate OTP HMAC — constant-time comparison
	key = _get_signing_key()
	stored_hash = frappe.utils.cstr(signatory_row.otp_hash or "")
	expected_hash = _hmac_hex(key, otp)

	if not hmac.compare_digest(stored_hash, expected_hash):
		frappe.throw(_("Verification failed."), frappe.AuthenticationError)

	# OTP valid — clear it, reset attempts, and issue a signing-session token
	signing_token = _gen_token()
	signatory_row.otp_hash = ""
	signatory_row.otp_used = 1
	signatory_row.signing_token = signing_token
	signatory_row.signing_expiry = frappe.utils.add_to_date(
		frappe.utils.now_datetime(), seconds=_SIGN_EXPIRY_SECONDS
	)
	contract_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()
	frappe.cache().set_value(attempts_key, 0, expires_in_sec=60)

	return {
		"signing_token": signing_token,
		"expiry": int(time.time()) + _SIGN_EXPIRY_SECONDS,
		"signatory_name": frappe.utils.cstr(signatory_row.signatory_name or ""),
		"signatory_role": frappe.utils.cstr(signatory_row.signatory_role or ""),
	}


# nosemgrep: guest-whitelisted-method -- short-lived signing-token validation is enforced below.
@frappe.whitelist(allow_guest=True)
def get_contract(signing_token: Any, contract: Any, role: Any):
	"""
	Return contract HTML and signatory metadata for the signing portal.
	Validates the signing-session token before returning any data.

	Returns: {contract_html, signatory_name, signatory_role, contract_date,
	signing_progress, price_list_summary}. The progress and pricing payloads
	intentionally exclude private delivery and authentication data.
	"""
	_check_contract_rate_limit()
	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()

	contract_doc, signatory_row = _load_signatory_by_token(contract, role, signing_token, "signing_token")
	_validate_signing(signatory_row, signing_token)
	price_snapshot = _contract_price_snapshot(contract_doc)

	return {
		"contract_html": frappe.utils.cstr(contract_doc.contract_html or ""),
		"signatory_name": frappe.utils.cstr(signatory_row.signatory_name or ""),
		"signatory_role": role,
		"contract_date": frappe.utils.cstr(contract_doc.contract_date or ""),
		"signing_progress": _signing_progress(contract_doc),
		"price_list_summary": _recipient_safe_price_snapshot(price_snapshot),
	}


# nosemgrep: guest-whitelisted-method -- short-lived signing-token validation and per-IP rate limit are enforced below.
@frappe.whitelist(allow_guest=True)
def sign(signing_token: Any, contract: Any, role: Any, signature_b64: Any):
	"""
	Record the signature on the signatory row and advance the workflow via _transition().

	Returns: {status: "signed"}
	"""
	_check_contract_rate_limit()
	contract = frappe.utils.cstr(contract).strip()
	role = frappe.utils.cstr(role).strip()

	contract_doc, signatory_row = _load_signatory_by_token(contract, role, signing_token, "signing_token")
	_validate_signing(signatory_row, signing_token)
	_ensure_contract_signing_open(contract_doc)

	_ensure_pending_signatory(signatory_row)

	# Capture client IP
	remote_addr = ""
	try:
		remote_addr = frappe.local.request.environ.get("REMOTE_ADDR", "")
	except AttributeError:
		pass

	# Record signature
	signatory_row.signature_data = frappe.utils.cstr(signature_b64)
	signatory_row.signed_at = frappe.utils.now_datetime()
	signatory_row.signature_ip = remote_addr
	signatory_row.status = "Signed"
	# Consume the signing-session token so it can't be replayed
	signatory_row.signing_token = ""

	contract_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()

	# Advance the contract workflow
	_transition(contract)

	return {"status": "signed"}
