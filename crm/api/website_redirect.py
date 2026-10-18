"""Authenticated-user routing and facility portal identity resolution.

Legacy facility portal access is bound to an explicit Frappe ``User Permission``:

    user     = the authenticated Frappe User
    allow    = CRM Opt-In Submission
    for_value = the OIS number

New no-OIS enrollment access is bound to a Customer User Permission and
Customer-linked Network Memberships. The browser never supplies either record
as authority; the portal resolves both from the logged-in user on the server.
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
		"token_credit_status": "Token allocation status is not available in the portal yet.",
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

	if not _ensure_ois_user_permission(user_name, submission.name):
		_set_submission_portal_field(submission, "portal_invitation_status", "Failed")
		_set_submission_portal_field(
			submission,
			"portal_invitation_error",
			"We could not link this account to the facility record. Please try again or contact support.",
		)
		return {"status": "failed", "user": user_name}

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
	"""Resolve OIS records explicitly linked to ``user`` and repair missing grants.

	Valid OIS-scoped User Permissions are primary. A missing grant may be repaired
	from the server-owned OIS.portal_user link. Invalid, stale, duplicate, broad,
	or empty permissions are ignored. No browser-supplied OIS is accepted.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []

	try:
		rows = frappe.get_all(
			"User Permission",
			filters={
				"user": user,
				"allow": OIS_PERMISSION_ALLOW,
			},
			fields=["for_value", "creation"],
			order_by="creation asc",
			limit_page_length=0,
		)
	except Exception:
		# Try the server-owned OIS.portal_user recovery path below. If that lookup
		# also fails, authorization resolves to an empty set without a 500.
		rows = []

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

	# Recover a missing/stale permission only from the server-owned OIS.portal_user
	# link. Never infer ownership from a browser selector or identity/contact data.
	linked_submissions = []
	try:
		if frappe.get_meta(OIS_DOCTYPE).has_field("portal_user"):
			linked_submissions = frappe.get_all(
				OIS_DOCTYPE,
				filters={"portal_user": user},
				pluck="name",
				ignore_permissions=True,
				limit_page_length=0,
			)
	except Exception:
		linked_submissions = []

	for ois_number in linked_submissions:
		ois_number = cstr(ois_number or "").strip()
		if not ois_number or ois_number in seen or not _ois_exists(ois_number):
			continue
		try:
			if not _ensure_ois_user_permission(user, ois_number):
				continue
		except Exception as exc:
			frappe.log_error(
				title="CRM CX portal permission reconciliation",
				message="User Permission reconciliation failed (%s)" % type(exc).__name__,
			)
			continue
		seen.add(ois_number)
		resolved.append(ois_number)

	return resolved


def _ensure_ois_user_permission(user: str, ois_number: str) -> bool:
	"""Ensure one least-privilege User Permission links a Website User to one OIS."""
	filters = {
		"user": user,
		"allow": OIS_PERMISSION_ALLOW,
		"for_value": ois_number,
		"apply_to_all_doctypes": 0,
		"applicable_for": OIS_DOCTYPE,
	}
	if frappe.get_all("User Permission", filters=filters, fields=["name"], limit_page_length=1):
		return True

	permission = frappe.new_doc("User Permission")
	permission.user = user
	permission.allow = OIS_PERMISSION_ALLOW
	permission.for_value = ois_number
	permission.apply_to_all_doctypes = 0
	permission.applicable_for = OIS_DOCTYPE
	permission.insert(ignore_permissions=True)
	return True


def _ensure_customer_user_permission(user: str, customer: str) -> bool:
	"""Ensure one least-privilege Customer permission for a verified portal account."""
	filters = {
		"user": user,
		"allow": "Customer",
		"for_value": customer,
	}
	existing = frappe.get_all("User Permission", filters=filters, fields=["name", "apply_to_all_doctypes"], limit_page_length=1)
	if existing:
		if not existing[0].get("apply_to_all_doctypes"):
			frappe.db.set_value("User Permission", existing[0]["name"], "apply_to_all_doctypes", 1, update_modified=False)
		return True
	permission = frappe.new_doc("User Permission")
	permission.update({
		**filters,
		"apply_to_all_doctypes": 1,
	})
	permission.insert(ignore_permissions=True)
	return True


def _ensure_facility_user_permission(user: str, facility_name: str) -> bool:
	"""Ensure User Permission for a verified facility."""
	facility_name = cstr(facility_name or "").strip()
	if not facility_name or not frappe.db.exists("CRM Pre-Qualified Facility", facility_name):
		return False
	filters = {
		"user": user,
		"allow": "CRM Pre-Qualified Facility",
		"for_value": facility_name,
	}
	if frappe.get_all("User Permission", filters=filters, fields=["name"], limit_page_length=1):
		return True
	permission = frappe.new_doc("User Permission")
	permission.update({
		**filters,
		"apply_to_all_doctypes": 1,
	})
	permission.insert(ignore_permissions=True)
	return True


def get_user_facility_names(user: str | None = None) -> list[str]:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	rows = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "CRM Pre-Qualified Facility"},
		fields=["for_value"],
		limit_page_length=0,
	)
	return [cstr(row.get("for_value")) for row in rows if row.get("for_value")]


def ensure_website_user_for_customer(customer, email=None, display_name=None):
	"""Link any active login, or create a Website User, with one Customer-scoped grant."""
	customer = cstr(customer or "").strip()
	requested_email = cstr(email or "").strip().lower()
	if not customer or not frappe.db.exists("Customer", customer):
		return {"status": "blocked", "reason": "Customer account is missing"}
	if not requested_email or frappe.utils.validate_email_address(requested_email).strip().lower() != requested_email:
		return {"status": "blocked", "reason": "No valid portal email is available"}

	user_name = frappe.db.get_value("User", {"email": requested_email}, "name")
	created = False
	if user_name:
		user = frappe.get_doc("User", user_name)
		if not user.enabled:
			return {"status": "blocked", "reason": "User account is disabled"}
	else:
		user = frappe.new_doc("User")
		user.update({
			"email": requested_email,
			"first_name": cstr(display_name or requested_email.split("@")[0]),
			"user_type": "Website User",
			"enabled": 1,
			"send_welcome_email": 0,
			"redirect_url": PORTAL_ROUTE,
		})
		user.flags.ignore_password_policy = True
		user.insert(ignore_permissions=True)
		user_name = user.name
		created = True

	try:
		# Keep an existing System User's normal Desk/CRM redirect unchanged.
		if user.user_type == "Website User":
			user.db_set("redirect_url", PORTAL_ROUTE, update_modified=False)
		if not _ensure_customer_user_permission(user_name, customer):
			return {"status": "failed", "user": user_name}
		if created:
			user._reset_password(send_email=True)
	except Exception as exc:
		frappe.log_error(
			title="CRM CX Customer portal provisioning",
			message="Customer account access setup failed (%s)" % type(exc).__name__,
		)
		return {"status": "failed", "user": user_name}
	return {"status": "sent" if created else "linked", "user": user_name}


def get_user_customer_names(user: str | None = None) -> list[str]:
	"""Resolve exact Customer grants belonging to any active authenticated user."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	try:
		account = frappe.db.get_value("User", user, ["enabled"], as_dict=True) or {}
		if not frappe.utils.cint(account.get("enabled")):
			return []
		rows = frappe.get_all(
			"User Permission",
			filters={
				"user": user,
				"allow": "Customer",
			},
			fields=["for_value"],
			limit_page_length=0,
		)
		names = []
		for row in rows:
			name = cstr(row.get("for_value") or "").strip()
			if name and frappe.db.exists("Customer", name) and name not in names:
				names.append(name)
		return names
	except Exception:
		return []


def _ois_exists(ois_number: str) -> bool:
	try:
		return bool(frappe.db.exists(OIS_DOCTYPE, ois_number))
	except Exception:
		return False


def get_portal_route(user: str | None = None) -> str | None:
	"""Return the CX route for any active user; APIs still authorize each record by permission."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None

	try:
		account = frappe.db.get_value("User", user, ["enabled"], as_dict=True) or {}
	except Exception:
		return None

	if not frappe.utils.cint(account.get("enabled")):
		return None

	return PORTAL_ROUTE


@frappe.whitelist(methods=["GET", "POST"])
def get_current_user_portal_route() -> str | None:
	"""Expose the CX destination for an active authenticated user."""
	return get_portal_route()


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
	elif frappe.db.get_value("User", user, "user_type") == "Website User" and get_portal_route(user):
		# Preserve the existing native behavior for non-branded Website User logins.
		frappe.cache.hset("redirect_after_login", user, PORTAL_ROUTE)


def require_portal_user() -> list[str]:
	"""Require an active login and return only its explicitly permitted OIS records."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Please sign in to access the facility portal."), frappe.PermissionError)

	if not frappe.utils.cint(frappe.db.get_value("User", user, "enabled")):
		frappe.throw(_("This login is disabled."), frappe.PermissionError)

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


def _customer_invoices(customer: str) -> list[dict]:
	if not customer or not frappe.db.exists("Customer", customer):
		return []
	filters = [
		["docstatus", "=", 1],
		["outstanding_amount", ">", 0],
		["customer", "=", customer],
	]
	rows = frappe.get_list(
		"Sales Invoice",
		filters=filters,
		fields=["name", "posting_date", "due_date", "outstanding_amount", "grand_total", "currency"],
		order_by="due_date asc, posting_date asc",
		limit_page_length=200,
		ignore_permissions=True,
	)
	return [
		{
			"name": row.name,
			"invoice_number": row.name,
			"posting_date": str(row.posting_date or ""),
			"due_date": str(row.due_date or ""),
			"amount": float(row.outstanding_amount or 0),
			"grand_total": float(row.grand_total or 0),
			"currency": row.currency or "KES",
			"status": "Outstanding",
			"customer": customer,
		}
		for row in rows
		if frappe.utils.flt(row.outstanding_amount) > 0
	]


def _customer_orders(customer: str) -> list[dict]:
	if not customer or not frappe.db.exists("Customer", customer):
		return []
	fields = [
		"name",
		"transaction_date",
		"delivery_date",
		"grand_total",
		"currency",
		"status",
	]
	for col in ("crm_token_facility_mfl", "crm_token_package_item"):
		if frappe.db.has_column("Sales Order", col):
			fields.append(col)
	orders = frappe.get_list(
		"Sales Order",
		filters={"customer": customer, "docstatus": 1, "per_billed": ["<", 100]},
		fields=fields,
		order_by="creation desc",
		limit_page_length=200,
		ignore_permissions=True,
	)
	for order in orders:
		order["customer"] = customer
		order["can_create_invoice"] = cstr(order.get("status") or "").strip().casefold() not in {"closed", "on hold", "cancelled"}
	return orders


def _customer_portal_accounts(user: str) -> list[dict]:
	"""Project only Customer-linked deals and memberships granted to this user."""
	customer_names = get_user_customer_names(user)
	if not customer_names or not frappe.db.has_column("CRM Facility Membership", "customer"):
		return []
	if not frappe.db.has_column("CRM Deal", "cx_customer"):
		return []
	deal_fields = ["name", "cx_customer", "organization"]
	for fieldname in ("optin_network", "cx_onboarding_source", "cx_onboarding_package_item"):
		if frappe.db.has_column("CRM Deal", fieldname):
			deal_fields.append(fieldname)
	deals = frappe.get_all(
		"CRM Deal",
		filters={"cx_customer": ["in", customer_names]},
		fields=deal_fields,
		ignore_permissions=True,  # SYSTEM-INTERNAL: exact Customer User Permission scoped this projection.
		limit_page_length=0,
	)
	if not deals:
		return []
	deals_by_customer = {}
	for row in deals:
		cust = row.get("cx_customer")
		if cust:
			deals_by_customer.setdefault(cust, []).append(row)
	memberships = frappe.get_all(
		"CRM Facility Membership",
		filters={"customer": ["in", customer_names]},
		fields=["name", "parent", "network", "status", "contact_name", "go_live", "customer"],
		ignore_permissions=True,  # SYSTEM-INTERNAL: exact Customer User Permission scoped this projection.
		limit_page_length=0,
	)
	parent_names = list({row.get("parent") for row in memberships if row.get("parent")})
	facilities = frappe.get_all(
		"CRM Pre-Qualified Facility",
		filters={"name": ["in", parent_names]},
		fields=["name", "mfl_code", "facility_name", "keph_level"],
		ignore_permissions=True,  # SYSTEM-INTERNAL: parent was selected from Customer-linked memberships.
		limit_page_length=0,
	) if parent_names else []
	facility_by_name = {row.name: row for row in facilities}
	deal_names = [cstr(row.get("name")) for row in deals if row.get("name")]
	deal_facility_fields = ["parent", "mfl_code"]
	package_fieldnames = (
		"cx_token_package_item",
		"cx_token_package_quantity",
		"cx_token_package_price",
		"cx_token_package_vat",
		"cx_token_package_gross_total",
		"cx_token_package_currency",
	)
	deal_facility_meta = frappe.get_meta("CRM Deal Facility")
	deal_facility_fields.extend(
		fieldname for fieldname in package_fieldnames if deal_facility_meta.has_field(fieldname)
	)
	deal_facility_rows = frappe.get_all(
		"CRM Deal Facility",
		filters={"parent": ["in", deal_names]},
		fields=deal_facility_fields,
		ignore_permissions=True,  # SYSTEM-INTERNAL: deal names were selected from Customer-scoped deals above.
		limit_page_length=0,
	) if deal_names else []
	package_by_mfl = {}
	deal_by_mfl = {}
	for row in deal_facility_rows:
		mfl = cstr(row.get("mfl_code")).strip().casefold()
		if mfl:
			package_by_mfl[mfl] = row
			deal_by_mfl[mfl] = row.get("parent")
	item_codes = list({cstr(row.get("cx_token_package_item")) for row in deal_facility_rows if row.get("cx_token_package_item")})
	item_rows = frappe.get_all(
		"Item",
		filters={"name": ["in", item_codes]},
		fields=["name", "item_name"],
		ignore_permissions=True,
		limit_page_length=0,
	) if item_codes else []
	item_names = {
		cstr(row.get("name")): cstr(row.get("item_name") or row.get("name"))
		for row in item_rows
	}
	accounts = []
	for customer in customer_names:
		cust_deals = deals_by_customer.get(customer, [])
		if not cust_deals:
			continue
		primary_deal = cust_deals[0]
		rows = []
		for membership in memberships:
			if membership.get("customer") != customer:
				continue
			facility = facility_by_name.get(membership.get("parent"))
			if not facility:
				continue
			mfl_key = cstr(facility.get("mfl_code")).strip().casefold()
			package = package_by_mfl.get(mfl_key, {})
			fac_deal = deal_by_mfl.get(mfl_key, primary_deal.get("name"))
			rows.append({
				"facility_name": cstr(facility.get("facility_name") or "Facility"),
				"mfl_code": cstr(facility.get("mfl_code") or ""),
				"keph_level": cstr(facility.get("keph_level") or ""),
				"network": membership.get("network"),
				"membership_status": cstr(membership.get("status") or "Active"),
				"go_live": bool(frappe.utils.cint(membership.get("go_live"))),
				"deal": fac_deal,
				"customer": customer,
				"token_package": item_names.get(
					cstr(package.get("cx_token_package_item")),
					cstr(package.get("cx_token_package_item") or ""),
				),
				"token_quantity": frappe.utils.cint(package.get("cx_token_package_quantity")),
				"package_price": package.get("cx_token_package_price"),
				"package_vat": package.get("cx_token_package_vat"),
				"package_gross_total": package.get("cx_token_package_gross_total"),
				"package_currency": cstr(package.get("cx_token_package_currency") or ""),
			})
		accounts.append({
			"customer": customer,
			"deal": primary_deal.get("name"),
			"deals": [d.get("name") for d in cust_deals if d.get("name")],
			"organization": cstr(primary_deal.get("organization") or customer),
			"network": primary_deal.get("optin_network"),
			"source": primary_deal.get("cx_onboarding_source"),
			# Retain this only as a legacy fallback; new enrollments show packages per facility.
			"selected_package": primary_deal.get("cx_onboarding_package_item"),
			"facilities": rows,
			"open_orders": _customer_orders(customer),
			"open_invoices": _customer_invoices(customer),
		})
	return accounts


@frappe.whitelist(methods=["GET", "POST"])
def get_portal_context():
	"""Return legacy OIS and Customer enrollment scoped to the authenticated user."""
	ois_numbers = require_portal_user()
	customer_accounts = _customer_portal_accounts(frappe.session.user)
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

	calculator_config = {}
	try:
		from crm.api.facility_onboarding import _calculator_config

		calculator_config = _calculator_config()
	except Exception:
		pass

	return {
		"success": True,
		"data": {
			"route": PORTAL_ROUTE,
			"user": frappe.session.user,
			"ois": rows,
			"customer_accounts": customer_accounts,
			"token_packages": _portal_token_catalog(),
			"calculator_config": calculator_config,
		},
	}
