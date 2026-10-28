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


def is_self_onboarding_contact(membership):
	"""Customer-linked facility memberships belong to Self-Onboarding."""
	if not membership:
		return False
	if isinstance(membership, dict):
		customer = membership.get("customer")
	else:
		customer = getattr(membership, "customer", None)
	return bool(str(customer or "").strip())


def is_network_optin_membership(membership) -> bool:
	"""Return True if a membership row is explicitly configured for the Network Opt-In contract journey."""
	if not membership or is_self_onboarding_contact(membership):
		return False
	if isinstance(membership, dict):
		override = membership.get("price_list_override")
		overrides_json = membership.get("price_list_overrides_json")
		flags = membership.get("flags") or {}
	else:
		override = getattr(membership, "price_list_override", None)
		overrides_json = getattr(membership, "price_list_overrides_json", None)
		flags = getattr(membership, "flags", None) or {}
	if flags.get("force_optin_invitation"):
		return True
	has_override = bool(str(override or "").strip())
	has_overrides_json = bool(str(overrides_json or "").strip() and str(overrides_json).strip() != "{}")
	return has_override or has_overrides_json


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

