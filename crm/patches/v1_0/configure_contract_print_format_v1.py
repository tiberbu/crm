"""Make CRM Contract Standard the single default contract PDF format."""

from crm.setup.optin import ensure_contract_print_format


def execute():
	ensure_contract_print_format()
