"""Shared source labels and canonical route builders across onboarding journeys.

Keep the two facility onboarding journeys strictly separated:
1. Network Opt-In (`/opt-in`): partner-invited multi-year negotiated pricing, quotation, and digital contract signature flow.
2. Self-Facility Onboarding (`/facility-onboarding`): public Value Express self-service identity verification and token-package purchase flow.
"""

from urllib.parse import urlencode

import frappe

NETWORK_OPTIN_CONTACT_SOURCE = "Network Opt-In"
SELF_ONBOARDING_CONTACT_SOURCE = "Self-Onboarding"

OPTIN_ROUTE = "/opt-in"
SELF_ONBOARDING_ROUTE = "/facility-onboarding"


def is_self_onboarding_contact(membership) -> bool:
	"""Customer-linked memberships belong to Self-Onboarding (Value Express, Partner Coupon).

	The Customer link is the only journey discriminator. Writers never move a row between
	journeys: Self-Onboarding appends its own customer-linked row and Network Opt-In
	(admin, Partner Portal) appends its own row without one.
	"""
	if not membership:
		return False
	if isinstance(membership, dict):
		customer = membership.get("customer")
	else:
		customer = getattr(membership, "customer", None)
	return bool(str(customer or "").strip())


def is_network_optin_membership(membership) -> bool:
	"""Memberships without a Customer belong to the Network Opt-In contract journey."""
	return bool(membership) and not is_self_onboarding_contact(membership)


def build_network_optin_invitation_url(
	network_slug: str,
	facility_name: str = "",
	base_url: str | None = None,
) -> str:
	"""Build the canonical `/opt-in` invitation URL for a Network Opt-In membership."""
	root = (base_url if base_url is not None else frappe.utils.get_url()).rstrip("/")
	params = {"network": frappe.utils.cstr(network_slug).strip()}
	facility_str = frappe.utils.cstr(facility_name).strip()
	if facility_str:
		params["facility"] = facility_str
	return f"{root}{OPTIN_ROUTE}?{urlencode(params)}"

