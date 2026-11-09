"""Partner Portal Pricing APIs.

Provides endpoints to:
1. Configure custom Year 1-5 pricing for a facility under a partner network (POST, idempotent).
2. Fetch/search custom Year 1-5 pricing for facilities (GET).
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from crm.partner_portal.utils import (
	check_idempotency,
	decode_json,
	normalize_pricing_payload,
	resolve_keph_item_code,
	resolve_network,
	resolve_or_create_facility,
	store_idempotency,
)
from crm.utils.onboarding_source import is_network_optin_membership


def _assert_portal_access(network_doc=None, partner_id=None):
	"""Verify that the caller has permission to access the partner portal."""
	user = frappe.session.user
	if user and user != "Guest":
		roles = frappe.get_roles(user)
		if any(r in roles for r in ("System Manager", "Sales Manager", "Partner RM", "Administrator")):
			return True
		if "Network Coordinator" in roles:
			if network_doc and frappe.db.exists(
				"CRM Network Coordinator",
				{"parent": network_doc.name, "user": user},
			):
				return True
			# If no network doc yet, permit coordinator to proceed to validation
			return True

	# For guest callers, require a valid enabled partner_id / network
	if network_doc and network_doc.enabled:
		return True
	if partner_id:
		net = resolve_network(partner_id)
		if net and net.enabled:
			return True

	frappe.throw(_("Access denied. Please authenticate or provide a valid Partner ID."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def configure_facility_pricing(
	facility: Any,
	partner_id: Any,
	pricing: Any = None,
	price_lists: Any = None,
	idempotency_key: Any = None,
	contact_name: Any = None,
	contact_email: Any = None,
	contact_phone: Any = None,
	currency: Any = "KES",
	**kwargs,
) -> dict[str, Any]:
	"""
	Configure custom Year 1-5 pricing for a facility under a partner network.

	Idempotent: Repeating with the same idempotency_key returns cached response.
	Repeating with identical pricing updates or re-confirms existing state.

	Args:
	    facility: Facility identifier (MFL code, facility name, docname, or dict).
	    partner_id: Six-digit partner ID or network name/slug.
	    pricing: Custom Year 1-5 pricing (dict, list, or JSON).
	    price_lists: Alternative alias for pricing.
	    idempotency_key: Optional client-provided idempotency key.
	    currency: Pricing currency (default 'KES').

	Returns:
	    Dict with facility, network, price_lists, and pricing_by_year.
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

	pricing_payload = pricing if pricing is not None else price_lists
	if not pricing_payload and "rates" in kwargs:
		pricing_payload = kwargs["rates"]
	if not pricing_payload:
		frappe.throw(_("Pricing details for Years 1-5 are required."), frappe.ValidationError)

	facility_doc = resolve_or_create_facility(facility, auto_create=True)
	currency_str = frappe.utils.cstr(currency or "KES").strip()

	price_lists_dict, pricing_by_year = normalize_pricing_payload(
		pricing_payload,
		facility_doc=facility_doc,
		network_doc=network_doc,
		currency=currency_str,
	)

	# Update or add membership on facility
	membership_found = False
	for mem in facility_doc.memberships or []:
		# Negotiated pricing belongs on the Network Opt-In row, never a Partner Coupon row.
		if mem.network == network_doc.name and is_network_optin_membership(mem):
			membership_found = True
			mem.price_list_override = price_lists_dict.get("1") or ""
			mem.price_list_overrides_json = json.dumps(price_lists_dict, separators=(",", ":"))
			if contact_name:
				mem.contact_name = frappe.utils.cstr(contact_name).strip()
			if contact_email:
				mem.contact_email = frappe.utils.cstr(contact_email).strip().lower()
			if contact_phone:
				mem.contact_phone = frappe.utils.cstr(contact_phone).strip()
			break

	if not membership_found:
		# Inherit contact details from any existing membership or provide clean defaults
		fallback_name = facility_doc.facility_name
		fallback_email = ""
		fallback_phone = ""
		for m in facility_doc.memberships or []:
			if not is_network_optin_membership(m):
				continue
			if getattr(m, "contact_email", None):
				fallback_email = m.contact_email
			if getattr(m, "contact_name", None):
				fallback_name = m.contact_name
			if getattr(m, "contact_phone", None):
				fallback_phone = m.contact_phone

		eff_name = frappe.utils.cstr(contact_name or fallback_name or facility_doc.facility_name).strip()
		clean_code = frappe.scrub(facility_doc.mfl_code or facility_doc.name or "facility").replace("_", "-")
		eff_email = frappe.utils.cstr(
			contact_email or fallback_email or f"info-{clean_code}@example.com"
		).strip().lower()
		eff_phone = frappe.utils.cstr(contact_phone or fallback_phone or "+254700000000").strip()

		facility_doc.append(
			"memberships",
			{
				"network": network_doc.name,
				"status": "Active",
				"contact_name": eff_name,
				"contact_email": eff_email,
				"contact_phone": eff_phone,
				"price_list_override": price_lists_dict.get("1") or "",
				"price_list_overrides_json": json.dumps(price_lists_dict, separators=(",", ":")),
			},
		)

	facility_doc.flags.skip_invitation = True
	facility_doc.save(ignore_permissions=True)
	frappe.db.commit()


	response = {
		"success": True,
		"message": "Custom Year 1-5 pricing successfully configured.",
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
			"slug": getattr(network_doc, "slug", ""),
		},
		"price_lists": price_lists_dict,
		"pricing_by_year": pricing_by_year,
	}

	if idempotency_key:
		store_idempotency(idempotency_key, response)

	return response


# Alias for backward compatibility and intuitive naming
set_facility_pricing = configure_facility_pricing


@frappe.whitelist(methods=["GET", "POST"])
def get_facility_pricing(
	facility: Any = None,
	search: Any = None,
	partner_id: Any = None,
	year: Any = None,
) -> dict[str, Any]:
	"""
	Search and fetch custom Year 1-5 pricing for facilities.

	Args:
	    facility: Specific facility identifier (MFL code, facility name, docname).
	    search: Search term across facility name or MFL code.
	    partner_id: Optional Partner ID or network name/slug filter.
	    year: Optional specific year (1-5) filter.

	Returns:
	    Pricing information structured by year for the matched facilities.
	"""
	target_network = None
	if partner_id:
		target_network = resolve_network(partner_id)
		_assert_portal_access(network_doc=target_network)
	else:
		_assert_portal_access()

	filters = {}
	or_filters = {}

	facility_str = frappe.utils.cstr(facility or "").strip()
	search_str = frappe.utils.cstr(search or "").strip()

	if facility_str:
		# Search by docname, mfl_code, or exact facility_name
		if frappe.db.exists("CRM Pre-Qualified Facility", facility_str):
			filters["name"] = facility_str
		else:
			or_filters = [
				["CRM Pre-Qualified Facility", "mfl_code", "=", facility_str],
				["CRM Pre-Qualified Facility", "facility_name", "=", facility_str],
			]
	elif search_str:
		or_filters = [
			["CRM Pre-Qualified Facility", "facility_name", "like", f"%{search_str}%"],
			["CRM Pre-Qualified Facility", "mfl_code", "like", f"%{search_str}%"],
		]

	facility_rows = frappe.get_list(
		"CRM Pre-Qualified Facility",
		filters=filters if filters else None,
		or_filters=or_filters if or_filters else None,
		fields=["name", "facility_name", "mfl_code", "keph_level", "organization"],
		limit=50,
		ignore_permissions=True,
	)

	results = []
	for fac_row in facility_rows:
		fac_doc = frappe.get_doc("CRM Pre-Qualified Facility", fac_row.name)
		memberships = fac_doc.memberships or []
		if target_network:
			memberships = [m for m in memberships if m.network == target_network.name]

		if not memberships and target_network:
			# If facility exists but has no membership row yet for this network,
			# resolve default network pricing
			price_lists_dict, pricing_by_year = normalize_pricing_payload(
				{},
				facility_doc=fac_doc,
				network_doc=target_network,
			)
			results.append(
				{
					"facility": fac_row,
					"network": {
						"name": target_network.name,
						"partner_id": getattr(target_network, "partner_id", ""),
						"display_name": target_network.display_name,
					},
					"membership_status": "None",
					"price_lists": price_lists_dict,
					"pricing_by_year": _filter_year(pricing_by_year, year),
				}
			)
			continue

		for mem in memberships:
			overrides_data = decode_json(getattr(mem, "price_list_overrides_json", "{}"), {})
			legacy_pl = getattr(mem, "price_list_override", "") or ""
			if not overrides_data and legacy_pl:
				overrides_data = {"1": legacy_pl}

			# Resolve network doc for this membership
			net_doc = target_network
			if not net_doc:
				try:
					net_doc = frappe.get_doc("CRM Opt-In Network", mem.network)
				except Exception:
					net_doc = None

			price_lists_dict, pricing_by_year = normalize_pricing_payload(
				overrides_data,
				facility_doc=fac_doc,
				network_doc=net_doc,
			)

			results.append(
				{
					"facility": fac_row,
					"network": {
						"name": mem.network,
						"partner_id": getattr(net_doc, "partner_id", "") if net_doc else "",
						"display_name": getattr(net_doc, "display_name", mem.network) if net_doc else mem.network,
					},
					"membership_status": mem.status,
					"contact_name": mem.contact_name,
					"contact_email": mem.contact_email,
					"price_lists": price_lists_dict,
					"pricing_by_year": _filter_year(pricing_by_year, year),
				}
			)

	if facility_str and len(results) == 1:
		single = results[0]
		return {
			"success": True,
			"facility": single["facility"],
			"network": single["network"],
			"membership_status": single.get("membership_status"),
			"price_lists": single["price_lists"],
			"pricing_by_year": single["pricing_by_year"],
			"results": results,
			"total": 1,
		}

	return {
		"success": True,
		"results": results,
		"total": len(results),
	}


def _filter_year(pricing_by_year: list[dict[str, Any]], year: Any) -> list[dict[str, Any]]:
	if not year:
		return pricing_by_year
	try:
		yr_int = int(year)
		return [p for p in pricing_by_year if p["year_number"] == yr_int]
	except (ValueError, TypeError):
		return pricing_by_year
