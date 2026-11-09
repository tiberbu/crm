"""Refresh the facility agreement with namespaced VAT-aware totals."""

from crm.patches.v1_0.seed_network_facility_terms_v1 import execute as refresh_facility_template
from crm.setup.optin import ensure_default_terms


def execute():
	"""Update system-owned templates while preserving administrator custom terms."""
	refresh_facility_template()
	ensure_default_terms()
