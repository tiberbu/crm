"""Add the Network rate and ERPNext Supplier payout mappings."""

from crm.finance.setup import ensure_network_payout_mappings


def execute():
	ensure_network_payout_mappings()
