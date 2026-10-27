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
	"CareverseHIMS Advanced & Enterprise",
	"Partnership",
	"Something else",
)
MAX_MESSAGE = 2000
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
				# A package buys a number of tokens, not a period of service.
				"tokens": "{:,}".format(int(package.get("token_quantity") or 0)),
			}
		)
	return plans


def get_value_express_offer() -> dict:
	"""Everything the Value Express landing page prices: Flex cards, Fixed tiers, Custom and the calculator."""
	from crm.api.facility_onboarding import _calculator_config, _catalog_packages, _custom_offer
	from crm.utils import value_express as vx
	from crm.utils.token_bonus import WELCOME_BONUS, bonus_settings

	flex = [p for p in _catalog_packages() if p.get("price_ex_vat")]
	tiers = vx.flex_tiers(flex)
	base_rate = tiers[0]["rate"] if tiers else 0
	cards = []
	for package in sorted(flex, key=lambda p: p["price_ex_vat"]):
		try:
			metrics = frappe.parse_json(package.get("coverage_metrics") or "{}") or {}
		except Exception:
			metrics = {}
		rate = vx.per_token_rate(package)
		extra = round((base_rate / rate - 1) * 100) if rate and base_rate else 0
		cards.append(
			{
				"item_code": package["item_code"],
				"name": package.get("display_name") or package["item_code"],
				"description": package.get("description") or "",
				"price": package["price_ex_vat"],
				"currency": package.get("currency") or "KES",
				"tokens": int(package.get("token_quantity") or 0),
				# The business publishes journeys per package; tokens ÷ 40 otherwise.
				"journeys": cstr(metrics.get("journeys")) or vx.journeys(package.get("token_quantity")),
				"rate": rate,
				"more_percent": extra if extra > 0 else 0,
				"recommended": "popular" in cstr(metrics.get("badge")).lower(),
			}
		)
	fixed = []
	for package in sorted(_catalog_packages((vx.FIXED,)), key=lambda p: p.get("price_ex_vat") or 0):
		levels = vx.levels_of(package)
		fixed.append(
			{
				"item_code": package["item_code"],
				"label": levels[0] if levels else package.get("display_name"),
				"levels": levels,
				"price": package.get("price_ex_vat") or 0,
				"currency": package.get("currency") or "KES",
			}
		)
	calculator = _calculator_config()
	return {
		"flex": cards,
		"fixed": fixed,
		"custom": _custom_offer(flex),
		"from_price": cards[0]["price"] if cards else 0,
		"currency": cards[0]["currency"] if cards else "KES",
		"welcome_bonus": bonus_settings()[WELCOME_BONUS],
		"access_tokens": int(calculator.get("monthly_platform_fee") or 0),
		"bill_value_per_token": float(calculator.get("bill_value_per_token") or 0),
		"min_tokens": vx.DEFAULT_MIN_TOKENS,
		"calculator": {
			"access": int(calculator.get("monthly_platform_fee") or 0),
			"bill_value_per_token": float(calculator.get("bill_value_per_token") or 0),
			"avg_bill": float(calculator.get("default_avg_bill") or 0),
			"operating_days": int(calculator.get("default_operating_days") or 0),
			# Value Express is outpatient: inpatient-only service points are not charged.
			"service_points": [
				point for point in calculator.get("service_points") or [] if "opd" in (point.get("applies_to") or ["opd"])
			],
			"presets": calculator.get("presets") or [],
			"packages": [{"name": c["name"], "price": c["price"], "tokens": c["tokens"], "item_code": c["item_code"]} for c in cards],
			"fixed": {f["label"]: f["price"] for f in fixed},
		},
	}


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

	_notify_team(lead.name, full_name, email, phone, organization, topic, message)
	return {"ok": True}


def _notify_team(lead, full_name, email, phone, organization, topic, message):
	"""Email the enquiry to the Contact Email in CRM Opt-In Settings, when one is set."""
	recipient = cstr(frappe.db.get_single_value("CRM Opt-In Settings", "landing_contact_email")).strip()
	if not recipient or not validate_email_address(recipient):
		return
	rows = (
		(_("Name"), full_name),
		(_("Email"), email),
		(_("Phone"), phone),
		(_("Facility or organisation"), organization),
		(_("Topic"), topic),
	)
	details = "".join(
		"<tr><th align='left'>%s</th><td>%s</td></tr>" % (escape_html(label), escape_html(value))
		for label, value in rows
		if value
	)
	try:
		frappe.sendmail(
			recipients=[recipient],
			reply_to=email,
			subject=_("Website enquiry: {0} ({1})").format(topic, full_name),
			message="<table>%s</table><p>%s</p>" % (details, escape_html(message).replace("\n", "<br>")),
			reference_doctype="CRM Lead",
			reference_name=lead,
		)
	except Exception:
		# The Lead and its note already hold the enquiry; a missing mail setup must not lose it.
		frappe.log_error(title="Landing enquiry email", message="lead=%s" % lead)
