"""Public OIS invoice checkout and internal payment reconciliation helpers.

The checkout deliberately sits outside the authenticated CRM UI.  A facility
signatory proves access with a short-lived OTP, then receives only submitted,
outstanding invoices belonging to the supplied OIS.  Paystack payments are
verified server-side before a Payment Entry is submitted; bank-transfer reports
create a draft Payment Entry for finance to reconcile and submit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from crm.api._email import OTP_QUEUE_REDACTION, create_transactional_communication, schedule_email_queue_redaction

OTP_TTL_SECONDS = 10 * 60
SESSION_TTL_SECONDS = 30 * 60
MAX_OTP_ATTEMPTS = 5


def _normalise(value: Any) -> str:
	return frappe.utils.cstr(value or "").strip()


def _cache_key(prefix: str, value: str) -> str:
	return "crm_checkout:%s:%s" % (prefix, hashlib.sha256(value.encode()).hexdigest())


def _client_ip() -> str:
	try:
		request = getattr(frappe.local, "request", None)
		return _normalise(request.headers.get("X-Forwarded-For", "").split(",")[0] if request else "") or _normalise(
			getattr(request, "remote_addr", "") if request else ""
		) or "unknown"
	except Exception:
		return "unknown"


def _settings():
	try:
		return frappe.get_single("CRM Finance Settings")
	except Exception:
		return None


def _setting_secret(settings, fieldname):
	if not settings:
		return ""
	try:
		if not frappe.db.has_column("CRM Finance Settings", fieldname):
			return ""
		return settings.get_password(fieldname, raise_exception=False) or ""
	except Exception:
		return ""


def _signing_secret() -> str:
	# Reuse the site's established secret; payment session tokens remain opaque and
	# are never accepted as contract signing tokens.
	try:
		from crm.api.optin import _get_signing_key

		return _get_signing_key()
	except Exception:
		return frappe.conf.get("encryption_key") or ""


def _get_submission(ois_number: str):
	ois_number = _normalise(ois_number)
	if not ois_number or not frappe.db.exists("CRM Opt-In Submission", ois_number):
		return None
	return frappe.get_doc("CRM Opt-In Submission", ois_number)


def _submission_email(submission) -> str:
	return _normalise(getattr(submission, "facility_signatory_email", "") or "").lower()


def _network_for_submission(submission) -> dict:
	if not getattr(submission, "network_slug", None):
		return {}
	rows = frappe.get_list(
		"CRM Opt-In Network",
		filters={"name": submission.network_slug},
		fields=["name", "display_name", "primary_colour", "logo_url"],
		limit_page_length=1,
		ignore_permissions=True,
	)
	return rows[0] if rows else {}


def _send_payment_otp(submission, otp):
	recipient = _submission_email(submission)
	if not recipient:
		return False
	network = _network_for_submission(submission)
	brand = frappe.utils.escape_html(network.get("display_name") or "CareverseHIMS")
	message = (
		"<div style='font-family:Arial,sans-serif;max-width:560px;margin:auto'>"
		"<h2>%s payment verification</h2>"
		"<p>Your one-time code is <strong style='font-size:24px;letter-spacing:4px'>%s</strong>.</p>"
		"<p>This code expires in 10 minutes. If you did not request invoice access, ignore this email.</p>"
		"</div>"
	) % (brand, frappe.utils.escape_html(otp))
	subject = "%s — invoice payment verification code" % (network.get("display_name") or "CareverseHIMS")
	communication = create_transactional_communication(
		"CRM Opt-In Submission",
		submission.name,
		subject=subject,
		content="Payment OTP content redacted from CRM email history.",
		recipients=[recipient],
		links=[("CRM Deal", submission.deal)] if getattr(submission, "deal", None) else None,
	)
	queue = frappe.sendmail(
		recipients=[recipient],
		subject=subject,
		message=message,
		**({"communication": communication} if communication else {}),
		reference_doctype="CRM Opt-In Submission",
		reference_name=submission.name,
		now=True,
	)
	schedule_email_queue_redaction(queue, OTP_QUEUE_REDACTION)
	return True


def _invoice_fields() -> list[str]:
	fields = ["name", "company", "customer", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency"]
	for field in ("crm_optin_submission", "crm_deal", "optin_network", "crm_checkout_reference"):
		try:
			if frappe.db.has_column("Sales Invoice", field):
				fields.append(field)
		except Exception:
			pass
	return fields


def _invoice_rows(submission) -> list[dict]:
	if not submission or getattr(submission, "status", "") != "Processed":
		return []
	filters: list[list[Any]] = [["docstatus", "=", 1], ["outstanding_amount", ">", 0]]
	if frappe.db.has_column("Sales Invoice", "crm_optin_submission"):
		filters.append(["crm_optin_submission", "=", submission.name])
	elif getattr(submission, "deal", None) and frappe.db.has_column("Sales Invoice", "crm_deal"):
		filters.append(["crm_deal", "=", submission.deal])
	else:
		return []
	rows = frappe.get_list(
		"Sales Invoice",
		filters=filters,
		fields=_invoice_fields(),
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
		}
		for row in rows
		if flt(row.outstanding_amount) > 0
	]


def _bank_details() -> dict:
	settings = _settings()
	bank_name = _normalise(getattr(settings, "bank_name", "") if settings else "") or "Gulf African Bank"
	branch = _normalise(getattr(settings, "bank_branch", "") if settings else "") or "UpperHill"
	account_no = _normalise(getattr(settings, "bank_account_number", "") if settings else "") or "0300163301"
	account = _normalise(getattr(settings, "bank_account", "") if settings else "")
	if account and frappe.db.exists("Bank Account", account):
		row = frappe.get_value(
			"Bank Account",
			account,
			["name", "bank", "bank_account_no", "branch_code", "account"],
			as_dict=True,
		)
		if row:
			bank_name = _normalise(row.bank) or bank_name
			account_no = _normalise(row.bank_account_no) or account_no
			branch = _normalise(row.branch_code) or branch
			account = _normalise(row.account) or account
	return {
		"account_name": "TIBERBU HEALTHNET LIMITED",
		"bank": bank_name,
		"account_number": account_no,
		"branch": branch,
		"gl_account": account,
		"currency": "KES",
	}


def _session(token: str) -> dict | None:
	if not token:
		return None
	try:
		value = frappe.cache().get_value(_cache_key("session", token))
		return frappe.parse_json(value) if value else None
	except Exception:
		return None


def _save_session(token: str, payload: dict):
	frappe.cache().set_value(_cache_key("session", token), json.dumps(payload), expires_in_sec=SESSION_TTL_SECONDS)


def _require_session(token: str):
	session = _session(_normalise(token))
	if not session:
		frappe.throw(_("Your payment session has expired. Request a new code."), frappe.PermissionError)
	submission = _get_submission(session.get("ois_number"))
	if not submission or _submission_email(submission) != session.get("email"):
		frappe.throw(_("Your payment session is no longer valid."), frappe.PermissionError)
	return session, submission


@frappe.whitelist(allow_guest=True)
def request_payment_otp(ois_number: Any):
	"""Send an OTP to the facility signatory for an OIS payment session."""
	ois = _normalise(ois_number)
	# Do not disclose whether an OIS exists or has invoices.
	rate_key = _cache_key("otp-rate", "%s:%s" % (ois, _client_ip()))
	count = int(frappe.cache().get_value(rate_key) or 0)
	if count >= 5:
		return {"sent": True, "message": _("If the OIS is eligible, a code was sent to its facility signatory.")}
	frappe.cache().set_value(rate_key, count + 1, expires_in_sec=10 * 60)
	submission = _get_submission(ois)
	email = _submission_email(submission) if submission else ""
	if submission and email and getattr(submission, "status", "") == "Processed":
		otp = "%06d" % secrets.randbelow(1_000_000)
		payload = {"ois_number": submission.name, "email": email, "otp_hash": _hash_otp(otp), "expires_at": int(time.time()) + OTP_TTL_SECONDS, "attempts": 0}
		frappe.cache().set_value(_cache_key("otp", "%s:%s" % (submission.name, email)), json.dumps(payload), expires_in_sec=OTP_TTL_SECONDS)
		try:
			_send_payment_otp(submission, otp)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "CRM checkout OTP delivery failed")
	return {"sent": True, "message": _("If the OIS is eligible, a code was sent to its facility signatory.")}


def _hash_otp(otp: str) -> str:
	return hmac.new((_signing_secret() or "checkout").encode(), otp.encode(), hashlib.sha256).hexdigest()


@frappe.whitelist(allow_guest=True)
def verify_payment_otp(ois_number: Any, otp: Any):
	ois = _normalise(ois_number)
	submission = _get_submission(ois)
	email = _submission_email(submission) if submission else ""
	key = _cache_key("otp", "%s:%s" % (ois, email))
	state = frappe.cache().get_value(key)
	if not state:
		frappe.throw(_("The code is invalid or expired."), frappe.PermissionError)
	state = frappe.parse_json(state)
	state["attempts"] = int(state.get("attempts") or 0) + 1
	if state["attempts"] > MAX_OTP_ATTEMPTS or int(state.get("expires_at") or 0) < int(time.time()):
		frappe.cache().delete_value(key)
		frappe.throw(_("The code is invalid or expired."), frappe.PermissionError)
	if not hmac.compare_digest(state.get("otp_hash", ""), _hash_otp(_normalise(otp))):
		frappe.cache().set_value(key, json.dumps(state), expires_in_sec=max(1, int(state.get("expires_at", 0) - time.time())))
		frappe.throw(_("The code is invalid or expired."), frappe.PermissionError)
	frappe.cache().delete_value(key)
	token = secrets.token_urlsafe(32)
	_save_session(token, {"ois_number": submission.name, "email": email, "issued_at": int(time.time())})
	return {"session_token": token, "network": _network_for_submission(submission), "bank_details": _bank_details(), "invoices": _invoice_rows(submission)}


@frappe.whitelist(allow_guest=True)
def get_payment_checkout(session_token: Any):
	session, submission = _require_session(_normalise(session_token))
	settings = _settings()
	secret = _setting_secret(settings, "paystack_secret_key")
	public = _normalise(getattr(settings, "paystack_public_key", "") if settings else "")
	enabled = bool(cint(getattr(settings, "paystack_enabled", 0))) and bool(secret and public)
	return {
		"ois_number": submission.name,
		"facility_name": _normalise(getattr(submission, "facility_signatory_name", "")) or _("Facility"),
		"network": _network_for_submission(submission),
		"bank_details": _bank_details(),
		"paystack": {"enabled": enabled, "public_key": public if enabled else ""},
		"invoices": _invoice_rows(submission),
	}


def _invoice_for_session(submission, invoice_name):
	return next((row for row in _invoice_rows(submission) if row["name"] == _normalise(invoice_name)), None)


def _paystack_settings():
	settings = _settings()
	secret = _setting_secret(settings, "paystack_secret_key")
	public = _normalise(getattr(settings, "paystack_public_key", "") if settings else "")
	if not secret or not public or not cint(getattr(settings, "paystack_enabled", 0)):
		frappe.throw(_("Paystack is not configured. Use bank transfer or contact finance."), frappe.ConfigurationError)
	return secret, public


def _paystack_request(method, url, secret, **kwargs):
	from frappe.integrations.utils import make_get_request, make_post_request

	kwargs.setdefault("headers", {})["Authorization"] = "Bearer %s" % secret
	kwargs["headers"].setdefault("Cache-Control", "no-cache")
	return (make_get_request if method == "GET" else make_post_request)(url, **kwargs)


@frappe.whitelist(allow_guest=True)
def initialize_paystack_payment(session_token: Any, invoice: Any):
	_, submission = _require_session(_normalise(session_token))
	invoice_row = _invoice_for_session(submission, invoice)
	if not invoice_row:
		frappe.throw(_("That invoice is no longer available for payment."), frappe.ValidationError)
	secret, _ = _paystack_settings()
	reference = "OIS-%s-%s-%s" % (submission.name.replace("/", "-"), invoice_row["name"].replace("/", "-"), secrets.token_hex(5))
	callback = "%s/payment-checkout?ois=%s&reference=%s" % (frappe.utils.get_url(), submission.name, reference)
	response = _paystack_request(
		"POST",
		"https://api.paystack.co/transaction/initialize",
		secret,
		json={
			"email": _submission_email(submission),
			"amount": int(round(flt(invoice_row["amount"]) * 100)),
			"currency": invoice_row["currency"] or "KES",
			"reference": reference,
			"callback_url": callback,
			"metadata": {"ois_number": submission.name, "invoice": invoice_row["name"]},
		},
	)
	if not response or not response.get("status") or not response.get("data", {}).get("authorization_url"):
		frappe.throw(_("Paystack could not start this payment. Try again or use bank transfer."), frappe.ValidationError)
	return {"authorization_url": response["data"]["authorization_url"], "reference": response["data"].get("reference") or reference}


def _payment_entry_for_invoice(invoice_name, amount, *, mode_of_payment=None, reference_no=None, reference_date=None):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	pe = get_payment_entry("Sales Invoice", invoice_name, party_amount=flt(amount))
	pe.flags.ignore_permissions = True
	pe.flags.ignore_mandatory = True
	if mode_of_payment and frappe.db.exists("Mode of Payment", mode_of_payment):
		pe.mode_of_payment = mode_of_payment
	if reference_no:
		pe.reference_no = _normalise(reference_no)
	if reference_date:
		pe.reference_date = getdate(reference_date)
	return pe


def _set_checkout_fields(pe, provider, reference, submission):
	for field, value in {
		"crm_checkout_provider": provider,
		"crm_checkout_reference": reference,
		"crm_optin_submission": submission.name,
	}.items():
		try:
			if frappe.db.has_column("Payment Entry", field):
				pe.set(field, value)
		except Exception:
			continue


def _record_verified_paystack_payment(submission, invoice_row, reference, amount_subunits):
	expected = int(round(flt(invoice_row["amount"]) * 100))
	if int(amount_subunits or 0) != expected:
		frappe.throw(_("The payment amount does not match the invoice balance."), frappe.ValidationError)
	if frappe.db.has_column("Payment Entry", "crm_checkout_reference"):
		existing = frappe.get_list(
			"Payment Entry",
			filters={"crm_checkout_reference": reference},
			fields=["name", "docstatus"],
			limit=1,
			ignore_permissions=True,
		)
		if existing:
			return {"paid": existing[0].docstatus == 1, "payment_entry": existing[0].name, "invoice": invoice_row["name"]}
	pe = _payment_entry_for_invoice(
		invoice_row["name"],
		invoice_row["amount"],
		mode_of_payment="Paystack",
		reference_no=reference,
		reference_date=nowdate(),
	)
	_set_checkout_fields(pe, "Paystack", reference, submission)
	pe.insert(ignore_permissions=True)
	pe.submit()
	return {"paid": True, "payment_entry": pe.name, "invoice": invoice_row["name"]}


@frappe.whitelist(allow_guest=True)
def verify_paystack_payment(session_token: Any, reference: Any):
	_, submission = _require_session(_normalise(session_token))
	secret, _ = _paystack_settings()
	reference = _normalise(reference)
	response = _paystack_request("GET", "https://api.paystack.co/transaction/verify/%s" % reference, secret)
	data = response.get("data") if response else None
	if not response or not response.get("status") or not data or data.get("status") != "success":
		return {"paid": False, "status": data.get("status") if data else "pending"}
	metadata = data.get("metadata") or {}
	if metadata.get("ois_number") != submission.name:
		frappe.throw(_("This payment does not belong to the supplied OIS."), frappe.PermissionError)
	invoice_row = _invoice_for_session(submission, metadata.get("invoice"))
	if not invoice_row:
		frappe.throw(_("The invoice is no longer outstanding."), frappe.ValidationError)
	return _record_verified_paystack_payment(submission, invoice_row, reference, data.get("amount"))


@frappe.whitelist(allow_guest=True)
def paystack_webhook():
	"""Receive Paystack's signed charge.success event for closed-browser payments."""
	secret, _ = _paystack_settings()
	request = getattr(frappe.local, "request", None)
	body = request.get_data() if request else b""
	signature = _normalise(request.headers.get("x-paystack-signature", "") if request else "")
	expected = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
	if not signature or not hmac.compare_digest(signature, expected):
		frappe.throw(_("Invalid payment notification signature."), frappe.PermissionError)
	try:
		event = json.loads(body.decode("utf-8") or "{}")
	except Exception:
		return {"ok": True}
	if event.get("event") != "charge.success":
		return {"ok": True}
	data = event.get("data") or {}
	metadata = data.get("metadata") or {}
	submission = _get_submission(metadata.get("ois_number"))
	if not submission:
		return {"ok": True}
	invoice_row = _invoice_for_session(submission, metadata.get("invoice"))
	if not invoice_row:
		return {"ok": True}
	_record_verified_paystack_payment(submission, invoice_row, _normalise(data.get("reference")), data.get("amount"))
	return {"ok": True}


@frappe.whitelist(allow_guest=True)
def report_bank_transfer(session_token: Any, invoice: Any, reference_no: Any, transfer_date: Any = None, amount: Any = None, notes: Any = None):
	_, submission = _require_session(_normalise(session_token))
	invoice_row = _invoice_for_session(submission, invoice)
	if not invoice_row:
		frappe.throw(_("That invoice is no longer available for payment."), frappe.ValidationError)
	reference_no = _normalise(reference_no)
	if not reference_no:
		frappe.throw(_("Enter the bank transfer reference."), frappe.ValidationError)
	amount = flt(amount or invoice_row["amount"])
	if amount <= 0 or amount > flt(invoice_row["amount"]) + 0.005:
		frappe.throw(_("The transfer amount must not exceed the invoice balance."), frappe.ValidationError)
	if frappe.db.has_column("Payment Entry", "crm_checkout_reference"):
		existing = frappe.get_list("Payment Entry", filters={"crm_checkout_reference": reference_no}, fields=["name", "docstatus"], limit=1, ignore_permissions=True)
		if existing:
			return {"status": "submitted_for_reconciliation", "payment_entry": existing[0].name, "duplicate": True}
	pe = _payment_entry_for_invoice(invoice_row["name"], amount, mode_of_payment="Bank Transfer", reference_no=reference_no, reference_date=transfer_date or nowdate())
	_set_checkout_fields(pe, "Bank Transfer", reference_no, submission)
	if frappe.db.has_column("Payment Entry", "crm_checkout_notes"):
		pe.crm_checkout_notes = _normalise(notes)
	pe.insert(ignore_permissions=True)
	return {"status": "submitted_for_reconciliation", "payment_entry": pe.name, "invoice": invoice_row["name"]}


@frappe.whitelist()
def confirm_bank_transfer(payment_entry: Any, submit: Any = 1):
	"""Finance action: confirm a reported transfer, then submit its draft entry."""
	roles = set(frappe.get_roles(frappe.session.user))
	if frappe.session.user != "Administrator" and not roles.intersection({"System Manager", "Finance Manager", "AR Accountant"}):
		frappe.throw(_("Only finance users can confirm bank transfers."), frappe.PermissionError)
	pe = frappe.get_doc("Payment Entry", _normalise(payment_entry))
	if pe.docstatus == 1:
		return {"name": pe.name, "docstatus": pe.docstatus}
	if pe.docstatus != 0:
		frappe.throw(_("Only draft payment entries can be confirmed."), frappe.ValidationError)
	pe.submit()
	return {"name": pe.name, "docstatus": pe.docstatus}
