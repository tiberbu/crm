"""Small, explicit helpers exposed to Frappe's print-format Jinja environment."""

from __future__ import annotations

from typing import Any

import frappe
from markupsafe import Markup


def get_quotation_tax_summary(quote: Any) -> frappe._dict:
	"""Return presentation-safe VAT totals for a quotation print format.

	The tax-template name is an accounting implementation detail.  Print formats
	need the friendly, configured VAT label and must also render a correct payable
	total for legacy quotations that predate native tax rows.  A malformed legacy
	configuration should not make an otherwise printable quotation unavailable, so
	the stored document values remain a conservative fallback.
	"""
	from crm.utils.quotation_tax import quotation_tax_summary

	try:
		return quotation_tax_summary(quote)
	except Exception:
		net_total = frappe.utils.flt(quote.get("net_total"))
		vat_amount = frappe.utils.flt(quote.get("vat_amount") or quote.get("total_taxes_and_charges"))
		vat_rate = 0.0
		for tax in quote.get("taxes") or []:
			tax_text = " ".join(
				frappe.utils.cstr(tax.get(fieldname) or "") for fieldname in ("description", "account_head")
			).lower()
			if "vat" in tax_text:
				vat_rate = frappe.utils.flt(tax.get("rate"))
				break
		if not vat_amount and net_total and vat_rate:
			vat_amount = round(net_total * vat_rate / 100, 2)
		grand_total = frappe.utils.flt(quote.get("grand_total"))
		if vat_amount and grand_total <= net_total:
			grand_total = round(net_total + vat_amount, 2)
		return frappe._dict(
			{
				"net_total": net_total,
				"vat_amount": vat_amount,
				"grand_total": grand_total,
				"vat_rate": vat_rate,
				"vat_label": "VAT (%s%%)" % "{:g}".format(vat_rate) if vat_rate else "VAT",
			}
		)


def render_current_terms_for_quote(quote: Any) -> Markup:
	"""Render the latest selected Terms document for an Opt-In quotation print.

	A Quotation's ``terms`` field is a copy made when it is saved, so using it in a
	print format leaves later Terms & Conditions edits invisible.  Opt-In quotes
	therefore resolve their selected/current source document at print time.  A
	non-Opt-In quotation keeps its ordinary per-document Terms value.
	"""
	deal = frappe.utils.cstr(quote.get("crm_deal") or "").strip()
	if not deal:
		return Markup(frappe.utils.cstr(quote.get("terms") or ""))

	tc_name = frappe.utils.cstr(quote.get("tc_name") or "").strip()
	if not tc_name:
		tc_name = frappe.utils.cstr(
			frappe.db.get_single_value("CRM Opt-In Settings", "active_tc_document") or ""
		).strip()
	if not tc_name or not frappe.db.exists("Terms and Conditions", tc_name):
		return Markup(frappe.utils.cstr(quote.get("terms") or ""))

	from crm.api.optin import build_tc_context_for_deal

	context = build_tc_context_for_deal(deal) or {}
	if not context:
		return Markup(frappe.utils.cstr(quote.get("terms") or ""))
	context.setdefault("quote", quote)
	return Markup(
		frappe.render_template(frappe.get_doc("Terms and Conditions", tc_name).terms or "", context)
	)


def render_current_terms_for_contract(contract: Any) -> Markup:
	"""Render the contract's selected Terms document for the standard print format."""
	from crm.api.contracts import _regenerate_contract_body

	return Markup(_regenerate_contract_body(contract))
