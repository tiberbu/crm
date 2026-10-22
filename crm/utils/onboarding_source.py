"""Shared source labels for facility contacts across onboarding journeys."""

NETWORK_OPTIN_CONTACT_SOURCE = "Network Opt-In"
SELF_ONBOARDING_CONTACT_SOURCE = "Self-Onboarding"


def is_self_onboarding_contact(membership):
	"""Customer-linked facility memberships belong to Self-Onboarding."""
	if not membership:
		return False
	if isinstance(membership, dict):
		customer = membership.get("customer")
	else:
		customer = getattr(membership, "customer", None)
	return bool(str(customer or "").strip())
