"""Install the CRM Finance print formats for existing ERPNext sites."""

from crm.finance.print_formats import ensure_finance_print_formats


def execute():
	ensure_finance_print_formats()
