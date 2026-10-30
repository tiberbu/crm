"""Fill missing Value Express packages, extra tokens and landing contacts on existing sites."""

from crm.setup.onboarding_catalogue import ensure_default_catalogue


def execute():
	ensure_default_catalogue()
