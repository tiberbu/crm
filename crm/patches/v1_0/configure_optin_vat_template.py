"""Select the unambiguous company VAT template for existing Opt-In sites."""

import frappe

from crm.utils.quotation_tax import list_company_tax_templates


def execute():
	if not frappe.db.table_exists("CRM Opt-In Settings") or not frappe.db.has_column(
		"CRM Opt-In Settings", "sales_tax_template"
	):
		return

	settings = frappe.get_single("CRM Opt-In Settings")
	if not settings.sales_tax_template:
		templates = list_company_tax_templates()
		defaults = [row.name for row in templates if frappe.utils.cint(row.is_default)]
		if len(defaults) == 1:
			settings.sales_tax_template = defaults[0]
		elif len(templates) == 1:
			settings.sales_tax_template = templates[0].name
		if settings.sales_tax_template:
			settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL

	# The rate belongs to the configured template; keeping 16% in the custom-field
	# label makes a legitimate configuration change look like a calculation bug.
	custom_field = "Quotation-vat_amount"
	if frappe.db.exists("Custom Field", custom_field):
		frappe.db.set_value("Custom Field", custom_field, "label", "VAT Amount", update_modified=False)

	frappe.clear_cache(doctype="CRM Opt-In Settings")
