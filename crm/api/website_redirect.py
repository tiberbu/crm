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
CRM_LOGIN_MARKER = "crm_login"
LOGIN_TEAM_ROUTES = {
	"sales": "/crm",
	"finance": "/finance-cockpit",
}
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
	is_self_onboarding = cstr(getattr(submission, "onboarding_source", "") or "").strip() == (
		"token_self_onboarding"
	)
	contract = None if is_self_onboarding else _contract_progress(submission.get("contract"))
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
	if is_self_onboarding:
		return _self_onboarding_progress(submission, contacts, opted_in, all_live)

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


def _self_onboarding_progress(submission, contacts, opted_in, all_live):
	"""Project self-onboarding without signature fields or actions."""
	payload = _json_object(submission.get("raw_json"))
	package = payload.get("token_package") if isinstance(payload.get("token_package"), dict) else {}
	package_selected = bool(cstr(package.get("item_code") or "").strip())
	from crm.api.customer_experience import _order_rows

	orders = _order_rows(submission)
	invoices = _portal_invoices(submission)
	paid_invoice = False
	try:
		filters = {"docstatus": 1, "outstanding_amount": ["<=", 0]}
		if frappe.db.has_column("Sales Invoice", "crm_optin_submission"):
			filters["crm_optin_submission"] = submission.name
		elif getattr(submission, "deal", None) and frappe.db.has_column("Sales Invoice", "crm_deal"):
			filters["crm_deal"] = submission.deal
		if len(filters) > 2:
			paid_invoice = bool(
				frappe.get_all(
					"Sales Invoice",
					filters=filters,
					fields=["name"],
					limit_page_length=1,
					ignore_permissions=True,
				)
			)
	except Exception:
		# A missing finance projection must not block the onboarding portal.
		paid_invoice = False

	quote_names = _json_object(getattr(submission, "quote_names_json", "[]"))
	if not isinstance(quote_names, list):
		try:
			quote_names = json.loads(getattr(submission, "quote_names_json", "[]") or "[]")
		except (TypeError, ValueError):
			quote_names = []
	quote_ready = bool(orders) or any(
		frappe.db.exists("Quotation", name) for name in quote_names if isinstance(name, str)
	)
	payment_complete = paid_invoice
	if all_live:
		next_action = {"key": "complete", "label": "Your facility is ready to go live"}
	elif invoices:
		next_action = {"key": "pay_invoice", "label": "Pay your open invoice when you are ready"}
	elif orders:
		next_action = {"key": "review_order", "label": "Create an invoice for your token order"}
	elif not quote_ready:
		next_action = {"key": "order_preparing", "label": "Your token quote and order are being prepared"}
	else:
		next_action = {"key": "implementation", "label": "Your implementation is in progress"}

	steps = [
		{"key": "identity", "label": "Identity verified", "status": "complete"},
		{"key": "facility", "label": "Facilities confirmed", "status": "complete" if contacts else "current"},
		{
			"key": "optin",
			"label": "Opt-In submitted",
			"status": "complete" if cstr(getattr(submission, "status", "")) == "Processed" else "current",
		},
		{"key": "package", "label": "Token package selected", "status": "complete" if package_selected else "upcoming"},
		{"key": "order", "label": "Quote and order ready", "status": "complete" if quote_ready else ("current" if package_selected else "upcoming")},
		{
			"key": "payment",
			"label": "Payment",
			"status": "complete" if payment_complete else ("current" if orders or invoices else "upcoming"),
		},
		{
			"key": "golive",
			"label": "GoLive",
			"status": "complete" if all_live else ("current" if opted_in and payment_complete else "locked"),
		},
	]
	return {
		"facilities": contacts,
		"current": next_action["key"],
		"next_action": next_action,
		"steps": steps,
		"orders": orders,
		"invoices": invoices,
		"payment_status": "Paid" if payment_complete else ("Open" if invoices else "Not started"),
		"token_credit_status": (
			"Payment received; token allocation is confirmed by your Network."
			if payment_complete
			else "Token balance appears after payment and Network allocation."
		),
		"package": {key: package.get(key) for key in ("item_code", "display_name", "token_quantity", "currency") if package.get(key)},
	}


def _set_submission_portal_field(submission, fieldname, value):
	if frappe.get_meta(OIS_DOCTYPE).has_field(fieldname):
		frappe.db.set_value(OIS_DOCTYPE, submission.name, fieldname, value, update_modified=False)


def ensure_website_user_for_ois(submission, email=None, display_name=None, send_password_setup=True):
	"""Create/reconcile a Website User and OIS permission exactly once."""
	requested_email = cstr(email or "").strip().lower()
	is_self_onboarding = cstr(getattr(submission, "onboarding_source", "") or "").strip() == (
		"token_self_onboarding"
	)
	if not requested_email and is_self_onboarding:
		requested_email = cstr(getattr(submission, "cx_account_email", "") or "").strip().lower()
	if not requested_email and not is_self_onboarding:
		requested_email = (
			cstr(submission.facility_signatory_email or submission.submitter_email or "").strip().lower()
		)
	if (
		not requested_email
		or frappe.utils.validate_email_address(requested_email).strip().lower() != requested_email
	):
		_set_submission_portal_field(submission, "portal_invitation_status", "Blocked")
		_set_submission_portal_field(
			submission, "portal_invitation_error", "No valid facility email is available."
		)
		return {"status": "blocked", "reason": "No valid facility email"}

	# A prior OIS-to-user link is authoritative. This keeps admin re-invites
	# idempotent when the Network Contact email changes after the first invite.
	linked_user = cstr(getattr(submission, "portal_user", "") or "").strip()
	user_name = linked_user if linked_user and frappe.db.exists("User", linked_user) else None
	if is_self_onboarding and user_name:
		linked_email = cstr(frappe.db.get_value("User", user_name, "email") or "").strip().lower()
		if linked_email != requested_email:
			_set_submission_portal_field(submission, "portal_invitation_status", "Blocked")
			_set_submission_portal_field(
				submission,
				"portal_invitation_error",
				"Enter the email already linked to this facility account to receive a password reset.",
			)
			return {"status": "blocked", "reason": "Account email does not match linked portal user"}
	if not user_name:
		user_name = frappe.db.get_value("User", {"email": requested_email}, "name")
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
		previous_invitation = frappe.db.get_value(
			OIS_DOCTYPE, submission.name, "portal_invitation_status"
		)
		if (
			is_self_onboarding
			and send_password_setup
			and previous_invitation not in {"Sent", "Already active"}
		):
			try:
				user.db_set("redirect_url", PORTAL_ROUTE, update_modified=False)
				user._reset_password(send_email=True)
			except Exception as exc:
				frappe.log_error(
				title="CRM CX password setup email",
					message="Native password reset failed (%s)" % type(exc).__name__,
				)
				_set_submission_portal_field(submission, "portal_invitation_status", "Failed")
				_set_submission_portal_field(
					submission,
					"portal_invitation_error",
					"We could not send password setup instructions. Please try again or contact support.",
				)
				return {"status": "failed", "user": user_name}
			welcome_email_sent = True
	else:
		user = frappe.new_doc("User")
		user.update(
			{
				"email": requested_email,
				"first_name": cstr(
					display_name
					or submission.facility_signatory_name
					or submission.submitter_name
					or requested_email.split("@")[0]
				),
				"user_type": "Website User",
				"enabled": 1,
				"send_welcome_email": 1,
				# Native Frappe update_password() consumes User.redirect_url after
				# the emailed reset link is used. This keeps the invitation flow on
				# Frappe's password-reset implementation while landing in CX.
				"redirect_url": PORTAL_ROUTE,
			}
		)
		user.flags.ignore_password_policy = True
		user.insert(ignore_permissions=True)
		user_name = user.name
		created = True
		welcome_email_sent = bool(getattr(user.flags, "email_sent", False))
	if not created:
		# Existing Website Users may have been invited before CX routing was
		# added. Set the native one-shot redirect without changing their account
		# or password state.
		try:
			if hasattr(user, "db_set") and not (is_self_onboarding and welcome_email_sent):
				user.db_set("redirect_url", PORTAL_ROUTE, update_modified=False)
			else:
				# Keeps lightweight unit-test doubles and migration-time stubs safe.
				user.redirect_url = PORTAL_ROUTE
		except Exception:
			# Access reconciliation must remain idempotent if a site is mid-migration.
			frappe.logger("crm.website_redirect").warning(
				"Could not set CX password redirect for %s", user_name, exc_info=True
			)

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
		submission,
		"portal_invitation_status",
		"Sent" if created or welcome_email_sent else "Already active",
	)
	if welcome_email_sent:
		_set_submission_portal_field(submission, "portal_invitation_sent_at", frappe.utils.now_datetime())
	_set_submission_portal_field(submission, "portal_invitation_error", "")
	return {
		"status": "sent" if created else ("reset_sent" if welcome_email_sent else "linked"),
		"user": user_name,
	}


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


def get_login_team_route(team: str | None = None) -> str:
	"""Return the allow-listed destination selected on the branded login form."""
	return LOGIN_TEAM_ROUTES.get(cstr(team or "").strip().lower(), PORTAL_ROUTE)


def on_login(login_manager=None):
	"""Set Frappe's one-shot post-login redirect for the branded login flow.

	Frappe calls ``on_login`` before ``set_user_info`` consumes the
	``redirect_after_login`` cache key. The marker limits team routing to the
	branded password-login page; API, OAuth, email-link, and other native login
	paths keep their existing behavior. The team value is only an allow-listed
	destination hint: the destination's own route guard remains authoritative.
	"""
	user = getattr(login_manager, "user", None) or frappe.session.user
	if cstr(frappe.form_dict.get(CRM_LOGIN_MARKER) or "") == "1":
		frappe.cache.hset(
			"redirect_after_login",
			user,
			get_login_team_route(frappe.form_dict.get("login_team")),
		)
	elif get_portal_route(user):
		# Preserve the existing native behavior for non-branded Website User logins.
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
		from crm.api.facility_onboarding import _catalog_packages

		return _catalog_packages()
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
		fields = [
			"name",
			"status",
			"network_slug",
			"facility_signatory_name",
			"contract",
			"raw_json",
		]
		if frappe.get_meta(OIS_DOCTYPE).has_field("onboarding_source"):
			fields.append("onboarding_source")
		if frappe.get_meta(OIS_DOCTYPE).has_field("quote_names_json"):
			fields.append("quote_names_json")
		row = frappe.db.get_value(
			OIS_DOCTYPE,
			ois_number,
			fields,
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
