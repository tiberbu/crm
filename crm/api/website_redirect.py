"""Website-user routing and facility portal identity resolution.

Facility portal access is bound to an explicit Frappe ``User Permission``:

    user     = the Website User
    allow    = CRM Opt-In Submission
    for_value = the OIS number

The browser never supplies the OIS number for authorization.  The portal
resolves it from the logged-in user on the server, which prevents a query-string
OIS from becoming an IDOR/BOLA primitive.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cstr

PORTAL_ROUTE = "/cx-portal"
OIS_DOCTYPE = "CRM Opt-In Submission"
OIS_PERMISSION_ALLOW = OIS_DOCTYPE
MAX_OIS_PER_USER = 100


def _json_object(value):
	try:
		parsed = json.loads(value or "{}") if isinstance(value, str) else value
	except (TypeError, ValueError, json.JSONDecodeError):
		return {}
	return parsed if isinstance(parsed, dict) else {}


def _submission_facilities(submission):
	"""Return the canonical facility snapshots retained on an OIS."""
	payload = _json_object(submission.get("raw_json"))
	facilities = (
		payload.get("facilities") or payload.get("pricing") or payload.get("selected_facilities") or []
	)
	if not isinstance(facilities, list):
		return []
	if facilities and isinstance(facilities[0], dict) and facilities[0].get("facilities"):
		facilities = [facility for plan in facilities for facility in (plan.get("facilities") or [])]
	return [facility for facility in facilities if isinstance(facility, dict)]


def _contract_progress(contract_name):
	if not contract_name or not frappe.db.exists("CRM Contract", contract_name):
		return {
			"status": "Not started",
			"signed": 0,
			"required": 0,
			"complete": False,
		}

	contract_status = cstr(frappe.db.get_value("CRM Contract", contract_name, "status") or "").strip()
	signatories = frappe.get_all(
		"CRM Contract Signatory",
		filters={"parent": contract_name, "parenttype": "CRM Contract", "parentfield": "signatories"},
		fields=["status"],
		ignore_permissions=True,  # SYSTEM-INTERNAL: OIS permission already scopes this contract.
		limit_page_length=100,
	)
	signed = sum(1 for row in signatories if cstr(row.get("status") or "") == "Signed")
	complete = contract_status == "Fully Executed" or (bool(signatories) and signed == len(signatories))
	return {
		"status": "Complete" if complete else (contract_status or "Awaiting signatures"),
		"signed": signed,
		"required": len(signatories),
		"complete": complete,
	}


def _portal_progress(submission):
	"""Build a customer-safe progress projection from canonical CRM records.

	The OIS permission is checked by the caller before this projection is built.
	Facility and membership lookups are therefore safe to perform server-side,
	while the response remains an allow-listed projection rather than raw docs.
	"""
	network = cstr(submission.get("network_slug") or "").strip()
	contract = _contract_progress(submission.get("contract"))
	facility_snapshots = _submission_facilities(submission)
	mfl_codes = list(
		{
			cstr(facility.get("mfl_code") or "").strip()
			for facility in facility_snapshots
			if cstr(facility.get("mfl_code") or "").strip()
		}
	)
	facility_rows = {}
	if mfl_codes:
		facility_rows = {
			row.mfl_code: row
			for row in frappe.get_all(
				"CRM Pre-Qualified Facility",
				filters={"mfl_code": ["in", mfl_codes]},
				fields=["name", "mfl_code", "facility_name", "keph_level"],
				ignore_permissions=True,  # SYSTEM-INTERNAL: OIS permission scopes the snapshot.
				limit_page_length=0,
			)
		}
	parent_names = [row.name for row in facility_rows.values()]
	membership_rows = {}
	if parent_names and network:
		membership_fields = ["name", "parent", "network", "status", "contact_name", "contact_email"]
		if frappe.db.has_column("CRM Facility Membership", "go_live"):
			membership_fields.append("go_live")
		membership_rows = {
			row.parent: row
			for row in frappe.get_all(
				"CRM Facility Membership",
				filters={
					"parenttype": "CRM Pre-Qualified Facility",
					"parent": ["in", parent_names],
					"network": network,
				},
				fields=membership_fields,
				ignore_permissions=True,  # SYSTEM-INTERNAL: OIS permission scopes the snapshot.
				limit_page_length=0,
			)
		}

	contacts = []
	for snapshot in facility_snapshots:
		mfl_code = cstr(snapshot.get("mfl_code") or "").strip()
		facility = facility_rows.get(mfl_code)
		membership = membership_rows.get(facility.name) if facility else None
		go_live = bool(frappe.utils.cint(membership.get("go_live"))) if membership else False
		membership_status = cstr(membership.get("status") or "Not linked") if membership else "Not linked"
		contacts.append(
			{
				"facility_name": cstr((facility or snapshot).get("facility_name") or "Facility"),
				"mfl_code": mfl_code,
				"keph_level": cstr((facility or snapshot).get("keph_level") or ""),
				"network": network,
				"membership_status": membership_status,
				"network_contact": {
					"name": membership.name if membership else None,
					"source": "token_self_onboarding",
					"go_live": go_live,
					"go_live_status": "Ready for GoLive" if go_live else "Implementation in progress",
				},
				"go_live": go_live,
			}
		)

	opted_in = any(row.get("membership_status") == "Opted In" for row in contacts)
	all_live = bool(contacts) and all(row.get("go_live") for row in contacts)
	if all_live:
		next_action = {"key": "complete", "label": "Your facility is ready to go live"}
	elif not contract["complete"]:
		next_action = {"key": "sign_contract", "label": "Complete the required signatures"}
	elif not opted_in:
		next_action = {"key": "complete_optin", "label": "Complete Opt-In"}
	else:
		next_action = {"key": "implementation", "label": "Your implementation is in progress"}

	return {
		"contract": contract,
		"facilities": contacts,
		"current": next_action["key"],
		"next_action": next_action,
		"steps": [
			{"key": "identity", "label": "Identity verified", "status": "complete"},
			{
				"key": "facility",
				"label": "Facility confirmed",
				"status": "complete" if contacts else "current",
			},
			{"key": "optin", "label": "Opt-In request", "status": "complete" if opted_in else "current"},
			{
				"key": "signatures",
				"label": "Required signatures",
				"status": "complete" if contract["complete"] else "current",
			},
			{
				"key": "golive",
				"label": "GoLive",
				"status": "complete" if all_live else ("current" if opted_in else "locked"),
			},
		],
	}


def _set_submission_portal_field(submission, fieldname, value):
	if frappe.get_meta(OIS_DOCTYPE).has_field(fieldname):
		frappe.db.set_value(OIS_DOCTYPE, submission.name, fieldname, value, update_modified=False)


def ensure_website_user_for_ois(submission):
	"""Create/reconcile a Website User and OIS permission exactly once."""
	email = cstr(submission.facility_signatory_email or submission.submitter_email or "").strip().lower()
	if not email or "@" not in email:
		_set_submission_portal_field(submission, "portal_invitation_status", "Blocked")
		_set_submission_portal_field(
			submission, "portal_invitation_error", "No valid facility email is available."
		)
		return {"status": "blocked", "reason": "No valid facility email"}

	user_name = frappe.db.get_value("User", {"email": email}, "name")
	created = False
	welcome_email_sent = False
	if user_name:
		user = frappe.get_doc("User", user_name)
		if user.user_type != "Website User":
			_set_submission_portal_field(submission, "portal_invitation_status", "Blocked")
			_set_submission_portal_field(
				submission, "portal_invitation_error", "The facility email belongs to an internal user."
			)
			return {"status": "blocked", "reason": "Email belongs to an internal user"}
		if not user.enabled:
			_set_submission_portal_field(submission, "portal_invitation_status", "Blocked")
			_set_submission_portal_field(
				submission, "portal_invitation_error", "The facility account is disabled."
			)
			return {"status": "blocked", "reason": "Website User is disabled"}
	else:
		user = frappe.new_doc("User")
		user.update(
			{
				"email": email,
				"first_name": cstr(
					submission.facility_signatory_name or submission.submitter_name or email.split("@")[0]
				),
				"user_type": "Website User",
				"enabled": 1,
				"send_welcome_email": 1,
			}
		)
		user.flags.ignore_password_policy = True
		user.insert(ignore_permissions=True)
		user_name = user.name
		created = True
		welcome_email_sent = bool(getattr(user.flags, "email_sent", False))

	permission = frappe.get_all(
		"User Permission",
		filters={"user": user_name, "allow": OIS_PERMISSION_ALLOW, "for_value": submission.name},
		fields=["name"],
		limit_page_length=1,
	)
	if not permission:
		permission = frappe.new_doc("User Permission")
		permission.user = user_name
		permission.allow = OIS_PERMISSION_ALLOW
		permission.for_value = submission.name
		permission.apply_to_all_doctypes = 0
		permission.applicable_for = OIS_DOCTYPE
		permission.insert(ignore_permissions=True)

	_set_submission_portal_field(submission, "portal_user", user_name)
	if created and not welcome_email_sent:
		_set_submission_portal_field(submission, "portal_invitation_status", "Failed")
		_set_submission_portal_field(
			submission,
			"portal_invitation_error",
			"The Website User was created, but the welcome email was not queued.",
		)
		return {"status": "failed", "user": user_name}
	_set_submission_portal_field(
		submission, "portal_invitation_status", "Sent" if created else "Already active"
	)
	if created and welcome_email_sent:
		_set_submission_portal_field(submission, "portal_invitation_sent_at", frappe.utils.now_datetime())
	_set_submission_portal_field(submission, "portal_invitation_error", "")
	return {"status": "sent" if created else "linked", "user": user_name}


def get_user_ois_numbers(user: str | None = None) -> list[str]:
	"""Return existing OIS records explicitly permitted for ``user``.

	This is the only authorization source for the facility portal.  Invalid,
	stale, duplicate, or empty User Permission values are ignored.  The helper is
	server-side and intentionally does not accept a browser-supplied OIS.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []

	try:
		rows = frappe.get_all(
			"User Permission",
			filters={"user": user, "allow": OIS_PERMISSION_ALLOW},
			fields=["for_value", "creation"],
			order_by="creation asc",
			limit_page_length=MAX_OIS_PER_USER,
		)
	except Exception:
		# Login routing must fail closed if permissions are not available during a
		# migration or site bootstrap.  Do not turn an auth request into a 500.
		return []

	resolved: list[str] = []
	seen: set[str] = set()
	for row in rows:
		ois_number = cstr(row.get("for_value") or "").strip()
		if not ois_number or ois_number in seen:
			continue
		if not _ois_exists(ois_number):
			continue
		seen.add(ois_number)
		resolved.append(ois_number)

	return resolved


def _ois_exists(ois_number: str) -> bool:
	try:
		return bool(frappe.db.exists(OIS_DOCTYPE, ois_number))
	except Exception:
		return False


def get_portal_route(user: str | None = None) -> str | None:
	"""Return the default Customer Experience route for any Website User."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None

	try:
		user_type = frappe.db.get_value("User", user, "user_type")
	except Exception:
		return None

	if user_type != "Website User":
		return None

	return PORTAL_ROUTE


def on_login(login_manager=None):
	"""Set Frappe's one-shot post-login redirect for every Website User.

	Frappe calls ``on_login`` before ``set_user_info`` consumes the
	``redirect_after_login`` cache key.  This preserves native login, password
	reset, 2FA, and email-link behavior while changing only the destination for
	Website Users. OIS permissions still scope the records shown after login.
	"""
	user = getattr(login_manager, "user", None) or frappe.session.user
	if get_portal_route(user):
		frappe.cache.hset("redirect_after_login", user, PORTAL_ROUTE)


def require_portal_user() -> list[str]:
	"""Require a logged-in Website User and return its permitted OIS records."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please sign in to access the facility portal."), frappe.PermissionError)

	user_type = frappe.db.get_value("User", user, "user_type")
	if user_type != "Website User":
		frappe.throw(_("This portal is available to facility Website Users."), frappe.PermissionError)

	return get_user_ois_numbers(user)


def _portal_network(network_name: str) -> dict:
	if not network_name:
		return {}
	rows = frappe.get_list(
		"CRM Opt-In Network",
		filters={"name": network_name},
		fields=["name", "display_name", "logo_url", "primary_colour", "contact_email", "footer_legal_name"],
		limit_page_length=1,
		ignore_permissions=True,
	)
	return rows[0] if rows else {}


def _portal_token_catalog() -> list[dict]:
	try:
		from crm.api.facility_onboarding import _token_packages

		return _token_packages()
	except Exception:
		return []


def _portal_invoices(submission) -> list[dict]:
	try:
		from crm.api.checkout import _invoice_rows

		return _invoice_rows(submission)
	except Exception:
		return []


def _portal_orders(submission) -> list[dict]:
	try:
		from crm.api.customer_experience import _order_rows

		return _order_rows(submission)
	except Exception:
		return []


@frappe.whitelist(methods=["GET"])
def get_portal_context():
	"""Return the authenticated user's safe, OIS-scoped portal context."""
	ois_numbers = require_portal_user()
	rows = []
	for ois_number in ois_numbers:
		row = frappe.db.get_value(
			OIS_DOCTYPE,
			ois_number,
			[
				"name",
				"status",
				"network_slug",
				"facility_signatory_name",
				"contract",
				"raw_json",
			],
			as_dict=True,
		)
		if row:
			progress = _portal_progress(row)
			row.pop("raw_json", None)
			row["progress"] = progress
			row["network"] = _portal_network(row.get("network_slug"))
			submission = frappe.get_doc(OIS_DOCTYPE, ois_number)
			row["open_orders"] = _portal_orders(submission)
			row["open_invoices"] = _portal_invoices(submission)
			rows.append(row)

	return {
		"success": True,
		"data": {
			"route": PORTAL_ROUTE,
			"user": frappe.session.user,
			"ois": rows,
			"token_packages": _portal_token_catalog(),
		},
	}
