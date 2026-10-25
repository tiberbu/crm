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


def _portal_hfr_registry_by_mfl(mfl_codes, organizations):
	"""Resolve the HFR FID from an authorized organization's facility table.

	Portal rows are projected from several older CRM records, while the
	organization facility table is where a verified HFR lookup may have saved
	the FID. Scope this fallback to both the already-authorized MFLs and the
	organizations attached to those records; never use a browser-supplied ID.
	"""
	mfl_codes = sorted({cstr(value or "").strip() for value in mfl_codes if cstr(value or "").strip()})
	organizations = sorted({cstr(value or "").strip() for value in organizations if cstr(value or "").strip()})
	if not mfl_codes or not organizations:
		return {}

	fields = ["parent", "mfl_code", "hfr_facility_id"]
	rows = frappe.get_all(
		"CRM Org Facility",
		filters={
			"parent": ["in", organizations],
			"parenttype": "CRM Organization",
			"mfl_code": ["in", mfl_codes],
		},
		fields=fields,
		ignore_permissions=True,  # SYSTEM-INTERNAL: both organization and MFL come from the authorized portal scope.
		limit_page_length=0,
	)
	return {
		(cstr(row.get("parent") or "").casefold(), cstr(row.get("mfl_code") or "").strip().casefold()): row
		for row in rows
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
				fields=["name", "mfl_code", "facility_name", "keph_level", "organization", "hfr_facility_id"],
				ignore_permissions=True,  # SYSTEM-INTERNAL: OIS permission scopes the snapshot.
				limit_page_length=0,
			)
		}
	registry_by_mfl = _portal_hfr_registry_by_mfl(
		mfl_codes,
		[row.get("organization") for row in facility_rows.values()],
	)
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
				"hfr_facility_id": (facility or {}).get("hfr_facility_id") or registry_by_mfl.get(
					(cstr((facility or {}).get("organization") or "").casefold(), mfl_code.casefold()), {}
				).get("hfr_facility_id") or "",
				"network": network,
				"membership_status": membership_status,
				"network_contact": {
					"name": membership.name if membership else None,
					"source": "token_self_onboarding" if is_self_onboarding else "network_optin",
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
			"label": "Self-Onboarding request submitted",
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


def get_user_lead_names(user: str | None = None) -> list[str]:
	"""Resolve permitted CRM Leads for this user."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	lead_names = set()
	rows = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": ["in", ["CRM Lead", "Lead"]]},
		fields=["for_value"],
		limit_page_length=0,
	)
	for r in rows:
		val = cstr(r.get("for_value") or "").strip()
		if val and frappe.db.exists("CRM Lead", val):
			lead_names.add(val)
	return list(lead_names)


def get_user_deal_names(user: str | None = None) -> list[str]:
	"""Resolve permitted CRM Deals for this user."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	deal_names = set()
	# 1. Direct Deal permissions
	deal_perms = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": ["in", ["CRM Deal", "Deal"]]},
		fields=["for_value"],
		limit_page_length=0,
	)
	for row in deal_perms:
		d = cstr(row.get("for_value") or "").strip()
		if d and frappe.db.exists("CRM Deal", d):
			deal_names.add(d)

	# 2. Deals linked to directly permitted Customers
	cust_perms = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Customer"},
		fields=["for_value"],
		limit_page_length=0,
	)
	cust_names = [cstr(r.get("for_value") or "").strip() for r in cust_perms if r.get("for_value")]
	if cust_names:
		if frappe.db.has_column("CRM Deal", "cx_customer"):
			deals = frappe.get_all(
				"CRM Deal",
				filters={"cx_customer": ["in", cust_names]},
				fields=["name"],
				limit_page_length=0,
			)
			deal_names.update(r["name"] for r in deals)
		if frappe.db.has_column("CRM Deal", "erpnext_customer"):
			deals = frappe.get_all(
				"CRM Deal",
				filters={"erpnext_customer": ["in", cust_names]},
				fields=["name"],
				limit_page_length=0,
			)
			deal_names.update(r["name"] for r in deals)

	# 3. Deals linked to directly permitted Leads
	lead_names = get_user_lead_names(user)
	if lead_names and frappe.db.has_column("CRM Deal", "lead"):
		deals = frappe.get_all(
			"CRM Deal",
			filters={"lead": ["in", lead_names]},
			fields=["name"],
			limit_page_length=0,
		)
		deal_names.update(r["name"] for r in deals)

	return list(deal_names)


def get_user_customer_names(user: str | None = None) -> list[str]:
	"""Resolve exact Customer grants belonging to any active authenticated user.
	Includes directly permitted Customers, plus Customers linked to permitted Deals or Leads.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	try:
		account = frappe.db.get_value("User", user, ["enabled"], as_dict=True) or {}
		if not frappe.utils.cint(account.get("enabled")):
			return []

		customer_names = set()
		# 1. Direct Customer User Permissions
		rows = frappe.get_all(
			"User Permission",
			filters={
				"user": user,
				"allow": "Customer",
			},
			fields=["for_value"],
			limit_page_length=0,
		)
		for row in rows:
			name = cstr(row.get("for_value") or "").strip()
			if name and frappe.db.exists("Customer", name):
				customer_names.add(name)

		# 2. Customers linked to permitted Deals
		deal_perms = frappe.get_all(
			"User Permission",
			filters={"user": user, "allow": ["in", ["CRM Deal", "Deal"]]},
			fields=["for_value"],
			limit_page_length=0,
		)
		for dp in deal_perms:
			deal_id = cstr(dp.get("for_value") or "").strip()
			if deal_id and frappe.db.exists("CRM Deal", deal_id):
				deal_doc = frappe.db.get_value(
					"CRM Deal",
					deal_id,
					["cx_customer", "erpnext_customer", "organization"],
					as_dict=True,
				) or {}
				for field in ("cx_customer", "erpnext_customer"):
					cust = cstr(deal_doc.get(field) or "").strip()
					if cust and frappe.db.exists("Customer", cust):
						customer_names.add(cust)
				org = cstr(deal_doc.get("organization") or "").strip()
				if org and frappe.db.exists("Customer", org):
					customer_names.add(org)

		# 3. Customers linked to permitted Leads
		lead_perms = frappe.get_all(
			"User Permission",
			filters={"user": user, "allow": ["in", ["CRM Lead", "Lead"]]},
			fields=["for_value"],
			limit_page_length=0,
		)
		for lp in lead_perms:
			lead_id = cstr(lp.get("for_value") or "").strip()
			if lead_id and frappe.db.exists("CRM Lead", lead_id):
				lead_org = cstr(frappe.db.get_value("CRM Lead", lead_id, "organization") or "").strip()
				if lead_org and frappe.db.exists("Customer", lead_org):
					customer_names.add(lead_org)
				if frappe.db.has_column("CRM Deal", "lead"):
					deals = frappe.get_all(
						"CRM Deal",
						filters={"lead": lead_id},
						fields=["cx_customer", "organization"],
						limit_page_length=1,
					)
					if deals:
						for c in (deals[0].get("cx_customer"), deals[0].get("organization")):
							c = cstr(c or "").strip()
							if c and frappe.db.exists("Customer", c):
								customer_names.add(c)

		return list(customer_names)
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
	cache = getattr(frappe.local, "_cx_portal_network_cache", None)
	if cache is None:
		cache = {}
		frappe.local._cx_portal_network_cache = cache
	if network_name in cache:
		return cache[network_name]
	rows = frappe.get_list(
		"CRM Opt-In Network",
		filters={"name": network_name},
		fields=[
			"name",
			"slug",
			"display_name",
			"partner_id",
			"logo_url",
			"primary_colour",
			"contact_email",
			"technology_delivery_partner_name",
			"technology_delivery_partner_short_name",
			"footer_legal_name",
		],
		limit_page_length=1,
		ignore_permissions=True,
	)
	if not rows:
		cache[network_name] = {}
		return {}

	network = dict(rows[0])
	coordinator_rows = frappe.get_all(
		"CRM Network Coordinator",
		filters={"parent": network_name, "parenttype": "CRM Opt-In Network"},
		fields=["user"],
		limit_page_length=20,
		ignore_permissions=True,
	)
	contacts = []
	for coordinator in coordinator_rows:
		user = coordinator.get("user")
		if not user:
			continue
		person = frappe.db.get_value(
			"User", user, ["full_name", "email", "mobile_no", "phone"], as_dict=True
		) or {}
		contacts.append(
			{
				"name": person.get("full_name") or user,
				"email": person.get("email") or "",
				"phone": person.get("mobile_no") or person.get("phone") or "",
			}
		)
	network["coordinators"] = contacts
	cache[network_name] = network
	return network


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
	fields = ["name", "posting_date", "due_date", "outstanding_amount", "grand_total", "currency"]
	if frappe.db.has_column("Sales Invoice", "crm_token_facility_mfl"):
		fields.append("crm_token_facility_mfl")
	rows = frappe.get_list(
		"Sales Invoice",
		filters=filters,
		fields=fields,
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
			"crm_token_facility_mfl": cstr(row.get("crm_token_facility_mfl") or ""),
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


def _customer_payments(customer: str) -> list[dict]:
	"""Retrieve posted payments and customer M-Pesa reports awaiting reconciliation."""
	if not customer:
		return []
	if not frappe.db.exists("DocType", "Payment Entry"):
		return []
	fields = ["name", "posting_date", "paid_amount", "received_amount", "mode_of_payment", "reference_no", "status", "docstatus", "remarks"]
	try:
		rows = frappe.get_list(
			"Payment Entry",
			filters={"party": customer, "party_type": "Customer", "docstatus": ["in", [0, 1]]},
			fields=fields,
			order_by="posting_date desc, creation desc",
			limit_page_length=50,
			ignore_permissions=True,
		)
		payment_names = [row.name for row in rows]
		refs_by_payment = {}
		if payment_names and frappe.db.exists("DocType", "Payment Entry Reference"):
			refs = frappe.get_all(
				"Payment Entry Reference",
				filters={"parent": ["in", payment_names], "reference_doctype": "Sales Invoice"},
				fields=["parent", "reference_name"],
				limit_page_length=0,
				ignore_permissions=True,
			)
			for ref in refs:
				refs_by_payment.setdefault(ref.parent, []).append(ref.reference_name)
		return [
			{
				"name": row.name,
				"posting_date": str(row.posting_date or ""),
				"amount": float(row.paid_amount or row.received_amount or 0),
				"mode_of_payment": "M-Pesa Paybill" if _is_pending_mpesa_report(row) else (row.mode_of_payment or "M-Pesa / Bank"),
				"reference_no": row.reference_no or "",
				"status": "Pending Verification" if _is_pending_mpesa_report(row) else "Recorded",
				"invoice_names": refs_by_payment.get(row.name, []),
				"invoice": (refs_by_payment.get(row.name) or [None])[0],
				"customer": customer,
			}
			for row in rows
			if row.docstatus == 1 or _is_pending_mpesa_report(row)
		]
	except Exception:
		return []


def _is_pending_mpesa_report(payment_entry) -> bool:
	"""Only portal M-Pesa reports are pending customer-visible Payment Entries."""
	if isinstance(payment_entry, dict):
		remarks = cstr(payment_entry.get("remarks") or "")
		docstatus = payment_entry.get("docstatus")
	else:
		remarks = cstr(getattr(payment_entry, "remarks", "") or "")
		docstatus = getattr(payment_entry, "docstatus", 0)
	return int(docstatus or 0) == 0 and remarks.startswith("M-Pesa Paybill payment ")


def _facility_payment_history(customer: str, facility_mfl: str) -> list[dict]:
	"""Return payments allocated to invoices tagged to one facility."""
	if not frappe.db.has_column("Sales Invoice", "crm_token_facility_mfl"):
		return []
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "crm_token_facility_mfl": facility_mfl},
		fields=["name"],
		limit_page_length=0,
		ignore_permissions=True,
	)
	invoice_names = [row.name for row in invoices]
	if not invoice_names or not frappe.db.exists("DocType", "Payment Entry Reference"):
		return []
	refs = frappe.get_all(
		"Payment Entry Reference",
		filters={"reference_doctype": "Sales Invoice", "reference_name": ["in", invoice_names]},
		fields=["parent", "reference_name", "allocated_amount"],
		limit_page_length=0,
		ignore_permissions=True,
	)
	parent_names = list({row.parent for row in refs if row.parent})
	if not parent_names:
		return []
	entries = frappe.get_all(
		"Payment Entry",
		filters={"name": ["in", parent_names], "party": customer, "party_type": "Customer", "docstatus": ["in", [0, 1]]},
		fields=["name", "posting_date", "paid_amount", "received_amount", "mode_of_payment", "reference_no", "remarks", "docstatus"],
		order_by="posting_date desc, creation desc",
		limit_page_length=100,
		ignore_permissions=True,
	)
	entry_by_name = {
		row.name: row for row in entries if row.docstatus == 1 or _is_pending_mpesa_report(row)
	}
	return [
		{
			"name": entry_by_name[row.parent].name,
			"invoice": row.reference_name,
			"posting_date": str(entry_by_name[row.parent].posting_date or ""),
			"amount": float(row.allocated_amount or 0),
			"mode_of_payment": "M-Pesa Paybill" if _is_pending_mpesa_report(entry_by_name[row.parent]) else (entry_by_name[row.parent].mode_of_payment or "M-Pesa / Bank"),
			"reference_no": entry_by_name[row.parent].reference_no or "",
			"status": "Pending Verification" if _is_pending_mpesa_report(entry_by_name[row.parent]) else "Recorded",
			"customer": customer,
		}
		for row in refs
		if row.parent in entry_by_name
	]


def _facility_invoice_history(customer: str, facility_mfl: str) -> list[dict]:
	"""Return paid and outstanding invoices carrying this facility's billing tag."""
	if not frappe.db.has_column("Sales Invoice", "crm_token_facility_mfl"):
		return []
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "crm_token_facility_mfl": facility_mfl, "docstatus": ["in", [0, 1]]},
		fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency", "status", "docstatus"],
		order_by="posting_date desc, creation desc",
		limit_page_length=100,
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
			"status": "Outstanding" if frappe.utils.flt(row.outstanding_amount) > 0 else "Paid",
			"customer": customer,
			"crm_token_facility_mfl": facility_mfl,
		}
		for row in rows
	]
def _customer_portal_accounts(user: str) -> list[dict]:
	"""Project Customer, Deal, and Lead-linked facilities, orders, invoices, and payments granted to this user."""
	hfr_detail_fields = (
		"hfr_facility_id", "registration_number", "facility_type", "facility_category",
		"facility_owner", "facility_owner_type", "regulatory_body", "board_registration_number",
		"kra_pin", "operational_status", "hfr_county", "hfr_sub_county", "hfr_constituency",
		"hfr_ward", "latitude", "longitude", "license_number", "license_type", "license_expiry",
		"facility_standing", "number_of_beds", "number_of_cots", "open_whole_day",
		"open_weekends", "open_public_holidays", "open_late_night",
		"hfr_sync_status", "hfr_last_synced",
	)

	def hfr_details(primary, fallback=None):
		primary = primary or {}
		fallback = fallback or {}
		result = {}
		for fieldname in hfr_detail_fields:
			value = primary.get(fieldname)
			if value in (None, ""):
				value = fallback.get(fieldname)
			result[fieldname] = value if value is not None else ""
		return result

	def available_fields(doctype, fieldnames):
		meta = frappe.get_meta(doctype)
		return [fieldname for fieldname in fieldnames if meta.has_field(fieldname)]

	customer_names = get_user_customer_names(user)
	deal_names = get_user_deal_names(user)
	lead_names = get_user_lead_names(user)

	if not customer_names and not deal_names and not lead_names:
		return []

	deal_fields = ["name", "cx_customer", "organization"]
	for fieldname in ("optin_network", "cx_onboarding_source", "cx_onboarding_package_item"):
		if frappe.db.has_column("CRM Deal", fieldname):
			deal_fields.append(fieldname)

	deals = []
	if frappe.db.has_column("CRM Deal", "cx_customer"):
		if customer_names and deal_names:
			deals = frappe.get_all(
				"CRM Deal",
				filters={"name": ["in", list(deal_names)]},
				fields=deal_fields,
				ignore_permissions=True,
				limit_page_length=0,
			)
			cust_deals = frappe.get_all(
				"CRM Deal",
				filters={"cx_customer": ["in", list(customer_names)]},
				fields=deal_fields,
				ignore_permissions=True,
				limit_page_length=0,
			)
			existing_names = {d["name"] for d in deals}
			for cd in cust_deals:
				if cd["name"] not in existing_names:
					deals.append(cd)
		elif customer_names:
			deals = frappe.get_all(
				"CRM Deal",
				filters={"cx_customer": ["in", list(customer_names)]},
				fields=deal_fields,
				ignore_permissions=True,
				limit_page_length=0,
			)
		elif deal_names:
			deals = frappe.get_all(
				"CRM Deal",
				filters={"name": ["in", list(deal_names)]},
				fields=deal_fields,
				ignore_permissions=True,
				limit_page_length=0,
			)

	deals_by_customer = {}
	all_scoped_deal_names = set(deal_names)
	for row in deals:
		all_scoped_deal_names.add(row.name)
		cust = row.get("cx_customer")
		if cust:
			deals_by_customer.setdefault(cust, []).append(row)

	memberships = []
	if customer_names and frappe.db.has_column("CRM Facility Membership", "customer"):
		memberships = frappe.get_all(
			"CRM Facility Membership",
			filters={"customer": ["in", list(customer_names)]},
			fields=["name", "parent", "network", "status", "contact_name", "go_live", "customer"],
			ignore_permissions=True,
			limit_page_length=0,
		)

	parent_names = list({row.get("parent") for row in memberships if row.get("parent")})
	facilities = frappe.get_all(
		"CRM Pre-Qualified Facility",
		filters={"name": ["in", parent_names]},
		fields=available_fields(
			"CRM Pre-Qualified Facility",
			["name", "mfl_code", "facility_name", "keph_level", "organization"] + list(hfr_detail_fields),
		),
		ignore_permissions=True,
		limit_page_length=0,
	) if parent_names else []
	facility_by_name = {row.name: row for row in facilities}

	deal_facility_fields = ["name", "parent", "mfl_code", "facility_name", "facility_level"]
	package_fieldnames = hfr_detail_fields + (
		"cx_token_package_item",
		"cx_token_package_quantity",
		"cx_token_package_price",
		"cx_token_package_vat",
		"cx_token_package_gross_total",
		"cx_token_package_currency",
	)
	deal_facility_meta = frappe.get_meta("CRM Deal Facility")
	deal_facility_fields.extend(fieldname for fieldname in package_fieldnames if deal_facility_meta.has_field(fieldname))
	deal_facility_rows = frappe.get_all(
		"CRM Deal Facility",
		filters={"parent": ["in", list(all_scoped_deal_names)]},
		fields=deal_facility_fields,
		ignore_permissions=True,
		limit_page_length=0,
	) if all_scoped_deal_names else []

	package_by_mfl = {}
	deal_by_mfl = {}
	deal_facilities_by_deal = {}
	for row in deal_facility_rows:
		deal_facilities_by_deal.setdefault(row.parent, []).append(row)
		mfl = cstr(row.get("mfl_code")).strip().casefold()
		if mfl:
			package_by_mfl[mfl] = row
			deal_by_mfl[mfl] = row.get("parent")

	customer_names_by_legal_name = {
		cstr(row.get("name") or ""): cstr(row.get("customer_name") or row.get("name") or "")
		for row in frappe.get_all(
			"Customer",
			filters={"name": ["in", list(customer_names)]},
			fields=["name", "customer_name"],
			limit_page_length=0,
			ignore_permissions=True,
		)
	} if customer_names else {}
	deal_organization_by_name = {
		cstr(row.get("name") or ""): cstr(row.get("organization") or "") for row in deals
	}
	registry_org_names = set(customer_names) | set(customer_names_by_legal_name.values())
	registry_org_names.update(value for value in deal_organization_by_name.values() if value)
	registry_org_names.update(cstr(row.get("organization") or "") for row in facilities if row.get("organization"))
	registry_mfl_codes = {
		cstr(row.get("mfl_code") or "").strip()
		for row in [*facilities, *deal_facility_rows]
		if cstr(row.get("mfl_code") or "").strip()
	}
	registry_by_org_mfl = _portal_hfr_registry_by_mfl(registry_mfl_codes, registry_org_names)

	def registry_facility(organization_names, mfl_code):
		mfl_key = cstr(mfl_code or "").strip().casefold()
		for organization in organization_names:
			key = (cstr(organization or "").strip().casefold(), mfl_key)
			if key in registry_by_org_mfl:
				return registry_by_org_mfl[key]
		return {}

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
	seen_deals = set()

	# 1. Process Customer-centric accounts
	for customer in customer_names:
		cust_deals = deals_by_customer.get(customer, [])
		primary_deal = cust_deals[0] if cust_deals else {}
		for d in cust_deals:
			seen_deals.add(d.get("name"))

		customer_doc = frappe.db.get_value("Customer", customer, ["customer_name", "customer_type"], as_dict=True) or {}
		customer_legal_name = cstr(customer_doc.get("customer_name") or customer)
		open_orders = _customer_orders(customer)
		open_invoices = _customer_invoices(customer)
		customer_payments = _customer_payments(customer)

		rows = []
		seen_mfls = set()

		# Collect from memberships
		for membership in memberships:
			if membership.get("customer") != customer:
				continue
			facility = facility_by_name.get(membership.get("parent"))
			if not facility:
				continue
			mfl_raw = cstr(facility.get("mfl_code") or "")
			mfl_key = mfl_raw.strip().casefold()
			if mfl_key:
				seen_mfls.add(mfl_key)
			package = package_by_mfl.get(mfl_key, {})
			fac_deal = deal_by_mfl.get(mfl_key, primary_deal.get("name") if primary_deal else "")

			latest_order = None
			for order in open_orders:
				if cstr(order.get("crm_token_facility_mfl")).strip().casefold() == mfl_key:
					latest_order = order
					break
			if not latest_order and mfl_key:
				past_orders = frappe.get_all(
					"Sales Order",
					filters={"customer": customer, "crm_token_facility_mfl": mfl_raw, "docstatus": 1},
					fields=["name", "transaction_date", "grand_total", "currency", "crm_token_package_item"],
					order_by="creation desc",
					limit=1,
					ignore_permissions=True,
				)
				if past_orders:
					latest_order = past_orders[0]

			fac_invoices = _facility_invoice_history(customer, mfl_raw)
			fac_payments = _facility_payment_history(customer, mfl_raw)

			rows.append({
				"facility_name": cstr(facility.get("facility_name") or "Facility"),
				"mfl_code": mfl_raw,
				**hfr_details(facility, package),
				"hfr_facility_id": facility.get("hfr_facility_id")
				or registry_facility(
					[facility.get("organization"), deal_organization_by_name.get(fac_deal), customer_legal_name, customer],
					mfl_raw,
				).get("hfr_facility_id")
				or package.get("hfr_facility_id")
				or "",
				"keph_level": cstr(facility.get("keph_level") or ""),
				"network": frappe.db.get_value("CRM Opt-In Network", membership.get("network"), "display_name") if membership.get("network") else (primary_deal.get("optin_network") if primary_deal else None) or "CareVerse Partner Network",
				"network_support": _portal_network(membership.get("network") or (primary_deal.get("optin_network") if primary_deal else "")),
				"membership_status": cstr(membership.get("status") or "Active"),
				"go_live": bool(frappe.utils.cint(membership.get("go_live"))),
				"deal": fac_deal,
				"customer": customer,
				"token_package": item_names.get(
					cstr(package.get("cx_token_package_item")),
					cstr(package.get("cx_token_package_item") or ""),
				),
				"token_package_item_code": cstr(package.get("cx_token_package_item") or ""),
				"token_quantity": frappe.utils.cint(package.get("cx_token_package_quantity")),
				"package_price": package.get("cx_token_package_price"),
				"package_vat": package.get("cx_token_package_vat"),
				"package_gross_total": package.get("cx_token_package_gross_total"),
				"package_currency": cstr(package.get("cx_token_package_currency") or ""),
				"recent_purchase": {
					"order_id": latest_order.get("name"),
					"date": str(latest_order.get("transaction_date") or ""),
					"package_name": item_names.get(cstr(latest_order.get("crm_token_package_item")), cstr(latest_order.get("crm_token_package_item") or "")),
					"amount": float(latest_order.get("grand_total") or 0),
					"currency": latest_order.get("currency") or "KES",
				} if latest_order else None,
				"invoice_summary": {
					"has_outstanding": bool(fac_invoices),
					"outstanding_amount": sum(float(inv.get("amount") or 0) for inv in fac_invoices),
					"currency": fac_invoices[0].get("currency") if fac_invoices else "KES",
					"invoice_name": fac_invoices[0].get("name") if fac_invoices else None,
					"count": len(fac_invoices),
				},
				"invoices": fac_invoices,
				"payments": fac_payments,
			})

		# Also collect from CRM Deal Facility for any deals under this customer
		for d in cust_deals:
			for df in deal_facilities_by_deal.get(d.get("name"), []):
				mfl_raw = cstr(df.get("mfl_code") or "")
				mfl_key = mfl_raw.strip().casefold()
				if mfl_key and mfl_key in seen_mfls:
					continue
				if mfl_key:
					seen_mfls.add(mfl_key)
				rows.append({
					"facility_name": cstr(df.get("facility_name") or "Facility"),
					"mfl_code": mfl_raw,
					**hfr_details(df),
					"hfr_facility_id": df.get("hfr_facility_id")
					or registry_facility([deal_organization_by_name.get(d.get("name")), customer_legal_name, customer], mfl_raw).get("hfr_facility_id")
					or "",
					"keph_level": cstr(df.get("facility_level") or "Level 2 Dispensary"),
					"network": d.get("optin_network") or "CareVerse Partner Network",
					"network_support": _portal_network(d.get("optin_network")),
					"membership_status": "Active",
					"go_live": True,
					"deal": d.get("name"),
					"customer": customer,
					"token_package": item_names.get(cstr(df.get("cx_token_package_item")), cstr(df.get("cx_token_package_item") or "")),
					"token_package_item_code": cstr(df.get("cx_token_package_item") or ""),
					"token_quantity": frappe.utils.cint(df.get("cx_token_package_quantity")),
					"package_price": df.get("cx_token_package_price"),
					"package_vat": df.get("cx_token_package_vat"),
					"package_gross_total": df.get("cx_token_package_gross_total"),
					"package_currency": cstr(df.get("cx_token_package_currency") or ""),
					"recent_purchase": None,
					"invoice_summary": {"has_outstanding": False, "outstanding_amount": 0, "currency": "KES", "invoice_name": None, "count": 0},
					"invoices": _facility_invoice_history(customer, mfl_raw),
					"payments": _facility_payment_history(customer, mfl_raw),
				})

		org_name = customer_legal_name
		if primary_deal:
			deal_org = cstr(primary_deal.get("organization") or "")
			if deal_org and deal_org != org_name:
				child_facility_names = {r["facility_name"].casefold() for r in rows}
				if deal_org.casefold() not in child_facility_names:
					org_name = deal_org

		accounts.append({
			"customer": customer,
			"deal": primary_deal.get("name") if primary_deal else "",
			"deals": [d.get("name") for d in cust_deals if d.get("name")],
			"organization": org_name,
			"network": (primary_deal.get("optin_network") if primary_deal else None) or "CareVerse Partner Network",
			"source": primary_deal.get("cx_onboarding_source") if primary_deal else "Customer",
			"selected_package": primary_deal.get("cx_onboarding_package_item") if primary_deal else None,
			"facilities": rows,
			"open_orders": open_orders,
			"open_invoices": open_invoices,
			"payments": customer_payments,
		})

	# 2. Process Standalone Deal permissions
	for d_name in deal_names:
		if d_name in seen_deals:
			continue
		deal_doc = frappe.db.get_value("CRM Deal", d_name, ["name", "organization", "optin_network", "lead", "cx_onboarding_source"], as_dict=True) or {}
		if not deal_doc:
			continue
		seen_deals.add(d_name)
		fac_rows = []
		for df in deal_facilities_by_deal.get(d_name, []):
			fac_rows.append({
				"facility_name": cstr(df.get("facility_name") or "Facility"),
				"mfl_code": cstr(df.get("mfl_code") or ""),
				**hfr_details(df),
				"hfr_facility_id": df.get("hfr_facility_id")
				or registry_facility([deal_organization_by_name.get(d_name), deal_doc.get("organization")], df.get("mfl_code")).get("hfr_facility_id")
				or "",
				"keph_level": cstr(df.get("facility_level") or "Level 2 Dispensary"),
				"network": deal_doc.get("optin_network") or "CareVerse Partner Network",
				"network_support": _portal_network(deal_doc.get("optin_network")),
				"membership_status": "Active",
				"go_live": True,
				"deal": d_name,
				"customer": d_name,
				"token_package": item_names.get(cstr(df.get("cx_token_package_item")), cstr(df.get("cx_token_package_item") or "")),
				"token_package_item_code": cstr(df.get("cx_token_package_item") or ""),
				"token_quantity": frappe.utils.cint(df.get("cx_token_package_quantity")),
				"package_price": df.get("cx_token_package_price"),
				"package_vat": df.get("cx_token_package_vat"),
				"package_gross_total": df.get("cx_token_package_gross_total"),
				"package_currency": cstr(df.get("cx_token_package_currency") or ""),
				"recent_purchase": None,
				"invoice_summary": {"has_outstanding": False, "outstanding_amount": 0, "currency": "KES", "invoice_name": None, "count": 0},
			})

		accounts.append({
			"customer": d_name,
			"deal": d_name,
			"deals": [d_name],
			"organization": deal_doc.get("organization") or f"Deal {d_name}",
			"network": deal_doc.get("optin_network") or "CareVerse Partner Network",
			"source": deal_doc.get("cx_onboarding_source") or "CRM Deal",
			"selected_package": None,
			"facilities": fac_rows,
			"open_orders": [],
			"open_invoices": [],
			"payments": [],
		})

	# 3. Process Standalone Lead permissions
	for l_name in lead_names:
		lead_doc = frappe.db.get_value("CRM Lead", l_name, ["name", "organization", "optin_network"], as_dict=True) or {}
		if not lead_doc:
			continue
		lead_fac_rows = frappe.get_all(
			"CRM Lead Facility",
			filters={"parent": l_name},
			fields=available_fields("CRM Lead Facility", ["facility_name", "mfl_code", "facility_level"] + list(hfr_detail_fields)),
			limit_page_length=0,
		)
		lead_registry = _portal_hfr_registry_by_mfl(
			[row.get("mfl_code") for row in lead_fac_rows],
			[lead_doc.get("organization")],
		)
		fac_rows = [
			{
				"facility_name": cstr(lf.get("facility_name") or "Facility"),
				"mfl_code": cstr(lf.get("mfl_code") or ""),
				**hfr_details(lf),
				"hfr_facility_id": lf.get("hfr_facility_id")
				or lead_registry.get(
					(cstr(lead_doc.get("organization") or "").casefold(), cstr(lf.get("mfl_code") or "").strip().casefold()),
					{},
				).get("hfr_facility_id")
				or "",
				"keph_level": cstr(lf.get("facility_level") or "Level 2 Dispensary"),
				"network": lead_doc.get("optin_network") or "CareVerse Partner Network",
				"network_support": _portal_network(lead_doc.get("optin_network")),
				"membership_status": "Lead Inquiry",
				"go_live": False,
				"deal": "",
				"customer": l_name,
				"token_package": "",
				"token_package_item_code": "",
				"token_quantity": 0,
				"package_price": 0,
				"package_vat": 0,
				"package_gross_total": 0,
				"package_currency": "KES",
				"recent_purchase": None,
				"invoice_summary": {"has_outstanding": False, "outstanding_amount": 0, "currency": "KES", "invoice_name": None, "count": 0},
			}
			for lf in lead_fac_rows
		]
		accounts.append({
			"customer": l_name,
			"deal": "",
			"deals": [],
			"organization": lead_doc.get("organization") or f"Lead {l_name}",
			"network": lead_doc.get("optin_network") or "CareVerse Partner Network",
			"source": "CRM Lead",
			"selected_package": None,
			"facilities": fac_rows,
			"open_orders": [],
			"open_invoices": [],
			"payments": [],
		})

	_attach_token_balances(accounts)
	return accounts


def _attach_token_balances(accounts: list[dict]) -> None:
	"""Add each facility's live token balance from the metering app, keyed by FID.

	The metering app answers through the crm_get_facility_token_balances hook, so CRM
	does not import it. Without that app, facilities keep showing their package size.
	"""
	facilities = [facility for account in accounts for facility in account.get("facilities") or []]
	fids = sorted({cstr(f.get("hfr_facility_id")).strip() for f in facilities if cstr(f.get("hfr_facility_id")).strip()})
	if not fids:
		return
	balances = {}
	for method in frappe.get_hooks("crm_get_facility_token_balances"):
		try:
			balances.update(frappe.get_attr(method)(fids) or {})
		except Exception:
			frappe.log_error(title="Facility token balances unavailable", message=frappe.get_traceback())
	for facility in facilities:
		entry = balances.get(cstr(facility.get("hfr_facility_id")).strip())
		if entry:
			facility["token_balance"] = entry


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

	user_doc = frappe.db.get_value("User", frappe.session.user, ["name", "email", "first_name", "last_name", "full_name", "user_image", "user_type"], as_dict=True) or {}
	full_name = user_doc.get("full_name") or f"{user_doc.get('first_name') or ''} {user_doc.get('last_name') or ''}".strip()
	user_info = {
		"email": user_doc.get("email") or frappe.session.user,
		"full_name": full_name or user_doc.get("email") or "User",
		"user_image": user_doc.get("user_image") or "",
		"user_type": user_doc.get("user_type") or "Website User",
	}

	return {
		"success": True,
		"data": {
			"route": PORTAL_ROUTE,
			"user": frappe.session.user,
			"user_info": user_info,
			"ois": rows,
			"customer_accounts": customer_accounts,
			"token_packages": _portal_token_catalog(),
			"calculator_config": calculator_config,
			"paybill_info": {
				"business_number": "4130669",
				"business_name": "Tiberbu Healthnet",
			},
		},
	}
