"""
crm/api/optin.py — Self Opt-In Portal API

Story:  optin-s1-1
BRD:    BRD_Customer_Self_Optin.docx  (v1.3)
ADR:    ADR_Customer_Self_Optin.docx

Security model:
- All public endpoints are guest-accessible.
- Identity is proven by email-OTP (OTP sent to registered phone/email from pre-qualified list).
- Further actions gated by a short-lived HMAC signing_token issued on OTP success.
- verify_prequalified reports {matched, rate_limited} so the portal can block an
  unregistered contact on step 1 before sending a code; enumeration is bounded by
  a per-IP rate limit (5 / 10 min) rather than a uniform response.

Rules:
- frappe.get_list() for every SELECT — no frappe.db.sql() SELECTs.
- ignore_permissions=True only on scheduler/system paths — marked # SYSTEM-INTERNAL.
- No f-strings in log/error messages — % formatting only.
- OTP delivery channel is caller-selectable (email or SMS). SMS uses the Frappe
  SMS Settings gateway; if SMS is requested but unavailable (no phone on file or
  no gateway configured), delivery silently falls back to email so a code is
  never dropped. See _dispatch_otp.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import random
import time

import frappe
from frappe import _

VAT_RATE = 0.16

# Static KEPH level → ERPNext item code mapping.
# Matches seed data in patch crm/patches/v1_0/seed_negotiated_price_lists.py (optin-s0-3).
_KEPH_MAP = [
    {"keph_level": "Level 2",  "item_code": "CV-HIMS-KEPH-2"},
    {"keph_level": "Level 3",  "item_code": "CV-HIMS-KEPH-3"},
    {"keph_level": "Level 3A", "item_code": "CV-HIMS-KEPH-3A"},
    {"keph_level": "Level 3B", "item_code": "CV-HIMS-KEPH-3B"},
    {"keph_level": "Level 4",  "item_code": "CV-HIMS-KEPH-4"},
    {"keph_level": "Level 4B", "item_code": "CV-HIMS-KEPH-4B"},
    {"keph_level": "Level 5",  "item_code": "CV-HIMS-KEPH-5"},
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_signing_key():
    """Return the optin_signing_key; auto-generates if absent."""
    settings = frappe.get_single("CRM Opt-In Settings")
    key = settings.get_password("optin_signing_key", raise_exception=False)
    if not key:
        from crm.setup.optin import ensure_signing_key
        ensure_signing_key()
        settings = frappe.get_single("CRM Opt-In Settings")
        key = settings.get_password("optin_signing_key", raise_exception=False)
    if not key:
        frappe.throw("Opt-in signing key not configured.", frappe.ConfigurationError)
    return key


def _get_optin_lead_source():
    """Ensure the source referenced by every Opt-In lead exists on this site."""
    from crm.setup.optin import OPTIN_LEAD_SOURCE, ensure_lead_source

    ensure_lead_source()
    if not frappe.db.exists("CRM Lead Source", OPTIN_LEAD_SOURCE):
        frappe.throw(
            _("The Opt-In lead source could not be configured. Please contact support."),
            frappe.ConfigurationError,
        )
    return OPTIN_LEAD_SOURCE


def _hmac_hex(secret, message):
    """Return HMAC-SHA256 hex digest of message under secret (both str)."""
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def _validate_signing_token(signing_token, email, network_slug, expiry):
    """
    Raise frappe.AuthenticationError if signing_token is invalid or expired.
    expiry is the Unix timestamp embedded in the token (passed as str or int).
    """
    try:
        exp_int = int(expiry)
    except (TypeError, ValueError):
        frappe.throw(_("Invalid session token."), frappe.AuthenticationError)

    if time.time() > exp_int:
        frappe.throw(
            _("Session expired. Please verify your email again."),
            frappe.AuthenticationError,
        )

    key = _get_signing_key()
    msg = "%s:%s:%s" % (email, network_slug, expiry)
    expected = _hmac_hex(key, msg)

    if not hmac.compare_digest(expected, frappe.utils.cstr(signing_token)):
        frappe.throw(_("Invalid session token."), frappe.AuthenticationError)


def _encode_deal_invitation(context):
    """Sign an opaque, time-limited invite that binds an OIS session to one Deal."""
    encoded = base64.urlsafe_b64encode(
        json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = _hmac_hex(_get_signing_key(), "deal-optin:%s" % encoded)
    return "%s.%s" % (encoded, signature)


def _decode_deal_invitation(deal_invitation, network_slug, email=None):
    """Validate and return a Deal OIS invitation context, or None when absent."""
    deal_invitation = frappe.utils.cstr(deal_invitation).strip()
    if not deal_invitation:
        return None
    try:
        encoded, signature = deal_invitation.rsplit(".", 1)
        expected = _hmac_hex(_get_signing_key(), "deal-optin:%s" % encoded)
        if not hmac.compare_digest(expected, signature):
            raise ValueError
        padded = encoded + "=" * (-len(encoded) % 4)
        context = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (AttributeError, TypeError, ValueError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        frappe.throw(_("This Opt-In invitation is invalid."), frappe.AuthenticationError)

    try:
        expiry = int(context.get("expiry") or 0)
    except (AttributeError, TypeError, ValueError):
        expiry = 0
    if (
        not isinstance(context, dict)
        or not context.get("deal")
        or context.get("network_slug") != network_slug
        or time.time() > expiry
    ):
        frappe.throw(_("This Opt-In invitation has expired."), frappe.AuthenticationError)
    if email and frappe.utils.cstr(context.get("email")).lower() != email.lower():
        frappe.throw(_("This invitation is for a different email address."), frappe.AuthenticationError)
    if not frappe.db.exists("CRM Deal", context["deal"]):
        frappe.throw(_("The linked Deal no longer exists."), frappe.AuthenticationError)
    return context


def _deal_invitation_facilities(context):
    """Return the invited Deal's facilities in the public Opt-In facility shape."""
    deal = frappe.get_doc("CRM Deal", context["deal"])
    facilities = []
    for row in deal.get("facilities") or []:
        mfl_code = frappe.utils.cstr(row.get("mfl_code") or "").strip()
        facility_name = frappe.utils.cstr(row.get("facility_name") or "").strip()
        keph_level = frappe.utils.cstr(row.get("facility_level") or "").strip()
        if mfl_code and facility_name and keph_level:
            facilities.append(
                frappe._dict(
                    {
                        "mfl_code": mfl_code,
                        "facility_name": facility_name,
                        "keph_level": keph_level,
                    }
                )
            )
    return facilities


def _deal_invitation_otp_key(deal_invitation):
    return "optin_deal_invite_otp:%s" % hashlib.sha256(
        frappe.utils.cstr(deal_invitation).encode()
    ).hexdigest()


def _keph_to_item_code(keph_level):
    """
    Map a KEPH level string to an ERPNext item code.
    'Level 4' → 'CV-HIMS-KEPH-4', 'Level 3A' → 'CV-HIMS-KEPH-3A'.
    """
    normalized = frappe.utils.cstr(keph_level).strip()
    if normalized.lower().startswith("level "):
        code_part = normalized[6:].strip().upper()
    else:
        code_part = normalized.upper()
    return "CV-HIMS-KEPH-%s" % code_part


def _get_network_doc(network_slug):
    """
    Return the first enabled CRM Opt-In Network row for slug, or None.
    """
    if not network_slug:
        return None
    rows = frappe.get_list(
        "CRM Opt-In Network",
        filters={"slug": network_slug, "enabled": 1},
        fields=[
            "name", "display_name", "logo_url", "primary_colour",
            "contact_email", "footer_legal_name", "price_list_override",
        ],
        limit=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    return rows[0] if rows else None


def _get_partner_logos(network_name):
    """
    Return the partner-logo child rows for a network as a list of dicts
    [{partner_name, logo, website}]. Read via get_list on the child DocType so a
    guest (get_settings is guest-facing) can never trip a read-permission check.
    Absolute URLs are resolved so the same payload works in the browser and in
    email HTML. Never raises.
    """
    if not network_name:
        return []
    try:
        rows = frappe.get_list(
            "CRM Opt-In Partner",
            filters={
                "parent": network_name,
                "parenttype": "CRM Opt-In Network",
                "parentfield": "partner_logos",
            },
            fields=["partner_name", "logo", "website"],
            order_by="idx asc",
            ignore_permissions=True,  # SYSTEM-INTERNAL
        )
    except Exception:
        return []
    logos = []
    for row in rows:
        logo = frappe.utils.cstr(row.get("logo") or "").strip()
        if not logo:
            continue
        abs_logo = logo if logo.startswith("http") else frappe.utils.get_url(logo)
        logos.append({
            "partner_name": frappe.utils.cstr(row.get("partner_name") or "").strip(),
            "logo": abs_logo,
            "website": frappe.utils.cstr(row.get("website") or "").strip(),
        })
    return logos


def _get_membership(email, network_slug):
    """
    Return the first Active CRM Facility Membership for this email+network,
    with its parent facility facts. Returns None if not found.
    """
    mem_rows = frappe.get_list(
        "CRM Facility Membership",
        filters={
            "contact_email": email,
            "network": network_slug,
            "status": "Active",
        },
        fields=["name", "parent", "contact_name", "contact_phone", "otp_expiry", "otp_attempts"],
        limit=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if not mem_rows:
        return None
    mem = mem_rows[0]
    # Fetch facility facts from parent
    fac_rows = frappe.get_list(
        "CRM Pre-Qualified Facility",
        filters={"name": mem.parent},
        fields=["name", "mfl_code", "facility_name", "keph_level"],
        limit=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if not fac_rows:
        return None
    fac = fac_rows[0]
    return frappe._dict({
        "membership_name": mem.name,
        "facility_name_ref": fac.name,  # parent facility docname
        "mfl_code": fac.mfl_code,
        "facility_name": fac.facility_name,
        "keph_level": fac.keph_level,
        "contact_name": mem.contact_name,
        "contact_email": email,
        "contact_phone": mem.contact_phone,
        "otp_expiry": mem.otp_expiry,
        "otp_attempts": mem.otp_attempts,
    })


def _get_all_memberships(email, network_slug):
    """Return all Active facilities for this email+network as a list of dicts."""
    mem_rows = frappe.get_list(
        "CRM Facility Membership",
        filters={
            "contact_email": email,
            "network": network_slug,
            "status": "Active",
        },
        fields=["name", "parent"],
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if not mem_rows:
        return []
    parent_names = [m.parent for m in mem_rows if m.parent]
    fac_rows = frappe.get_list(
        "CRM Pre-Qualified Facility",
        filters={"name": ["in", parent_names]},
        fields=["name", "mfl_code", "facility_name", "keph_level"],
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    return fac_rows


def _get_quoted_facility_map(mfl_codes):
    """Map each mfl_code that is ALREADY linked to a CRM Deal carrying a quote
    to that deal's name. Used to lock such facilities out of re-quoting on the
    wizard. There is no relational link between a pre-qualified facility and a
    deal, so correlation is by mfl_code value against CRM Deal Facility rows,
    then filtered to deals that actually have an ERPNext Quotation.

    Returns {mfl_code: deal_name}. Guest/system path — ignore_permissions.
    """
    codes = [c for c in {frappe.utils.cstr(m).strip() for m in (mfl_codes or [])} if c]
    if not codes:
        return {}

    # 1. Deal-facility rows carrying these MFL codes → their parent deals
    deal_rows = frappe.get_list(
        "CRM Deal Facility",
        filters={"mfl_code": ["in", codes], "parenttype": "CRM Deal"},
        fields=["mfl_code", "parent"],
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    deal_names = list({r.parent for r in deal_rows if r.parent})
    if not deal_names:
        return {}

    # 2. Keep only deals that have at least one quote
    quoted_deals = {
        q.crm_deal
        for q in frappe.get_list(
            "Quotation",
            filters={"crm_deal": ["in", deal_names]},
            fields=["crm_deal"],
            ignore_permissions=True,  # SYSTEM-INTERNAL
        )
        if q.crm_deal
    }
    if not quoted_deals:
        return {}

    # 3. First quoted deal wins per MFL code
    result = {}
    for r in deal_rows:
        if r.parent in quoted_deals and r.mfl_code not in result:
            result[r.mfl_code] = r.parent
    return result


def _get_client_ip():
    """Return the remote IP for rate-limiting. Degrades gracefully in non-request contexts."""
    try:
        return frappe.local.request_ip or "unknown"
    except AttributeError:
        pass
    try:
        env = frappe.request.environ
        forwarded = env.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return env.get("REMOTE_ADDR", "unknown")
    except Exception:
        return "unknown"


def _get_job_progress(submission_ref):
    """Read optional Redis-backed progress without affecting the submission workflow."""
    try:
        raw = frappe.cache().get_value("optin_job:%s" % submission_ref)
        return json.loads(raw) if raw else None
    except Exception:
        # Redis is only a progress transport. The submission record is the
        # source of truth and must remain usable when Redis is unavailable.
        return None


def _set_job_progress(submission_ref, data):
    """Write optional guest progress and never make a CRM workflow depend on it."""
    try:
        frappe.cache().set_value(
            "optin_job:%s" % submission_ref,
            json.dumps(data),
            expires_in_sec=3600,
        )
        return True
    except Exception:
        try:
            frappe.log_error(
                frappe.get_traceback(),
                "optin: progress cache unavailable for %s" % submission_ref,
            )
        except Exception:
            pass
        return False


def _update_job_step(submission_ref, name, status, label):
    """Upsert a best-effort guest progress entry for one background step."""
    data = _get_job_progress(submission_ref) or {}
    steps = [s for s in data.get("steps", []) if s.get("name") != name]
    steps.append({"name": name, "status": status, "label": label})
    data["steps"] = steps
    _set_job_progress(submission_ref, data)


def _mark_active_job_step_failed(submission_ref):
    """Turn the visible in-progress step into a safe failed state for the guest."""
    data = _get_job_progress(submission_ref) or {}

    steps = data.get("steps") or []
    active_step = next(
        (step for step in reversed(steps) if step.get("status") == "in_progress"), None
    )
    if active_step:
        active_step["status"] = "failed"
        active_step["label"] = _("We could not complete this step.")
    else:
        steps.append(
            {
                "name": "lead",
                "status": "failed",
                "label": _("We could not start this submission."),
            }
        )
    data["steps"] = steps
    _set_job_progress(submission_ref, data)


def _public_submission_failure_message(submission_ref):
    """Return an actionable, non-sensitive failure message for a guest submitter."""
    return _(
        "We could not finish this Opt-In submission. It has been saved for our team to review. "
        "Please contact support and quote reference {0}."
    ).format(submission_ref)


def _reset_submission_progress(submission_ref):
    """Reset guest-visible progress before a synchronous processing run."""
    _set_job_progress(
        submission_ref,
        {"steps": [], "overall": "in_progress", "lead_id": None},
    )


def _prepare_submission_payload(
    payload, signing_token, email, network_slug, expiry, deal_invitation=None
):
    """Validate a completed wizard payload and replace client pricing with server pricing.

    The browser can only request the facilities that belong to its signed session;
    the server remains the authority for the actual facilities, item codes and
    locked prices.  Rejecting an invalid or stale selection here means the person
    can correct it in the wizard instead of receiving a generic background-job
    failure after their submission has been staged.
    """
    if not isinstance(payload, dict):
        frappe.throw(_("Invalid submission payload."), frappe.ValidationError)

    contact = payload.get("contact")
    if not isinstance(contact, dict):
        frappe.throw(_("Please return to your contact details and try again."), frappe.ValidationError)

    contact_email = frappe.utils.cstr(contact.get("email") or "").strip().lower()
    if contact_email != email:
        frappe.throw(
            _("Your email address changed. Please verify the updated address before submitting."),
            frappe.ValidationError,
        )

    witness = payload.get("witness")
    if not isinstance(witness, dict):
        frappe.throw(_("Please add your facility witness before submitting."), frappe.ValidationError)
    witness_name = frappe.utils.cstr(witness.get("name") or "").strip()
    witness_email = frappe.utils.cstr(witness.get("email") or "").strip().lower()
    if not witness_name or frappe.utils.validate_email_address(witness_email) != witness_email:
        frappe.throw(
            _("Please provide a valid name and email address for your facility witness."),
            frappe.ValidationError,
        )

    requested_codes = []
    for facility in payload.get("facilities") or []:
        if not isinstance(facility, dict):
            continue
        mfl_code = frappe.utils.cstr(facility.get("mfl_code") or "").strip()
        if mfl_code:
            requested_codes.append(mfl_code)

    if not requested_codes:
        frappe.throw(_("Select at least one facility before submitting."), frappe.ValidationError)
    if len(set(requested_codes)) != len(requested_codes):
        frappe.throw(_("Each selected facility must appear only once."), frappe.ValidationError)

    pricing_result = get_pricing(
        signing_token,
        email,
        network_slug,
        expiry,
        requested_codes,
        deal_invitation,
    )
    pricing = pricing_result.get("facilities") or []
    priced_codes = {
        frappe.utils.cstr(row.get("mfl_code") or "").strip()
        for row in pricing
        if row.get("mfl_code")
    }
    if set(requested_codes) != priced_codes:
        frappe.throw(
            _("One or more selected facilities are no longer available. Please review your selection."),
            frappe.ValidationError,
        )

    invalid_rows = [
        row
        for row in pricing
        if not row.get("item_code")
        or not frappe.db.exists("Item", {"name": row.get("item_code"), "disabled": 0})
    ]
    if invalid_rows:
        frappe.throw(
            _("Pricing is temporarily unavailable for one or more selected facilities. Please contact support."),
            frappe.ValidationError,
        )

    default_company = frappe.db.get_single_value("Global Defaults", "default_company")
    if not default_company or not frappe.db.exists("Company", default_company):
        frappe.throw(
            _("Opt-In is temporarily unavailable. Please contact support."),
            frappe.ConfigurationError,
        )

    if not payload.get("terms_accepted") or not payload.get("tc_doc_name") or not payload.get("tc_doc_hash"):
        frappe.throw(
            _("Please review and accept the Terms and Conditions before submitting."),
            frappe.ValidationError,
        )

    # Store canonical facility and price data, never the browser's editable copy.
    payload["contact"] = contact
    payload["witness"] = {"name": witness_name, "email": witness_email}
    payload["facilities"] = [
        {
            "mfl_code": row.get("mfl_code"),
            "facility_name": row.get("facility_name"),
            "keph_level": row.get("keph_level"),
        }
        for row in pricing
    ]
    payload["pricing"] = pricing
    return payload


def _get_optin_deal_forecast_fields(pricing):
    """Build the mandatory Deal forecast fields from the accepted Opt-In pricing."""
    expected_deal_value = round(
        sum(frappe.utils.flt(product.get("annual_kes")) for product in pricing or []), 2
    )
    if expected_deal_value <= 0:
        frappe.throw(
            _("Opt-In pricing must be greater than zero. Please contact support."),
            frappe.ValidationError,
        )
    return {
        "expected_deal_value": expected_deal_value,
        "expected_closure_date": frappe.utils.add_days(frappe.utils.today(), 30),
    }


def _get_or_create_submission_contact(lead):
    """Reuse a Contact by email so a retry never fails on a duplicate person."""
    existing_name = ""
    if lead.email:
        existing_name = frappe.db.get_value("Contact Email", {"email_id": lead.email}, "parent") or ""
    if existing_name and frappe.db.exists("Contact", existing_name):
        return existing_name

    contact_doc = frappe.new_doc("Contact")
    contact_doc.first_name = lead.first_name or lead.organization or "Contact"
    contact_doc.last_name = lead.last_name or ""
    if lead.email:
        contact_doc.append("email_ids", {"email_id": lead.email, "is_primary": 1})
    if lead.mobile_no:
        contact_doc.append("phone_nos", {"phone": lead.mobile_no, "is_primary_mobile_no": 1})
    contact_doc.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
    return contact_doc.name


def _get_or_create_submission_organization(lead, submission_ref):
    """Return the organisation for a submission, reusing its stable display name."""
    organization_name = lead.organization or lead.email or ("Org-%s" % submission_ref)
    existing_name = frappe.db.get_value(
        "CRM Organization", {"organization_name": organization_name}, "name"
    )
    if existing_name:
        return existing_name

    organization = frappe.new_doc("CRM Organization")
    organization.organization_name = organization_name
    organization.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
    return organization.name


DEFAULT_BRAND_COLOUR = "#b91c1c"  # Tiberbu red — used when a network has no colour set


def _hex_to_rgba(hex_colour, alpha):
    """Convert '#RRGGBB' / '#RGB' to 'rgba(r,g,b,alpha)'. Falls back to the brand red."""
    value = frappe.utils.cstr(hex_colour).strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    try:
        r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        r, g, b = (185, 28, 28)  # DEFAULT_BRAND_COLOUR
    return "rgba(%d,%d,%d,%s)" % (r, g, b, alpha)


def _valid_brand_colour(hex_colour):
    """Return a usable #RRGGBB brand colour, defaulting to the Tiberbu red."""
    value = frappe.utils.cstr(hex_colour).strip()
    if value.startswith("#") and len(value) in (4, 7):
        return value
    return DEFAULT_BRAND_COLOUR


def _otp_email_html(otp, network):
    """
    Build a professional, brand-aware OTP email (table-based layout for broad email-client
    support). Honours the opt-in network's logo, display name, primary colour, and footer.
    """
    display_name = (network.get("display_name") if network else "") or "CareverseHIMS"
    logo_url = (network.get("logo_url") if network else "") or ""
    contact_email = (network.get("contact_email") if network else "") or ""
    footer_legal = (network.get("footer_legal_name") if network else "") or ""
    brand = _valid_brand_colour(network.get("primary_colour") if network else "")
    tint = _hex_to_rgba(brand, "0.08")

    if logo_url:
        abs_logo = logo_url if logo_url.startswith("http") else frappe.utils.get_url(logo_url)
        header = (
            '<img src="%s" alt="%s" height="44" '
            'style="max-height:44px;width:auto;border:0;outline:none;text-decoration:none" />'
            % (abs_logo, frappe.utils.escape_html(display_name))
        )
    else:
        header = (
            '<div style="font-size:20px;font-weight:700;color:%s;'
            'font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">%s</div>'
            % (brand, frappe.utils.escape_html(display_name))
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
          <h1 style="margin:0;font-size:20px;font-weight:700;color:#111827">Verify your email</h1>
        </td></tr>
        <tr><td align="center" style="padding:8px 32px 0">
          <p style="margin:0;font-size:14px;line-height:1.5;color:#4b5563">
            Use the code below to continue your CareverseHIMS opt-in for
            <strong style="color:#111827">%(display_name)s</strong>.
          </p>
        </td></tr>
        <tr><td align="center" style="padding:20px 32px 4px">
          <div style="display:inline-block;background:%(tint)s;border:1px solid %(brand)s;border-radius:10px;padding:16px 30px">
            <span style="font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:34px;font-weight:700;letter-spacing:8px;color:#111827">%(otp)s</span>
          </div>
        </td></tr>
        <tr><td align="center" style="padding:12px 32px 0">
          <p style="margin:0;font-size:13px;color:#6b7280">This code expires in <strong>10 minutes</strong>.</p>
        </td></tr>
        <tr><td align="center" style="padding:6px 32px 24px">
          <p style="margin:0;font-size:12px;color:#9ca3af;line-height:1.5">
            Didn't request this? You can safely ignore this email — your account stays secure.
          </p>
        </td></tr>
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
        "tint": tint,
        "header": header,
        "display_name": frappe.utils.escape_html(display_name),
        "otp": frappe.utils.escape_html(otp),
        "help_line": help_line,
        "footer_line": footer_line,
    }


def _send_otp_email(contact_email, otp, network=None):
    """
    Send the branded OTP verification email. The code is placed in the subject line
    (e.g. "Your Verification Code - 101783") so it is visible before the email is opened.
    Invoked via frappe.enqueue — not whitelisted.
    """
    frappe.sendmail(
        recipients=[contact_email],
        subject="Your Verification Code - %s" % otp,
        message=_otp_email_html(otp, network),
        now=True,
    )


def _sms_gateway_configured():
    """True if an SMS Settings gateway URL is set — else send_sms would silently no-op."""
    try:
        return bool(frappe.db.get_single_value("SMS Settings", "sms_gateway_url"))
    except Exception:
        return False


def _send_otp_sms(contact_phone, otp, brand_name="CareverseHIMS"):
    """Send OTP via the configured SMS gateway. Invoked via frappe.enqueue — not whitelisted."""
    from frappe.core.doctype.sms_settings.sms_settings import send_sms

    msg = (
        "Your %s verification code is %s. "
        "It expires in 10 minutes. Do not share it." % (brand_name, otp)
    )
    # success_msg=False suppresses the desk msgprint — this runs headless for a guest.
    send_sms([contact_phone], msg, success_msg=False)


def _dispatch_otp(channel, contact_email, contact_phone, otp, network_slug=None):
    """
    Background OTP dispatcher. Delivers via the requested channel, falling back to
    email so a code is never silently dropped:
      - channel="sms" + phone on file + gateway configured  → SMS
      - anything else (incl. SMS send failure)               → email
    Both channels are branded with the opt-in network's identity.
    Invoked via frappe.enqueue — not whitelisted.
    """
    network = _get_network_doc(network_slug) if network_slug else None
    brand_name = (network.get("display_name") if network else "") or "CareverseHIMS"

    if channel == "sms" and contact_phone and _sms_gateway_configured():
        try:
            _send_otp_sms(contact_phone, otp, brand_name)
            return
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "optin._dispatch_otp: SMS send failed, falling back to email",
            )
    if contact_email:
        _send_otp_email(contact_email, otp, network)


def _require_optin_manager():
    """Restrict internal Opt-In handoffs to the users who can negotiate pricing."""
    user = frappe.session.user
    roles = frappe.get_roles(user)
    if not (
        "System Manager" in roles
        or user == "Administrator"
        or "Sales Manager" in roles
    ):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


def _quote_pricing_rows(quote):
    """Shape the finalized quotation lines for Opt-In summary and contract rendering."""
    rows = []
    for item in quote.items or []:
        annual_kes = float(item.amount or (item.qty or 0) * (item.rate or 0))
        rows.append(
            {
                "facility_name": frappe.utils.cstr(
                    item.get("facility_name") or item.item_name or item.item_code
                ).strip(),
                "mfl_code": "",
                "keph_level": frappe.utils.cstr(item.get("package_tier") or "").strip(),
                "item_code": frappe.utils.cstr(item.item_code or "").strip(),
                "monthly_kes": round(annual_kes / 12, 2),
                "annual_kes": annual_kes,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Public whitelisted API
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def get_settings(network_slug, deal_invitation=None):
    """
    Return network branding config, default price list, and KEPH item-code map.
    Unknown or disabled slug returns default Tiberbu config — never errors.
    """
    network_slug = frappe.utils.cstr(network_slug).strip()

    try:
        settings = frappe.get_single("CRM Opt-In Settings")
        default_price_list = settings.default_price_list or "Negotiated Year 1"
    except Exception:
        default_price_list = "Negotiated Year 1"

    invitation = _decode_deal_invitation(deal_invitation, network_slug)
    network_doc = _get_network_doc(network_slug)

    if network_doc:
        network_config = {
            "display_name": network_doc.get("display_name") or "",
            "logo_url": network_doc.get("logo_url") or "",
            "primary_colour": network_doc.get("primary_colour") or "",
            "contact_email": network_doc.get("contact_email") or "",
            "footer_legal_name": network_doc.get("footer_legal_name") or "",
            "partner_logos": _get_partner_logos(network_doc.get("name")),
        }
        price_list = (
            invitation.get("price_list")
            if invitation
            else network_doc.get("price_list_override") or default_price_list
        )
    else:
        network_config = {
            "display_name": "CareverseHIMS",
            "logo_url": "",
            "primary_colour": "",
            "contact_email": "",
            "footer_legal_name": "Tiberbu Healthnet Solutions",
            "partner_logos": [],
        }
        price_list = invitation.get("price_list") if invitation else default_price_list

    result = {
        "network_config": network_config,
        "default_price_list": price_list,
        "keph_map": _KEPH_MAP,
    }
    if invitation:
        deal = frappe.get_doc("CRM Deal", invitation["deal"])
        result["deal_invitation"] = {
            "contact": {
                "first_name": deal.get("first_name") or "",
                "last_name": deal.get("last_name") or "",
                "email": invitation["email"],
                "mobile_no": deal.get("mobile_no") or "",
                "organisation": deal.get("organization_name") or deal.get("organization") or "",
            },
            "facility_count": len(_deal_invitation_facilities(invitation)),
        }
    return result


@frappe.whitelist(allow_guest=True)
def verify_prequalified(email, network_slug, channel="email", deal_invitation=None):
    """
    Check email against pre-qualified list for this network.
    If matched: generate OTP, store HMAC on record, dispatch OTP via the chosen
    channel ("email" or "sms"). SMS falls back to email when unavailable.

    Returns {matched: bool, rate_limited: bool} so the portal can show a loud
    "not a registered contact" state on step 1 before any code is sent. This is a
    deliberate product decision — enumeration is bounded by the per-IP rate limit
    (5 calls / 10 minutes), which returns {rate_limited: true} rather than a match
    verdict once tripped.
    """
    email = frappe.utils.cstr(email).strip().lower()
    network_slug = frappe.utils.cstr(network_slug).strip()
    channel = frappe.utils.cstr(channel).strip().lower()
    if channel not in ("email", "sms"):
        channel = "email"

    # Rate limiting — keyed on client IP, 5 attempts per 10 minutes
    client_ip = _get_client_ip()
    rate_key = "optin_rate_vp:%s" % client_ip
    call_count = int(frappe.cache().get_value(rate_key) or 0)
    if call_count >= 5:
        return {"matched": False, "rate_limited": True}
    frappe.cache().set_value(rate_key, call_count + 1, expires_in_sec=600)

    invitation = _decode_deal_invitation(deal_invitation, network_slug, email)
    record = _get_membership(email, network_slug) if not invitation else None
    if not record and not invitation:
        return {"matched": False, "rate_limited": False}
    if invitation and not _deal_invitation_facilities(invitation):
        frappe.throw(
            _("The linked Deal needs at least one facility with an MFL code, name, and KEPH level."),
            frappe.ValidationError,
        )

    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))
    key = _get_signing_key()
    otp_hash = _hmac_hex(key, otp)
    otp_expiry = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=10)

    if invitation:
        frappe.cache().set_value(
            _deal_invitation_otp_key(deal_invitation),
            json.dumps({"otp_hash": otp_hash, "otp_expiry": str(otp_expiry), "otp_attempts": 0}),
            expires_in_sec=600,
        )
        contact_phone = frappe.get_doc("CRM Deal", invitation["deal"]).get("mobile_no") or ""
    else:
        # Persist OTP hash on the membership record
        mem_doc = frappe.get_doc("CRM Facility Membership", record.membership_name)
        mem_doc.otp_hash = otp_hash
        mem_doc.otp_expiry = otp_expiry
        mem_doc.otp_attempts = 0
        mem_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
        frappe.db.commit()
        contact_phone = record.contact_phone

    # Dispatch OTP via the requested channel. A single enqueue on both matched and
    # unmatched paths keeps timing equal, removing the side-channel that would reveal
    # whether a record was found. _dispatch_otp falls back to email if SMS is
    # unavailable (no phone / no gateway) so a code is never dropped.
    frappe.enqueue(
        "crm.api.optin._dispatch_otp",
        channel=channel,
        contact_email=email,
        contact_phone=contact_phone,
        otp=otp,
        network_slug=network_slug,
        queue="short",
        timeout=30,
    )

    return {"matched": True, "rate_limited": False}


@frappe.whitelist(allow_guest=True)
def verify_otp(email, network_slug, otp, deal_invitation=None):
    """
    Validate OTP. On success: clear OTP, issue signing_token, return facility list.
    Raises frappe.AuthenticationError on wrong OTP, too many attempts, or expiry.
    """
    email = frappe.utils.cstr(email).strip().lower()
    network_slug = frappe.utils.cstr(network_slug).strip()
    otp = frappe.utils.cstr(otp).strip()

    invitation = _decode_deal_invitation(deal_invitation, network_slug, email)
    record = _get_membership(email, network_slug) if not invitation else None
    if not record and not invitation:
        frappe.throw(_("Verification failed."), frappe.AuthenticationError)

    if invitation:
        cache_key = _deal_invitation_otp_key(deal_invitation)
        raw_otp = frappe.cache().get_value(cache_key)
        try:
            otp_state = json.loads(raw_otp) if raw_otp else {}
        except json.JSONDecodeError:
            otp_state = {}
        if (
            not otp_state
            or int(otp_state.get("otp_attempts") or 0) >= 3
            or not otp_state.get("otp_expiry")
            or frappe.utils.now_datetime() > frappe.utils.get_datetime(otp_state["otp_expiry"])
        ):
            frappe.throw(_("Verification failed."), frappe.AuthenticationError)

        otp_state["otp_attempts"] = int(otp_state.get("otp_attempts") or 0) + 1
        frappe.cache().set_value(cache_key, json.dumps(otp_state), expires_in_sec=600)
        stored_hash = otp_state.get("otp_hash") or ""
    else:
        # Load full doc so we can read/write OTP fields including the Password field
        pqf = frappe.get_doc("CRM Facility Membership", record.membership_name)

        # 1. Lockout check — before any DB write
        if (pqf.otp_attempts or 0) >= 3:
            frappe.throw(_("Verification failed."), frappe.AuthenticationError)

        # 2. Expiry check — before incrementing attempts (no state mutation on expired codes)
        if not pqf.otp_expiry or frappe.utils.now_datetime() > pqf.otp_expiry:
            frappe.throw(_("Verification failed."), frappe.AuthenticationError)

        # 3. Increment attempt counter before validating (prevents brute-force)
        pqf.otp_attempts = (pqf.otp_attempts or 0) + 1
        pqf.save(ignore_permissions=True)  # SYSTEM-INTERNAL
        frappe.db.commit()

        stored_hash = pqf.get_password("otp_hash", raise_exception=False) or ""

    # 4. Validate HMAC — constant-time comparison
    key = _get_signing_key()
    expected_hash = _hmac_hex(key, otp)

    if not hmac.compare_digest(stored_hash, expected_hash):
        frappe.throw(_("Verification failed."), frappe.AuthenticationError)

    if invitation:
        frappe.cache().delete_value(_deal_invitation_otp_key(deal_invitation))
    else:
        # OTP valid — clear hash and reset counter
        pqf.otp_hash = ""
        pqf.otp_attempts = 0
        pqf.save(ignore_permissions=True)  # SYSTEM-INTERNAL
        frappe.db.commit()

    # Issue signing token valid for 2 hours
    expiry = int(time.time()) + 7200
    msg = "%s:%s:%s" % (email, network_slug, expiry)
    signing_token = _hmac_hex(key, msg)

    all_records = (
        _deal_invitation_facilities(invitation)
        if invitation
        else _get_all_memberships(email, network_slug)
    )
    quoted_map = {} if invitation else _get_quoted_facility_map([r.mfl_code for r in all_records])
    facilities = [
        {
            "mfl_code": r.mfl_code,
            "facility_name": r.facility_name,
            "keph_level": r.keph_level,
            "already_quoted": bool(quoted_map.get(r.mfl_code)),
            "quoted_deal": quoted_map.get(r.mfl_code),
        }
        for r in all_records
    ]

    return {
        "signing_token": signing_token,
        "expiry": expiry,
        "facilities": facilities,
    }


@frappe.whitelist(allow_guest=True)
def get_pricing(signing_token, email, network_slug, expiry, selected_mfl_codes, deal_invitation=None):
    """
    Compute KEPH-based pricing for selected MFL codes.
    Validates signing_token before any data access.
    Returns per-facility pricing + monthly and annual totals incl. 16% VAT.
    """
    signing_token = frappe.utils.cstr(signing_token)
    email = frappe.utils.cstr(email).strip().lower()
    network_slug = frappe.utils.cstr(network_slug).strip()

    _validate_signing_token(signing_token, email, network_slug, expiry)
    invitation = _decode_deal_invitation(deal_invitation, network_slug, email)

    if isinstance(selected_mfl_codes, str):
        try:
            selected_mfl_codes = json.loads(selected_mfl_codes)
        except Exception:
            selected_mfl_codes = []

    # Determine price list (network override or default)
    network_doc = _get_network_doc(network_slug)
    try:
        settings = frappe.get_single("CRM Opt-In Settings")
        default_pl = settings.default_price_list or "Negotiated Year 1"
    except Exception:
        default_pl = "Negotiated Year 1"
    price_list = (
        invitation.get("price_list")
        if invitation
        else (network_doc.get("price_list_override") if network_doc else None) or default_pl
    )
    if not frappe.db.exists("Price List", {"name": price_list, "selling": 1, "enabled": 1}):
        frappe.throw(
            _("Pricing is temporarily unavailable. Please contact support."),
            frappe.ConfigurationError,
        )

    # Build MFL → facility info map from pre-qualified records via membership child table
    all_records = (
        _deal_invitation_facilities(invitation)
        if invitation
        else _get_all_memberships(email, network_slug)
    )
    facility_map = {r.mfl_code: r for r in all_records if r.mfl_code}

    # Defence-in-depth: facilities already linked+quoted to a deal are locked out
    # of re-quoting on the wizard UI; enforce the same server-side.
    quoted_map = {} if invitation else _get_quoted_facility_map(list(facility_map.keys()))

    result_facilities = []
    subtotal_monthly = 0.0
    subtotal_annual = 0.0

    for mfl_code in selected_mfl_codes:
        mfl_code = frappe.utils.cstr(mfl_code)
        fac = facility_map.get(mfl_code)
        if not fac or quoted_map.get(mfl_code):
            continue

        item_code = _keph_to_item_code(fac.keph_level)

        price_rows = frappe.get_list(
            "Item Price",
            filters={"item_code": item_code, "price_list": price_list, "selling": 1},
            fields=["price_list_rate"],
            limit=1,
            ignore_permissions=True,  # SYSTEM-INTERNAL
        )
        if not price_rows:
            frappe.throw(
                _("Pricing is temporarily unavailable for one or more selected facilities. Please contact support."),
                frappe.ConfigurationError,
            )
        monthly_kes = float(price_rows[0].price_list_rate)
        annual_kes = round(monthly_kes * 12, 2)

        result_facilities.append({
            "mfl_code": mfl_code,
            "facility_name": fac.facility_name,
            "keph_level": fac.keph_level,
            "item_code": item_code,
            "monthly_kes": monthly_kes,
            "annual_kes": annual_kes,
        })
        subtotal_monthly += monthly_kes
        subtotal_annual += annual_kes

    subtotal_monthly = round(subtotal_monthly, 2)
    subtotal_annual = round(subtotal_annual, 2)
    vat_monthly = round(subtotal_monthly * VAT_RATE, 2)
    vat_annual = round(subtotal_annual * VAT_RATE, 2)
    grand_total_monthly = round(subtotal_monthly + vat_monthly, 2)
    grand_total_annual = round(subtotal_annual + vat_annual, 2)

    return {
        "facilities": result_facilities,
        "subtotal_monthly": subtotal_monthly,
        "vat_monthly": vat_monthly,
        "grand_total_monthly": grand_total_monthly,
        "subtotal_annual": subtotal_annual,
        "vat_annual": vat_annual,
        "grand_total_annual": grand_total_annual,
    }


def _fmt_kes(value):
    """Format a number as a KES amount with thousands separators, e.g. 12000 -> '12,000.00'."""
    try:
        return "{:,.2f}".format(float(value or 0))
    except (TypeError, ValueError):
        return "0.00"


def _build_pricing_table(facilities):
    """
    Pre-render the per-facility pricing table as a safe HTML string.

    The T&C is stored in a Text Editor field whose sanitiser strips Jinja {% for %}
    block tags, so the table cannot be looped in the template — it is built here and
    injected via the {{ pricing_table }} expression instead. See
    crm.setup.optin._default_terms_template.

    Styling is theme-NEUTRAL on purpose: only structure (padding, borders, weight,
    alignment) is inlined; text colour is inherited from whatever renders the table.
    That keeps it readable standalone in the contract PDF/print format (dark text on
    white) AND inside the portal's dark-mode T&C panel (light text on dark), while the
    portal's UI layer (StepTerms.vue :deep()) can refine it further. Inline colours
    would win over that CSS and break dark mode, so they are deliberately omitted.
    """
    # Shared, colour-free cell styles (translucent greys read fine on any background).
    cell = "padding:8px 11px;border-bottom:1px solid rgba(128,128,128,0.2);"
    amt = cell + "font-weight:700;white-space:nowrap;"
    th = (
        "padding:9px 11px;font-size:11px;font-weight:700;text-transform:uppercase;"
        "letter-spacing:.04em;opacity:.6;border-bottom:2px solid rgba(128,128,128,0.35);"
        "background:rgba(128,128,128,0.06);"
    )
    rows = []
    for f in facilities or []:
        name = frappe.utils.escape_html(f.get("facility_name") or "")
        mfl = frappe.utils.escape_html(f.get("mfl_code") or "")
        keph = frappe.utils.escape_html(frappe.utils.cstr(f.get("keph_level") or ""))
        monthly = _fmt_kes(f.get("monthly_kes"))
        annual = _fmt_kes(f.get("annual_kes"))
        # Each f-string is substituted independently, then implicitly concatenated —
        # no trailing .format() (which would bind only to the last literal group).
        rows.append(
            "<tr>"
            f'<td style="{cell}font-weight:600">{name}</td>'
            f'<td style="{cell}opacity:.7">{mfl}</td>'
            f'<td style="{cell}">{keph}</td>'
            f'<td align="right" style="{amt}">KES {monthly}</td>'
            f'<td align="right" style="{amt}">KES {annual}</td>'
            "</tr>"
        )
    body = "".join(rows) or (
        '<tr><td colspan="5" style="' + cell + 'text-align:center;opacity:.7">'
        "No facilities selected.</td></tr>"
    )
    return (
        '<table style="width:100%;border-collapse:collapse;font-size:13px;margin:8px 0 4px">'
        "<thead><tr>"
        '<th align="left" style="' + th + '">Facility</th>'
        '<th align="left" style="' + th + '">MFL Code</th>'
        '<th align="left" style="' + th + '">KEPH Level</th>'
        '<th align="right" style="' + th + '">Monthly (KES)</th>'
        '<th align="right" style="' + th + '">Annual (KES)</th>'
        "</tr></thead>"
        "<tbody>" + body + "</tbody>"
        "</table>"
    )


def build_tc_context_for_deal(deal):
    """Reconstruct the T&C render context (network, contact, pricing) for a deal
    from its opt-in submission.

    The Terms & Conditions Jinja template references {{ network.display_name }},
    {{ contact.email }}, {{ pricing_table }} and {{ grand_total_*_display }}; a
    context missing any of these raises UndefinedError. Contract generation and PDF
    export call this so they render the SAME priced terms the customer accepted,
    sourced from the submission's stored payload. Returns None if no submission is
    found for the deal (caller should degrade gracefully).
    """
    if not deal:
        return None
    subs = frappe.get_list(
        "CRM Opt-In Submission",
        filters={"deal": deal},
        fields=["name", "network_slug"],
        order_by="creation desc",
        limit=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if not subs:
        return None

    raw = frappe.db.get_value("CRM Opt-In Submission", subs[0].name, "raw_json")
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    # The submission stores the priced facilities under "pricing" (facility_name,
    # mfl_code, keph_level, monthly_kes, annual_kes) — the shape _build_pricing_table
    # expects. Fall back to "facilities" for older payloads.
    pricing = data.get("pricing") or data.get("facilities") or []
    contact = data.get("contact") or {}
    monthly = sum(frappe.utils.flt(f.get("monthly_kes")) for f in pricing)
    annual = sum(frappe.utils.flt(f.get("annual_kes")) for f in pricing)

    network_doc = _get_network_doc(subs[0].network_slug)
    network_display = (network_doc.get("display_name") if network_doc else "CareverseHIMS") or "CareverseHIMS"

    return {
        "contact": {"email": frappe.utils.cstr(contact.get("email") or "")},
        "facilities": pricing,
        "pricing": pricing,
        "pricing_table": _build_pricing_table(pricing),
        "grand_total_monthly": monthly,
        "grand_total_annual": annual,
        "grand_total_monthly_display": _fmt_kes(monthly),
        "grand_total_annual_display": _fmt_kes(annual),
        "date": frappe.utils.format_date(frappe.utils.today()),
        "network": {"display_name": network_display},
    }


@frappe.whitelist(allow_guest=True)
def get_terms_text(signing_token, email, network_slug, expiry, selected_mfl_codes, deal_invitation=None):
    """
    Render the active T&C Jinja template with facility+pricing context.
    Returns rendered HTML and its SHA-256 hash (proves customer saw their specific numbers).
    """
    signing_token = frappe.utils.cstr(signing_token)
    email = frappe.utils.cstr(email).strip().lower()
    network_slug = frappe.utils.cstr(network_slug).strip()

    _validate_signing_token(signing_token, email, network_slug, expiry)

    if isinstance(selected_mfl_codes, str):
        try:
            selected_mfl_codes = json.loads(selected_mfl_codes)
        except Exception:
            selected_mfl_codes = []

    # Fetch the active T&C document name
    settings = frappe.get_single("CRM Opt-In Settings")
    tc_name = settings.active_tc_document
    if not tc_name:
        frappe.throw(_("No active Terms and Conditions document configured."))

    tc_doc = frappe.get_doc("Terms and Conditions", tc_name)

    # Resolve network display name for the template
    network_doc = _get_network_doc(network_slug)
    network_display = (
        network_doc.get("display_name") if network_doc else "CareverseHIMS"
    ) or "CareverseHIMS"

    # Compute pricing to embed in the T&C
    pricing_result = get_pricing(
        signing_token, email, network_slug, expiry, selected_mfl_codes, deal_invitation
    )

    facilities = pricing_result.get("facilities", [])
    context = {
        "contact": {"email": email},
        "facilities": facilities,
        "pricing": facilities,
        # Pre-rendered so the template needs no {% for %} loop (sanitiser-stripped).
        "pricing_table": _build_pricing_table(facilities),
        "grand_total_monthly": pricing_result.get("grand_total_monthly", 0),
        "grand_total_annual": pricing_result.get("grand_total_annual", 0),
        "grand_total_monthly_display": _fmt_kes(pricing_result.get("grand_total_monthly", 0)),
        "grand_total_annual_display": _fmt_kes(pricing_result.get("grand_total_annual", 0)),
        "date": frappe.utils.format_date(frappe.utils.today()),
        "network": {"display_name": network_display},
    }

    rendered_html = frappe.render_template(tc_doc.terms or "", context)
    # Content-integrity fingerprint of the rendered T&C — NOT a credential.
    # Stored alongside the acceptance so we can prove the terms the user
    # accepted match what was displayed. SHA-256 is the correct primitive for
    # a fixed-length content digest; a password KDF (Argon2/PHC) is not
    # applicable here. Credentials in this module (OTPs, signing tokens) use
    # HMAC-SHA256 + hmac.compare_digest — see _hmac_hex().
    doc_hash = hashlib.sha256(rendered_html.encode()).hexdigest()

    return {
        "html": rendered_html,
        "doc_name": tc_doc.name,
        "doc_hash": doc_hash,
    }


@frappe.whitelist(allow_guest=True)
def submit_async(signing_token, email, network_slug, expiry, payload_json, deal_invitation=None):
    """
    Validate and process one Opt-In submission in the request transaction.

    The name is retained for the established frontend API path. Record creation is
    synchronous: before this method returns, the Lead, Contact, Organisation,
    Deal, and Quotation have either all been saved or the submission is marked
    Failed with no partial pipeline records from this attempt.
    """
    signing_token = frappe.utils.cstr(signing_token)
    email = frappe.utils.cstr(email).strip().lower()
    network_slug = frappe.utils.cstr(network_slug).strip()

    _validate_signing_token(signing_token, email, network_slug, expiry)
    invitation = _decode_deal_invitation(deal_invitation, network_slug, email)

    # Normalise payload
    if isinstance(payload_json, dict):
        payload = payload_json
        payload_json = json.dumps(payload_json)
    else:
        payload_json = frappe.utils.cstr(payload_json)
        try:
            payload = json.loads(payload_json)
        except Exception:
            frappe.throw(_("Invalid submission payload."))

    if invitation:
        existing_submission = frappe.db.get_value(
            "CRM Deal", invitation["deal"], "optin_submission", for_update=True
        )
        if existing_submission:
            frappe.throw(
                _("This Deal already has an Opt-In submission."), frappe.ValidationError
            )
        payload["_deal_invitation"] = {
            "deal": invitation["deal"],
            "price_list": invitation["price_list"],
        }

    # Never carry browser-provided pricing or item codes into the submission
    # processor. Validate the final submission synchronously and persist the
    # canonical facilities/pricing the server calculated for this signed session.
    payload = _prepare_submission_payload(
        payload,
        signing_token,
        email,
        network_slug,
        expiry,
        deal_invitation,
    )
    payload_json = json.dumps(payload)

    selected_mfl_codes = [
        frappe.utils.cstr(f.get("mfl_code"))
        for f in (payload.get("facilities") or [])
        if f.get("mfl_code")
    ]

    # Check for MFL codes already linked to an existing Lead facility row
    has_duplicate = False
    for mfl_code in selected_mfl_codes:
        try:
            dupes = frappe.get_list(
                "CRM Lead Facility",
                filters={"mfl_code": mfl_code},
                fields=["name"],
                limit=1,
                ignore_permissions=True,  # SYSTEM-INTERNAL
            )
            if dupes:
                has_duplicate = True
                break
        except Exception:
            pass  # Child table may not yet have rows; non-fatal

    # Create staging record
    sub = frappe.new_doc("CRM Opt-In Submission")
    sub.naming_series = "OIS-.YYYY.-"
    sub.status = "Pending"
    sub.network_slug = network_slug
    sub.submitter_email = email
    # Facility witness captured in the wizard — carried here so the contract's
    # Facility Witness row can be pre-filled at generate() without re-keying.
    witness = payload.get("witness") or {}
    sub.facility_witness_name = frappe.utils.cstr(witness.get("name") or "").strip()
    sub.facility_witness_email = frappe.utils.cstr(witness.get("email") or "").strip().lower()
    sub.submitted_at = frappe.utils.now_datetime()
    if invitation:
        sub.deal = invitation["deal"]
    sub.raw_json = payload_json
    sub.has_duplicate_mfl = 1 if has_duplicate else 0
    sub.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
    frappe.db.commit()

    _reset_submission_progress(sub.name)
    _process_submission(sub.name)

    status = frappe.db.get_value("CRM Opt-In Submission", sub.name, "status")
    return {
        "submission_ref": sub.name,
        "status": "processed" if status == "Processed" else "failed",
    }


@frappe.whitelist()
def send_deal_optin_invitation(deal, price_list=None):
    """Email a Deal-bound OIS link that preserves the selected negotiated price list."""
    _require_optin_manager()
    deal = frappe.utils.cstr(deal).strip()
    if not frappe.has_permission("CRM Deal", "write", deal):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    deal_doc = frappe.get_doc("CRM Deal", deal)
    network_slug = frappe.utils.cstr(deal_doc.get("optin_network") or "").strip()
    email = frappe.utils.cstr(deal_doc.get("email") or "").strip().lower()
    if not network_slug:
        frappe.throw(_("Select an Opt-In Network on this Deal before sending an invitation."))
    if not email:
        frappe.throw(_("Add a primary contact email to this Deal before sending an invitation."))
    if deal_doc.get("optin_submission"):
        frappe.throw(_("This Deal already has an Opt-In submission."))
    if frappe.get_list("Quotation", filters={"crm_deal": deal}, fields=["name"], limit_page_length=1):
        frappe.throw(_("This Deal already has a quote. Use the assisted quote workflow instead."))

    network = _get_network_doc(network_slug)
    if not network:
        frappe.throw(_("Select an enabled Opt-In Network."))
    if not _deal_invitation_facilities({"deal": deal}):
        frappe.throw(
            _("Add at least one facility with an MFL code, name, and KEPH level before sending an invitation.")
        )

    if not price_list:
        settings = frappe.get_single("CRM Opt-In Settings")
        price_list = network.get("price_list_override") or settings.default_price_list
    price_list = frappe.utils.cstr(price_list).strip()
    if not frappe.db.exists("Price List", {"name": price_list, "selling": 1, "enabled": 1}):
        frappe.throw(_("Select an enabled selling price list."))

    expiry = int(time.time()) + 7 * 24 * 60 * 60
    invitation = _encode_deal_invitation(
        {
            "deal": deal,
            "email": email,
            "network_slug": network_slug,
            "price_list": price_list,
            "expiry": expiry,
        }
    )
    url = "%s/opt-in?network=%s&deal_invitation=%s" % (
        frappe.utils.get_url(),
        network_slug,
        invitation,
    )
    recipient_name = frappe.utils.escape_html(
        " ".join(
            part for part in (deal_doc.get("first_name"), deal_doc.get("last_name")) if part
        )
        or "there"
    )
    network_name = frappe.utils.escape_html(network.get("display_name") or network_slug)
    frappe.sendmail(
        recipients=[email],
        subject="Complete your %s Opt-In" % (network.get("display_name") or "CareverseHIMS"),
        message=(
            "<p>Dear %s,</p>"
            "<p>Please review your facility details, pricing, and agreement for "
            "<strong>%s</strong>.</p>"
            '<p style="margin:24px 0"><a href="%s" '
            'style="background:#b91c1c;color:#fff;padding:12px 24px;border-radius:6px;'
            'text-decoration:none;font-weight:600">Complete Opt-In</a></p>'
            "<p>If the button does not work, paste this link into your browser:<br>"
            '<a href="%s">%s</a></p><p>This invitation expires in seven days.</p>'
        )
        % (recipient_name, network_name, url, url, url),
        now=True,
    )
    return {"sent_to": email, "price_list": price_list}


@frappe.whitelist(allow_guest=True)
def get_job_status(submission_ref, signing_token, email, network_slug, expiry):
    """
    Poll Redis for async job progress.
    Falls back to CRM Opt-In Submission.status if Redis key is absent.
    Returns {steps: [{name, status, label}], overall, lead_id}.
    Validates signing_token and verifies submission ownership before returning data.
    Rate limit: max 20 calls per IP per minute; over-limit returns safe default.
    """
    submission_ref = frappe.utils.cstr(submission_ref)
    email = frappe.utils.cstr(email).strip().lower()
    network_slug = frappe.utils.cstr(network_slug).strip()

    # Rate limiting — 20 req/IP/min
    client_ip = _get_client_ip()
    rate_key = "optin_rate_gjs:%s" % client_ip
    try:
        call_count = int(frappe.cache().get_value(rate_key) or 0)
        if call_count >= 20:
            return {"steps": [], "overall": "in_progress", "lead_id": None}
        frappe.cache().set_value(rate_key, call_count + 1, expires_in_sec=60)
    except Exception:
        # Redis is unavailable: retain secure token/ownership validation and
        # fall through to the database-backed submission status.
        pass

    _validate_signing_token(signing_token, email, network_slug, expiry)

    # Verify ownership: submission must belong to the authenticated email
    owner_rows = frappe.get_list(
        "CRM Opt-In Submission",
        filters={"name": submission_ref},
        fields=["submitter_email"],
        limit=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if not owner_rows or (owner_rows[0].get("submitter_email") or "").lower() != email:
        frappe.throw(_("Access denied."), frappe.PermissionError)

    response = _get_job_progress(submission_ref)
    if response:
        response["submission_ref"] = submission_ref
        if response.get("overall") == "failed":
            response.setdefault("message", _public_submission_failure_message(submission_ref))
        return response

    # Fallback: read from DB
    try:
        rows = frappe.get_list(
            "CRM Opt-In Submission",
            filters={"name": submission_ref},
            fields=["status", "lead"],
            limit=1,
            ignore_permissions=True,  # SYSTEM-INTERNAL
        )
        if rows:
            row = rows[0]
            db_status = row.get("status") or "Pending"
            overall_map = {"Processed": "complete", "Failed": "failed"}
            overall = overall_map.get(db_status, "in_progress")
            response = {
                "steps": [],
                "overall": overall,
                "lead_id": row.get("lead") or None,
                "submission_ref": submission_ref,
            }
            if overall == "failed":
                response["message"] = _public_submission_failure_message(submission_ref)
            return response
    except Exception:
        pass

    return {"steps": [], "overall": "in_progress", "lead_id": None}


@frappe.whitelist(allow_guest=True)
def save_partial(signing_token, email, network_slug, expiry, contact_json):
    """
    Save a partial CRM Lead (early exit / "I'll Decide Later") and send a magic resume link.
    Returns {submission_ref: lead_name}.
    """
    signing_token = frappe.utils.cstr(signing_token)
    email = frappe.utils.cstr(email).strip().lower()
    network_slug = frappe.utils.cstr(network_slug).strip()

    _validate_signing_token(signing_token, email, network_slug, expiry)

    if isinstance(contact_json, str):
        try:
            contact = json.loads(contact_json)
        except Exception:
            contact = {}
    else:
        contact = contact_json or {}

    lead = frappe.new_doc("CRM Lead")
    lead.first_name = frappe.utils.cstr(contact.get("first_name", ""))
    lead.last_name = frappe.utils.cstr(contact.get("last_name", ""))
    lead.email = email
    lead.mobile_no = frappe.utils.cstr(contact.get("mobile_no", ""))
    lead.organization = frappe.utils.cstr(contact.get("organisation", ""))
    lead.job_title = frappe.utils.cstr(contact.get("role", ""))
    lead.source = _get_optin_lead_source()
    lead.status = "Open"
    lead.insert(ignore_permissions=True)  # SYSTEM-INTERNAL

    # Set opt-in partial flags via db_set to avoid controller side effects
    for field, value in [("optin_partial", 1), ("optin_resume_token_used", 0)]:
        try:
            frappe.db.set_value("CRM Lead", lead.name, field, value)
        except Exception:
            pass  # Custom fields may not yet exist on all environments

    frappe.db.commit()

    # Generate magic resume link token — 24-hour expiry
    link_expiry = int(time.time()) + 86400
    key = _get_signing_key()
    resume_tok = _hmac_hex(key, "%s:%s" % (lead.name, link_expiry))

    try:
        frappe.sendmail(
            recipients=[email],
            subject="Continue Your CareverseHIMS Opt-In",
            message=(
                "<p>You started the CareverseHIMS opt-in process but did not finish.</p>"
                "<p>Click the link below to continue where you left off:</p>"
                "<p><a href='/opt-in?resume=%s&exp=%s&tok=%s'>Continue Opt-In</a></p>"
                "<p>This link expires in 24 hours.</p>"
            ) % (lead.name, link_expiry, resume_tok),
            now=True,
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "optin.save_partial: resume email failed for lead %s" % lead.name,
        )

    return {"submission_ref": lead.name}


@frappe.whitelist(allow_guest=True)
def resume(lead_id, exp, tok):
    """
    Validate HMAC magic-link token. Mark token as used. Return Step 1 pre-fill data.
    Raises frappe.PermissionError on invalid/expired/already-used token.
    """
    lead_id = frappe.utils.cstr(lead_id)
    tok = frappe.utils.cstr(tok)

    # Validate expiry
    try:
        exp_int = int(exp)
    except (TypeError, ValueError):
        frappe.throw(_("Invalid resume link."), frappe.PermissionError)

    if time.time() > exp_int:
        frappe.throw(_("This resume link has expired."), frappe.PermissionError)

    # Validate HMAC
    key = _get_signing_key()
    expected = _hmac_hex(key, "%s:%s" % (lead_id, exp))
    if not hmac.compare_digest(expected, tok):
        frappe.throw(_("Invalid resume link."), frappe.PermissionError)

    # Fetch lead
    rows = frappe.get_list(
        "CRM Lead",
        filters={"name": lead_id},
        fields=[
            "name", "first_name", "last_name", "email",
            "mobile_no", "organization", "job_title",
            "optin_resume_token_used",
        ],
        limit=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if not rows:
        frappe.throw(_("Invalid resume link."), frappe.PermissionError)

    lead_row = rows[0]

    if int(lead_row.get("optin_resume_token_used") or 0):
        frappe.throw(_("This resume link has already been used."), frappe.PermissionError)

    # Mark token as used
    try:
        frappe.db.set_value("CRM Lead", lead_id, "optin_resume_token_used", 1)
        frappe.db.commit()
    except Exception:
        pass  # Custom field may not exist yet; non-fatal

    return {
        "first_name": lead_row.get("first_name") or "",
        "last_name": lead_row.get("last_name") or "",
        "email": lead_row.get("email") or "",
        "mobile_no": lead_row.get("mobile_no") or "",
        "lead_name": lead_id,
        "organization": lead_row.get("organization") or "",
    }


def _confirmation_email_html(first_name, submission_ref, network, pricing):
    """
    Build the branded opt-in confirmation email (table-based layout for broad
    email-client support). Mirrors the OTP email's brand treatment and adds the
    facilities registered, a pricing summary (incl. 16% VAT), and next steps.
    """
    display_name = (network.get("display_name") if network else "") or "CareverseHIMS"
    logo_url = (network.get("logo_url") if network else "") or ""
    contact_email = (network.get("contact_email") if network else "") or ""
    footer_legal = (network.get("footer_legal_name") if network else "") or ""
    brand = _valid_brand_colour(network.get("primary_colour") if network else "")
    tint = _hex_to_rgba(brand, "0.08")

    if logo_url:
        abs_logo = logo_url if logo_url.startswith("http") else frappe.utils.get_url(logo_url)
        header = (
            '<img src="%s" alt="%s" height="44" '
            'style="max-height:44px;width:auto;border:0;outline:none;text-decoration:none" />'
            % (abs_logo, frappe.utils.escape_html(display_name))
        )
    else:
        header = (
            '<div style="font-size:20px;font-weight:700;color:%s;'
            'font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">%s</div>'
            % (brand, frappe.utils.escape_html(display_name))
        )

    # Pricing summary (subtotal + VAT + totals) computed from the pricing rows.
    subtotal_monthly = sum(float(p.get("monthly_kes") or 0) for p in (pricing or []))
    subtotal_annual = sum(float(p.get("annual_kes") or 0) for p in (pricing or []))
    vat_annual = round(subtotal_annual * VAT_RATE, 2)
    grand_annual = round(subtotal_annual + vat_annual, 2)
    grand_monthly = round(subtotal_monthly * (1 + VAT_RATE), 2)

    facilities_table = _build_pricing_table(pricing) if pricing else ""

    totals_block = ""
    if pricing:
        totals_block = (
            '<tr><td style="padding:4px 32px 0">'
            '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;font-size:13px;color:#4b5563">'
            '<tr><td style="padding:3px 0">Subtotal (annual)</td>'
            '<td align="right" style="padding:3px 0">KES %(sub_annual)s</td></tr>'
            '<tr><td style="padding:3px 0">VAT (16%%)</td>'
            '<td align="right" style="padding:3px 0">KES %(vat_annual)s</td></tr>'
            '<tr><td style="padding:8px 0 0;font-weight:700;color:#111827;'
            'border-top:1px solid #eceef0">Total payable (annual)</td>'
            '<td align="right" style="padding:8px 0 0;font-weight:700;color:%(brand)s;'
            'border-top:1px solid #eceef0">KES %(grand_annual)s</td></tr>'
            '<tr><td colspan="2" style="padding:6px 0 0;font-size:12px;color:#9ca3af">'
            'Approx. KES %(grand_monthly)s / month incl. VAT</td></tr>'
            '</table></td></tr>'
        ) % {
            "sub_annual": _fmt_kes(subtotal_annual),
            "vat_annual": _fmt_kes(vat_annual),
            "grand_annual": _fmt_kes(grand_annual),
            "grand_monthly": _fmt_kes(grand_monthly),
            "brand": brand,
        }

    help_line = ""
    if contact_email:
        help_line = (
            '<p style="font-size:12px;color:#9ca3af;margin:0 0 6px">Questions? Contact '
            '<a href="mailto:%s" style="color:%s;text-decoration:none">%s</a></p>'
            % (contact_email, brand, contact_email)
        )
    footer_bits = [b for b in (footer_legal, "Powered by Tiberbu Healthnet Solutions") if b]
    footer_line = frappe.utils.escape_html(" · ".join(footer_bits))

    facilities_section = ""
    if facilities_table:
        facilities_section = (
            '<tr><td style="padding:18px 32px 0">'
            '<div style="font-size:12px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:.04em;color:#6b7280;margin:0 0 4px">Facilities registered</div>'
            '%s</td></tr>' % facilities_table
        )

    return """\
<div style="background:#f4f5f6;margin:0;padding:24px 12px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">
  <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:560px;max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(16,24,40,0.08)">
        <tr><td style="height:4px;line-height:4px;font-size:0;background:%(brand)s">&nbsp;</td></tr>
        <tr><td align="center" style="padding:32px 32px 4px">%(header)s</td></tr>
        <tr><td align="center" style="padding:14px 32px 0">
          <div style="display:inline-flex;align-items:center;justify-content:center;width:52px;height:52px;border-radius:50%%;background:%(tint)s">
            <span style="font-size:26px;color:%(brand)s;line-height:1">&#10003;</span>
          </div>
        </td></tr>
        <tr><td align="center" style="padding:14px 32px 0">
          <h1 style="margin:0;font-size:22px;font-weight:700;color:#111827">You're all set, %(first_name)s</h1>
        </td></tr>
        <tr><td align="center" style="padding:8px 32px 0">
          <p style="margin:0;font-size:14px;line-height:1.55;color:#4b5563">
            Thank you for opting in to <strong style="color:#111827">%(display_name)s</strong>.
            Your registration has been received and is now with our onboarding team.
          </p>
        </td></tr>
        <tr><td align="center" style="padding:18px 32px 0">
          <div style="display:inline-block;background:%(tint)s;border:1px solid %(brand)s;border-radius:10px;padding:10px 22px">
            <span style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#6b7280">Reference</span><br/>
            <span style="font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:20px;font-weight:700;letter-spacing:2px;color:#111827">%(ref)s</span>
          </div>
        </td></tr>
        %(facilities_section)s
        %(totals_block)s
        <tr><td style="padding:20px 32px 0">
          <div style="background:%(tint)s;border-radius:10px;padding:16px 18px">
            <div style="font-size:13px;font-weight:700;color:#111827;margin:0 0 8px">What happens next</div>
            <table role="presentation" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:13px;color:#4b5563;line-height:1.5">
              <tr><td style="padding:2px 8px 2px 0;color:%(brand)s;font-weight:700">1.</td><td style="padding:2px 0">Our onboarding team reviews your registration and prepares your contract.</td></tr>
              <tr><td style="padding:2px 8px 2px 0;color:%(brand)s;font-weight:700">2.</td><td style="padding:2px 0">You'll receive your contract by email to review and sign online — no printing needed.</td></tr>
              <tr><td style="padding:2px 8px 2px 0;color:%(brand)s;font-weight:700">3.</td><td style="padding:2px 0">Once signed and approved, your facilities are activated on CareverseHIMS.</td></tr>
            </table>
          </div>
        </td></tr>
        <tr><td style="padding:18px 32px 0"><div style="border-top:1px solid #eceef0;font-size:0;line-height:0">&nbsp;</div></td></tr>
        <tr><td align="center" style="padding:16px 32px 30px">
          %(help_line)s
          <p style="margin:0;font-size:11px;color:#b6bcc4">%(footer_line)s</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</div>""" % {
        "brand": brand,
        "tint": tint,
        "header": header,
        "first_name": frappe.utils.escape_html(first_name or "there"),
        "display_name": frappe.utils.escape_html(display_name),
        "ref": frappe.utils.escape_html(submission_ref),
        "facilities_section": facilities_section,
        "totals_block": totals_block,
        "help_line": help_line,
        "footer_line": footer_line,
    }


# ---------------------------------------------------------------------------
# Synchronous Opt-In pipeline — NOT whitelisted
# ---------------------------------------------------------------------------


def _process_deal_invitation_submission(sub, payload):
    """Attach a completed invited OIS to its existing Deal and create its quote."""
    _update_job_step(sub.name, "deal", "in_progress", "Checking your existing account...")
    context = payload.get("_deal_invitation") or {}
    deal_name = frappe.utils.cstr(context.get("deal") or "").strip()
    if not deal_name or not frappe.db.exists("CRM Deal", deal_name):
        frappe.throw(_("The Deal for this Opt-In invitation no longer exists."))

    deal = frappe.get_doc("CRM Deal", deal_name)
    if deal.get("optin_submission") and deal.optin_submission != sub.name:
        frappe.throw(_("This Deal already has an Opt-In submission."))
    pricing = payload.get("pricing") or []
    if not pricing:
        frappe.throw(_("No pricing rows were submitted."))
    existing_quotes = frappe.get_list(
        "Quotation",
        filters={"crm_deal": deal_name},
        fields=["name", "crm_sent"],
        limit_page_length=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if existing_quotes and not existing_quotes[0].crm_sent:
        frappe.throw(_("This Deal already has a quote."))

    _update_job_step(sub.name, "lead", "done", "Using the existing Deal")
    _update_job_step(sub.name, "deal", "in_progress", "Updating your account...")
    contact = payload.get("contact") or {}
    sub.deal = deal_name
    sub.facility_signatory_name = (
        frappe.utils.cstr(contact.get("first_name") or "").strip()
        + " "
        + frappe.utils.cstr(contact.get("last_name") or "").strip()
    ).strip()
    sub.facility_signatory_email = frappe.utils.cstr(contact.get("email") or "").strip().lower()
    sub.save(ignore_permissions=True)  # SYSTEM-INTERNAL
    deal.optin_submission = sub.name
    deal.save(ignore_permissions=True)  # SYSTEM-INTERNAL
    _update_job_step(sub.name, "deal", "done", "Existing Deal updated")

    _update_job_step(sub.name, "quote", "in_progress", "Generating your quote...")
    from crm.api.quotes import _ensure_customer

    if existing_quotes:
        quote = frappe.get_doc("Quotation", existing_quotes[0].name)
    else:
        customer_name = _ensure_customer(deal.get("organization") or "", commit=False)
        quote = frappe.get_doc(
            {
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": customer_name,
                "company": frappe.db.get_single_value("Global Defaults", "default_company"),
                "transaction_date": frappe.utils.today(),
                "valid_till": frappe.utils.add_days(frappe.utils.today(), 30),
                "currency": "KES",
                "order_type": "Sales",
                "crm_deal": deal_name,
                "selling_price_list": context.get("price_list"),
                "ignore_pricing_rule": 1,
                "crm_sent": 1,
            }
        )
        annual_rates = []
        for product in pricing:
            annual_rate = float(product.get("annual_kes") or 0)
            annual_rates.append(annual_rate)
            quote.append(
                "items",
                {
                    "item_code": frappe.utils.cstr(product.get("item_code") or ""),
                    "item_name": "CareverseHIMS - %s"
                    % frappe.utils.cstr(product.get("facility_name") or ""),
                    "description": "KEPH %s - Annual Subscription"
                    % frappe.utils.cstr(product.get("keph_level") or ""),
                    "qty": 1,
                    "price_list_rate": annual_rate,
                    "rate": annual_rate,
                    "discount_percentage": 0,
                    "uom": "Nos",
                    "facility_name": frappe.utils.cstr(product.get("facility_name") or ""),
                },
            )
        quote.flags.ignore_permissions = True  # SYSTEM-INTERNAL
        quote.flags.ignore_validate = True
        quote.flags.ignore_mandatory = True
        quote.set_missing_values()
        for row, annual_rate in zip(quote.items or [], annual_rates):
            row.price_list_rate = annual_rate
            row.rate = annual_rate
            row.discount_percentage = 0
        quote.calculate_taxes_and_totals()
        quote.vat_amount = round((quote.net_total or 0) * VAT_RATE, 2)
        quote.insert(ignore_mandatory=True)
    _update_job_step(sub.name, "quote", "done", "Quote ready")

    recipient = sub.submitter_email
    if recipient:
        try:
            network = _get_network_doc(sub.network_slug)
            frappe.sendmail(
                recipients=[recipient],
                subject="%s Opt-In Confirmed - Reference %s"
                % (((network or {}).get("display_name") or "CareverseHIMS"), sub.name),
                message=_confirmation_email_html(
                    contact.get("first_name") or "", sub.name, network, pricing
                ),
            )
            _update_job_step(sub.name, "email", "done", "Confirmation email sent")
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "optin._process_deal_invitation_submission: confirmation email failed for %s"
                % sub.name,
            )
            _update_job_step(sub.name, "email", "done", "Confirmation email pending")
    else:
        _update_job_step(sub.name, "email", "done", "Email step complete")
    sub.status = "Processed"
    sub.save(ignore_permissions=True)  # SYSTEM-INTERNAL
    data = _get_job_progress(sub.name) or {}
    data["overall"] = "complete"
    data["lead_id"] = None
    _set_job_progress(sub.name, data)


def _process_submission(submission_ref):
    """
    Process CRM Opt-In Submission → Lead → Deal → Quotation synchronously.

    The committed staging record remains as an audit trail on failure, while all
    pipeline records created by this run are protected by a savepoint. Confirmation
    delivery is deferred to Frappe's Email Queue and is not part of the save.
    """
    previous_user = frappe.session.user
    frappe.set_user("Administrator")  # SYSTEM-INTERNAL: create CRM records as system
    savepoint = "optin_submission_processing"
    frappe.db.savepoint(savepoint)
    try:
        # Claim the staged record before performing any side effects. A repeated
        # browser request or retry must not create a second CRM pipeline.
        status = frappe.db.get_value(
            "CRM Opt-In Submission", submission_ref, "status", for_update=True
        )
        if not status:
            return False

        sub = frappe.get_doc("CRM Opt-In Submission", submission_ref)
        if status == "Processed":
            progress = _get_job_progress(submission_ref) or {}
            progress["overall"] = "complete"
            progress["lead_id"] = sub.lead or None
            _set_job_progress(submission_ref, progress)
            return True
        if status == "Processing":
            return False
        if status != "Pending":
            return False

        sub.status = "Processing"
        sub.save(ignore_permissions=True)  # SYSTEM-INTERNAL

        payload = json.loads(sub.raw_json or "{}")
        if payload.get("_deal_invitation"):
            _process_deal_invitation_submission(sub, payload)
            frappe.db.commit()
            return True
        contact = payload.get("contact", {})
        facilities = payload.get("facilities", [])
        pricing = payload.get("pricing", [])

        # ── Step 1: Create CRM Lead ──────────────────────────────────────────
        _update_job_step(submission_ref, "lead", "in_progress", "Saving your details...")

        if sub.lead and frappe.db.exists("CRM Lead", sub.lead):
            lead = frappe.get_doc("CRM Lead", sub.lead)
        else:
            lead = frappe.new_doc("CRM Lead")
            lead.first_name = frappe.utils.cstr(contact.get("first_name", ""))
            lead.last_name = frappe.utils.cstr(contact.get("last_name", ""))
            lead.email = frappe.utils.cstr(contact.get("email", ""))
            lead.mobile_no = frappe.utils.cstr(contact.get("mobile_no", ""))
            lead.organization = frappe.utils.cstr(contact.get("organisation", ""))
            lead.job_title = frappe.utils.cstr(contact.get("role", ""))
            lead.source = _get_optin_lead_source()
            lead.status = "New"

            try:
                _settings = frappe.get_single("CRM Opt-In Settings")
                lead.lead_owner = _settings.default_lead_owner or "Administrator"
            except Exception:
                lead.lead_owner = "Administrator"

            # Opt-in provenance / T&C fields are persisted as first-class Custom
            # Fields. They are only written for the newly created lead so a retry
            # cannot overwrite the original acceptance evidence.
            lead.optin_network_slug = sub.network_slug
            lead.tc_accepted = 1
            lead.tc_document = payload.get("tc_doc_name", "")
            lead.tc_document_hash = payload.get("tc_doc_hash", "")
            lead.tc_accepted_at = frappe.utils.now_datetime()
            lead.tc_ip_address = payload.get("ip_address", "")

            for fac in facilities:
                lead.append(
                    "facilities",
                    {
                        "mfl_code": frappe.utils.cstr(fac.get("mfl_code", "")),
                        "facility_name": frappe.utils.cstr(fac.get("facility_name", "")),
                        "facility_level": frappe.utils.cstr(fac.get("keph_level", "")),
                        "hfr_sync_status": "HFR Verified",
                    },
                )

            # The CRM Products child table's product_code is a CRM Product Link,
            # not the ERPNext Item code from pricing, so it is deliberately unset.
            for prod in pricing:
                product_name = (
                    frappe.utils.cstr(prod.get("facility_name", ""))
                    or frappe.utils.cstr(prod.get("item_code", ""))
                    or "CareverseHIMS Subscription"
                )
                lead.append(
                    "products",
                    {
                        "product_name": product_name,
                        "qty": 1,
                        "rate": float(prod.get("monthly_kes") or 0),
                    },
                )

            lead.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
            sub.lead = lead.name
            sub.save(ignore_permissions=True)  # SYSTEM-INTERNAL

        _update_job_step(
            submission_ref, "lead", "done",
            "%s facilities linked" % len(facilities) if facilities else "Details saved",
        )

        # ── Step 2: Create Contact + Organisation → convert Lead to Deal ─────
        _update_job_step(submission_ref, "deal", "in_progress", "Creating your account...")

        contact_name = _get_or_create_submission_contact(lead)
        organization_name = _get_or_create_submission_organization(lead, submission_ref)

        is_existing_deal = bool(sub.deal and frappe.db.exists("CRM Deal", sub.deal))
        if is_existing_deal:
            deal_name = sub.deal
        else:
            prior_deal = frappe.db.get_value("CRM Deal", {"lead": lead.name}, "name")
            if prior_deal:
                deal_name = prior_deal
            else:
                from crm.fcrm.doctype.crm_lead.crm_lead import convert_to_deal

                # Set flag so convert_to_deal skips the has_permission guard.
                lead.flags.ignore_permissions = True
                deal_name = convert_to_deal(
                    lead=lead.name,
                    doc=lead,
                    deal=_get_optin_deal_forecast_fields(pricing),
                    existing_contact=contact_name,
                    existing_organization=organization_name,
                )

        sub.deal = deal_name
        # Persist signatory contact for exec pre-fill (oh-s2-2)
        sub.facility_signatory_name = (
            frappe.utils.cstr(contact.get("first_name", "")).strip()
            + " "
            + frappe.utils.cstr(contact.get("last_name", "")).strip()
        ).strip()
        sub.facility_signatory_email = frappe.utils.cstr(contact.get("email", "")).strip().lower()
        sub.save(ignore_permissions=True)  # SYSTEM-INTERNAL

        # Forward back-link Deal -> Opt-In Submission for traceability (oh-s1-1).
        frappe.db.set_value(
            "CRM Deal", deal_name, "optin_submission", submission_ref
        )  # SYSTEM-INTERNAL

        # Deal transition timeline (oh-s1-3)
        from crm.api._timeline import log_deal_event

        if not is_existing_deal:
            log_deal_event(
                deal_name,
                "Opt-in submission %s processed — Lead %s converted to Deal"
                % (submission_ref, lead.name),
            )

        _update_job_step(submission_ref, "deal", "done", "Account set up")

        # ── Step 3: Create or update Quotation with KEPH pricing ─────────────
        _update_job_step(submission_ref, "quote", "in_progress", "Generating your quote...")

        if pricing:
            # Quote creation is mandatory when pricing is present.
            # Do NOT wrap in a bare try/except here — failures must propagate
            # to the outer handler which sets status="Failed". A deal without
            # a quote is a data-integrity violation, not a warn-and-continue.

            # Resolve the negotiated price list the wizard priced against
            # (network override → settings default → seeded fallback), mirroring
            # get_pricing(). The quote must carry THIS list, not Standard Selling.
            _q_network = _get_network_doc(sub.network_slug)
            try:
                _q_settings = frappe.get_single("CRM Opt-In Settings")
                _default_pl = _q_settings.default_price_list or "Negotiated Year 1"
            except Exception:
                _default_pl = "Negotiated Year 1"
            quote_price_list = (
                (_q_network.get("price_list_override") if _q_network else None) or _default_pl
            )

            existing_quotes = frappe.get_list(
                "Quotation",
                filters={"crm_deal": deal_name},
                fields=["name"],
                limit=1,
                ignore_permissions=True,  # SYSTEM-INTERNAL
            )

            if existing_quotes:
                q = frappe.get_doc("Quotation", existing_quotes[0].name)
                q.items = []
            else:
                # convert_to_deal does not create a Quotation; create one now
                from crm.api.quotes import _ensure_customer

                customer_name = _ensure_customer(lead.organization or "", commit=False)
                q = frappe.get_doc({
                    "doctype": "Quotation",
                    "quotation_to": "Customer",
                    "party_name": customer_name,
                    "company": frappe.db.get_single_value(
                        "Global Defaults", "default_company"
                    ),
                    "transaction_date": frappe.utils.today(),
                    "valid_till": frappe.utils.add_days(frappe.utils.today(), 30),
                    "currency": "KES",
                    "order_type": "Sales",
                    "crm_deal": deal_name,
                })

            # Pin the negotiated price list on the quote so it overrides the
            # Selling Settings default (Standard Selling). ignore_pricing_rule
            # stops set_missing_values() / validate from re-deriving line rates.
            q.selling_price_list = quote_price_list
            q.ignore_pricing_rule = 1

            annual_rates = []
            for prod in pricing:
                annual_rate = float(prod.get("annual_kes") or 0)
                annual_rates.append(annual_rate)
                q.append("items", {
                    "item_code": frappe.utils.cstr(prod.get("item_code", "")),
                    "item_name": "CareverseHIMS - %s" % frappe.utils.cstr(
                        prod.get("facility_name", "")
                    ),
                    "description": "KEPH %s - Annual Subscription" % frappe.utils.cstr(
                        prod.get("keph_level", "")
                    ),
                    "qty": 1,
                    # Line is an ANNUAL subscription; the price list stores the
                    # MONTHLY Item Price. Pin price_list_rate to the annual figure
                    # with zero discount so set_missing_values() (which now has a
                    # price list to fetch from) can't back-compute a phantom
                    # discount or overwrite the annual rate with the monthly one.
                    "price_list_rate": annual_rate,
                    "rate": annual_rate,
                    "discount_percentage": 0,
                    "uom": "Nos",
                })

            # (D-3) The opt-in quote is pre-Sent: the customer already
            # accepted this exact pricing in the wizard, so it is
            # immediately Accept-able / execution-ready without a manual
            # Send. crm_sent=1 + docstatus=0 => frontend status "Sent".
            q.crm_sent = 1

            q.flags.ignore_permissions = True  # SYSTEM-INTERNAL
            q.flags.ignore_validate = True
            # set_missing_values() populates the ERPNext currency fields
            # (conversion_rate, price_list_currency, plc_conversion_rate,
            # conversion_factor); without it q.save() on the re-process /
            # existing-quote branch raised MandatoryError and the whole
            # quote step was silently swallowed, so no quote ever reached
            # the Deal. Run it on both branches and ignore any residual
            # mandatory gaps so the pre-Sent quote is created reliably.
            q.flags.ignore_mandatory = True
            q.set_missing_values()
            # set_missing_values may refresh rates from the price list. The
            # accepted Opt-In annual rates are authoritative, so restore them
            # before calculating the quotation totals.
            for row, annual_rate in zip(q.items or [], annual_rates):
                row.price_list_rate = annual_rate
                row.rate = annual_rate
                row.discount_percentage = 0
            q.calculate_taxes_and_totals()
            q.vat_amount = round((q.net_total or 0) * VAT_RATE, 2)
            if q.is_new():
                q.insert(ignore_mandatory=True)
            else:
                q.save(ignore_permissions=True)  # SYSTEM-INTERNAL

        _update_job_step(submission_ref, "quote", "done", "Draft quote ready")

        # ── Step 4: Send confirmation email ──────────────────────────────────
        _update_job_step(submission_ref, "email", "in_progress", "Sending confirmation...")

        recipient = lead.email or ""
        if recipient:
            try:
                network = _get_network_doc(sub.network_slug)
                brand_name = (network.get("display_name") if network else "") or "CareverseHIMS"
                frappe.sendmail(
                    recipients=[recipient],
                    subject="%s Opt-In Confirmed — Reference %s" % (brand_name, submission_ref),
                    message=_confirmation_email_html(
                        lead.first_name, submission_ref, network, pricing
                    ),
                )
                _update_job_step(
                    submission_ref, "email", "done",
                    "Confirmation email sent",
                )
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    "optin._process_submission: confirmation email failed for %s" % submission_ref,
                )
                _update_job_step(submission_ref, "email", "done", "Email step complete")
        else:
            _update_job_step(submission_ref, "email", "done", "Email step complete")

        # ── Mark submission complete ──────────────────────────────────────────
        sub.status = "Processed"
        sub.save(ignore_permissions=True)  # SYSTEM-INTERNAL
        frappe.db.commit()

        data = _get_job_progress(submission_ref) or {}
        data["overall"] = "complete"
        data["lead_id"] = lead.name
        _set_job_progress(submission_ref, data)
        return True

    except Exception as exc:
        frappe.db.rollback(save_point=savepoint)
        frappe.log_error(
            frappe.get_traceback(),
            "Opt-In Submission Failed: %s" % submission_ref,
        )
        try:
            _mark_active_job_step_failed(submission_ref)
        except Exception:
            # Failure reporting must never obscure the original worker error.
            frappe.log_error(
                frappe.get_traceback(),
                "optin._process_submission: could not update failed progress for %s"
                % submission_ref,
            )
        try:
            sub = frappe.get_doc("CRM Opt-In Submission", submission_ref)
            sub.status = "Failed"
            sub.error_log = frappe.utils.cstr(exc)
            sub.save(ignore_permissions=True)  # SYSTEM-INTERNAL
            frappe.db.commit()
        except Exception:
            pass
        data = _get_job_progress(submission_ref) or {}
        data["overall"] = "failed"
        data["submission_ref"] = submission_ref
        data["message"] = _public_submission_failure_message(submission_ref)
        _set_job_progress(submission_ref, data)
        return False
    finally:
        frappe.set_user(previous_user)


# ---------------------------------------------------------------------------
# Internal Opt-In submission review API — CRM staff, NOT guest (oh-s2-1)
#
# Unlike every public wizard endpoint above (allow_guest=True), these two are
# for internal CRM staff, so they are plain @frappe.whitelist() and rely on the
# CRM Opt-In Submission permission model (System Manager r/w/c, Sales User r).
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_submissions(status=None, page=0, page_size=20):
    """
    Paginated Opt-In submissions for the staff review surface.

    Permission-scoped: frappe.get_list() is called WITHOUT ignore_permissions, so
    the doctype permission model (System Manager r/w/c, Sales User r) governs what
    each caller sees. Returns {"rows": [...], "total": <int>}.
    """
    page = int(page or 0)
    page_size = int(page_size or 20)

    filters = {}
    if status and status != "All":
        filters["status"] = status

    rows = frappe.get_list(
        "CRM Opt-In Submission",
        filters=filters,
        fields=[
            "name", "status", "network_slug", "submitter_email",
            "submitted_at", "lead", "deal", "has_duplicate_mfl", "error_log",
        ],
        order_by="submitted_at desc",
        limit_start=page * page_size,
        limit_page_length=page_size,
    )

    # Total via a permission-scoped get_list (limit_page_length=0 => all rows) —
    # keeps the count on the same "get_list only" path as the page read.
    total = len(
        frappe.get_list(
            "CRM Opt-In Submission",
            filters=filters,
            fields=["name"],
            limit_page_length=0,
        )
    )

    return {
        "rows": [
            {
                **row,
                "failure_reason": row.error_log if row.status == "Failed" else "",
            }
            for row in rows
        ],
        "total": total,
    }


@frappe.whitelist()
def retry_submission(submission_ref):
    """
    Retry a Failed/Pending submission synchronously. Requires write permission.
    """
    submission_ref = frappe.utils.cstr(submission_ref)

    if not frappe.has_permission("CRM Opt-In Submission", "write", submission_ref):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    status = frappe.db.get_value("CRM Opt-In Submission", submission_ref, "status")
    if status not in ("Failed", "Pending"):
        frappe.throw(_("Only failed or pending submissions can be retried."))

    frappe.db.set_value("CRM Opt-In Submission", submission_ref, "status", "Pending")
    frappe.db.commit()
    _reset_submission_progress(submission_ref)
    _process_submission(submission_ref)

    status = frappe.db.get_value("CRM Opt-In Submission", submission_ref, "status")
    return {"status": "processed" if status == "Processed" else "failed"}


@frappe.whitelist(allow_guest=True)
def retry_public_submission(signing_token, email, network_slug, expiry, submission_ref):
    """Safely let the verified submitter retry their own failed submission.

    The signing token proves the same verified email that created the staging
    record. The synchronous processor is idempotent, so a transient failure can
    be retried without creating another Lead, Contact, Deal or Quotation.
    """
    signing_token = frappe.utils.cstr(signing_token)
    email = frappe.utils.cstr(email).strip().lower()
    network_slug = frappe.utils.cstr(network_slug).strip()
    submission_ref = frappe.utils.cstr(submission_ref).strip()
    _validate_signing_token(signing_token, email, network_slug, expiry)

    rows = frappe.get_list(
        "CRM Opt-In Submission",
        filters={"name": submission_ref, "submitter_email": email},
        fields=["name", "status"],
        limit=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if not rows:
        frappe.throw(_("Access denied."), frappe.PermissionError)
    if rows[0].status != "Failed":
        frappe.throw(_("This submission is already being processed."), frappe.ValidationError)

    frappe.db.set_value("CRM Opt-In Submission", submission_ref, "status", "Pending")
    frappe.db.commit()
    _reset_submission_progress(submission_ref)
    _process_submission(submission_ref)
    status = frappe.db.get_value("CRM Opt-In Submission", submission_ref, "status")
    return {"status": "processed" if status == "Processed" else "failed"}


@frappe.whitelist()
def submit_deal_optin_summary(deal, quote, network_slug):
    """
    Record the finalized quote as an Opt-In summary for an existing Deal.

    This is the internal counterpart to the self-service Commit & Opt In step:
    it deliberately skips lead/deal creation because both already exist, while
    preserving the selected network and priced lines for contracting.
    """
    _require_optin_manager()
    deal = frappe.utils.cstr(deal).strip()
    quote = frappe.utils.cstr(quote).strip()
    network_slug = frappe.utils.cstr(network_slug).strip()

    if not frappe.has_permission("CRM Deal", "write", deal):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    if not frappe.db.exists(
        "CRM Opt-In Network", {"name": network_slug, "enabled": 1}
    ):
        frappe.throw(_("Select an enabled Opt-In Network."))

    # Lock the Deal through the snapshot write so concurrent quote changes cannot
    # pass their own finalized check before this summary is linked.
    existing_name = frappe.utils.cstr(
        frappe.db.get_value("CRM Deal", deal, "optin_submission", for_update=True) or ""
    ).strip()
    if existing_name:
        frappe.throw(
            _("This Deal already has an Opt-In submission and its summary cannot be replaced.")
        )

    quotation = frappe.get_doc("Quotation", quote)
    if quotation.get("crm_deal") != deal:
        frappe.throw(_("The quote does not belong to this Deal."))
    if int(quotation.docstatus or 0) != 0:
        frappe.throw(_("Only a draft quote can be submitted as an Opt-In summary."))

    pricing = _quote_pricing_rows(quotation)
    if not pricing:
        frappe.throw(_("Add at least one quote line before submitting the Opt-In summary."))

    deal_doc = frappe.get_doc("CRM Deal", deal)
    contact = {
        "first_name": frappe.utils.cstr(deal_doc.get("first_name") or "").strip(),
        "last_name": frappe.utils.cstr(deal_doc.get("last_name") or "").strip(),
        "email": frappe.utils.cstr(deal_doc.get("email") or "").strip().lower(),
        "mobile_no": frappe.utils.cstr(deal_doc.get("mobile_no") or "").strip(),
        "organisation": frappe.utils.cstr(deal_doc.get("organization") or "").strip(),
    }
    payload = {
        "contact": contact,
        "facilities": pricing,
        "pricing": pricing,
        "committed": True,
        "quote": quotation.name,
        "submitted_by": frappe.session.user,
    }

    submission = frappe.new_doc("CRM Opt-In Submission")
    submission.naming_series = "OIS-.YYYY.-"

    submission.status = "Processed"
    submission.network_slug = network_slug
    submission.submitter_email = contact["email"]
    submission.submitted_at = frappe.utils.now_datetime()
    submission.deal = deal
    submission.raw_json = json.dumps(payload)
    submission.save(ignore_permissions=True)  # SYSTEM-INTERNAL

    quotation.crm_sent = 1
    quotation.save(ignore_permissions=True)  # SYSTEM-INTERNAL
    deal_doc.optin_submission = submission.name
    deal_doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
    frappe.db.commit()

    return {"submission_ref": submission.name, "quote": quotation.name}


@frappe.whitelist()
def build_ois_quote(deal):
    """
    Create or refresh the Quotation for an OIS-sourced Deal where the quote
    step was missed or failed during _process_submission.

    Requires Sales Manager or System Manager. Idempotent — if a Quotation
    already exists for this deal, returns its name without creating a duplicate.
    Returns {"quote": <quotation_name>}.
    """
    deal = frappe.utils.cstr(deal).strip()

    user = frappe.session.user
    roles = frappe.get_roles(user)
    if not (
        "System Manager" in roles
        or user == "Administrator"
        or "Sales Manager" in roles
    ):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    submission_ref = frappe.db.get_value("CRM Deal", deal, "optin_submission")
    if not submission_ref:
        frappe.throw(_("Deal has no linked Opt-In Submission"))

    sub = frappe.get_doc("CRM Opt-In Submission", submission_ref)
    payload = json.loads(sub.raw_json or "{}")
    pricing = payload.get("pricing") or []

    # Idempotent: return existing quote if one already exists for this deal
    existing = frappe.get_list(
        "Quotation",
        filters={"crm_deal": deal},
        fields=["name"],
        limit=1,
        ignore_permissions=True,  # SYSTEM-INTERNAL
    )
    if existing:
        return {"quote": existing[0].name}

    if not pricing:
        frappe.throw(_("No pricing rows found in the submission payload"))

    from crm.api.quotes import _ensure_customer

    # Resolve the customer name from the linked lead's organisation
    org_name = frappe.db.get_value("CRM Lead", sub.lead, "organization") or ""
    customer_name = _ensure_customer(org_name)

    q = frappe.get_doc({
        "doctype": "Quotation",
        "quotation_to": "Customer",
        "party_name": customer_name,
        "company": frappe.db.get_single_value("Global Defaults", "default_company"),
        "transaction_date": frappe.utils.today(),
        "valid_till": frappe.utils.add_days(frappe.utils.today(), 30),
        "currency": "KES",
        "order_type": "Sales",
        "crm_deal": deal,
    })

    for prod in pricing:
        q.append("items", {
            "item_code": frappe.utils.cstr(prod.get("item_code", "")),
            "item_name": "CareverseHIMS - %s" % frappe.utils.cstr(
                prod.get("facility_name", "")
            ),
            "description": "KEPH %s - Annual Subscription" % frappe.utils.cstr(
                prod.get("keph_level", "")
            ),
            "qty": 1,
            "rate": float(prod.get("annual_kes") or 0),
            "uom": "Nos",
        })

    # The opt-in quote is pre-Sent: the customer already accepted this pricing
    # in the wizard, so it is immediately Accept-able without a manual Send.
    q.crm_sent = 1

    q.flags.ignore_permissions = True  # SYSTEM-INTERNAL
    q.flags.ignore_validate = True
    q.flags.ignore_mandatory = True
    q.set_missing_values()
    # ignore_validate skips the normal validate→calculate chain, so compute
    # item amounts + net/grand totals explicitly (else grand_total stays 0).
    q.calculate_taxes_and_totals()
    q.vat_amount = round((q.net_total or 0) * 0.16, 2)  # 16% VAT, tracked as custom field
    q.insert(ignore_mandatory=True)
    frappe.db.commit()

    return {"quote": q.name}
