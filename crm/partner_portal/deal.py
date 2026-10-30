"""Partner Portal Deal API.

Provides the 'deal-won' API endpoint to:
- Receive Facility, Partner ID, and Year 1-5 custom PriceList.
- Add or update the facility under the network with custom Year 1-5 pricing.
- Trigger the opt-in journey and signature flow via email notification.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility import (
	_send_membership_invitation,
)
from crm.partner_portal.pricing import _assert_portal_access
from crm.partner_portal.utils import (
	check_idempotency,
	normalize_pricing_payload,
	resolve_network,
	resolve_or_create_facility,
	store_idempotency,
)
from crm.utils.onboarding_source import (
	build_network_optin_invitation_url,
	is_network_optin_membership,
)



@frappe.whitelist(methods=["POST"])
def deal_won(
	facility: Any,
	partner_id: Any,
	price_lists: Any = None,
	pricing: Any = None,
	contact_email: Any = None,
	facility_email: Any = None,
	email: Any = None,
	contact_name: Any = None,
	contact_person: Any = None,
	contact_phone: Any = None,
	phone: Any = None,
	idempotency_key: Any = None,
	send_email: Any = 1,
	currency: Any = "KES",
	**kwargs,
) -> dict[str, Any]:
	"""
	Deal-Won endpoint: Adds facility under partner network with custom Yr 1-5 pricing
	and kicks off the Opt-In journey through signature notification.

	Args:
	    facility: Facility identifier (MFL code, name, docname, or dict).
	    partner_id: Partner six-digit ID or network slug/name.
	    price_lists: Yr 1-5 custom price lists or rates.
	    pricing: Alias for price_lists.
	    contact_email: Facility contact email (also facility_email, email).
	    contact_name: Facility contact person (also contact_person).
	    contact_phone: Facility contact phone (also phone).
	    idempotency_key: Client-provided idempotency key.
	    send_email: Whether to dispatch invitation email (default 1 / True).
	    currency: Pricing currency (default 'KES').

	Returns:
	    Full deal-won enrollment payload including membership, pricing, and invitation status.
	"""
	req = getattr(frappe.local, "request", None)
	header_key = req.headers.get("X-Idempotency-Key") if req and hasattr(req, "headers") else ""
	idempotency_key = frappe.utils.cstr(idempotency_key or header_key or "").strip()
	if idempotency_key:
		cached_result = check_idempotency(idempotency_key)
		if cached_result:
			cached_result["cached"] = True
			return cached_result

	network_doc = resolve_network(partner_id)
	_assert_portal_access(network_doc=network_doc)

	# Normalize contact payload
	email_val = frappe.utils.cstr(contact_email or facility_email or email or "").strip().lower()
	if not email_val or "@" not in email_val:
		frappe.throw(_("A valid facility contact email is required."), frappe.ValidationError)

	name_val = frappe.utils.cstr(contact_name or contact_person or "").strip()
	if not name_val:
		frappe.throw(_("A facility contact person name is required."), frappe.ValidationError)

	# Resolve or create Pre-Qualified Facility
	facility_doc = resolve_or_create_facility(facility, auto_create=True)
	currency_str = frappe.utils.cstr(currency or "KES").strip()

	phone_val = frappe.utils.cstr(contact_phone or phone or "").strip()
	if not phone_val:
		for m in getattr(facility_doc, "memberships", []) or []:
			if getattr(m, "contact_phone", None):
				phone_val = m.contact_phone
				break
	if not phone_val:
		phone_val = "+254700000000"

	# Normalize pricing payload
	pricing_payload = price_lists if price_lists is not None else pricing
	if not pricing_payload and "rates" in kwargs:
		pricing_payload = kwargs["rates"]
	if not pricing_payload:
		# Fall back to network defaults if partner omitted explicit pricing
		pricing_payload = {}

	# Configure custom Year 1-5 price lists
	price_lists_dict, pricing_by_year = normalize_pricing_payload(
		pricing_payload,
		facility_doc=facility_doc,
		network_doc=network_doc,
		currency=currency_str,
	)

	# Locate or append membership under this network
	membership_row = None
	for mem in facility_doc.memberships or []:
		# Only the facility's Network Opt-In row; a Self-Onboarding (Partner Coupon) row in the
		# same network belongs to the customer and is never rewritten here.
		if mem.network == network_doc.name and is_network_optin_membership(mem):
			membership_row = mem
			mem.contact_name = name_val
			mem.contact_email = email_val
			if phone_val:
				mem.contact_phone = phone_val
			mem.price_list_override = price_lists_dict.get("1") or ""
			mem.price_list_overrides_json = json.dumps(price_lists_dict, separators=(",", ":"))
			if mem.status != "Opted In":
				mem.status = "Active"
			break

	if not membership_row:
		membership_row = facility_doc.append(
			"memberships",
			{
				"network": network_doc.name,
				"status": "Active",
				"contact_name": name_val,
				"contact_email": email_val,
				"contact_phone": phone_val,
				"price_list_override": price_lists_dict.get("1") or "",
				"price_list_overrides_json": json.dumps(price_lists_dict, separators=(",", ":")),
			},
		)

	facility_doc.flags.skip_invitation = True
	facility_doc.save(ignore_permissions=True)
	frappe.db.commit()

	# Reload facility doc to get assigned membership name and persisted state
	facility_doc.reload()
	active_membership = next(
		(
			m
			for m in facility_doc.memberships
			if m.network == network_doc.name and is_network_optin_membership(m)
		),
		None,
	)
	if not active_membership:
		active_membership = membership_row

	# Trigger opt-in journey email notification & signature flow
	email_dispatched = False
	email_error = None
	should_send = frappe.utils.cint(send_email) if send_email is not None else 1

	if should_send:
		try:
			_send_membership_invitation(facility_doc, active_membership)
			email_dispatched = True
		except Exception as err:
			email_error = str(err)
			frappe.log_error(
				frappe.get_traceback(),
				f"partner_portal.deal_won: invitation email failed for {facility_doc.name}",
			)

	slug = getattr(network_doc, "slug", "") or network_doc.name
	invitation_url = build_network_optin_invitation_url(slug, facility_doc.facility_name)

	response = {
		"success": True,
		"message": _("Facility successfully enrolled in network with custom pricing and opt-in invitation dispatched."),
		"deal_won": True,
		"facility": {
			"name": facility_doc.name,
			"facility_name": facility_doc.facility_name,
			"mfl_code": facility_doc.mfl_code,
			"keph_level": facility_doc.keph_level,
		},
		"network": {
			"name": network_doc.name,
			"partner_id": getattr(network_doc, "partner_id", ""),
			"display_name": network_doc.display_name,
			"slug": slug,
		},
		"membership": {
			"name": getattr(active_membership, "name", ""),
			"status": getattr(active_membership, "status", "Active"),
			"contact_name": getattr(active_membership, "contact_name", name_val),
			"contact_email": getattr(active_membership, "contact_email", email_val),
			"contact_phone": getattr(active_membership, "contact_phone", phone_val),
			"invite_sent_at": getattr(active_membership, "invite_sent_at", None),
			"invite_email_queue": getattr(active_membership, "invite_email_queue", None),
		},
		"invitation_url": invitation_url,
		"price_lists": price_lists_dict,
		"pricing_by_year": pricing_by_year,
		"email_sent": email_dispatched,
		"email_error": email_error,
	}

	if idempotency_key:
		store_idempotency(idempotency_key, response)

	return response
