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


def _send_membership_invitation(doc, membership):
	"""Send and track a branded invitation for one active network membership."""
	if not _can_invite(membership):
		frappe.throw("Only active memberships with a contact email can be invited.")

	network = frappe.get_doc("CRM Opt-In Network", membership.network)
	slug = network.slug or membership.network
	optin_url = "{}/opt-in?network={}".format(frappe.utils.get_url(), slug)
	queue = frappe.sendmail(
		recipients=[membership.contact_email],
		subject="You've been pre-qualified: {} — CareverseHIMS".format(network.display_name),
		message=_invite_html(membership.contact_name, network.display_name, doc.facility_name, optin_url),
		reference_doctype=doc.doctype,
		reference_name=doc.name,
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
    Start Opt-In &rarr;
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
