"""Public Tiberbu Express landing page: settings, pricing preview and contact form."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cstr, escape_html, getdate, validate_email_address

LEAD_SOURCE = "Website"
NOTE_TITLE = "Landing page enquiry"
CONTACT_TOPICS = (
	"Getting started",
	"Packages and pricing",
	"Request a demo",
	"Partnership",
	"Something else",
)
MAX_MESSAGE = 2000
PERIOD_UNITS = {"Monthly": "month", "Quarterly": "quarter", "Annual": "year"}


def get_landing_settings() -> dict:
	"""Contact and certification details maintained in CRM Opt-In Settings."""
	settings = frappe.get_single("CRM Opt-In Settings")
	phones = [
		line.strip() for line in cstr(settings.get("landing_contact_phones")).splitlines() if line.strip()
	]
	valid_until = settings.get("landing_certificate_valid_until")
	return {
		"certificate_url": cstr(settings.get("landing_certificate_url")).strip(),
		"certificate_id": cstr(settings.get("landing_certificate_id")).strip(),
		"certificate_valid_until": getdate(valid_until).strftime("%B %Y") if valid_until else "",
		"phones": [
			{"label": phone, "tel": "".join(ch for ch in phone if ch.isdigit() or ch == "+")}
			for phone in phones
		],
		"email": cstr(settings.get("landing_contact_email")).strip(),
		"hours": cstr(settings.get("landing_contact_hours")).strip(),
	}


def get_pricing_preview() -> list[dict]:
	"""Read-only view of the public token packages; empty when no price list is configured."""
	from crm.api.facility_onboarding import _catalog_packages

	plans = []
	for package in _catalog_packages():
		try:
			metrics = frappe.parse_json(package.get("coverage_metrics") or "{}") or {}
		except Exception:
			metrics = {}
		plans.append(
			{
				"name": package.get("display_name") or package.get("item_code"),
				"description": package.get("description") or "",
				"audience": cstr(metrics.get("audience")),
				"badge": cstr(metrics.get("badge")),
				"features": [cstr(item) for item in (metrics.get("features") or [])][:5],
				"price": "{:,.0f}".format(package["price_ex_vat"]) if package.get("price_ex_vat") else "",
				"currency": package.get("currency") or "KES",
				"vat_label": package.get("vat_label") or "VAT",
				"period": PERIOD_UNITS.get(package.get("billing_period"), "month"),
			}
		)
	return plans


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60, methods="POST")
def submit_contact(
	full_name=None, email=None, phone=None, organization=None, message=None, topic=None, website=None
):
	"""Turn a landing page enquiry into a CRM Lead with the message as a note."""
	# Honeypot: real visitors never see this field, so a value means a bot.
	if cstr(website).strip():
		return {"ok": True}

	full_name = cstr(full_name).strip()[:140]
	email = cstr(email).strip()[:140]
	phone = cstr(phone).strip()[:30]
	organization = cstr(organization).strip()[:140]
	message = cstr(message).strip()
	topic = cstr(topic).strip()
	if topic not in CONTACT_TOPICS:
		topic = CONTACT_TOPICS[0]

	if not full_name:
		frappe.throw(_("Please tell us your name."))
	if not email or not validate_email_address(email):
		frappe.throw(_("Please enter a valid email address."))
	if not message:
		frappe.throw(_("Please write a message."))
	if len(message) > MAX_MESSAGE:
		frappe.throw(_("Please keep your message under {0} characters.").format(MAX_MESSAGE))

	first_name, _sep, last_name = full_name.partition(" ")
	lead = frappe.get_doc(
		{
			"doctype": "CRM Lead",
			"first_name": first_name,
			"last_name": last_name.strip(),
			"email": email,
			"mobile_no": phone,
			"organization": organization,
			"source": LEAD_SOURCE if frappe.db.exists("CRM Lead Source", LEAD_SOURCE) else None,
			"lead_owner": frappe.db.get_single_value("CRM Opt-In Settings", "default_lead_owner") or None,
		}
	)
	lead.insert(ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "FCRM Note",
			"title": "%s: %s" % (NOTE_TITLE, topic),
			"content": "<p>%s</p>" % escape_html(message).replace("\n", "<br>"),
			"reference_doctype": "CRM Lead",
			"reference_docname": lead.name,
		}
	).insert(ignore_permissions=True)

	return {"ok": True}
