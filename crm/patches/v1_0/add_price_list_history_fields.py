"""Add structured price-list provenance and backfill legacy records safely."""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from crm.utils.price_list_history import HISTORY_FIELD, INITIAL_FIELD, set_snapshot, snapshot


def execute():
	# Quotation is supplied by ERPNext. CRM-only installations must remain
	# migratable when the optional commercial doctypes are not installed.
	if not frappe.db.exists("DocType", "Quotation"):
		return

	create_custom_fields(
		{
			"Quotation": [
				{
					"fieldname": INITIAL_FIELD,
					"fieldtype": "Data",
					"label": "Initial Price List",
					"insert_after": "selling_price_list",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": HISTORY_FIELD,
					"fieldtype": "Long Text",
					"label": "Price List History",
					"insert_after": INITIAL_FIELD,
					"read_only": 1,
					"no_copy": 1,
				},
			]
		},
		ignore_validate=True,
	)

	# Existing quotations predate structured events. Their current list is the
	# only authoritative value available, so seed a truthful initial event rather
	# than inventing a change history. The operation is idempotent.
	if not frappe.db.has_column("Quotation", INITIAL_FIELD):
		return
	for row in frappe.get_list(
		"Quotation",
		fields=["name", "selling_price_list", "creation", "owner", HISTORY_FIELD, INITIAL_FIELD],
		limit_page_length=0,
		ignore_permissions=True,
	):
		if row.get(INITIAL_FIELD) and row.get(HISTORY_FIELD):
			continue
		quote = frappe.get_doc("Quotation", row.name)
		data = snapshot(quote)
		if not quote.get(INITIAL_FIELD):
			quote.set(INITIAL_FIELD, data["initial"])
		if not quote.get(HISTORY_FIELD):
			quote.set(HISTORY_FIELD, json.dumps(data["history"], separators=(",", ":"), default=str))
		quote.flags.ignore_permissions = True  # SYSTEM-INTERNAL
		quote.flags.ignore_validate = True
		quote.flags.ignore_mandatory = True
		quote.save(ignore_permissions=True)  # SYSTEM-INTERNAL

	frappe.clear_cache(doctype="Quotation")

	# Copy the same provenance into historical contracts when the native CRM
	# fields are present. Existing values always win; this is a backfill, never a
	# rewrite of an accepted commercial record.
	contract_fields = ("initial_price_list", "negotiated_price_list", "price_list_history")
	if not frappe.db.exists("DocType", "CRM Contract"):
		return
	if not all(frappe.db.has_column("CRM Contract", field) for field in contract_fields):
		return
	for row in frappe.get_list(
		"CRM Contract",
		fields=["name", "quote", *contract_fields],
		limit_page_length=0,
		ignore_permissions=True,
	):
		if (
			row.get("initial_price_list")
			and row.get("negotiated_price_list")
			and row.get("price_list_history")
		):
			continue
		if not row.get("quote") or not frappe.db.exists("Quotation", row.quote):
			continue
		contract = frappe.get_doc("CRM Contract", row.name)
		quote = frappe.get_doc("Quotation", row.quote)
		set_snapshot(contract, snapshot(quote))
		contract.flags.ignore_permissions = True  # SYSTEM-INTERNAL
		contract.flags.ignore_validate = True
		contract.save(ignore_permissions=True)  # SYSTEM-INTERNAL

	frappe.clear_cache(doctype="CRM Contract")
