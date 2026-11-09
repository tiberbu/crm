"""Backfill native tax rows and VAT totals on editable quotations only."""

import frappe

from crm.utils.quotation_tax import apply_quotation_taxes, get_vat_tax_configuration


def execute():
	# Quotation belongs to ERPNext; CRM-only installations must remain migratable.
	if not all(
		frappe.db.exists("DocType", doctype)
		for doctype in ("Quotation", "Sales Taxes and Charges Template", "Sales Taxes and Charges")
	):
		return
	if not all(
		frappe.db.has_column("Quotation", fieldname) for fieldname in ("taxes_and_charges", "vat_amount")
	):
		return

	# Validate once before changing data. Ambiguous configuration leaves existing
	# records untouched and asks an administrator to select the template explicitly.
	try:
		get_vat_tax_configuration()
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"backfill_quotation_vat: VAT template configuration is incomplete",
		)
		return

	quote_names = frappe.get_all(
		"Quotation",
		filters={"docstatus": 0, "crm_deal": ["!=", ""]},
		pluck="name",
		limit_page_length=0,
	)
	for quote_name in quote_names:
		quote = frappe.get_doc("Quotation", quote_name)
		if (
			quote.taxes_and_charges
			and quote.get("taxes")
			and frappe.utils.flt(quote.total_taxes_and_charges)
			and frappe.utils.flt(quote.vat_amount)
		):
			continue
		quote.flags.ignore_permissions = True  # SYSTEM-INTERNAL
		quote.flags.ignore_validate = True
		quote.flags.ignore_mandatory = True
		apply_quotation_taxes(quote, quote.taxes_and_charges or None)
		quote.save(ignore_permissions=True)  # SYSTEM-INTERNAL

	# Submitted/cancelled quotations are historical commercial records. Deliberately
	# do not rewrite their tax rows or totals in a migration; new prints calculate
	# their VAT display from the configured template without changing audit data.
