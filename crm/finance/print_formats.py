"""Idempotent native ERPNext finance print-format bootstrap."""

from __future__ import annotations

from pathlib import Path

import frappe


FINANCE_PRINT_FORMATS = (
	("CRM Finance Quotation", "Quotation", "crm_finance_quotation.html"),
	("CRM Finance Sales Order", "Sales Order", "crm_finance_sales_order.html"),
	("CRM Finance Invoice", "Sales Invoice", "crm_finance_invoice.html"),
	("CRM Finance Payment Receipt", "Payment Entry", "crm_finance_payment_receipt.html"),
)


def _set_default_print_format(doctype: str, print_format: str) -> None:
	"""Make the CRM finance format the native default for this document type."""
	property_setter = frappe.db.get_value(
		"Property Setter",
		{
			"doctype_or_field": "DocType",
			"doc_type": doctype,
			"property": "default_print_format",
		},
		"name",
	)
	if property_setter:
		frappe.db.set_value(
			"Property Setter", property_setter, "value", print_format, update_modified=False
		)
	else:
		frappe.make_property_setter(
			{
				"doctype_or_field": "DocType",
				"doctype": doctype,
				"property": "default_print_format",
				"value": print_format,
				"property_type": "Data",
			},
			validate_fields_for_doctype=False,
		)


def ensure_finance_print_formats() -> list[str]:
	"""Create or refresh the professional native finance formats.

	The templates deliberately do not render a company masthead. ERPNext's
	``letterhead`` print setting owns that concern, so the same configured
	Letter Head is used in Desk, PDF downloads, and emailed attachments.
	"""
	try:
		template_dir = Path(frappe.get_app_path("crm", "finance", "templates"))
		created_or_updated = []
		for name, doctype, filename in FINANCE_PRINT_FORMATS:
			if not frappe.db.exists("DocType", doctype):
				continue
			html = (template_dir / filename).read_text(encoding="utf-8")
			values = {
				"print_format_for": "DocType",
				"doc_type": doctype,
				"custom_format": 1,
				"print_format_type": "Jinja",
				"standard": "No",
				"disabled": 0,
				"font": "Default",
				"margin_top": 12,
				"margin_bottom": 12,
				"margin_left": 12,
				"margin_right": 12,
				"html": html,
			}
			if frappe.db.exists("Print Format", name):
				print_format = frappe.get_doc("Print Format", name)
				changed = False
				for fieldname, value in values.items():
					if print_format.get(fieldname) != value:
						setattr(print_format, fieldname, value)
						changed = True
				if changed:
					print_format.save(ignore_permissions=True)  # SYSTEM-INTERNAL
			else:
				frappe.get_doc({"doctype": "Print Format", "name": name, **values}).insert(
					ignore_permissions=True
				)  # SYSTEM-INTERNAL
			_set_default_print_format(doctype, name)
			frappe.clear_cache(doctype=doctype)
			created_or_updated.append(name)

		if created_or_updated:
			frappe.db.commit()
		return created_or_updated
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ensure_finance_print_formats: failed to seed formats")
		return []
