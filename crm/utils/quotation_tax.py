"""Configured VAT handling for ERPNext Quotations and the Opt-In journey.

The Sales Taxes and Charges Template is the single source of truth.  Opt-In
prices are net rates, so the selected template must be one, additive VAT row on
the quotation net total.  Rejecting an ambiguous template is intentional: a
wrong grand total is worse than a clear configuration error.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr, flt

_TAX_TEMPLATE = "Sales Taxes and Charges Template"
_OPTIN_SETTINGS = "CRM Opt-In Settings"


def _erpnext_taxing_is_available() -> bool:
	return all(
		frappe.db.exists("DocType", doctype)
		for doctype in ("Quotation", "Sales Taxes and Charges Template", "Sales Taxes and Charges")
	)


def _ensure_erpnext_taxing() -> None:
	if not _erpnext_taxing_is_available():
		frappe.throw(
			_("ERPNext quotation taxes are not available on this site."),
			frappe.ConfigurationError,
		)


def _settings_tax_template() -> str:
	"""Return the optional template selected in Opt-In Settings.

	The column check keeps this callable during an update where Python is deployed
	before the new single-doctype field has been migrated.
	"""
	if not frappe.db.table_exists(_OPTIN_SETTINGS) or not frappe.db.has_column(
		_OPTIN_SETTINGS, "sales_tax_template"
	):
		return ""
	return cstr(frappe.db.get_single_value(_OPTIN_SETTINGS, "sales_tax_template") or "").strip()


def _is_vat_row(tax: Any) -> bool:
	text = " ".join(cstr(tax.get(fieldname) or "") for fieldname in ("description", "account_head")).lower()
	return "vat" in text


def _format_rate(rate: float) -> str:
	return "{:g}".format(rate)


def _candidate_tax_template(company: str) -> str:
	"""Find an unambiguous fallback for sites not yet explicitly configured."""
	rows = frappe.get_all(
		_TAX_TEMPLATE,
		filters={"company": company, "disabled": 0},
		fields=["name", "is_default"],
		order_by="is_default desc, creation asc",
		limit_page_length=0,
	)
	defaults = [row.name for row in rows if frappe.utils.cint(row.is_default)]
	if len(defaults) == 1:
		return defaults[0]
	if len(rows) == 1:
		return rows[0].name
	if not rows:
		frappe.throw(
			_("Configure an enabled Sales Taxes and Charges Template for company {0}.").format(company),
			frappe.ConfigurationError,
		)
	frappe.throw(
		_(
			"Select the VAT Sales Taxes and Charges Template in CRM Opt-In Settings; "
			"multiple enabled templates exist for company {0}."
		).format(company),
		frappe.ConfigurationError,
	)


def get_vat_tax_configuration(company: str | None = None, tax_template: str | None = None) -> frappe._dict:
	"""Return the validated configured VAT template and its display metadata.

	Opt-In previews must equal the native quotation calculation.  The current
	product supports a single, non-inclusive ``On Net Total`` VAT row; this is the
	shape of Tiberbu's ``Kenya Tax - TB`` document.  Any other template is rejected
	instead of being silently approximated in the web form or a contract.
	"""
	_ensure_erpnext_taxing()
	company = cstr(company or frappe.db.get_single_value("Global Defaults", "default_company") or "").strip()
	if not company:
		frappe.throw(_("A default company is required to calculate VAT."), frappe.ConfigurationError)

	tax_template = cstr(tax_template or _settings_tax_template() or "").strip()
	if not tax_template:
		tax_template = _candidate_tax_template(company)
	if not frappe.db.exists(_TAX_TEMPLATE, tax_template):
		frappe.throw(
			_("The configured Sales Taxes and Charges Template does not exist."),
			frappe.ConfigurationError,
		)

	template = frappe.get_doc(_TAX_TEMPLATE, tax_template)
	if template.company != company or frappe.utils.cint(template.disabled):
		frappe.throw(
			_("The configured Sales Taxes and Charges Template is not enabled for company {0}.").format(
				company
			),
			frappe.ConfigurationError,
		)

	taxes = list(template.get("taxes") or [])
	vat_rows = [tax for tax in taxes if _is_vat_row(tax)]
	if len(taxes) != 1 or len(vat_rows) != 1:
		frappe.throw(
			_(
				"The Opt-In VAT template must contain exactly one VAT charge so portal, quote, "
				"email, and contract totals remain identical."
			),
			frappe.ConfigurationError,
		)

	vat = vat_rows[0]
	if vat.charge_type != "On Net Total" or frappe.utils.cint(vat.included_in_print_rate):
		frappe.throw(
			_("The Opt-In VAT charge must be an exclusive 'On Net Total' charge."),
			frappe.ConfigurationError,
		)
	rate = flt(vat.rate)
	if rate <= 0:
		frappe.throw(_("The configured VAT charge must have a positive rate."), frappe.ConfigurationError)

	return frappe._dict(
		{
			"company": company,
			"template": template.name,
			"vat_rate": rate,
			"vat_fraction": rate / 100,
			"vat_label": "VAT (%s%%)" % _format_rate(rate),
		}
	)


def calculate_vat_totals(
	net_total: float, company: str | None = None, tax_template: str | None = None
) -> frappe._dict:
	"""Calculate the exclusive VAT summary used before a Quotation exists."""
	configuration = get_vat_tax_configuration(company, tax_template)
	net_total = round(flt(net_total), 2)
	vat_amount = round(net_total * configuration.vat_fraction, 2)
	return frappe._dict(
		{
			**configuration,
			"net_total": net_total,
			"vat_amount": vat_amount,
			"grand_total": round(net_total + vat_amount, 2),
		}
	)


def apply_quotation_taxes(quotation: Any, tax_template: str | None = None) -> frappe._dict:
	"""Hydrate the configured template on a Quotation and recalculate native totals."""
	configuration = get_vat_tax_configuration(quotation.company, tax_template)

	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	quotation.taxes_and_charges = configuration.template
	quotation.set("taxes", get_taxes_and_charges(_TAX_TEMPLATE, configuration.template))
	quotation.calculate_taxes_and_totals()
	quotation.vat_amount = round(
		sum(flt(tax.tax_amount) for tax in quotation.get("taxes") or [] if _is_vat_row(tax)),
		2,
	)
	return configuration


def quotation_tax_summary(quotation: Any) -> frappe._dict:
	"""Return an accurate VAT summary without mutating an existing quotation."""
	configuration = get_vat_tax_configuration(
		quotation.get("company"), quotation.get("taxes_and_charges") or None
	)
	net_total = round(flt(quotation.get("net_total")), 2)
	tax_rows = quotation.get("taxes") or []
	vat_amount = round(
		sum(flt(tax.tax_amount) for tax in tax_rows if _is_vat_row(tax)),
		2,
	)
	if not vat_amount:
		vat_amount = round(flt(quotation.get("vat_amount")), 2)
	if not vat_amount and net_total:
		vat_amount = round(net_total * configuration.vat_fraction, 2)

	has_native_taxes = bool(tax_rows and flt(quotation.get("total_taxes_and_charges")))
	grand_total = (
		round(flt(quotation.get("grand_total")), 2) if has_native_taxes else round(net_total + vat_amount, 2)
	)
	return frappe._dict(
		{
			**configuration,
			"net_total": net_total,
			"vat_amount": vat_amount,
			"grand_total": grand_total,
		}
	)


def list_company_tax_templates(company: str | None = None) -> list[frappe._dict]:
	"""List enabled company templates for the Opt-In settings picker."""
	if not _erpnext_taxing_is_available():
		return []
	company = cstr(company or frappe.db.get_single_value("Global Defaults", "default_company") or "").strip()
	if not company:
		return []
	return frappe.get_all(
		_TAX_TEMPLATE,
		filters={"company": company, "disabled": 0},
		fields=["name", "is_default"],
		order_by="is_default desc, name asc",
		limit_page_length=0,
	)
