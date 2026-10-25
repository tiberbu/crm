from urllib.parse import urlencode

import frappe
from frappe.model.document import Document


class CRMPreQualifiedFacility(Document):
	def before_validate(self):
		# Ownership is independent of network membership. Most facilities own
		# themselves, so retain that useful default unless an operator provides
		# the group/organization that owns multiple facilities.
		if not frappe.utils.cstr(self.organization).strip():
			self.organization = frappe.utils.cstr(self.facility_name).strip()

	def after_insert(self):
		if self.flags.get("skip_invitation"):
			return
		for membership in self.memberships or []:
			if _can_invite(membership):
				try:
					_send_membership_invitation(self, membership)
				except Exception:
					frappe.log_error(
						frappe.get_traceback(),
						"CRMPreQualifiedFacility: invitation email failed",
					)


def _can_invite(membership):
	return bool(
		membership.network and membership.contact_email and (membership.status or "Active") == "Active"
	)


def is_self_onboarded_facility(doc_or_name) -> bool:
	"""Return True if this facility was enrolled via the self-onboarding journey."""
	if not doc_or_name:
		return False

	doc = doc_or_name
	if isinstance(doc_or_name, str):
		if getattr(frappe, "db", None) and hasattr(frappe.db, "exists") and frappe.db.exists("CRM Pre-Qualified Facility", doc_or_name):
			doc = frappe.get_doc("CRM Pre-Qualified Facility", doc_or_name)
		else:
			return False

	flags = getattr(doc, "flags", {}) or {}
	if flags.get("is_self_onboarded"):
		return True
	if isinstance(doc, dict):
		if frappe.utils.cint(doc.get("is_self_onboarded")):
			return True
	elif frappe.utils.cint(getattr(doc, "is_self_onboarded", 0)):
		return True

	has_memberships_attr = hasattr(doc, "memberships") or (isinstance(doc, dict) and "memberships" in doc)
	memberships = (doc.get("memberships") if isinstance(doc, dict) else getattr(doc, "memberships", None)) or []
	for membership in memberships:
		cust = membership.get("customer") if isinstance(membership, dict) else getattr(membership, "customer", None)
		if cust:
			return True

	if has_memberships_attr and getattr(doc, "name", None) is None:
		return False

	if getattr(frappe, "db", None) and hasattr(frappe.db, "get_value"):
		doc_name = getattr(doc, "name", None)
		if doc_name and hasattr(frappe.db, "has_column") and frappe.db.has_column("CRM Pre-Qualified Facility", "is_self_onboarded"):
			if frappe.utils.cint(frappe.db.get_value("CRM Pre-Qualified Facility", doc_name, "is_self_onboarded")):
				return True

		if doc_name and hasattr(frappe.db, "table_exists") and frappe.db.table_exists("User Permission"):
			if frappe.db.exists(
				"User Permission",
				{"allow": "CRM Pre-Qualified Facility", "for_value": doc_name},
			):
				return True

		if doc_name and hasattr(frappe.db, "table_exists") and frappe.db.table_exists("CRM Onboarding Evidence"):
			if frappe.db.exists(
				"CRM Onboarding Evidence",
				{"reference_doctype": "CRM Pre-Qualified Facility", "reference_name": doc_name},
			):
				return True

		mfl = getattr(doc, "mfl_code", None)
		if not mfl and doc_name and hasattr(frappe.db, "has_column") and frappe.db.has_column("CRM Pre-Qualified Facility", "mfl_code"):
			mfl = frappe.db.get_value("CRM Pre-Qualified Facility", doc_name, "mfl_code")

		if mfl and hasattr(frappe.db, "table_exists") and frappe.db.table_exists("CRM Deal Facility"):
			if frappe.db.exists("CRM Deal Facility", {"mfl_code": mfl}):
				return True

	return False


def _ensure_self_onboarded_facility_cx_access(doc, membership):
	"""Ensure user permissions and portal account for a self-onboarded facility."""
	email = frappe.utils.cstr(membership.contact_email or "").strip().lower()
	if not email:
		return
	facility_name = getattr(doc, "name", None)
	if not facility_name:
		return

	customer = getattr(membership, "customer", None)
	if not customer:
		for other in getattr(doc, "memberships", []) or []:
			if getattr(other, "customer", None):
				customer = other.customer
				membership.customer = customer
				if (
					getattr(membership, "name", None)
					and getattr(frappe, "db", None)
					and hasattr(frappe.db, "set_value")
					and hasattr(frappe.db, "has_column")
					and frappe.db.has_column("CRM Facility Membership", "customer")
				):
					frappe.db.set_value(
						"CRM Facility Membership", membership.name, "customer", customer, update_modified=False
					)
				break

	try:
		from crm.api.website_redirect import (
			_ensure_customer_user_permission,
			_ensure_facility_user_permission,
			ensure_website_user_for_customer,
		)

		_ensure_facility_user_permission(email, facility_name)
		if customer:
			_ensure_customer_user_permission(email, customer)
			ensure_website_user_for_customer(customer, email=email, display_name=getattr(membership, "contact_name", None))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "CRMPreQualifiedFacility: CX access provisioning failed")


def _send_membership_invitation(doc, membership):
	"""Send and track a branded invitation for one active network membership."""
	if not _can_invite(membership):
		frappe.throw("Only active memberships with a contact email can be invited.")

	network = frappe.get_doc("CRM Opt-In Network", membership.network)
	slug = network.slug or membership.network
	if is_self_onboarded_facility(doc):
		portal_url = "{}/cx-portal".format(frappe.utils.get_url())
		subject = "You've been added to {} — Log in to Tiberbu Express".format(network.display_name)
		message = _cx_login_alert_html(
			membership.contact_name,
			network.display_name,
			doc.facility_name,
			portal_url,
		)
		_ensure_self_onboarded_facility_cx_access(doc, membership)
	else:
		invitation_query = urlencode({"network": slug, "facility": doc.facility_name})
		invitation_url = "{}/facility-onboarding?{}".format(frappe.utils.get_url(), invitation_query)
		subject = "You've been pre-qualified: {} — CareverseHIMS".format(network.display_name)
		message = _invite_html(
			membership.contact_name,
			network.display_name,
			doc.facility_name,
			invitation_url,
		)

	queue = frappe.sendmail(
		recipients=[membership.contact_email],
		subject=subject,
		message=message,
		reference_doctype=getattr(doc, "doctype", None) or "CRM Pre-Qualified Facility",
		reference_name=getattr(doc, "name", None) or "",
		now=True,
	)

	if not queue:
		frappe.throw("The invitation email could not be queued.")

	sent_at = frappe.utils.now_datetime()
	frappe.db.set_value(
		"CRM Facility Membership",
		membership.name,
		{
			"invite_email_queue": queue.name,
			"invite_sent_at": sent_at,
		},
		update_modified=False,
	)
	membership.invite_email_queue = queue.name
	membership.invite_sent_at = sent_at
	return queue


def _invite_html(contact_name, network_name, facility_name, optin_url):
	return """
<p>Dear {contact_name},</p>

<p>You have been pre-qualified to join the <strong>{network_name}</strong> network on
CareverseHIMS — Tiberbu's health information management platform.</p>

<p>Your facility, <strong>{facility_name}</strong>, is ready to be enrolled. The process
takes about 5 minutes:</p>

<ol>
  <li>Verify your email with a one-time code.</li>
  <li>Confirm your facility details and review pricing.</li>
  <li>Accept the subscription agreement.</li>
</ol>

<p style="margin: 24px 0;">
  <a href="{optin_url}"
     style="background:#b91c1c;color:#fff;padding:12px 24px;border-radius:6px;
            text-decoration:none;font-weight:600;">
    View your invitation &rarr;
  </a>
</p>

<p>If the button doesn't work, paste this link in your browser:<br/>
<a href="{optin_url}">{optin_url}</a></p>

<p>If you have questions, reply to this email or contact us at
<a href="mailto:hello@tiberbu.com">hello@tiberbu.com</a>.</p>

<p>Best regards,<br/>The Tiberbu Team</p>
""".format(
		contact_name=contact_name,
		network_name=network_name,
		facility_name=facility_name,
		optin_url=optin_url,
	)


def _cx_login_alert_html(contact_name, network_name, facility_name, portal_url):
	return """
<p>Dear {contact_name},</p>

<p>Your facility, <strong>{facility_name}</strong>, has been added to the <strong>{network_name}</strong> network on
CareverseHIMS — Tiberbu's health information management platform.</p>

<p>Since your facility is already onboarded, you can access your updated network details, token balance, and orders directly in Tiberbu Express.</p>

<p style="margin: 24px 0;">
  <a href="{portal_url}"
     style="background:#0284c7;color:#fff;padding:12px 24px;border-radius:6px;
            text-decoration:none;font-weight:600;">
    Log in to Tiberbu Express &rarr;
  </a>
</p>

<p>If the button doesn't work, paste this link in your browser:<br/>
<a href="{portal_url}">{portal_url}</a></p>

<p>If you have questions, reply to this email or contact us at
<a href="mailto:hello@tiberbu.com">hello@tiberbu.com</a>.</p>

<p>Best regards,<br/>The Tiberbu Team</p>
""".format(
		contact_name=contact_name or "Facility Representative",
		network_name=network_name,
		facility_name=facility_name,
		portal_url=portal_url,
	)

