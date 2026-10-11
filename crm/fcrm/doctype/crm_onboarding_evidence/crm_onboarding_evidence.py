"""Append-only evidence for guest facility onboarding.

Rows hold keyed digests and short redacted text only: no identity number,
contact, OTP, or upstream payload is ever stored.
"""

import hashlib
import hmac
import re

import frappe
from frappe import _
from frappe.model.document import Document

# Emails and any run of six or more digits (identity numbers, phones, OTPs).
_SENSITIVE_RE = re.compile(r"[^\s@]+@[^\s@]+|\d{6,}")
_MAX_DETAIL = 140


def evidence_ref(value: str) -> str:
	"""Return a stable keyed digest of a session token or identity for correlation."""
	secret = frappe.conf.get("encryption_key") or frappe.local.site
	return hmac.new(secret.encode(), (value or "").encode(), hashlib.sha256).hexdigest()[:32]


def record_event(
	event: str,
	*,
	session_ref: str = "",
	subject_ref: str = "",
	outcome: str = "ok",
	channel: str = "",
	reference_doctype: str = "",
	reference_name: str = "",
	detail: str = "",
) -> str:
	"""Insert one immutable evidence row and return its name."""
	row = frappe.get_doc(
		{
			"doctype": "CRM Onboarding Evidence",
			"event": event,
			"outcome": outcome,
			"session_ref": session_ref,
			"subject_ref": subject_ref,
			"channel": channel,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"detail": detail,
		}
	)
	row.insert(ignore_permissions=True)  # SYSTEM-INTERNAL: guest flow writes server-side evidence
	return row.name


class CRMOnboardingEvidence(Document):
	def before_insert(self):
		self.occurred_at = frappe.utils.now_datetime()

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Onboarding evidence is append-only."), frappe.PermissionError)
		detail = frappe.utils.cstr(self.detail).strip()
		if len(detail) > _MAX_DETAIL or _SENSITIVE_RE.search(detail):
			frappe.throw(
				_("Evidence detail must be short and contain no personal data."), frappe.ValidationError
			)
		self.detail = detail

	def on_trash(self):
		frappe.throw(_("Onboarding evidence cannot be deleted."), frappe.PermissionError)
