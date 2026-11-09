import frappe
from frappe.utils import nowdate


def _page_arg(value, label, default, maximum):
	if value in (None, ""):
		return default
	if isinstance(value, (dict, list, tuple, set, bool)):
		frappe.throw(f"{label} must be a whole number.", frappe.ValidationError)
	try:
		value = int(value)
	except (TypeError, ValueError):
		frappe.throw(f"{label} must be a whole number.", frappe.ValidationError)
	if value < 0 or value > maximum:
		frappe.throw(f"{label} must be between 0 and {maximum}.", frappe.ValidationError)
	return value


def is_hrms_installed():
	return "hrms" in frappe.get_installed_apps()


def get_expense_claims(company, filters=None, page=0, page_size=20):
	page = _page_arg(page, "Page", 0, 100000)
	page_size = _page_arg(page_size, "Page size", 20, 200)
	if not is_hrms_installed():
		return {"items": [], "hrms_not_installed": True}
	base_filters = [["company", "=", company]]
	if filters:
		base_filters.extend(filters)
	rows = frappe.get_list(
		"Expense Claim",
		fields=[
			"name",
			"employee",
			"employee_name",
			"department",
			"posting_date",
			"total_claimed_amount",
			"total_sanctioned_amount",
			"mode_of_payment",
			"status",
			"is_paid",
			"clearance_date",
		],
		filters=base_filters,
		limit_page_length=int(page_size),
		limit_start=int(page) * int(page_size),
		order_by="posting_date desc",
	)
	return {"items": rows, "hrms_not_installed": False}


def get_employee_advances(company, filters=None, page=0, page_size=20):
	page = _page_arg(page, "Page", 0, 100000)
	page_size = _page_arg(page_size, "Page size", 20, 200)
	if not is_hrms_installed():
		return {"items": [], "hrms_not_installed": True}
	base_filters = [
		["company", "=", company],
		["status", "=", "Paid"],
		["pending_amount", ">", 0],
	]
	if filters:
		base_filters.extend(filters)
	rows = frappe.get_list(
		"Employee Advance",
		fields=[
			"name",
			"employee",
			"employee_name",
			"department",
			"posting_date",
			"advance_amount",
			"claimed_amount",
			"pending_amount",
			"status",
		],
		filters=base_filters,
		limit_page_length=int(page_size),
		limit_start=int(page) * int(page_size),
		order_by="posting_date desc",
	)
	return {"items": rows, "hrms_not_installed": False}


def get_expense_journals(company, filters=None, page=0, page_size=20):
	page = _page_arg(page, "Page", 0, 100000)
	page_size = _page_arg(page_size, "Page size", 20, 200)
	# Journal Entry is available without the optional expense module.
	base_filters = [
		["company", "=", company],
		["docstatus", "!=", 2],
	]
	if filters:
		base_filters.extend(filters)
	rows = frappe.get_list(
		"Journal Entry",
		fields=["name", "posting_date", "entry_type", "total_debit", "remark", "docstatus"],
		filters=base_filters,
		limit_page_length=int(page_size),
		limit_start=int(page) * int(page_size),
		order_by="posting_date desc",
	)
	return {"items": rows}


def mark_expense_claim_paid(name):
	if not is_hrms_installed():
		frappe.throw("Expense processing is not available in this installation.")
	roles = frappe.get_roles(frappe.session.user)
	if not any(r in roles for r in ("Accounts User", "Accounts Manager")) and frappe.session.user != "Administrator":
		frappe.throw(
			"Finance access requires the Accounts User or Accounts Manager role.",
			frappe.PermissionError,
		)
	if not isinstance(name, str) or not name.strip():
		frappe.throw("Expense Claim must be plain text.", frappe.ValidationError)
	frappe.has_permission("Expense Claim", doc=name, ptype="write", throw=True)
	frappe.db.set_value(
		"Expense Claim",
		name,
		{
			"is_paid": 1,
			"clearance_date": nowdate(),
		},
	)
	return {"status": "paid", "name": name}
