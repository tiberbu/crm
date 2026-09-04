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


def get_contract_quote_summary(quote: Any) -> frappe._dict:
	"""Return the quote-year total and, for Opt-In bundles, the full commitment.

	The Quote PDF is generated from one yearly Quotation while its terms belong to
	the single multi-year agreement.  Expose both figures explicitly so a reader
	can distinguish the amount payable for this quote from the selected-term
	commitment shown in the contract.
	"""
	tax_summary = get_quotation_tax_summary(quote)
	result = frappe._dict(
		{
			"quote_net_total": tax_summary.net_total,
			"quote_vat_amount": tax_summary.vat_amount,
			"quote_grand_total": tax_summary.grand_total,
			"vat_label": tax_summary.vat_label,
			"has_multi_year": False,
			"commitment_years_label": "",
			"commitment_net_total": tax_summary.net_total,
			"commitment_vat_amount": tax_summary.vat_amount,
			"commitment_grand_total": tax_summary.grand_total,
		}
	)
	deal = frappe.utils.cstr(quote.get("crm_deal") or "").strip()
	if not deal:
		return result
	try:
		from crm.api.optin import build_tc_context_for_deal

		context = build_tc_context_for_deal(deal) or {}
		years = frappe.utils.cint(context.get("commitment_years") or 1)
		if years > 1:
			result.update(
				{
					"has_multi_year": True,
					"commitment_years_label": context.get("commitment_years_label") or "%s years" % years,
					"commitment_net_total": context.get("contract_commitment_excl_vat") or 0,
					"commitment_grand_total": context.get("contract_commitment_incl_vat") or 0,
				}
			)
			result["commitment_vat_amount"] = round(
				result["commitment_grand_total"] - result["commitment_net_total"], 2
			)
	except Exception:
		# Printing the quote must remain available when an old deal has no stored
		# Opt-In pricing payload. The yearly totals above are still authoritative.
		pass
	return result


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
	"""Render terms for the standard print format without changing executed history."""
	# Fully executed agreements are immutable.  The standard print format calls
	# this helper directly, so it must make the same snapshot-vs-live decision as
	# the API/PDF path instead of always re-rendering the current default T&C.
	if frappe.utils.cstr(contract.get("status") or "").strip() == "Fully Executed":
		return Markup(
			frappe.utils.cstr(contract.get("contract_html_snapshot") or contract.get("contract_html") or "")
		)
	from crm.api.contracts import _regenerate_contract_body

	return Markup(
		_regenerate_contract_body(contract) or frappe.utils.cstr(contract.get("contract_html") or "")
	)
