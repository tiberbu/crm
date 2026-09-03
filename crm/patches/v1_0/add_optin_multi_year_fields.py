"""Additive metadata for multi-year Opt-In pricing and billing.

The portal historically stored one price list, quotation and contract link.  The
new fields deliberately keep those columns and store the expanded bundle as JSON
so v15 sites (and CRM-only installs without ERPNext) can migrate safely.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from crm.utils.optin_bundles import billing_schedule


def _add(fields_by_doctype):
	available = {
		doctype: fields
		for doctype, fields in fields_by_doctype.items()
		if frappe.db.exists("DocType", doctype)
	}
	if available:
		create_custom_fields(available, ignore_validate=True)


def execute():
	_add(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "optional_services_price_list",
					"fieldtype": "Link",
					"label": "Optional Services Price List",
					"options": "Price List",
					"insert_after": "default_price_list",
					"description": "Curated selling list used to populate optional hardware and service choices. These items are informational and are not added to subscription quotations.",
				},
			],
			"CRM Opt-In Network": [
				{
					"fieldname": "price_lists_json",
					"fieldtype": "Long Text",
					"label": "Yearly Price Lists",
					"read_only": 0,
					"description": "JSON list of ordered yearly price lists: [{year_number, price_list, label, enabled}]. The legacy Price List Override remains the fallback.",
				},
				{
					"fieldname": "first_invoice_offset_months",
					"fieldtype": "Int",
					"label": "First Invoice Offset (Months)",
					"default": "3",
					"description": "Months after Opt-In submission before the first quarterly invoice is issued.",
				},
				{
					"fieldname": "optional_services_price_list",
					"fieldtype": "Link",
					"label": "Optional Services Price List",
					"options": "Price List",
					"description": "Optional network-specific override for the curated services list.",
				},
			],
			"CRM Facility Membership": [
				{
					"fieldname": "price_list_overrides_json",
					"fieldtype": "Long Text",
					"label": "Yearly Price List Overrides",
					"description": "JSON map of year number to selling Price List. A blank map preserves the legacy single override.",
				},
			],
			"CRM Opt-In Submission": [
				{
					"fieldname": "pricing_plans_json",
					"fieldtype": "Long Text",
					"label": "Yearly Pricing Plans",
					"read_only": 1,
					"description": "Server-authoritative yearly pricing and quotation bundle snapshot.",
				},
				{
					"fieldname": "optional_items_json",
					"fieldtype": "Long Text",
					"label": "Optional Services Information",
					"read_only": 1,
				},
				{
					"fieldname": "billing_schedule_json",
					"fieldtype": "Long Text",
					"label": "Quarterly Billing Schedule",
					"read_only": 1,
				},
				{
					"fieldname": "quote_names_json",
					"fieldtype": "Long Text",
					"label": "Yearly Quotations",
					"read_only": 1,
				},
			],
			"CRM Contract": [
				{
					"fieldname": "quote_names_json",
					"fieldtype": "Long Text",
					"label": "Yearly Quotations",
					"read_only": 1,
				},
				{
					"fieldname": "contract_html_snapshot",
					"fieldtype": "Long Text",
					"label": "Accepted Contract HTML Snapshot",
					"read_only": 1,
					"no_copy": 1,
					"description": "Immutable copy of the terms accepted at generation/signing time.",
				},
				{
					"fieldname": "current_tc_document_hash",
					"fieldtype": "Data",
					"label": "Current T&C Hash",
					"read_only": 1,
					"no_copy": 1,
				},
			],
			"Quotation": [
				{
					"fieldname": "crm_optin_submission",
					"fieldtype": "Link",
					"label": "Opt-In Submission",
					"options": "CRM Opt-In Submission",
					"insert_after": "crm_deal",
				},
				{
					"fieldname": "crm_optin_year",
					"fieldtype": "Int",
					"label": "Opt-In Year",
					"insert_after": "crm_optin_submission",
				},
				{
					"fieldname": "crm_optin_bundle_key",
					"fieldtype": "Data",
					"label": "Opt-In Bundle Key",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "crm_optin_year",
				},
			],
			"Sales Order": [
				{
					"fieldname": "crm_optin_submission",
					"fieldtype": "Link",
					"label": "Opt-In Submission",
					"options": "CRM Opt-In Submission",
				},
				{
					"fieldname": "crm_optin_year",
					"fieldtype": "Int",
					"label": "Opt-In Year",
				},
				{
					"fieldname": "crm_optin_quarter",
					"fieldtype": "Int",
					"label": "Opt-In Quarter",
				},
				{
					"fieldname": "crm_optin_quotation",
					"fieldtype": "Link",
					"label": "Opt-In Quotation",
					"options": "Quotation",
				},
				{
					"fieldname": "crm_optin_billing_key",
					"fieldtype": "Data",
					"label": "Opt-In Billing Key",
					"read_only": 1,
					"no_copy": 1,
				},
			],
			"Sales Invoice": [
				{
					"fieldname": "crm_optin_submission",
					"fieldtype": "Link",
					"label": "Opt-In Submission",
					"options": "CRM Opt-In Submission",
				},
				{
					"fieldname": "crm_optin_year",
					"fieldtype": "Int",
					"label": "Opt-In Year",
				},
				{
					"fieldname": "crm_optin_quarter",
					"fieldtype": "Int",
					"label": "Opt-In Quarter",
				},
				{
					"fieldname": "crm_optin_quotation",
					"fieldtype": "Link",
					"label": "Opt-In Quotation",
					"options": "Quotation",
				},
				{
					"fieldname": "crm_optin_billing_key",
					"fieldtype": "Data",
					"label": "Opt-In Billing Key",
					"read_only": 1,
					"no_copy": 1,
				},
			],
		}
	)

	# A network can be migrated repeatedly. Preserve a configured value and only
	# normalize an empty offset to the documented default.
	if frappe.db.exists("DocType", "CRM Opt-In Network") and frappe.db.has_column(
		"CRM Opt-In Network", "first_invoice_offset_months"
	):
		frappe.db.sql(
			"UPDATE `tabCRM Opt-In Network` SET first_invoice_offset_months = 3 "
			"WHERE IFNULL(first_invoice_offset_months, 0) <= 0"
		)

	# Preserve a truthful single-year representation for historical submissions.
	# This never changes existing quote/contract links or signatures and is safe to
	# rerun after a partially completed migration.
	if frappe.db.exists("DocType", "CRM Opt-In Submission") and frappe.db.has_column(
		"CRM Opt-In Submission", "raw_json"
	):
		fields = ["name", "raw_json", "submitted_at"]
		# CRM Opt-In Submission historically has no native ``quote`` field on
		# every site; some deployments added one as a custom field.  Do not ask
		# MariaDB for a column that is not present during a rolling migration.
		if frappe.db.has_column("CRM Opt-In Submission", "quote"):
			fields.append("quote")
		for field in ("pricing_plans_json", "quote_names_json", "billing_schedule_json"):
			if frappe.db.has_column("CRM Opt-In Submission", field):
				fields.append(field)
		for row in frappe.get_list(
			"CRM Opt-In Submission", fields=fields, limit_page_length=0, ignore_permissions=True
		):
			data = {}
			try:
				data = frappe.parse_json(row.raw_json or "{}")
			except Exception:
				continue
			if not isinstance(data, dict):
				continue
			updates = {}
			pricing = data.get("pricing") or data.get("facilities") or []
			if "pricing_plans_json" in row and not row.get("pricing_plans_json") and pricing:
				updates["pricing_plans_json"] = frappe.as_json(
					[{"year_number": 1, "label": "Year 1", "facilities": pricing}]
				)
			if "quote_names_json" in row and not row.get("quote_names_json") and row.get("quote"):
				updates["quote_names_json"] = frappe.as_json([row.quote])
			if "billing_schedule_json" in row and not row.get("billing_schedule_json") and row.get("submitted_at"):
				updates["billing_schedule_json"] = frappe.as_json(
					billing_schedule(row.submitted_at, [1], 3, key_prefix=row.name)
				)
			if updates:
				frappe.db.set_value("CRM Opt-In Submission", row.name, updates, update_modified=False)

	if frappe.db.exists("DocType", "CRM Contract") and frappe.db.has_column(
		"CRM Contract", "contract_html_snapshot"
	):
		for row in frappe.get_list(
			"CRM Contract", fields=["name", "contract_html", "contract_html_snapshot"], limit_page_length=0, ignore_permissions=True
		):
			if row.contract_html and not row.contract_html_snapshot:
				frappe.db.set_value(
					"CRM Contract", row.name, "contract_html_snapshot", row.contract_html, update_modified=False
				)

	frappe.clear_cache()
