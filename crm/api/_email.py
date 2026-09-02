"""
crm/api/_email.py — Shared branded transactional-email builder.

All CRM transactional emails (opt-in OTP, contract invitation / OTP / approval)
render through branded_email_html() so every message honours the opt-in network's
logo, display name, primary colour and footer — and stays visually aligned with
the Network opt-in email. Table-based markup for broad email-client support.

The colour helpers here are the single source of truth; crm/api/optin.py keeps
its own local copies for its already-shipped OTP path — new code should import
from here.
"""

from __future__ import annotations

import frappe

DEFAULT_BRAND_COLOUR = "#b91c1c"  # Tiberbu red — used when a network has no colour set


def hex_to_rgba(hex_colour, alpha):
	"""Convert '#RRGGBB' / '#RGB' to 'rgba(r,g,b,alpha)'. Falls back to the brand red."""
	value = frappe.utils.cstr(hex_colour).strip().lstrip("#")
	if len(value) == 3:
		value = "".join(ch * 2 for ch in value)
	try:
		r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
	except (ValueError, IndexError):
		r, g, b = (185, 28, 28)  # DEFAULT_BRAND_COLOUR
	return "rgba(%d,%d,%d,%s)" % (r, g, b, alpha)


def valid_brand_colour(hex_colour):
	"""Return a usable #RRGGBB brand colour, defaulting to the Tiberbu red."""
	value = frappe.utils.cstr(hex_colour).strip()
	if value.startswith("#") and len(value) in (4, 7):
		return value
	return DEFAULT_BRAND_COLOUR


def _header_html(display_name, logo_url, brand):
	if logo_url:
		abs_logo = logo_url if logo_url.startswith("http") else frappe.utils.get_url(logo_url)
		return (
			'<img src="%s" alt="%s" height="44" '
			'style="max-height:44px;width:auto;border:0;outline:none;text-decoration:none" />'
			% (abs_logo, frappe.utils.escape_html(display_name))
		)
	return (
		'<div style="font-size:20px;font-weight:700;color:%s;'
		'font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">%s</div>'
		% (brand, frappe.utils.escape_html(display_name))
	)


def branded_email_html(
	network=None,
	*,
	heading,
	intro_html="",
	highlight_html="",
	cta_label="",
	cta_url="",
	note_html="",
):
	"""
	Build a branded, table-based transactional email.

	network       — CRM Opt-In Network dict (display_name, logo_url, primary_colour,
	                contact_email, footer_legal_name) or None for CareverseHIMS defaults.
	heading       — the bold H1 line (plain text, escaped by caller if needed).
	intro_html    — the introductory paragraph(s) (trusted HTML).
	highlight_html— optional boxed content, e.g. an OTP code block (trusted HTML).
	cta_label/url — optional primary call-to-action button.
	note_html     — optional small-print note below the body (trusted HTML).
	"""
	display_name = (network.get("display_name") if network else "") or "CareverseHIMS"
	logo_url = (network.get("logo_url") if network else "") or ""
	contact_email = (network.get("contact_email") if network else "") or ""
	footer_legal = (network.get("footer_legal_name") if network else "") or ""
	brand = valid_brand_colour(network.get("primary_colour") if network else "")

	header = _header_html(display_name, logo_url, brand)

	highlight_row = ""
	if highlight_html:
		highlight_row = '<tr><td align="center" style="padding:20px 32px 4px">%s</td></tr>' % highlight_html

	cta_row = ""
	if cta_label and cta_url:
		cta_row = (
			'<tr><td align="center" style="padding:22px 32px 4px">'
			'<a href="%s" style="display:inline-block;background:%s;color:#ffffff;'
			"font-size:15px;font-weight:600;text-decoration:none;padding:13px 34px;"
			'border-radius:10px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">%s</a>'
			"</td></tr>" % (cta_url, brand, frappe.utils.escape_html(cta_label))
		)

	note_row = ""
	if note_html:
		note_row = (
			'<tr><td align="center" style="padding:6px 32px 24px">'
			'<p style="margin:0;font-size:12px;color:#9ca3af;line-height:1.5">%s</p>'
			"</td></tr>" % note_html
		)

	help_line = ""
	if contact_email:
		help_line = (
			'<p style="font-size:12px;color:#9ca3af;margin:0 0 6px">Need help? Contact '
			'<a href="mailto:%s" style="color:%s;text-decoration:none">%s</a></p>'
			% (contact_email, brand, contact_email)
		)

	footer_bits = [b for b in (footer_legal, "Powered by Tiberbu Healthnet Solutions") if b]
	footer_line = frappe.utils.escape_html(" · ".join(footer_bits))

	return """\
<div style="background:#f4f5f6;margin:0;padding:24px 12px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">
  <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="width:480px;max-width:480px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(16,24,40,0.08)">
        <tr><td style="height:4px;line-height:4px;font-size:0;background:%(brand)s">&nbsp;</td></tr>
        <tr><td align="center" style="padding:32px 32px 4px">%(header)s</td></tr>
        <tr><td align="center" style="padding:12px 32px 0">
          <h1 style="margin:0;font-size:20px;font-weight:700;color:#111827">%(heading)s</h1>
        </td></tr>
        <tr><td align="center" style="padding:8px 32px 0">
          <div style="margin:0;font-size:14px;line-height:1.5;color:#4b5563">%(intro_html)s</div>
        </td></tr>
        %(highlight_row)s
        %(cta_row)s
        %(note_row)s
        <tr><td style="padding:0 32px"><div style="border-top:1px solid #eceef0;font-size:0;line-height:0">&nbsp;</div></td></tr>
        <tr><td align="center" style="padding:18px 32px 30px">
          %(help_line)s
          <p style="margin:0;font-size:11px;color:#b6bcc4">%(footer_line)s</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>""" % {
		"brand": brand,
		"header": header,
		"heading": frappe.utils.escape_html(heading),
		"intro_html": intro_html,
		"highlight_row": highlight_row,
		"cta_row": cta_row,
		"note_row": note_row,
		"help_line": help_line,
		"footer_line": footer_line,
	}


def otp_code_block(otp, network=None):
	"""Return the boxed OTP-code highlight used inside branded_email_html."""
	brand = valid_brand_colour(network.get("primary_colour") if network else "")
	tint = hex_to_rgba(brand, "0.08")
	return (
		'<div style="display:inline-block;background:%s;border:1px solid %s;border-radius:10px;padding:16px 30px">'
		"<span style=\"font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:34px;"
		'font-weight:700;letter-spacing:8px;color:#111827">%s</span></div>'
		% (tint, brand, frappe.utils.escape_html(otp))
	)


def internal_signatory_reminder_html(
	network=None,
	*,
	signatory_name,
	role,
	facility_label,
	action_url,
	pending_items=None,
):
	"""Render the login-only reminder sent to CRM-user signatories.

	Internal signatories do not receive a public contract invitation.  This
	message deliberately links to the permission-scoped CRM queue instead, so a
	forwarded email cannot expose a contract or bypass the normal CRM session.
	When several contracts are waiting, ``pending_items`` keeps them in one
	readable workload email rather than sending one message per contract.
	"""
	name = frappe.utils.escape_html(signatory_name or "there")
	items = list(pending_items or [])
	if not items:
		items = [{"facility_label": facility_label, "role": role}]

	rows = []
	for item in items:
		if not isinstance(item, dict):
			continue
		facility = frappe.utils.escape_html(item.get("facility_label") or facility_label or "your facility")
		role_label = frappe.utils.escape_html(item.get("role") or role or "signatory")
		contract = frappe.utils.escape_html(item.get("contract") or "")
		contract_ref = (
			"<span style='display:block;color:#9ca3af;font-size:11px;margin-top:2px'>Contract %s</span>"
			% contract
			if contract
			else ""
		)
		rows.append(
			"<li style='margin:0 0 10px;padding:0 0 10px;border-bottom:1px solid #eceef0'>"
			"<strong style='display:block;color:#111827;font-size:14px'>%s</strong>"
			"<span style='display:block;color:#6b7280;font-size:12px;margin-top:2px'>%s</span>%s</li>"
			% (facility, role_label, contract_ref)
		)
	if not rows:
		rows.append(
			"<li style='margin:0;color:#6b7280'>No pending contract details are available. "
			"Open CRM to review your queue.</li>"
		)
	count = len(rows)
	plural = "s" if count != 1 else ""
	workload = (
		"<div style='margin:18px 0 4px;text-align:left;background:#f8fafc;border:1px solid #eceef0;"
		"border-radius:10px;padding:14px 16px'>"
		"<p style='margin:0 0 10px;color:#374151;font-size:12px;font-weight:700;text-transform:uppercase;"
		"letter-spacing:.04em'>Pending workload</p>"
		"<ul style='list-style:none;margin:0;padding:0'>%s</ul></div>" % "".join(rows)
	)
	return branded_email_html(
		network,
		heading="Your approvals are waiting",
		intro_html=(
			"<p style='margin:0 0 6px'>Hello %s,</p>"
			"<p style='margin:0'>You have <strong>%d pending contract approval%s</strong> "
			"in CRM. Sign in to review the quote and complete your secure signature.</p>%s"
			% (name, count, plural, workload)
		),
		cta_label="Open pending approvals",
		cta_url=action_url,
		note_html=(
			"This is a secure CRM reminder; no contract link is included. "
			"You can open the same pending-action list from CRM at any time."
		),
	)
