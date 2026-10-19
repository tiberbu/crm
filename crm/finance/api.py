import calendar
import json
from datetime import date
from functools import wraps

import frappe
from frappe import _
from frappe.utils import add_months, date_diff, flt, get_first_day, today

from crm.finance import erpnext_adapter
from crm.finance.access import is_manager, require_access
from crm.utils.optin_network import set_network_link


def _request_text(value, label, *, required=False, default=""):
	"""Return clean request text or raise a readable validation error.

	Request arguments can arrive as JSON objects when a client sends the
	wrong shape. Do not coerce dictionaries to strings: that hides the input
	problem and can make downstream code fail with an unrelated AttributeError.
	"""
	if value is None:
		text = default
	elif isinstance(value, str):
		text = value.strip()
	elif isinstance(value, (int, float)) and not isinstance(value, bool):
		text = str(value)
	else:
		frappe.throw(_("{0} must be plain text.").format(label), frappe.ValidationError)

	if required and not text:
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	return text


def _safe_text(value, default=""):
	"""Return text for trusted display data without throwing on malformed rows."""
	if isinstance(value, str):
		return value.strip()
	if value is None:
		return default
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		return str(value)
	return default


def _request_filters(filters):
	"""Parse client filters into safe condition rows for list queries."""
	if not filters:
		return []
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except (TypeError, ValueError):
			frappe.throw(_("The filters could not be read. Clear the filters and try again."), frappe.ValidationError)

	if isinstance(filters, dict):
		if any(isinstance(value, (dict, list, tuple, set)) for value in filters.values()):
			frappe.throw(_("Filter values must be plain values, not objects or lists."), frappe.ValidationError)
		filters = [[field, "=", value] for field, value in filters.items()]
	if not isinstance(filters, list):
		frappe.throw(_("Filters must be a list of conditions."), frappe.ValidationError)

	validated = []
	for condition in filters:
		if not isinstance(condition, (list, tuple)) or len(condition) not in (2, 3):
			frappe.throw(_("Each filter must contain a field, an operator, and a value."), frappe.ValidationError)
		if not isinstance(condition[0], str) or (len(condition) == 3 and not isinstance(condition[1], str)):
			frappe.throw(_("Each filter must use a text field and operator."), frappe.ValidationError)
		if isinstance(condition[-1], (dict, tuple, set)):
			frappe.throw(_("Filter values must be plain values, not objects."), frappe.ValidationError)
		validated.append(list(condition))
	return validated


def _request_page(value, label, default, maximum):
	if value in (None, ""):
		return default
	if isinstance(value, (dict, list, tuple, set, bool)):
		frappe.throw(_("{0} must be a whole number.").format(label), frappe.ValidationError)
	try:
		parsed = int(value)
	except (TypeError, ValueError):
		frappe.throw(_("{0} must be a whole number.").format(label), frappe.ValidationError)
	if parsed < 0 or parsed > maximum:
		frappe.throw(_("{0} must be between 0 and {1}.").format(label, maximum), frappe.ValidationError)
	return parsed


def _page_args(page, page_size, maximum=200):
	return (
		_request_page(page, "Page", 0, 100000),
		_request_page(page_size, "Page size", 20, maximum),
	)


def _request_flag(value, label, default=0):
	if value in (None, ""):
		return default
	if isinstance(value, bool):
		return int(value)
	if isinstance(value, int) and value in (0, 1):
		return value
	if isinstance(value, str) and value.strip().lower() in {"0", "1"}:
		return int(value.strip())
	frappe.throw(_("{0} must be yes or no.").format(label), frappe.ValidationError)


_COCKPIT_DOCTYPE_ROUTES = {
	"Sales Invoice": ("invoices", None),
	"Sales Order": ("orders", None),
	"Quotation": ("quotes", None),
	"Payment Entry": ("payments", None),
	"Purchase Invoice": ("payables", "invoices"),
	"Purchase Order": ("payables", "orders"),
	"Supplier": ("payables", "suppliers"),
	"Customer": ("invoices", None),
	"Expense Claim": ("expenses", "claims"),
	"Employee Advance": ("expenses", "advances"),
	"Journal Entry": ("general-ledger", "journal"),
	"Period Closing Voucher": ("general-ledger", "closing"),
	"Bank Account": ("banking", "accounts"),
	"Bank Transaction": ("banking", "transactions"),
	"CRM Partner Rebate Voucher": ("partner-commission", "rebates"),
	"CRM Sales Commission": ("partner-commission", "commissions"),
	"Asset": ("assets", None),
	"Subscription": ("liabilities", "subscriptions"),
}


def _record_url(doctype, docname):
	"""Build a Finance Cockpit record link without assuming row values are strings."""
	from urllib.parse import urlencode

	doctype_text = _safe_text(doctype)
	docname_text = _safe_text(docname)
	if not doctype_text or not docname_text:
		return ""
	section, tab = _COCKPIT_DOCTYPE_ROUTES.get(doctype_text, ("dashboard", None))
	params = {}
	if tab:
		params["tab"] = tab
	params["doctype"] = doctype_text
	params["name"] = docname_text
	return f"/finance-cockpit#/{section}?{urlencode(params)}"


def _require_document_permission(doctype, name, ptype="read"):
	"""Validate the document name and defer authorization to native permissions."""
	name = _request_text(name, doctype, required=True)
	frappe.has_permission(doctype, doc=name, ptype=ptype, throw=True)
	return name


@frappe.whitelist()
def get_accessible_companies():
	return frappe.get_list(
		"Company",
		fields=["name", "abbr", "default_currency"],
		order_by="name asc",
	)


def _get_date_filter(period):
	"""Return (from_date, to_date) for the given period string."""
	period = _request_text(period, "Period", default="month")
	if period not in {"month", "quarter", "year", "ytd"}:
		frappe.throw(_("Period must be month, quarter, year, or ytd."), frappe.ValidationError)
	t = today()
	t_date = date.fromisoformat(t)
	if period == "quarter":
		month = t_date.month
		q_start = ((month - 1) // 3) * 3 + 1
		from_date = date(t_date.year, q_start, 1).isoformat()
		to_date = t
	elif period in ("year", "ytd"):
		from_date = date(t_date.year, 1, 1).isoformat()
		to_date = t
	else:  # month (default)
		from_date = get_first_day(t)
		to_date = t
	return from_date, to_date


def _resolve_company(company):
	"""Return a validated company name, falling back to the first accessible company.
	Throws PermissionError if the user has access to no company at all."""
	if company is not None:
		company = _request_text(company, "Company")
	company = company or frappe.defaults.get_user_default("company")
	if not company:
		rows = frappe.get_list("Company", fields=["name"], limit=1, order_by="name asc")
		company = rows[0].name if rows else None
	if not company:
		frappe.throw("No company accessible for this user", frappe.PermissionError)
	frappe.has_permission("Company", doc=company, ptype="read", throw=True)
	return company


def _is_admin(roles):
	return frappe.session.user == "Administrator"


def _has_ar_access(roles):
	return _is_admin(roles) or bool({"Accounts User", "Accounts Manager"} & set(roles))


def _has_ap_access(roles):
	return _is_admin(roles) or bool({"Accounts User", "Accounts Manager"} & set(roles))


def _company_currency(company):
	"""Return the default currency for the company."""
	rows = frappe.get_list(
		"Company",
		filters=[["name", "=", company]],
		fields=["default_currency"],
		limit=1,
	)
	return rows[0].default_currency if rows else ""


def _sum_query_value(doctype, filters, field):
	"""Return a permission-checked SUM for one DocType field on Frappe v15/v16."""
	get_query = getattr(frappe.qb, "get_query", None)
	if get_query:
		rows = get_query(
			doctype,
			fields=[{"SUM": field, "as": "total"}],
			filters=filters,
			ignore_permissions=False,
		).run(as_dict=True)
		total = rows[0].get("total") if rows else 0
		return flt(total or 0)

	# Frappe v15 lacks the permission-aware Query Builder aggregate API. get_list
	# enforces document and user permissions, so summing its numeric rows retains
	# the same visibility rules without passing an aggregate expression to it.
	rows = frappe.get_list(doctype, filters=filters, fields=[field])
	return sum(flt(row.get(field) or 0) for row in rows)


def _get_ar_outstanding(company, currency):
	total = _sum_query_value(
		"Sales Invoice",
		[
			["company", "=", company],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
		],
		"outstanding_amount",
	)
	return {"value": float(total or 0), "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}


def _get_ar_overdue(company, currency):
	total = _sum_query_value(
		"Sales Invoice",
		[
			["company", "=", company],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
			["due_date", "<", today()],
		],
		"outstanding_amount",
	)
	return {"value": float(total or 0), "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}


def _get_invoiced_mtd(company, currency, date_filter):
	from_date, to_date = date_filter
	total = _sum_query_value(
		"Sales Invoice",
		[
			["company", "=", company],
			["docstatus", "=", 1],
			["posting_date", ">=", from_date],
			["posting_date", "<=", to_date],
		],
		"grand_total",
	)
	return {"value": float(total or 0), "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}


def _get_collected_mtd(company, currency, date_filter):
	from_date, to_date = date_filter
	total = _sum_query_value(
		"Payment Entry",
		[
			["company", "=", company],
			["docstatus", "=", 1],
			["payment_type", "=", "Receive"],
			["posting_date", ">=", from_date],
			["posting_date", "<=", to_date],
		],
		"paid_amount",
	)
	return {"value": float(total or 0), "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}


def _get_ap_outstanding(company, currency):
	total = _sum_query_value(
		"Purchase Invoice",
		[
			["company", "=", company],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
		],
		"outstanding_amount",
	)
	return {"value": float(total or 0), "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}


def _get_ap_overdue(company, currency):
	total = _sum_query_value(
		"Purchase Invoice",
		[
			["company", "=", company],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
			["due_date", "<", today()],
		],
		"outstanding_amount",
	)
	return {"value": float(total or 0), "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}


def _get_pending_rebates(company, roles):
	if not frappe.db.exists("DocType", "CRM Partner Rebate Voucher"):
		return {"value": 0, "currency": "", "delta_pct": 0, "delta_direction": "neutral"}
	currency = _company_currency(company)
	filters = [["status", "=", "Pending"]]
	# Scope to own partners when user is Partner RM only (no elevated role)
	if (
		"Partner RM" in roles
		and "Accounts Manager" not in roles
		and "Accounts User" not in roles
		and not _is_admin(roles)
	):
		own_partners = frappe.get_list(
			"CRM Partner",
			filters={"partner_rm": frappe.session.user},
			pluck="name",
		)
		if not own_partners:
			return {"value": 0, "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}
		filters.append(["partner", "in", own_partners])
	total = _sum_query_value(
		"CRM Partner Rebate Voucher",
		filters,
		"rebate_amount",
	)
	return {"value": float(total or 0), "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}


def _get_unpaid_commissions(company, roles):
	if not frappe.db.exists("DocType", "CRM Sales Commission"):
		return {"value": 0, "currency": "", "delta_pct": 0, "delta_direction": "neutral"}
	currency = _company_currency(company)
	filters = [["status", "in", ["Reported", "Confirmed"]]]
	# Scope to own deals when user is Sales Manager only (no elevated role)
	if (
		"Sales Manager" in roles
		and "Accounts Manager" not in roles
		and "Accounts User" not in roles
		and not _is_admin(roles)
	):
		own_deals = frappe.get_list(
			"CRM Deal",
			filters={"deal_owner": frappe.session.user},
			pluck="name",
		) or ["__none__"]
		filters.append(["deal", "in", own_deals])
	total = _sum_query_value(
		"CRM Sales Commission",
		filters,
		"commission_amount",
	)
	return {"value": float(total or 0), "currency": currency, "delta_pct": 0, "delta_direction": "neutral"}


@frappe.whitelist()
def get_finance_kpis(company=None, period="month", force=0):
	period = _request_text(period, "Period", default="month")
	force = _request_flag(force, "Refresh KPIs")
	company = _resolve_company(company)
	try:
		return _get_finance_kpis_payload(company, period, force)
	except (frappe.PermissionError, frappe.ValidationError):
		raise
	except Exception:
		try:
			error_log = frappe.log_error(
				title="Finance KPI Load Failed",
				message=frappe.get_traceback(),
			)
			reference = getattr(error_log, "name", "FINANCE-KPI")
		except Exception:
			reference = "FINANCE-KPI"
		frappe.throw(
			_("Finance KPI data could not be loaded. Retry this section. If it continues, contact Finance support with reference {0}.").format(reference),
			frappe.ValidationError,
		)


def _get_finance_kpis_payload(company, period, force):
	date_filter = _get_date_filter(period)
	roles = frappe.get_roles(frappe.session.user)
	cache_key = "fc_kpis_%s_%s_%s" % (frappe.session.user, company, period)
	if not force:
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached
	result = {}
	currency = _company_currency(company)
	if _has_ar_access(roles):
		result["ar_outstanding"] = _get_ar_outstanding(company, currency)
		result["ar_overdue"] = _get_ar_overdue(company, currency)
		result["invoiced_mtd"] = _get_invoiced_mtd(company, currency, date_filter)
		result["collected_mtd"] = _get_collected_mtd(company, currency, date_filter)
	if _has_ap_access(roles):
		result["ap_outstanding"] = _get_ap_outstanding(company, currency)
		result["ap_overdue"] = _get_ap_overdue(company, currency)
	result["pending_rebates"] = _get_pending_rebates(company, roles)
	result["unpaid_commissions"] = _get_unpaid_commissions(company, roles)
	frappe.cache().set_value(cache_key, result, expires_in_sec=300)
	return result


# ---------------------------------------------------------------------------
# fc-s2-1: Pending Actions Inbox
# ---------------------------------------------------------------------------


def _age(date_str):
	"""Return age in days from a date string to today."""
	if not date_str:
		return 0
	try:
		return int(date_diff(today(), str(date_str)))
	except Exception:
		return 0


def _action_item(
	type_,
	doctype,
	docname,
	party_type,
	party_name,
	amount,
	currency,
	age,
	urgency,
	primary_action,
	primary_action_label,
	secondary_actions=None,
	record_url=None,
):
	doctype_text = _safe_text(doctype)
	docname_text = _safe_text(docname)
	return {
		"type": type_,
		"doctype": doctype_text,
		"docname": docname_text,
		"party_type": party_type,
		"party_name": party_name,
		"amount": float(amount or 0),
		"currency": currency or "",
		"age_days": age,
		"urgency": urgency,
		"primary_action": primary_action,
		"primary_action_label": primary_action_label,
		"secondary_actions": secondary_actions or [],
		"record_url": _safe_text(record_url) or _record_url(doctype_text, docname_text),
	}


def _collect_overdue_invoices(company, currency, roles):
	if not _has_ar_access(roles):
		return []
	rows = frappe.get_list(
		"Sales Invoice",
		filters=[
			["company", "=", company],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
			["due_date", "<", today()],
		],
		fields=["name", "customer", "outstanding_amount", "due_date"],
		order_by="due_date asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.due_date)
		urgency = "critical" if age > 30 else "warning"
		items.append(
			_action_item(
				"overdue_invoice",
				"Sales Invoice",
				r.name,
				"Customer",
				r.customer,
				r.outstanding_amount,
				currency,
				age,
				urgency,
				"record_payment",
				"Record Payment",
				record_url="/finance-cockpit#/payments?doctype=Payment+Entry&mode=new&party_type=Customer&party=%s"
				% r.customer,
			)
		)
	return items


def _collect_unapplied_payments(company, currency, roles):
	if not _has_ar_access(roles):
		return []
	rows = frappe.get_list(
		"Payment Entry",
		filters=[
			["company", "=", company],
			["docstatus", "=", 1],
			["payment_type", "=", "Receive"],
			["unallocated_amount", ">", 0],
		],
		fields=["name", "party", "unallocated_amount", "posting_date"],
		order_by="posting_date asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.posting_date)
		urgency = "warning" if age > 7 else "normal"
		items.append(
			_action_item(
				"unapplied_payment",
				"Payment Entry",
				r.name,
				"Customer",
				r.party,
				r.unallocated_amount,
				currency,
				age,
				urgency,
				"reconcile",
				"Reconcile",
			)
		)
	return items


def _collect_pending_rebates(company, currency, roles):
	if not frappe.db.exists("DocType", "CRM Partner Rebate Voucher"):
		return []
	if not (_has_ar_access(roles) or "Partner RM" in roles):
		return []
	base_filters = [["status", "=", "Pending"]]
	if "Partner RM" in roles and "Accounts Manager" not in roles and "Accounts User" not in roles:
		own_partners = frappe.get_list(
			"CRM Partner",
			filters={"partner_rm": frappe.session.user},
			pluck="name",
		)
		if not own_partners:
			return []
		base_filters.append(["partner", "in", own_partners])
	rows = frappe.get_list(
		"CRM Partner Rebate Voucher",
		filters=base_filters,
		fields=["name", "partner", "rebate_amount", "creation"],
		order_by="creation asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.creation)
		urgency = "warning" if age > 5 else "normal"
		items.append(
			_action_item(
				"pending_rebate",
				"CRM Partner Rebate Voucher",
				r.name,
				"Partner",
				r.partner,
				r.rebate_amount,
				currency,
				age,
				urgency,
				"approve",
				"Approve",
			)
		)
	return items


def _collect_approved_rebates_unpaid(company, currency, roles):
	if not frappe.db.exists("DocType", "CRM Partner Rebate Voucher"):
		return []
	if "Accounts Manager" not in roles and not _is_admin(roles):
		return []
	rows = frappe.get_list(
		"CRM Partner Rebate Voucher",
		filters=[["status", "=", "Approved"]],
		fields=["name", "partner", "rebate_amount", "approved_date"],
		order_by="approved_date asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.approved_date)
		urgency = "warning" if age > 7 else "normal"
		items.append(
			_action_item(
				"approved_rebate_unpaid",
				"CRM Partner Rebate Voucher",
				r.name,
				"Partner",
				r.partner,
				r.rebate_amount,
				currency,
				age,
				urgency,
				"mark_paid",
				"Mark Paid",
			)
		)
	return items


def _collect_unconfirmed_commissions(company, currency, roles):
	if not frappe.db.exists("DocType", "CRM Sales Commission"):
		return []
	if not (_has_ar_access(roles) or "Sales Manager" in roles):
		return []
	base_filters = [["status", "=", "Reported"]]
	if "Sales Manager" in roles and "Accounts Manager" not in roles and "Accounts User" not in roles:
		# scope to own team — deals where deal_owner == session user for now
		base_filters.append(
			[
				"deal",
				"in",
				frappe.get_list(
					"CRM Deal",
					filters={"deal_owner": frappe.session.user},
					pluck="name",
				)
				or ["__none__"],
			]
		)
	rows = frappe.get_list(
		"CRM Sales Commission",
		filters=base_filters,
		fields=["name", "sales_person", "commission_amount", "creation"],
		order_by="creation asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.creation)
		urgency = "warning" if age > 3 else "normal"
		items.append(
			_action_item(
				"unconfirmed_commission",
				"CRM Sales Commission",
				r.name,
				"User",
				r.sales_person,
				r.commission_amount,
				currency,
				age,
				urgency,
				"confirm",
				"Confirm",
			)
		)
	return items


def _collect_confirmed_commissions_unpaid(company, currency, roles):
	if not frappe.db.exists("DocType", "CRM Sales Commission"):
		return []
	if "Accounts Manager" not in roles and not _is_admin(roles):
		return []
	rows = frappe.get_list(
		"CRM Sales Commission",
		filters=[["status", "=", "Confirmed"]],
		fields=["name", "sales_person", "commission_amount", "creation"],
		order_by="creation asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.creation)
		urgency = "warning" if age > 7 else "normal"
		items.append(
			_action_item(
				"confirmed_commission_unpaid",
				"CRM Sales Commission",
				r.name,
				"User",
				r.sales_person,
				r.commission_amount,
				currency,
				age,
				urgency,
				"mark_paid",
				"Mark Paid",
			)
		)
	return items


def _collect_expense_claims_pending_payment(company, currency, roles):
	if not _has_ap_access(roles):
		return []
	if not frappe.db.exists("DocType", "Expense Claim"):
		return []
	rows = frappe.get_list(
		"Expense Claim",
		filters=[
			["company", "=", company],
			["status", "=", "Approved"],
			["is_paid", "=", 0],
		],
		fields=["name", "employee_name", "total_sanctioned_amount", "posting_date"],
		order_by="posting_date asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.posting_date)
		urgency = "warning" if age > 5 else "normal"
		items.append(
			_action_item(
				"expense_claim_pending_payment",
				"Expense Claim",
				r.name,
				"Employee",
				r.employee_name,
				r.total_sanctioned_amount,
				currency,
				age,
				urgency,
				"mark_paid",
				"Mark Paid",
			)
		)
	return items


def _collect_employee_advances_unclaimed(company, currency, roles):
	if not _has_ap_access(roles):
		return []
	if not frappe.db.exists("DocType", "Employee Advance"):
		return []
	rows = frappe.get_list(
		"Employee Advance",
		filters=[
			["company", "=", company],
			["status", "=", "Paid"],
			["pending_amount", ">", 0],
		],
		fields=["name", "employee_name", "pending_amount", "posting_date"],
		order_by="posting_date asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.posting_date)
		urgency = "warning" if age > 30 else "normal"
		items.append(
			_action_item(
				"employee_advance_unclaimed",
				"Employee Advance",
				r.name,
				"Employee",
				r.employee_name,
				r.pending_amount,
				currency,
				age,
				urgency,
				"review",
				"Review",
			)
		)
	return items


def _collect_overdue_purchase_invoices(company, currency, roles):
	if not _has_ap_access(roles):
		return []
	rows = frappe.get_list(
		"Purchase Invoice",
		filters=[
			["company", "=", company],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
			["due_date", "<", today()],
		],
		fields=["name", "supplier", "outstanding_amount", "due_date"],
		order_by="due_date asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.due_date)
		urgency = "critical" if age > 30 else "warning"
		items.append(
			_action_item(
				"overdue_purchase_invoice",
				"Purchase Invoice",
				r.name,
				"Supplier",
				r.supplier,
				r.outstanding_amount,
				currency,
				age,
				urgency,
				"record_payment",
				"Record Payment",
				record_url="/finance-cockpit#/payables?tab=payments&doctype=Payment+Entry&mode=new&payment_type=Pay&party_type=Supplier&party=%s"
				% r.supplier,
			)
		)
	return items


def _collect_purchase_invoices_pending_approval(company, currency, roles):
	if "Accounts Manager" not in roles and not _is_admin(roles):
		return []
	rows = frappe.get_list(
		"Purchase Invoice",
		filters=[
			["company", "=", company],
			["docstatus", "=", 0],
		],
		fields=["name", "supplier", "grand_total", "creation"],
		order_by="creation asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.creation)
		items.append(
			_action_item(
				"purchase_invoice_pending_approval",
				"Purchase Invoice",
				r.name,
				"Supplier",
				r.supplier,
				r.grand_total,
				currency,
				age,
				"warning",
				"approve",
				"Approve",
			)
		)
	return items


def _collect_bank_transactions_unmatched(company, currency, roles):
	if not (_has_ar_access(roles) or _has_ap_access(roles)):
		return []
	if not frappe.db.exists("DocType", "Bank Transaction"):
		return []
	rows = frappe.get_list(
		"Bank Transaction",
		filters=[
			["company", "=", company],
			["status", "=", "Unreconciled"],
		],
		fields=["name", "bank_account", "deposit", "withdrawal", "date"],
		order_by="date asc",
		limit=50,
	)
	items = []
	for r in rows:
		age = _age(r.date)
		urgency = "warning" if age > 3 else "normal"
		amount = float(r.deposit or 0) + float(r.withdrawal or 0)
		items.append(
			_action_item(
				"bank_transaction_unmatched",
				"Bank Transaction",
				r.name,
				"Bank Account",
				r.bank_account,
				amount,
				currency,
				age,
				urgency,
				"reconcile",
				"Reconcile",
				record_url="/finance-cockpit#/banking?tab=transactions&status=Unreconciled&bank_account=%s"
				% r.bank_account,
			)
		)
	return items


def _collect_period_closing_due(currency, roles):
	if "Accounts Manager" not in roles and not _is_admin(roles):
		return []
	# Check if a Period Closing Voucher exists for the current fiscal year
	if not frappe.db.exists("DocType", "Period Closing Voucher"):
		return []
	current_year = date.today().year
	existing = frappe.get_list(
		"Period Closing Voucher",
		filters=[["transaction_date", ">=", "%s-01-01" % current_year]],
		limit=1,
	)
	if existing:
		return []
	return [
		_action_item(
			"period_closing_due",
			"Period Closing Voucher",
			"new",
			"",
			"Current Fiscal Period",
			0,
			currency,
			0,
			"critical",
			"create",
			"Create Period Closing",
			record_url="/finance-cockpit#/general-ledger?tab=closing&doctype=Period+Closing+Voucher&mode=new",
		)
	]


def _collect_subscription_invoices_due(company, currency, roles):
	if not _has_ar_access(roles):
		return []
	if not frappe.db.exists("DocType", "Subscription"):
		return []
	# Use current_invoice_end as the invoice-due indicator for Subscription.
	meta = frappe.get_meta("Subscription")
	date_field = "current_invoice_end" if meta.has_field("current_invoice_end") else None
	if not date_field:
		return []
	rows = frappe.get_list(
		"Subscription",
		filters=[
			["company", "=", company],
			["status", "=", "Active"],
			[date_field, "<=", today()],
		],
		fields=["name", "party", date_field],
		order_by=date_field + " asc",
		limit=50,
	)
	items = []
	for r in rows:
		due_date = r.get(date_field)
		age = _age(due_date)
		items.append(
			_action_item(
				"subscription_invoice_due",
				"Subscription",
				r.name,
				"Customer",
				r.party or "",
				0,
				currency,
				age,
				"warning",
				"generate_invoice",
				"Generate Invoice",
			)
		)
	return items


_URGENCY_RANK = {"critical": 0, "warning": 1, "normal": 2}


@frappe.whitelist()
def get_pending_actions(company=None):
	company = _resolve_company(company)
	roles = frappe.get_roles(frappe.session.user)
	currency = _company_currency(company)

	items = []
	items.extend(_collect_overdue_invoices(company, currency, roles))
	items.extend(_collect_unapplied_payments(company, currency, roles))
	items.extend(_collect_pending_rebates(company, currency, roles))
	items.extend(_collect_approved_rebates_unpaid(company, currency, roles))
	items.extend(_collect_unconfirmed_commissions(company, currency, roles))
	items.extend(_collect_confirmed_commissions_unpaid(company, currency, roles))
	items.extend(_collect_expense_claims_pending_payment(company, currency, roles))
	items.extend(_collect_employee_advances_unclaimed(company, currency, roles))
	items.extend(_collect_overdue_purchase_invoices(company, currency, roles))
	items.extend(_collect_purchase_invoices_pending_approval(company, currency, roles))
	items.extend(_collect_bank_transactions_unmatched(company, currency, roles))
	items.extend(_collect_period_closing_due(currency, roles))
	items.extend(_collect_subscription_invoices_due(company, currency, roles))

	items.sort(key=lambda x: (_URGENCY_RANK.get(x["urgency"], 2), -x["age_days"]))
	return items


# ---------------------------------------------------------------------------
# fc-s2-2: Receivables APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_ar_invoices(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	base_filters = [
		["company", "=", company],
		["docstatus", "=", 1],
		["outstanding_amount", ">", 0],
	]
	base_filters.extend(_request_filters(filters))
	rows = erpnext_adapter.get_list(
		"Sales Invoice",
		filters=base_filters,
		fields=[
			"name",
			"customer",
			"posting_date",
			"due_date",
			"creation",
			"modified",
			"owner",
			"grand_total",
			"outstanding_amount",
			"status",
			"crm_deal",
			"crm_quotation",
		],
		order_by="due_date asc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)
	today_str = today()
	for r in rows:
		due = r.get("due_date")
		r["days_overdue"] = max(0, int(date_diff(today_str, str(due)))) if due else 0
	return rows


@frappe.whitelist()
def get_sales_orders(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	# Draft orders remain visible so Accounts Users can validate and submit them
	# before generating an invoice. Document permissions still govern the
	# detail action itself.
	base_filters = [["company", "=", company], ["docstatus", "in", [0, 1]]]
	base_filters.extend(_request_filters(filters))
	return erpnext_adapter.get_list(
		"Sales Order",
		filters=base_filters,
		fields=[
			"name",
			"customer",
			"transaction_date",
			"delivery_date",
			"creation",
			"modified",
			"owner",
			"grand_total",
			"status",
			"billing_status",
		],
		order_by="transaction_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


def _finance_handoff_doc(doctype, filters, fields):
	"""Read one linked financial document without assuming optional CRM fields exist."""
	if not frappe.db.exists("DocType", doctype):
		return None
	available_fields = [field for field in fields if frappe.db.has_column(doctype, field)]
	if not available_fields:
		return None
	try:
		rows = frappe.get_list(
			doctype,
			filters=filters,
			fields=available_fields,
			order_by="creation desc",
			limit=1,
		)
	except frappe.PermissionError:
		return None
	return rows[0] if rows else None


def _facility_signature_snapshot(contract_name):
	"""Return native Contract status and Facility Signatory timestamp when readable."""
	if not contract_name or not frappe.db.exists("CRM Contract", contract_name):
		return {"status": "", "signed_at": ""}
	try:
		contract = frappe.get_doc("CRM Contract", contract_name)
		facility_signatures = [
			row
			for row in contract.get("signatories") or []
			if row.signatory_role == "Facility Signatory" and row.status == "Signed"
			and row.signed_at
		]
		signed_at = max((row.signed_at for row in facility_signatures), default="")
		return {"status": contract.status or "", "signed_at": signed_at}
	except Exception:
		# Financial users should still receive the handoff row if contract metadata is
		# unavailable; the linked accounting documents remain authoritative.
		return {"status": "", "signed_at": ""}


def _handoff_schedule(submission):
	if not frappe.db.has_column("CRM Opt-In Submission", "billing_schedule_json"):
		return {}
	try:
		schedules = json.loads(submission.get("billing_schedule_json") or "[]")
	except (TypeError, ValueError, json.JSONDecodeError):
		return {}
	if not isinstance(schedules, list):
		return {}
	return next(
		(
			row
			for row in schedules
			if isinstance(row, dict)
			and int(row.get("year_number") or 0) == 1
			and int(row.get("quarter_number") or 0) == 1
		),
		{},
	)


@frappe.whitelist()
def get_signed_handoff_timeline(company=None, page=0, page_size=20):
	"""Return signed facility handoffs and their native Year 1/Q1 documents.

	The endpoint is intentionally read-only. It does not introduce a finance
	status: each document exposes its native status/docstatus, while
	``next_step`` is explanatory UI guidance derived from those records.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	if not frappe.db.exists("DocType", "CRM Opt-In Submission"):
		return []

	fields = ["name", "deal", "contract", "network_slug", "status", "submitted_at", "creation", "modified", "owner"]
	if frappe.db.has_column("CRM Opt-In Submission", "billing_schedule_json"):
		fields.append("billing_schedule_json")
	try:
		submissions = frappe.get_list(
			"CRM Opt-In Submission",
			filters=[["status", "=", "Processed"], ["contract", "is", "set"]],
			fields=fields,
			order_by="modified desc",
			limit_page_length=min(max(page_size * 5, 20), 200),
		)
	except frappe.PermissionError:
		return []

	items = []
	for submission in submissions:
		quote_filters = {}
		if frappe.db.has_column("Quotation", "crm_optin_submission"):
			quote_filters = {"crm_optin_submission": submission.name}
			if frappe.db.has_column("Quotation", "crm_optin_year"):
				quote_filters["crm_optin_year"] = 1
		elif submission.deal and frappe.db.has_column("Quotation", "crm_deal"):
			quote_filters = {"crm_deal": submission.deal}
		quotation = _finance_handoff_doc(
			"Quotation",
			quote_filters,
			["name", "company", "party_name", "status", "docstatus", "currency", "grand_total", "creation", "modified", "owner"],
		) if quote_filters else None
		if quotation and quotation.get("company") != company:
			continue

		order_filters = {}
		if frappe.db.has_column("Sales Order", "crm_optin_submission"):
			order_filters = {"crm_optin_submission": submission.name}
			if frappe.db.has_column("Sales Order", "crm_optin_year"):
				order_filters["crm_optin_year"] = 1
			if frappe.db.has_column("Sales Order", "crm_optin_quarter"):
				order_filters["crm_optin_quarter"] = 1
		elif quotation and frappe.db.has_column("Sales Order", "quotation"):
			order_filters = {"quotation": quotation.name}
		order = _finance_handoff_doc(
			"Sales Order",
			order_filters,
			["name", "company", "customer", "status", "docstatus", "currency", "grand_total", "creation", "modified", "owner"],
		) if order_filters else None
		if order and order.get("company") != company:
			continue

		invoice_filters = {}
		if frappe.db.has_column("Sales Invoice", "crm_optin_submission"):
			invoice_filters = {"crm_optin_submission": submission.name}
			if frappe.db.has_column("Sales Invoice", "crm_optin_year"):
				invoice_filters["crm_optin_year"] = 1
			if frappe.db.has_column("Sales Invoice", "crm_optin_quarter"):
				invoice_filters["crm_optin_quarter"] = 1
		invoice = _finance_handoff_doc(
			"Sales Invoice",
			invoice_filters,
			["name", "company", "customer", "status", "docstatus", "currency", "grand_total", "outstanding_amount", "posting_date", "due_date", "creation", "modified", "owner"],
		) if invoice_filters else None
		if invoice and invoice.get("company") != company:
			continue
		linked_companies = {
			doc.get("company")
			for doc in (quotation, order, invoice)
			if doc and doc.get("company")
		}
		if linked_companies != {company}:
			# CRM Opt-In submissions do not carry a Company field. Do not expose an
			# unresolvable or cross-company handoff to the current finance user.
			continue
		payments = []
		if invoice and frappe.db.exists("DocType", "Payment Entry Reference"):
			try:
				references = frappe.get_list(
					"Payment Entry Reference",
					filters={"reference_doctype": "Sales Invoice", "reference_name": invoice.name},
					fields=["parent"],
					order_by="creation desc",
					limit_page_length=20,
				)
				payment_names = list(dict.fromkeys(row.parent for row in references if row.parent))
				if payment_names and frappe.db.exists("DocType", "Payment Entry"):
					payments = frappe.get_list(
						"Payment Entry",
						filters={"name": ["in", payment_names], "company": company},
						fields=["name", "docstatus", "posting_date", "paid_amount", "creation", "modified", "owner"],
						order_by="posting_date desc",
						limit_page_length=20,
					)
			except frappe.PermissionError:
				payments = []

		schedule = _handoff_schedule(submission)
		contract = _facility_signature_snapshot(submission.contract)
		if invoice:
			next_step = "Record payment when funds are received"
		elif order and int(order.get("docstatus") or 0) == 0:
			next_step = "Submit the Sales Order"
		elif order:
			next_step = (
				"Review the handoff error"
				if schedule.get("error") or schedule.get("status") == "Failed"
				else "Review the Network billing schedule"
				if schedule.get("invoice_schedule_configured") is False
				else (
					"Wait for the scheduled Network billing period"
					if schedule.get("invoice_issue_timing") != "contract_signature"
					and schedule.get("invoice_date")
					and str(schedule.get("invoice_date")) > today()
					else "Generate the Sales Invoice"
				)
			)
		elif quotation and int(quotation.get("docstatus") or 0) == 0:
			next_step = "Submit the Year 1 Quotation"
		else:
			next_step = "Review the missing Sales Order"

		items.append(
			{
				"submission": submission.name,
				"network": submission.network_slug or "",
				"submission_status": submission.status or "",
				"submitted_at": submission.submitted_at or submission.creation,
				"modified": submission.modified,
				"owner": submission.owner,
				"contract": {"name": submission.contract, **contract},
				"quotation": quotation.as_dict() if quotation else None,
				"sales_order": order.as_dict() if order else None,
				"sales_invoice": invoice.as_dict() if invoice else None,
				"payments": [payment.as_dict() for payment in payments],
				"schedule": {
					"order_date": schedule.get("scheduled_order_date", ""),
					"invoice_date": schedule.get("invoice_date", ""),
					"due_date": schedule.get("invoice_due_date", ""),
					"invoice_issue_timing": schedule.get("invoice_issue_timing", ""),
					"invoice_schedule_configured": schedule.get("invoice_schedule_configured"),
					"error": schedule.get("error", ""),
					"handoff_note": schedule.get("handoff_note", ""),
				},
				"next_step": next_step,
			}
		)

	start = page * page_size
	return items[start : start + page_size]


@frappe.whitelist()
def get_sales_order_invoice_state(order_name, company=None):
	"""Return native Sales Invoice links for one Sales Order.

	The child-table relationship is the source of truth. Draft and submitted
	invoices both count as generated so a retry cannot create a duplicate draft
	while the first invoice is still being reviewed.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	order_name = _request_text(order_name, "Sales Order", required=True)
	company = _resolve_company(company)
	frappe.has_permission("Sales Order", doc=order_name, ptype="read", throw=True)
	order_company = frappe.db.get_value("Sales Order", order_name, "company")
	if not order_company:
		frappe.throw("Sales Order %s was not found" % order_name, frappe.DoesNotExistError)
	if order_company != company:
		frappe.throw("Sales Order %s belongs to another company" % order_name, frappe.PermissionError)
	rows = erpnext_adapter.get_list(
		"Sales Invoice Item",
		filters=[
			["sales_order", "=", order_name],
			["docstatus", "<", 2],
		],
		fields=["parent"],
		order_by="creation desc",
		limit_page_length=50,
	)
	names = []
	for row in rows:
		name = row.get("parent")
		if name and name not in names:
			names.append(name)
	return {"has_invoice": bool(names), "invoice_names": names}


@frappe.whitelist()
def make_sales_invoice_from_order(order_name, company=None):
	"""Create one native draft Sales Invoice from a submitted Sales Order.

	This endpoint deliberately does not submit the invoice. Finance reviews and
	submits it through the native document lifecycle. Existing draft or submitted
	invoices linked through Sales Invoice Item are treated as already generated.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	order_name = _request_text(order_name, "Sales Order", required=True)
	company = _resolve_company(company)
	_require_document_permission("Sales Order", order_name, "read")
	frappe.has_permission("Sales Invoice", ptype="create", throw=True)
	order = frappe.get_doc("Sales Order", order_name)
	if order.company != company:
		frappe.throw("Sales Order %s belongs to another company" % order_name, frappe.PermissionError)
	if order.docstatus != 1:
		frappe.throw("Submit Sales Order %s before generating an invoice" % order_name)

	# Serialize concurrent retries on the source order, then re-check the native
	# child-table relationship before invoking the document mapper.
	frappe.db.sql("select name from `tabSales Order` where name=%s for update", order_name)
	state = get_sales_order_invoice_state(order_name, company)
	if state["has_invoice"]:
		frappe.throw(
			"Sales Order %s already has an invoice: %s"
			% (order_name, ", ".join(state["invoice_names"])),
			frappe.ValidationError,
		)

	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	invoice = frappe.get_doc(make_sales_invoice(order_name))
	if not invoice.get("items"):
		frappe.throw("Sales Order %s has no billable items" % order_name)
	invoice.insert()
	return {
		"name": invoice.name,
		"doctype": "Sales Invoice",
		"docstatus": invoice.docstatus,
	}


@frappe.whitelist()
def get_customer_payments(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	base_filters = [
		["company", "=", company],
		["payment_type", "=", "Receive"],
		["docstatus", "!=", 2],
	]
	base_filters.extend(_request_filters(filters))
	fields = [
		"name",
		"party",
		"posting_date",
		"paid_amount",
		"mode_of_payment",
		"total_allocated_amount",
		"unallocated_amount",
	]
	if frappe.db.has_column("Payment Entry", "workflow_state"):
		fields.append("workflow_state")
	return erpnext_adapter.get_list(
		"Payment Entry",
		filters=base_filters,
		fields=fields,
		order_by="posting_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_sales_invoice_payments(invoice_name, company=None):
	"""Return submitted customer payments allocated to one Sales Invoice."""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(
			_("Finance access requires the Accounts User or Accounts Manager role."),
			frappe.PermissionError,
		)
	company = _resolve_company(company)
	invoice_name = _require_document_permission("Sales Invoice", invoice_name, "read")
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice.company != company:
		frappe.throw(_("Sales Invoice {0} belongs to another company").format(invoice_name), frappe.PermissionError)

	if not frappe.db.exists("DocType", "Payment Entry Reference"):
		return []

	references = frappe.get_list(
		"Payment Entry Reference",
		filters={"reference_doctype": "Sales Invoice", "reference_name": invoice_name},
		fields=["parent", "allocated_amount"],
		order_by="creation desc",
		limit_page_length=200,
	)
	payment_names = list(dict.fromkeys(row.parent for row in references if row.parent))
	if not payment_names:
		return []

	payments = frappe.get_list(
		"Payment Entry",
		filters={
			"name": ["in", payment_names],
			"company": company,
			"payment_type": "Receive",
			"docstatus": 1,
		},
		fields=[
			"name",
			"posting_date",
			"paid_amount",
			"mode_of_payment",
			"reference_no",
			"reference_date",
			"owner",
			"modified",
		],
		order_by="posting_date desc, modified desc",
		limit_page_length=200,
	)
	allocated_by_payment = {row.parent: row.allocated_amount for row in references}
	for payment in payments:
		payment["allocated_amount"] = allocated_by_payment.get(payment.name, 0)
	return payments


@frappe.whitelist()
def get_customer_outstanding_invoices(company=None, customer=None):
	"""Outstanding submitted Sales Invoices for a customer, for payment allocation.

	Powers the cockpit's Receive-Payment composer: the user picks a customer and
	allocates a receipt across these invoices. Amounts are the live outstanding
	balances straight from the ledger.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	if customer is not None:
		customer = _request_text(customer, "Customer")
	if not customer:
		return []
	rows = erpnext_adapter.get_list(
		"Sales Invoice",
		filters=[
			["company", "=", company],
			["customer", "=", customer],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
		],
		fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency"],
		order_by="due_date asc",
		limit_page_length=200,
	)
	today_str = today()
	for r in rows:
		due = r.get("due_date")
		r["days_overdue"] = max(0, int(date_diff(today_str, str(due)))) if due else 0
	return rows


@frappe.whitelist()
def get_customer_payment_options(company=None, search_term=""):
	"""Customers with currently outstanding submitted invoices in one Company.

	Build choices from permission-filtered Sales Invoice rows so a Customer is
	never offered based on another Company's receivables or a stale Customer
	record with no eligible invoice. Customer IDs remain the option values.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	search_term = _request_text(search_term, "Customer search").casefold()
	page_size = 100 if search_term else 20
	filters = [
		["company", "=", company],
		["docstatus", "=", 1],
		["outstanding_amount", ">", 0],
	]
	options = []
	seen = set()
	limit_start = 0
	while len(options) < 20:
		rows = erpnext_adapter.get_list(
			"Sales Invoice",
			filters=filters,
			fields=["customer"],
			group_by="customer",
			order_by="customer asc",
			limit_start=limit_start,
			limit_page_length=page_size,
		)
		if not rows:
			break

		customer_ids = list(dict.fromkeys(_safe_text(row.get("customer")) for row in rows if row.get("customer")))
		customer_ids = [customer for customer in customer_ids if customer and customer not in seen]
		seen.update(customer_ids)
		if customer_ids:
			customer_rows = erpnext_adapter.get_list(
				"Customer",
				filters=[["name", "in", customer_ids]],
				fields=["name", "customer_name"],
				order_by="name asc",
				limit_page_length=len(customer_ids),
			)
			customer_names = {
				_safe_text(row.get("name")): _safe_text(row.get("customer_name"), _safe_text(row.get("name")))
				for row in customer_rows
				if row.get("name")
			}
			for customer in customer_ids:
				customer_name = customer_names.get(customer, customer)
				if search_term and search_term not in customer.casefold() and search_term not in customer_name.casefold():
					continue
				# Keep IDs visible even when a search returns one of two records
				# sharing a display name. Values remain the stable Customer IDs.
				options.append({"label": _("{0} · {1}").format(customer_name, customer), "value": customer})
				if len(options) == 20:
					break

		limit_start += len(rows)
		if len(rows) < page_size:
			break
	return options


def _get_customer_payment_context(company, mode_of_payment):
	"""Resolve a receipt Mode of Payment to its account for the selected Company."""
	mode_of_payment = _request_text(mode_of_payment, "Mode of Payment", required=True)
	context = {
		"company": company,
		"mode_of_payment": mode_of_payment,
		"mode_type": None,
		"configured": False,
		"account": None,
		"account_type": None,
		"requires_reference": False,
		"message": "",
	}
	if not frappe.db.exists("Mode of Payment", mode_of_payment):
		context["message"] = _("Mode of Payment {0} could not be found.").format(mode_of_payment)
		return context
	mode_type = frappe.db.get_value("Mode of Payment", mode_of_payment, "type")
	context["mode_type"] = mode_type

	configured_account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode_of_payment, "company": company},
		"default_account",
	)
	if not configured_account:
		context["message"] = _(
			"{0} has no account configured for {1}. Configure a company account before posting."
		).format(mode_of_payment, company)
		return context

	# Keep this call compatible with ERPNext v15 and v16. Both public APIs accept
	# company and mode_of_payment; do not pass v16-only optional keywords here.
	from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account

	resolved = get_default_bank_cash_account(company, mode_of_payment=mode_of_payment)
	account = resolved.get("account") if resolved else None
	if account != configured_account:
		context["message"] = _(
			"The account configured for {0} in {1} could not be resolved. Review the Mode of Payment setup."
		).format(mode_of_payment, company)
		return context

	account_details = frappe.db.get_value(
		"Account", account, ["company", "account_type", "is_group", "disabled"], as_dict=True
	)
	if (
		not account_details
		or account_details.company != company
		or account_details.account_type not in ("Bank", "Cash")
		or account_details.is_group
		or account_details.disabled
	):
		context["message"] = _(
			"The account configured for {0} must be an active Bank or Cash account belonging to {1}."
		).format(mode_of_payment, company)
		return context

	if mode_type in ("Cash", "Bank") and mode_type != account_details.account_type:
		context["message"] = _(
			"{0} Mode of Payment is mapped to a {1} account for {2}; configure a {0} account before posting."
		).format(mode_type, account_details.account_type, company)
		return context

	context.update(
		{
			"configured": True,
			"account": account,
			"account_type": account_details.account_type,
			"requires_reference": account_details.account_type == "Bank",
		}
	)
	return context


@frappe.whitelist()
def get_customer_payment_context(company=None, mode_of_payment=None):
	"""Return the company-resolved account and native reference rules for a receipt."""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	return _get_customer_payment_context(company, mode_of_payment)


def _get_customer_payment_entry(invoice, amount, bank_account):
	"""Build a receipt with ERPNext's public mapper and its shared v15/v16 account argument."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	pe = get_payment_entry(
		"Sales Invoice", invoice, party_amount=amount, bank_account=bank_account
	)
	# ERPNext's mapper can prefer the invoice's own mode account over bank_account.
	# The Finance composer selection is authoritative, so align the mapped account
	# and its currency/type before native Payment Entry validation runs.
	if pe.paid_to != bank_account:
		account_details = frappe.db.get_value(
			"Account", bank_account, ["account_currency", "account_type"], as_dict=True
		)
		if not account_details:
			frappe.throw(_("The selected payment account is no longer available."), frappe.ValidationError)
		pe.paid_to = bank_account
		pe.paid_to_account_currency = account_details.account_currency
		pe.paid_to_account_type = account_details.account_type
	return pe


@frappe.whitelist()
def create_customer_payment(
	company=None,
	customer=None,
	mode_of_payment=None,
	posting_date=None,
	reference_no=None,
	reference_date=None,
	allocations=None,
	submit=1,
):
	"""Create (and optionally submit) a Receive Payment Entry for a customer.

	`allocations` is a JSON array of {invoice, amount}. The payment helper
	seeds the correct bank/party accounts and exchange rates from the first invoice;
	remaining invoices are appended as additional references. When no invoice is
	allocated, an on-account (unallocated) receipt is created instead.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	frappe.has_permission("Payment Entry", ptype="create", throw=True)
	customer = _request_text(customer, "Customer", required=True)
	payment_context = _get_customer_payment_context(company, mode_of_payment)
	if not payment_context["configured"]:
		frappe.throw(payment_context["message"], frappe.ValidationError)

	if isinstance(allocations, str):
		try:
			allocations = json.loads(allocations or "[]")
		except (TypeError, ValueError):
			frappe.throw(_("Payment allocations could not be read. Review the invoice amounts and try again."), frappe.ValidationError)
	if allocations in (None, ""):
		allocations = []
	if not isinstance(allocations, list) or any(not isinstance(item, dict) for item in allocations):
		frappe.throw(_("Payment allocations must be a list of invoice amounts."), frappe.ValidationError)
	allocations = [a for a in allocations if flt(a.get("amount")) > 0]
	submit = _request_flag(submit, "Submit payment", default=1)

	# Re-derive the allowed invoices server-side and reject any allocation that
	# doesn't belong to this (company, customer). The client-supplied list is
	# untrusted — never allocate against an invoice the ledger didn't surface.
	allowed = {
		r["name"]: flt(r["outstanding_amount"])
		for r in get_customer_outstanding_invoices(company=company, customer=customer)
	}
	for a in allocations:
		inv = a.get("invoice")
		if inv not in allowed:
			frappe.throw(_("Invoice {0} is not an outstanding invoice for this customer").format(inv))
		if flt(a.get("amount")) > allowed[inv] + 0.005:
			frappe.throw(_("Allocation for {0} exceeds its outstanding balance").format(inv))

	if allocations:
		# Seed from the first allocated invoice so accounts + rates resolve natively.
		first = allocations[0]
		pe = _get_customer_payment_entry(
			first.get("invoice"), flt(first.get("amount")), payment_context["account"]
		)
		if frappe.db.has_column("Sales Invoice", "optin_network"):
			set_network_link(
				pe,
				frappe.db.get_value("Sales Invoice", first.get("invoice"), "optin_network"),
			)
		# Reset references to exactly what the user allocated.
		pe.set("references", [])
		total = 0.0
		for a in allocations:
			amt = flt(a.get("amount"))
			pe.append(
				"references",
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": a.get("invoice"),
					"allocated_amount": amt,
				},
			)
			total += amt
		pe.paid_amount = total
		pe.received_amount = total
	else:
		# On-account receipt: still needs accounts/rates seeded from an invoice-less
		# entry, which get_payment_entry cannot do. Require at least one allocation.
		frappe.throw("Allocate the receipt to at least one invoice")

	pe.company = company
	pe.mode_of_payment = payment_context["mode_of_payment"]
	if posting_date:
		pe.posting_date = posting_date
	if reference_no:
		pe.reference_no = reference_no
	if reference_date:
		pe.reference_date = reference_date

	pe.set_amounts()
	pe.insert()
	if int(submit or 0):
		from frappe.model.workflow import apply_workflow

		pe = apply_workflow(pe.as_json(), "Submit for Approval")
	warning_map = getattr(frappe.flags, "crm_finance_payment_warnings", {})
	integration_warnings = warning_map.pop(pe.name, []) if isinstance(warning_map, dict) else []
	_invalidate_kpi_cache(frappe.session.user, company)
	return {
		"name": pe.name,
		"docstatus": pe.docstatus,
		"workflow_state": pe.get("workflow_state"),
		"paid_amount": pe.paid_amount,
		"integration_warnings": integration_warnings,
	}


@frappe.whitelist()
def make_payment_entry_from_invoice(source_name):
	"""
	Seed an unsaved Payment Entry from a submitted Sales Invoice.
	Used by the Finance Cockpit CreateFromPicker (Invoices → Receive Payment).
	Returns the unsaved Payment Entry as a dict.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	source_name = _request_text(source_name, "Sales Invoice", required=True)
	_require_document_permission("Sales Invoice", source_name, "read")
	frappe.has_permission("Payment Entry", ptype="create", throw=True)

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	inv = frappe.get_doc("Sales Invoice", source_name)
	if inv.docstatus != 1:
		frappe.throw("Only submitted Sales Invoices can receive a payment")
	if flt(inv.outstanding_amount) <= 0:
		frappe.throw("Invoice %s is already fully paid (outstanding: 0)" % source_name)

	pe = get_payment_entry("Sales Invoice", source_name, party_amount=flt(inv.outstanding_amount))
	set_network_link(
		pe,
		frappe.db.get_value("Sales Invoice", source_name, "optin_network")
		if frappe.db.has_column("Sales Invoice", "optin_network")
		else "",
	)
	return pe.as_dict()


@frappe.whitelist()
def make_sales_order_from_quotation(source_name):
	"""Seed an unsaved Sales Order from a submitted Quotation.
	Carries forward all Quotation commercial data plus derives delivery_date
	from the linked CRM Opt-In billing schedule's first invoice date when available.
	"""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	source_name = _request_text(source_name, "Quotation", required=True)
	_require_document_permission("Quotation", source_name, "read")
	frappe.has_permission("Sales Order", ptype="create", throw=True)

	from erpnext.selling.doctype.quotation.quotation import make_sales_order

	so_dict = make_sales_order(source_name)
	if isinstance(so_dict, dict):
		so = frappe.get_doc(so_dict)
	else:
		so = so_dict

	# Check for linked CRM Opt-In Submission and first invoice date
	quote = frappe.get_doc("Quotation", source_name)
	submission_name = getattr(quote, "crm_optin_submission", None)
	if not submission_name and quote.get("crm_deal"):
		submission_name = frappe.db.get_value("CRM Opt-In Submission", {"deal": quote.get("crm_deal")}, "name")

	first_invoice_date = None
	if submission_name and frappe.db.exists("DocType", "CRM Opt-In Submission"):
		sub = frappe.get_doc("CRM Opt-In Submission", submission_name)
		schedule = _handoff_schedule(sub)
		if schedule and schedule.get("invoice_date"):
			first_invoice_date = schedule.get("invoice_date")

	if first_invoice_date:
		so.delivery_date = first_invoice_date
		for item in so.get("items", []):
			item.delivery_date = first_invoice_date
	elif not so.delivery_date:
		so.delivery_date = frappe.utils.add_days(so.transaction_date or frappe.utils.today(), 30)
		for item in so.get("items", []):
			if not item.delivery_date:
				item.delivery_date = so.delivery_date
	set_network_link(
		so,
		getattr(quote, "optin_network", "")
		or (frappe.db.get_value("CRM Opt-In Submission", submission_name, "optin_network") if submission_name else ""),
	)

	return so.as_dict()


@frappe.whitelist()
def get_document_workflow_transitions(doctype, name):
	"""Return allowed workflow transitions and status for a document under the current session."""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	doctype = _request_text(doctype, "DocType", required=True)
	name = _request_text(name, "Document Name", required=True)
	_require_document_permission(doctype, name, "read")

	from frappe.model.workflow import get_transitions, get_workflow

	workflow = get_workflow(doctype)
	if not workflow:
		return {"has_workflow": False, "transitions": [], "workflow_state": None}

	doc = frappe.get_doc(doctype, name)
	current_state = doc.get(workflow.workflow_state_field)
	try:
		transitions = get_transitions(doc, workflow)
	except Exception:
		transitions = []

	return {
		"has_workflow": True,
		"workflow_name": workflow.name,
		"state_field": workflow.workflow_state_field,
		"workflow_state": current_state,
		"transitions": transitions,
	}


@frappe.whitelist()
def apply_document_workflow_action(doctype, name, action):
	"""Apply a workflow transition action to a document."""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	doctype = _request_text(doctype, "DocType", required=True)
	name = _request_text(name, "Document Name", required=True)
	action = _request_text(action, "Workflow Action", required=True)
	_require_document_permission(doctype, name, "write")

	from frappe.model.workflow import apply_workflow

	doc = frappe.get_doc(doctype, name)
	updated_doc = apply_workflow(doc, action)
	return {
		"name": updated_doc.name,
		"doctype": updated_doc.doctype,
		"docstatus": updated_doc.docstatus,
	}


@frappe.whitelist()
def get_customers(company=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	return erpnext_adapter.get_list(
		"Customer",
		fields=["name", "customer_name", "customer_group", "territory"],
		order_by="customer_name asc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_quotation_finance_context(quotation_name=None, company=None):
	"""Return Opt-In provenance and Company-matched accounting links for a quote."""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	quotation_name = _request_text(quotation_name, "Quotation", required=True)
	quotation_rows = erpnext_adapter.get_list(
		"Quotation",
		filters=[["name", "=", quotation_name], ["company", "=", company]],
		fields=["name", "company", "party_name", "currency", "grand_total", "docstatus", "crm_optin_submission", "optin_network", "crm_deal"],
		limit_page_length=1,
	)
	quotation = next((row for row in quotation_rows if row.get("company") == company), None)
	if not quotation:
		frappe.throw(_("Quotation is unavailable in the selected Company."), frappe.PermissionError)
	customer_name = _safe_text(quotation.get("party_name"))
	customer_label = customer_name
	customer_available = False
	if customer_name:
		try:
			customer_rows = erpnext_adapter.get_list(
				"Customer",
				filters=[["name", "=", customer_name]],
				fields=["name", "customer_name"],
				limit_page_length=1,
			)
			if customer_rows:
				customer_label = _safe_text(customer_rows[0].get("customer_name"), customer_name)
				customer_available = True
		except frappe.PermissionError:
			pass

	submission = None
	submission_name = _safe_text(quotation.get("crm_optin_submission"))
	if submission_name and frappe.db.exists("DocType", "CRM Opt-In Submission"):
		fields = ["name"]
		for field in ("network_slug", "contract", "deal", "status", "raw_json", "billing_schedule_json", "submitted_at"):
			if frappe.db.has_column("CRM Opt-In Submission", field):
				fields.append(field)
		try:
			rows = frappe.get_list(
				"CRM Opt-In Submission",
				filters=[["name", "=", submission_name]],
				fields=fields,
				limit_page_length=1,
			)
			submission = rows[0] if rows else None
		except frappe.PermissionError:
			submission = None

	network_reference = _safe_text((submission or {}).get("network_slug")) or _safe_text(quotation.get("optin_network"))
	network = None
	if network_reference and frappe.db.exists("DocType", "CRM Opt-In Network"):
		try:
			rows = frappe.get_list(
				"CRM Opt-In Network",
				filters=[["name", "=", network_reference]],
				fields=["name", "slug", "display_name", "partner_id"],
				limit_page_length=1,
			)
			if not rows:
				rows = frappe.get_list(
					"CRM Opt-In Network",
					filters=[["slug", "=", network_reference]],
					fields=["name", "slug", "display_name", "partner_id"],
					limit_page_length=1,
				)
			network = rows[0] if rows else None
		except frappe.PermissionError:
			network = None
	network_slug = _safe_text(network.get("slug")) if network else network_reference

	payload = {}
	try:
		payload = json.loads((submission or {}).get("raw_json") or "{}")
	except (TypeError, ValueError, json.JSONDecodeError):
		payload = {}
	if not isinstance(payload, dict):
		payload = {}
	facility_rows = payload.get("pricing") or payload.get("facilities") or []
	if not facility_rows and isinstance(payload.get("pricing_plans"), list):
		facility_rows = [
			facility
			for plan in payload["pricing_plans"] if isinstance(plan, dict)
			for facility in (plan.get("facilities") or []) if isinstance(facility, dict)
		]
	if not facility_rows and frappe.db.exists("DocType", "Quotation Item"):
		try:
			item_fields = ["item_name"]
			if frappe.db.has_column("Quotation Item", "facility_name"):
				item_fields.append("facility_name")
			quote_items = erpnext_adapter.get_list(
				"Quotation Item",
				filters=[["parent", "=", quotation_name], ["parenttype", "=", "Quotation"]],
				fields=item_fields,
				limit_page_length=100,
			)
			facility_rows = [
				{"facility_name": _safe_text(row.get("facility_name")) or _safe_text(row.get("item_name"))}
				for row in quote_items
				if _safe_text(row.get("facility_name")) or _safe_text(row.get("item_name"))
			]
		except frappe.PermissionError:
			facility_rows = []
	mfl_codes = list(dict.fromkeys(
		_safe_text(row.get("mfl_code")) for row in facility_rows
		if isinstance(row, dict) and _safe_text(row.get("mfl_code"))
	))
	facilities = []
	if mfl_codes and frappe.db.exists("DocType", "CRM Pre-Qualified Facility"):
		try:
			facilities = frappe.get_list(
				"CRM Pre-Qualified Facility",
				filters=[["mfl_code", "in", mfl_codes]],
				fields=["name", "mfl_code", "facility_name"],
				limit_page_length=min(len(mfl_codes), 100),
			)
		except frappe.PermissionError:
			facilities = []
	facility_by_code = {_safe_text(row.get("mfl_code")): row for row in facilities}
	facility_context = []
	for item in facility_rows:
		if not isinstance(item, dict):
			continue
		code = _safe_text(item.get("mfl_code"))
		name = _safe_text(item.get("facility_name"), code)
		facility = facility_by_code.get(code)
		facility_context.append({
			"name": _safe_text(facility.get("name")) if facility else "",
			"mfl_code": code,
			"label": _safe_text(facility.get("facility_name"), name) if facility else name,
			"available": bool(facility),
		})

	contract = None
	contract_name = _safe_text((submission or {}).get("contract"))
	if contract_name and frappe.db.exists("DocType", "CRM Contract"):
		try:
			rows = frappe.get_list(
				"CRM Contract",
				filters=[["name", "=", contract_name]],
				fields=["name", "status"],
				limit_page_length=1,
			)
			contract = rows[0] if rows else None
		except frappe.PermissionError:
			contract = None

	schedule = _handoff_schedule(submission) if submission else {}
	if not schedule and isinstance(payload.get("billing_schedule"), list):
		schedule = next((row for row in payload["billing_schedule"] if isinstance(row, dict) and int(row.get("year_number") or 0) == 1 and int(row.get("quarter_number") or 0) == 1), {})
	contract_signature = {"status": _safe_text((contract or {}).get("status")), "signed_at": ""}
	if contract_name and frappe.db.exists("DocType", "CRM Contract Signatory"):
		try:
			signatures = frappe.get_list(
				"CRM Contract Signatory",
				filters=[
					["parent", "=", contract_name],
					["parenttype", "=", "CRM Contract"],
					["signatory_role", "=", "Facility Signatory"],
					["status", "=", "Signed"],
				],
				fields=["signed_at"],
				order_by="signed_at desc",
				limit_page_length=1,
			)
			contract_signature["signed_at"] = _safe_text(signatures[0].get("signed_at")) if signatures else ""
		except frappe.PermissionError:
			pass
	docstatus = int(quotation.get("docstatus") or 0)
	submit_allowed = bool(
		docstatus == 0
		and frappe.has_permission("Quotation", doc=quotation_name, ptype="submit")
	)
	if docstatus == 2:
		quotation_state = "Cancelled"
	elif docstatus == 1:
		quotation_state = "Submitted · read-only"
	elif submit_allowed:
		quotation_state = "Draft · submit with ERPNext checks"
	else:
		quotation_state = "Ineligible · no submit permission"
	quotation_record = {
		"name": quotation_name,
		"company": company,
		"currency": _safe_text(quotation.get("currency")),
		"grand_total": float(quotation.get("grand_total") or 0),
		"docstatus": docstatus,
		"finance_state": quotation_state,
		"submit_allowed": submit_allowed,
	}
	order_filter_groups = []
	if frappe.db.has_column("Sales Order", "crm_optin_quotation"):
		order_filter_groups.append([["crm_optin_quotation", "=", quotation_name]])
	if frappe.db.exists("DocType", "Sales Order Item"):
		try:
			order_items = erpnext_adapter.get_list(
				"Sales Order Item",
				filters=[["prevdoc_docname", "=", quotation_name]],
				fields=["parent"],
				limit_page_length=100,
			)
		except frappe.PermissionError:
			order_items = []
		order_names = list(dict.fromkeys(_safe_text(row.get("parent")) for row in order_items if row.get("parent")))
		if order_names:
			order_filter_groups.append([["name", "in", order_names]])
	orders_by_name = {}
	for order_filters in order_filter_groups:
		try:
			matched_orders = erpnext_adapter.get_list(
				"Sales Order",
				filters=[["company", "=", company], ["docstatus", "in", [0, 1]], *order_filters],
				fields=["name", "company", "customer", "docstatus", "status", "currency", "grand_total"],
				order_by="creation desc",
				limit_page_length=20,
			)
		except frappe.PermissionError:
			matched_orders = []
		for row in matched_orders:
			if row.get("company") == company and row.get("name"):
				orders_by_name[row["name"]] = row
	orders = list(orders_by_name.values())
	order_names = list(dict.fromkeys(_safe_text(row.get("name")) for row in orders if row.get("name")))
	invoices = []
	if order_names and frappe.db.exists("DocType", "Sales Invoice Item"):
		try:
			invoice_items = erpnext_adapter.get_list(
				"Sales Invoice Item",
				filters=[["sales_order", "in", order_names]],
				fields=["parent"],
				limit_page_length=100,
			)
		except frappe.PermissionError:
			invoice_items = []
		invoice_names = list(dict.fromkeys(_safe_text(row.get("parent")) for row in invoice_items if row.get("parent")))
		if invoice_names:
			try:
				invoices = erpnext_adapter.get_list(
					"Sales Invoice",
					filters=[["name", "in", invoice_names], ["company", "=", company], ["docstatus", "in", [0, 1]]],
					fields=["name", "company", "customer", "docstatus", "status", "currency", "grand_total", "outstanding_amount", "posting_date", "due_date"],
					order_by="creation desc",
					limit_page_length=20,
				)
			except frappe.PermissionError:
				invoices = []
	invoices = [row for row in invoices if row.get("company") == company]
	invoice_names = list(dict.fromkeys(_safe_text(row.get("name")) for row in invoices if row.get("name")))
	payments = []
	if invoice_names and frappe.db.exists("DocType", "Payment Entry Reference"):
		try:
			payment_refs = erpnext_adapter.get_list(
				"Payment Entry Reference",
				filters=[["reference_doctype", "=", "Sales Invoice"], ["reference_name", "in", invoice_names]],
				fields=["parent"],
				limit_page_length=100,
			)
		except frappe.PermissionError:
			payment_refs = []
		payment_names = list(dict.fromkeys(_safe_text(row.get("parent")) for row in payment_refs if row.get("parent")))
		if payment_names:
			try:
				payments = erpnext_adapter.get_list(
					"Payment Entry",
					filters=[["name", "in", payment_names], ["company", "=", company], ["docstatus", "in", [0, 1]]],
					fields=["name", "company", "docstatus", "payment_type", "posting_date", "paid_amount", "paid_from_account_currency", "paid_to_account_currency"]
					+ (["workflow_state"] if frappe.db.has_column("Payment Entry", "workflow_state") else []),
					order_by="posting_date desc",
					limit_page_length=20,
				)
			except frappe.PermissionError:
				payments = []
	payments = [row for row in payments if row.get("company") == company]
	if payments:
		for payment in payments:
			payment["finance_state"] = _safe_text(payment.get("workflow_state")) or (
				"Submitted" if int(payment.get("docstatus") or 0) == 1 else "Draft"
			)
	if payments:
		handoff_state = "Payment recorded"
	elif invoices:
		handoff_state = "Invoice created"
	elif orders:
		handoff_state = "Sales Order created"
	elif docstatus == 2:
		handoff_state = "Cancelled"
	elif docstatus == 0:
		handoff_state = "Waiting for Quotation submission"
	elif (contract or {}).get("status") != "Fully Executed":
		handoff_state = "Waiting for Facility contract completion"
	else:
		handoff_state = "Waiting for scheduled Sales Order"

	return {
		"quotation": quotation_record,
		"company": company,
		"customer": {"name": customer_name, "label": customer_label, "available": customer_available},
		"submission": {"name": submission_name, "status": _safe_text((submission or {}).get("status")), "available": bool(submission)},
		"network": {"name": _safe_text(network.get("name")) if network else network_slug, "label": _safe_text(network.get("display_name"), network_slug) if network else network_slug, "partner_id": _safe_text(network.get("partner_id")) if network else "", "available": bool(network)},
		"facilities": facility_context,
		"contract": {"name": _safe_text(contract.get("name")) if contract else contract_name, "status": _safe_text(contract.get("status")) if contract else contract_signature.get("status", ""), "signed_at": contract_signature.get("signed_at", ""), "available": bool(contract)},
		"schedule": {"order_date": _safe_text(schedule.get("scheduled_order_date")), "invoice_date": _safe_text(schedule.get("invoice_date")), "due_date": _safe_text(schedule.get("invoice_due_date")), "issue_timing": _safe_text(schedule.get("invoice_issue_timing")), "invoice_schedule_configured": schedule.get("invoice_schedule_configured"), "error": _safe_text(schedule.get("error")), "handoff_note": _safe_text(schedule.get("handoff_note"))},
		"handoff_state": handoff_state,
		"sales_orders": orders,
		"sales_invoices": invoices,
		"payments": payments,
	}


@frappe.whitelist()
def get_quotations(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	base_filters = [["company", "=", company]]
	base_filters.extend(_request_filters(filters))
	rows = erpnext_adapter.get_list(
		"Quotation",
		filters=base_filters,
		fields=[
			"name",
			"party_name",
			"transaction_date",
			"valid_till",
			"creation",
			"modified",
			"owner",
			"grand_total",
			"status",
			"docstatus",
		],
		order_by="transaction_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)
	for row in rows:
		docstatus = int(row.get("docstatus") or 0)
		if docstatus == 2:
			row["finance_state"] = "Cancelled"
		elif docstatus == 1:
			row["finance_state"] = "Submitted · read-only"
		elif row.get("status") != "Draft":
			row["finance_state"] = "Ineligible · {0}".format(_safe_text(row.get("status"), "status unavailable"))
		elif frappe.has_permission("Quotation", doc=row.get("name"), ptype="submit"):
			row["finance_state"] = "Draft · submit with ERPNext checks"
		else:
			row["finance_state"] = "Ineligible · no submit permission"
	return rows


@frappe.whitelist()
def get_pipeline_summary(company=None, period="month"):
	"""Return counts + values for the 4 pipeline stages: Quotes, Orders, Invoices, Payments."""
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ar_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	t = today()

	# A submitted Quotation's status is "Open" (there is no "Submitted"
	# status); the prior ["Draft", "Submitted"] filter silently excluded every
	# submitted quote from this KPI. These are the real in-play statuses.
	open_quotes = frappe.get_list(
		"Quotation",
		filters=[
			["company", "=", company],
			["docstatus", "in", [0, 1]],
			["status", "in", ["Draft", "Open", "Replied", "Partially Ordered"]],
		],
		fields=["grand_total"],
	)
	active_orders = frappe.get_list(
		"Sales Order",
		filters=[
			["company", "=", company],
			["docstatus", "=", 1],
			["status", "in", ["To Deliver and Bill", "To Bill", "Draft"]],
		],
		fields=["grand_total"],
	)
	unpaid_invoices = frappe.get_list(
		"Sales Invoice",
		filters=[["company", "=", company], ["docstatus", "=", 1], ["outstanding_amount", ">", 0]],
		fields=["outstanding_amount"],
	)

	from frappe.utils import get_first_day, get_last_day

	period_start = get_first_day(t)
	payments_mtd = frappe.get_list(
		"Payment Entry",
		filters=[
			["company", "=", company],
			["docstatus", "=", 1],
			["payment_type", "=", "Receive"],
			["posting_date", ">=", period_start],
			["posting_date", "<=", t],
		],
		fields=["paid_amount"],
	)

	currency = frappe.defaults.get_global_default("currency") or "KES"
	return {
		"open_quotes": len(open_quotes),
		"quotes_value": sum(r.grand_total or 0 for r in open_quotes),
		"active_orders": len(active_orders),
		"orders_value": sum(r.grand_total or 0 for r in active_orders),
		"unpaid_invoices": len(unpaid_invoices),
		"invoices_value": sum(r.outstanding_amount or 0 for r in unpaid_invoices),
		"payments_mtd": len(payments_mtd),
		"payments_value": sum(r.paid_amount or 0 for r in payments_mtd),
		"currency": currency,
	}


# ---------------------------------------------------------------------------
# fc-s2-3: Payables APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_ap_invoices(company=None, filters=None, page=0, page_size=20, include_draft=0):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ap_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	include_draft = _request_flag(include_draft, "Include draft invoices")
	base_filters = [["company", "=", company]]
	if frappe.utils.cint(include_draft):
		# Pending-approval view: draft invoices only
		base_filters.append(["docstatus", "=", 0])
	else:
		base_filters.extend(
			[
				["docstatus", "=", 1],
				["outstanding_amount", ">", 0],
			]
		)
	base_filters.extend(_request_filters(filters))
	rows = erpnext_adapter.get_list(
		"Purchase Invoice",
		filters=base_filters,
		fields=[
			"name",
			"supplier",
			"posting_date",
			"due_date",
			"grand_total",
			"outstanding_amount",
			"status",
		],
		order_by="due_date asc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)
	today_str = today()
	for r in rows:
		due = r.get("due_date")
		r["days_overdue"] = max(0, int(date_diff(today_str, str(due)))) if due else 0
	return rows


@frappe.whitelist()
def get_purchase_orders(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ap_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	base_filters = [["company", "=", company], ["docstatus", "=", 1]]
	base_filters.extend(_request_filters(filters))
	return erpnext_adapter.get_list(
		"Purchase Order",
		filters=base_filters,
		fields=["name", "supplier", "transaction_date", "grand_total", "status", "billing_status"],
		order_by="transaction_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_supplier_payments(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ap_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	base_filters = [
		["company", "=", company],
		["payment_type", "=", "Pay"],
		["docstatus", "=", 1],
	]
	base_filters.extend(_request_filters(filters))
	return erpnext_adapter.get_list(
		"Payment Entry",
		filters=base_filters,
		fields=[
			"name",
			"party",
			"posting_date",
			"paid_amount",
			"mode_of_payment",
			"total_allocated_amount",
			"unallocated_amount",
		],
		order_by="posting_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_suppliers(company=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ap_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	return erpnext_adapter.get_list(
		"Supplier",
		fields=["name", "supplier_name", "supplier_group", "supplier_type"],
		order_by="supplier_name asc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


# ---------------------------------------------------------------------------
# fc-s3-2: Expenses APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_expense_claims(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ap_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	from crm.finance.hrms_adapter import get_expense_claims as _get_claims

	return _get_claims(company, _request_filters(filters), page, page_size)


@frappe.whitelist()
def get_employee_advances(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ap_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	from crm.finance.hrms_adapter import get_employee_advances as _get_advances

	return _get_advances(company, _request_filters(filters), page, page_size)


@frappe.whitelist()
def get_expense_journals(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not _has_ap_access(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	from crm.finance.hrms_adapter import get_expense_journals as _get_journals

	return _get_journals(company, _request_filters(filters), page, page_size)


@frappe.whitelist()
def mark_expense_claim_paid(name: str) -> dict:
	from crm.finance.hrms_adapter import mark_expense_claim_paid as _mark_paid

	return _mark_paid(name)


# ---------------------------------------------------------------------------
# fc-s3-3: Partner & Commission APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_rebate_vouchers(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not (_has_ar_access(roles) or "Partner RM" in roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	filters = _request_filters(filters)
	base_filters = [["docstatus", "!=", 2]]
	if "Partner RM" in roles and "Accounts Manager" not in roles and "Accounts User" not in roles:
		own_partners = frappe.get_list(
			"CRM Partner",
			filters={"partner_rm": frappe.session.user},
			pluck="name",
		)
		if not own_partners:
			return []
		base_filters.append(["partner", "in", own_partners])
	base_filters.extend(filters)
	fields = [
		"name",
		"partner",
		"deal",
		"customer",
		"payment_reference",
		"source_invoice",
		"facility_mfl_code",
		"facility_name",
		"payee_supplier",
		"rebate_pct",
		"calculation_basis",
		"rebate_amount",
		"currency",
		"status",
		"creation",
	]
	if frappe.db.has_column("CRM Partner Rebate Voucher", "optin_network"):
		fields.append("optin_network")
	rows = _get_company_scoped_finance_rows(
		"CRM Partner Rebate Voucher", base_filters, fields, company, page, page_size
	)
	return _add_legacy_payout_labels(_add_finance_network_labels(rows, company))


@frappe.whitelist()
def get_sales_commissions(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not (_has_ar_access(roles) or "Sales Manager" in roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	filters = _request_filters(filters)
	base_filters = [["docstatus", "!=", 2]]
	if "Sales Manager" in roles and "Accounts Manager" not in roles and "Accounts User" not in roles:
		own_deals = frappe.get_list(
			"CRM Deal",
			filters={"deal_owner": frappe.session.user},
			pluck="name",
		) or ["__none__"]
		base_filters.append(["deal", "in", own_deals])
	base_filters.extend(filters)
	fields = [
		"name",
		"sales_person",
		"employee",
		"deal",
		"customer",
		"payment_reference",
		"source_invoice",
		"commission_pct",
		"calculation_basis",
		"commission_amount",
		"currency",
		"status",
		"creation",
	]
	if frappe.db.has_column("CRM Sales Commission", "optin_network"):
		fields.append("optin_network")
	rows = _get_company_scoped_finance_rows(
		"CRM Sales Commission", base_filters, fields, company, page, page_size
	)
	rows = _add_finance_network_labels(rows, company)
	return _add_legacy_payout_labels(_add_finance_employee_labels(rows, company))


@frappe.whitelist()
def get_employee_commission_rates(company=None, filters=None):
	"""List configured Employee commission rates for Finance Setup."""
	roles = frappe.get_roles(frappe.session.user)
	if not (_is_admin(roles) or "Accounts Manager" in roles):
		frappe.throw(_("Only an Accounts Manager can view commission settings."), frappe.PermissionError)
	if not frappe.db.exists("DocType", "CRM Employee Commission Structure"):
		return []
	filters = _request_filters(filters)
	if company:
		filters.append(["employee", "in", frappe.get_all("Employee", filters={"company": company}, pluck="name") or ["__none__"]])
	return frappe.get_list(
		"CRM Employee Commission Structure",
		filters=filters,
		fields=["name", "employee", "commission_pct", "enabled", "modified"],
		order_by="modified desc",
		limit_page_length=500,
	)


@frappe.whitelist()
def get_finance_rule_options():
	"""Return active Employee and Supplier choices for Finance Settings."""
	roles = frappe.get_roles(frappe.session.user)
	if not (_is_admin(roles) or "Accounts Manager" in roles):
		frappe.throw(_("Only an Accounts Manager can view Finance settings."), frappe.PermissionError)
	employees = []
	if frappe.db.exists("DocType", "Employee"):
		employees = frappe.get_all(
			"Employee",
			filters={"status": "Active"},
			fields=["name", "employee_name"],
			order_by="employee_name asc, name asc",
			limit=500,
		)
	suppliers = []
	if frappe.db.exists("DocType", "Supplier"):
		suppliers = frappe.get_all(
			"Supplier",
			filters={"disabled": 0},
			fields=["name", "supplier_name"],
			order_by="supplier_name asc, name asc",
			limit=500,
		)
	return {"employees": employees, "suppliers": suppliers}


@frappe.whitelist()
def get_optin_network_conflicts():
	"""Return read-only Opt-In Network link conflicts for Finance review."""
	roles = frappe.get_roles(frappe.session.user)
	if not (_is_admin(roles) or "Accounts Manager" in roles):
		frappe.throw(_("Only an Accounts Manager can review Network link conflicts."), frappe.PermissionError)
	from crm.patches.v1_0.link_optin_records_to_network import collect_conflict_inventory

	return collect_conflict_inventory()


@frappe.whitelist()
def save_employee_commission_rate(employee: str, commission_pct: float, enabled: int = 1, notes: str | None = None):
	"""Create or update one Employee commission rate from Finance Setup."""
	roles = frappe.get_roles(frappe.session.user)
	if not (_is_admin(roles) or "Accounts Manager" in roles):
		frappe.throw(_("Only an Accounts Manager can change commission rates."), frappe.PermissionError)
	employee = _request_text(employee, _("Employee"), required=True)
	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Select an Employee that exists."), frappe.ValidationError)
	employee_doc = frappe.get_doc("Employee", employee)
	if employee_doc.status != "Active":
		frappe.throw(_("Commission rates can only be set for active Employees."), frappe.ValidationError)
	try:
		rate = float(commission_pct)
	except (TypeError, ValueError):
		frappe.throw(_("Enter a valid commission percentage."), frappe.ValidationError)
	if not 0 <= rate <= 100:
		frappe.throw(_("Commission percentage must be between 0 and 100."), frappe.ValidationError)
	if enabled not in (0, 1, True, False, "0", "1"):
		frappe.throw(_("Enabled must be selected or cleared."), frappe.ValidationError)
	name = frappe.db.get_value("CRM Employee Commission Structure", {"employee": employee}, "name")
	doc = frappe.get_doc("CRM Employee Commission Structure", name) if name else frappe.new_doc(
		"CRM Employee Commission Structure"
	)
	doc.employee = employee
	doc.commission_pct = rate
	doc.enabled = int(enabled)
	doc.notes = _request_text(notes, _("Notes")) if notes is not None else ""
	doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL after explicit Accounts Manager check
	return {"name": doc.name, "employee": doc.employee, "commission_pct": doc.commission_pct, "enabled": doc.enabled}


@frappe.whitelist()
def get_network_rebate_settings():
	"""List each Opt-In Network's rebate rate and configured fallback Supplier."""
	roles = frappe.get_roles(frappe.session.user)
	if not (_is_admin(roles) or "Accounts Manager" in roles):
		frappe.throw(_("Only an Accounts Manager can view rebate settings."), frappe.PermissionError)
	if not frappe.db.exists("DocType", "CRM Opt-In Network"):
		return []
	fields = ["name", "display_name", "partner_id"]
	for fieldname in ("finance_rebate_structure", "finance_supplier"):
		if frappe.db.has_column("CRM Opt-In Network", fieldname):
			fields.append(fieldname)
	rows = frappe.get_all("CRM Opt-In Network", fields=fields, order_by="display_name asc, name asc", limit=500)
	for row in rows:
		structure = row.get("finance_rebate_structure")
		row["rebate_pct"] = (
			flt(frappe.db.get_value("CRM Rebate Structure", structure, "rebate_pct"))
			if structure and frappe.db.exists("CRM Rebate Structure", structure)
			else None
		)
		row["supplier_name"] = (
			frappe.db.get_value("Supplier", row.finance_supplier, "supplier_name")
			if row.get("finance_supplier") and frappe.db.exists("Supplier", row.finance_supplier)
			else ""
		)
	return rows


@frappe.whitelist()
def save_network_rebate_settings(network: str, rebate_pct: float, supplier: str = ""):
	"""Save one Network's rebate percentage and optional fallback Supplier."""
	roles = frappe.get_roles(frappe.session.user)
	if not (_is_admin(roles) or "Accounts Manager" in roles):
		frappe.throw(_("Only an Accounts Manager can change rebate settings."), frappe.PermissionError)
	network = _request_text(network, _("Opt-In Network"), required=True)
	if not frappe.db.exists("CRM Opt-In Network", network):
		frappe.throw(_("Select an available Opt-In Network."), frappe.ValidationError)
	try:
		rate = float(rebate_pct)
	except (TypeError, ValueError):
		frappe.throw(_("Enter a valid rebate percentage."), frappe.ValidationError)
	if not 0 <= rate <= 100:
		frappe.throw(_("Rebate percentage must be between 0 and 100."), frappe.ValidationError)
	supplier = _request_text(supplier, _("Supplier"))
	if supplier:
		if not frappe.db.exists("DocType", "Supplier") or not frappe.db.exists(
			"Supplier", {"name": supplier, "disabled": 0}
		):
			frappe.throw(_("Select an active Supplier or clear the Supplier selection."), frappe.ValidationError)
	if not frappe.db.has_column("CRM Opt-In Network", "finance_rebate_structure"):
		frappe.throw(_("Rebate settings are not available until the Finance setup is refreshed."), frappe.ValidationError)
	structure_name = frappe.db.get_value("CRM Opt-In Network", network, "finance_rebate_structure")
	used_by = frappe.get_all(
		"CRM Opt-In Network",
		filters={"finance_rebate_structure": structure_name, "name": ["!=", network]},
		pluck="name",
		limit=1,
	) if structure_name else []
	if not structure_name or used_by or not frappe.db.exists("CRM Rebate Structure", structure_name):
		network_label = frappe.db.get_value("CRM Opt-In Network", network, "display_name") or network
		structure = frappe.get_doc(
			{
				"doctype": "CRM Rebate Structure",
				"structure_name": f"Network rebate {network}",
				"rebate_pct": rate,
				"notes": _("Configured for Opt-In Network {0}.").format(network_label),
			}
		).insert(ignore_permissions=True)
		structure_name = structure.name
	else:
		frappe.db.set_value("CRM Rebate Structure", structure_name, "rebate_pct", rate)
	if frappe.db.has_column("CRM Opt-In Network", "finance_supplier"):
		frappe.db.set_value("CRM Opt-In Network", network, "finance_supplier", supplier, update_modified=True)
	frappe.db.set_value(
		"CRM Opt-In Network", network, "finance_rebate_structure", structure_name, update_modified=True
	)
	return {"network": network, "finance_rebate_structure": structure_name, "rebate_pct": rate, "finance_supplier": supplier}


def _add_legacy_payout_labels(rows):
	"""Avoid presenting historical status-only Paid flags as verified payouts."""
	for row in rows:
		row.finance_status = (
			_("Legacy Paid · payout not linked") if row.get("status") == "Paid" else row.get("status")
		)
	return rows


def _get_company_scoped_finance_rows(doctype, filters, fields, company, page, page_size):
	"""Page CRM records only after validating their linked Payment Entry Company."""
	start = page * page_size
	stop = start + page_size
	scan_start = 0
	scan_size = max(page_size, 100)
	company_rows = []

	while len(company_rows) < stop:
		candidates = frappe.get_list(
			doctype,
			fields=fields,
			filters=filters,
			limit_page_length=scan_size,
			limit_start=scan_start,
			order_by="creation desc",
		)
		if not candidates:
			break

		payment_names = sorted(
			{row.get("payment_reference") for row in candidates if row.get("payment_reference")}
		)
		valid_payments = set()
		if payment_names:
			valid_payments = {
				row.get("name")
				for row in erpnext_adapter.get_list(
					"Payment Entry",
					filters=[
						["company", "=", company],
						["name", "in", payment_names],
					],
					fields=["name"],
					limit_page_length=len(payment_names),
				)
				if row.get("name")
			}
		company_rows.extend(
			row for row in candidates if row.get("payment_reference") in valid_payments
		)
		scan_start += len(candidates)
		if len(candidates) < scan_size:
			break

	return company_rows[start:stop]


def _add_finance_network_labels(rows, company):
	"""Add permission-checked Network labels and Company context to finance rows."""
	if not rows:
		return rows

	network_names = sorted({row.get("optin_network") for row in rows if row.get("optin_network")})
	networks = {}
	if network_names:
		for network in frappe.get_list(
			"CRM Opt-In Network",
			filters={"name": ["in", network_names]},
			fields=["name", "display_name"],
			limit_page_length=len(network_names),
		):
			networks[network.name] = network

	for row in rows:
		name = row.get("optin_network")
		network = networks.get(name)
		row.company = company
		row.network_label = (network.get("display_name") or name) if network else ""
		row.network_available = bool(network)
	return rows


def _add_finance_employee_labels(rows, company):
	"""Resolve CRM salespeople to one active, company-scoped ERPNext Employee."""
	if not rows:
		return rows

	users = sorted({row.get("sales_person") for row in rows if row.get("sales_person")})
	employees_by_user = {}
	if users:
		try:
			employees = erpnext_adapter.get_list(
				"Employee",
				filters=[
					["company", "=", company],
					["user_id", "in", users],
					["status", "=", "Active"],
				],
				fields=["name", "user_id", "employee_name", "company", "status"],
				limit_page_length=max(len(users) * 2, 20),
			)
			for employee in employees:
				if employee.get("company") != company or employee.get("status") != "Active":
					continue
				employees_by_user.setdefault(employee.get("user_id"), []).append(employee)
		except Exception:
			frappe.logger("crm.finance").warning(
				"Could not resolve Finance commission Employee mappings for company %s", company
			)
			employees_by_user = None

	for row in rows:
		matches = employees_by_user.get(row.get("sales_person"), []) if employees_by_user is not None else []
		if employees_by_user is None:
			row.employee = ""
			row.employee_name = "Employee mapping unavailable"
		elif len(matches) == 1:
			employee = matches[0]
			row.employee = employee.get("name")
			row.employee_name = employee.get("employee_name") or employee.get("name")
		elif len(matches) > 1:
			row.employee = ""
			row.employee_name = "Multiple active Employees match this user"
		else:
			row.employee = ""
			row.employee_name = "No active Employee linked for this Company"
		row.employee_available = len(matches) == 1 if employees_by_user is not None else False
		row.company = company
	return rows


@frappe.whitelist()
def approve_rebate_voucher(name: str, company: str | None = None) -> dict:
	roles = frappe.get_roles(frappe.session.user)
	if not any(r in roles for r in ("Accounts User", "Accounts Manager")) and not _is_admin(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	name = _require_document_permission("CRM Partner Rebate Voucher", name, "write")
	doc = frappe.get_doc("CRM Partner Rebate Voucher", name)
	doc.status = "Approved"
	doc.approved_by = frappe.session.user
	doc.approved_date = frappe.utils.nowdate()
	doc.save()
	partner_rm = frappe.db.get_value("CRM Partner", doc.partner, "partner_rm")
	if partner_rm:
		frappe.publish_realtime(
			"crm_notification",
			{
				"message": "Rebate voucher %s approved" % name,
				"user": partner_rm,
			},
		)
	_invalidate_kpi_cache(frappe.session.user, company)
	return doc.as_dict()


@frappe.whitelist()
def reject_rebate_voucher(name: str, reason: str = "", company: str | None = None) -> dict:
	roles = frappe.get_roles(frappe.session.user)
	if not any(r in roles for r in ("Accounts User", "Accounts Manager")) and not _is_admin(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	name = _require_document_permission("CRM Partner Rebate Voucher", name, "write")
	reason = _request_text(reason, "Rejection reason")
	doc = frappe.get_doc("CRM Partner Rebate Voucher", name)
	doc.status = "Rejected"
	doc.rejection_reason = reason
	doc.save()
	partner_rm = frappe.db.get_value("CRM Partner", doc.partner, "partner_rm")
	if partner_rm:
		frappe.publish_realtime(
			"crm_notification",
			{
				"message": "Rebate voucher %s rejected" % name,
				"user": partner_rm,
			},
		)
	_invalidate_kpi_cache(frappe.session.user, company)
	return doc.as_dict()


@frappe.whitelist()
def mark_rebate_paid(name: str, company: str | None = None) -> dict:
	roles = frappe.get_roles(frappe.session.user)
	if not is_manager(roles=roles):
		frappe.throw(_("Accounts Manager access is required to mark rebates as paid."), frappe.PermissionError)
	frappe.throw(
		_("Rebate payout is unavailable until Finance configures the native payable and payment flow. No status was changed."),
		frappe.ValidationError,
	)


@frappe.whitelist()
def confirm_commission(name: str, company: str | None = None) -> dict:
	roles = frappe.get_roles(frappe.session.user)
	if not any(r in roles for r in ("Accounts User", "Accounts Manager")) and not _is_admin(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	name = _require_document_permission("CRM Sales Commission", name, "write")
	doc = frappe.get_doc("CRM Sales Commission", name)
	doc.status = "Confirmed"
	doc.confirmed_by = frappe.session.user
	doc.confirmed_date = frappe.utils.nowdate()
	doc.save()
	if doc.sales_person:
		frappe.publish_realtime(
			"crm_notification",
			{
				"message": "Commission %s confirmed" % name,
				"user": doc.sales_person,
			},
		)
	_invalidate_kpi_cache(frappe.session.user, company)
	return doc.as_dict()


@frappe.whitelist()
def reject_commission(name: str, company: str | None = None) -> dict:
	roles = frappe.get_roles(frappe.session.user)
	if not any(r in roles for r in ("Accounts User", "Accounts Manager")) and not _is_admin(roles):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	name = _require_document_permission("CRM Sales Commission", name, "write")
	doc = frappe.get_doc("CRM Sales Commission", name)
	doc.status = "Rejected"
	doc.save()
	if doc.sales_person:
		frappe.publish_realtime(
			"crm_notification",
			{
				"message": "Commission %s rejected" % name,
				"user": doc.sales_person,
			},
		)
	_invalidate_kpi_cache(frappe.session.user, company)
	return doc.as_dict()


@frappe.whitelist()
def mark_commission_paid(name: str, company: str | None = None) -> dict:
	roles = frappe.get_roles(frappe.session.user)
	if not is_manager(roles=roles):
		frappe.throw(_("Accounts Manager access is required to mark commissions as paid."), frappe.PermissionError)
	frappe.throw(
		_("Commission payout is unavailable until Finance configures the payroll component and period. No status was changed."),
		frappe.ValidationError,
	)


def _invalidate_kpi_cache(user, company):
	if not company:
		return
	for period in ("month", "quarter", "year", "ytd"):
		frappe.cache().delete_value("fc_kpis_%s_%s_%s" % (user, company, period))


# ---------------------------------------------------------------------------
# fc-s3-4: Banking APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_bank_accounts(company=None):
	roles = frappe.get_roles(frappe.session.user)
	if not (_has_ar_access(roles) or _has_ap_access(roles)):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	if not frappe.db.exists("DocType", "Bank Account"):
		return []
	return erpnext_adapter.get_list(
		"Bank Account",
		fields=["name", "bank", "account", "is_company_account"],
		filters=[["company", "=", company], ["is_company_account", "=", 1]],
		order_by="name asc",
	)


@frappe.whitelist()
def get_bank_transactions(company=None, filters=None, page=0, page_size=20):
	roles = frappe.get_roles(frappe.session.user)
	if not (_has_ar_access(roles) or _has_ap_access(roles)):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	if not frappe.db.exists("DocType", "Bank Transaction"):
		return []
	base_filters = [["company", "=", company]]
	base_filters.extend(_request_filters(filters))
	return erpnext_adapter.get_list(
		"Bank Transaction",
		fields=["name", "date", "description", "deposit", "withdrawal", "currency", "status", "bank_account"],
		filters=base_filters,
		limit_page_length=page_size,
		limit_start=page * page_size,
		order_by="date desc",
	)


@frappe.whitelist()
def approve_purchase_invoice(name: str) -> dict:
	roles = frappe.get_roles(frappe.session.user)
	if "Accounts Manager" not in roles and not _is_admin(roles):
		frappe.throw(_("Only Accounts Manager can approve purchase invoices."), frappe.PermissionError)
	name = _require_document_permission("Purchase Invoice", name, "write")
	doc = frappe.get_doc("Purchase Invoice", name)
	frappe.has_permission("Company", doc=doc.company, ptype="read", throw=True)
	doc.submit()
	return {"status": "submitted", "name": name}


# ---------------------------------------------------------------------------
# fc-s4-1: Dashboard charts
# ---------------------------------------------------------------------------


def _get_cashflow_series(company, months=6):
	"""Return [{month, inflow, outflow}, ...] for the last N months."""
	t = date.fromisoformat(today())
	result = []
	for i in range(months - 1, -1, -1):
		# target month = today minus i months
		ref = date(t.year, t.month, 1)
		y = ref.year
		m = ref.month - i
		while m <= 0:
			m += 12
			y -= 1
		first = date(y, m, 1).isoformat()
		last_day = calendar.monthrange(y, m)[1]
		last = date(y, m, last_day).isoformat()
		label = date(y, m, 1).strftime("%b %Y")

		inflow = _sum_query_value(
			"Payment Entry",
			[
				["company", "=", company],
				["docstatus", "=", 1],
				["payment_type", "=", "Receive"],
				["posting_date", ">=", first],
				["posting_date", "<=", last],
			],
			"paid_amount",
		)
		outflow = _sum_query_value(
			"Payment Entry",
			[
				["company", "=", company],
				["docstatus", "=", 1],
				["payment_type", "=", "Pay"],
				["posting_date", ">=", first],
				["posting_date", "<=", last],
			],
			"paid_amount",
		)
		result.append(
			{
				"month": label,
				"inflow": float(inflow or 0),
				"outflow": float(outflow or 0),
			}
		)
	return result


def _get_ar_aging_buckets(company):
	today_str = today()
	rows = frappe.get_list(
		"Sales Invoice",
		filters=[
			["company", "=", company],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
		],
		fields=["outstanding_amount", "due_date"],
		limit=500,
	)
	buckets = {"Current": 0, "1-30d": 0, "31-60d": 0, "60+d": 0}
	for r in rows:
		age = max(0, int(date_diff(today_str, str(r.due_date)))) if r.due_date else 0
		amt = float(r.outstanding_amount or 0)
		if age <= 0:
			buckets["Current"] += amt
		elif age <= 30:
			buckets["1-30d"] += amt
		elif age <= 60:
			buckets["31-60d"] += amt
		else:
			buckets["60+d"] += amt
	return [{"bucket": k, "amount": v} for k, v in buckets.items()]


def _get_ap_aging_buckets(company):
	today_str = today()
	rows = frappe.get_list(
		"Purchase Invoice",
		filters=[
			["company", "=", company],
			["docstatus", "=", 1],
			["outstanding_amount", ">", 0],
		],
		fields=["outstanding_amount", "due_date"],
		limit=500,
	)
	buckets = {"Current": 0, "1-30d": 0, "31-60d": 0, "60+d": 0}
	for r in rows:
		age = max(0, int(date_diff(today_str, str(r.due_date)))) if r.due_date else 0
		amt = float(r.outstanding_amount or 0)
		if age <= 0:
			buckets["Current"] += amt
		elif age <= 30:
			buckets["1-30d"] += amt
		elif age <= 60:
			buckets["31-60d"] += amt
		else:
			buckets["60+d"] += amt
	return [{"bucket": k, "amount": v} for k, v in buckets.items()]


def _get_pl_summary(company, from_date, to_date):
	income = _sum_query_value(
		"Sales Invoice",
		[
			["company", "=", company],
			["docstatus", "=", 1],
			["posting_date", ">=", from_date],
			["posting_date", "<=", to_date],
		],
		"grand_total",
	)
	expenses = _sum_query_value(
		"Purchase Invoice",
		[
			["company", "=", company],
			["docstatus", "=", 1],
			["posting_date", ">=", from_date],
			["posting_date", "<=", to_date],
		],
		"grand_total",
	)
	income = float(income or 0)
	expenses = float(expenses or 0)
	return {
		"income": income,
		"expenses": expenses,
		"net": income - expenses,
		"period_label": "%s to %s" % (from_date, to_date),
	}


@frappe.whitelist()
def get_dashboard_charts(company=None, period="month"):
	company = _resolve_company(company)
	roles = frappe.get_roles(frappe.session.user)
	if not (_has_ar_access(roles) or _has_ap_access(roles) or _is_admin(roles)):
		frappe.throw(_("Finance access requires the Accounts User or Accounts Manager role."), frappe.PermissionError)

	from_date, to_date = _get_date_filter(period)
	result = {"cashflow": _get_cashflow_series(company)}
	if _has_ar_access(roles):
		result["ar_aging"] = _get_ar_aging_buckets(company)
		result["pl"] = _get_pl_summary(company, from_date, to_date)
	if _has_ap_access(roles):
		result["ap_aging"] = _get_ap_aging_buckets(company)
	# Accounts Manager gets the full accounting view.
	if _is_admin(roles) or "Accounts Manager" in roles:
		if "ar_aging" not in result:
			result["ar_aging"] = _get_ar_aging_buckets(company)
		if "pl" not in result:
			result["pl"] = _get_pl_summary(company, from_date, to_date)
		if "ap_aging" not in result:
			result["ap_aging"] = _get_ap_aging_buckets(company)
	return result


# ---------------------------------------------------------------------------
# fc-s4-3: General Ledger, Assets, Liabilities APIs
# ---------------------------------------------------------------------------


def _require_finance_manager():
	if not is_manager():
		frappe.throw("Accounts Manager role required", frappe.PermissionError)


@frappe.whitelist()
def get_journal_entries(company=None, filters=None, page=0, page_size=20):
	_require_finance_manager()
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	base_filters = [["company", "=", company], ["docstatus", "!=", 2]]
	base_filters.extend(_request_filters(filters))
	return erpnext_adapter.get_list(
		"Journal Entry",
		filters=base_filters,
		fields=["name", "posting_date", "entry_type", "total_debit", "remark", "docstatus"],
		order_by="posting_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_gl_entries(company=None, filters=None, page=0, page_size=50):
	_require_finance_manager()
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size, maximum=200)
	base_filters = [["company", "=", company], ["is_cancelled", "=", 0]]
	base_filters.extend(_request_filters(filters))
	return erpnext_adapter.get_list(
		"GL Entry",
		filters=base_filters,
		fields=[
			"name",
			"posting_date",
			"account",
			"party_type",
			"party",
			"debit",
			"credit",
			"voucher_type",
			"voucher_no",
			"cost_center",
			"remarks",
		],
		order_by="posting_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_period_closing_vouchers(company=None, page=0, page_size=20):
	_require_finance_manager()
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	if not frappe.db.exists("DocType", "Period Closing Voucher"):
		return []
	return erpnext_adapter.get_list(
		"Period Closing Voucher",
		filters=[["company", "=", company]],
		fields=["name", "transaction_date", "fiscal_year", "closing_account_head", "remarks"],
		order_by="transaction_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_subscriptions(company=None, filters=None, page=0, page_size=20):
	_require_finance_manager()
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	if not frappe.db.exists("DocType", "Subscription"):
		return []
	base_filters = [["company", "=", company]]
	base_filters.extend(_request_filters(filters))
	return erpnext_adapter.get_list(
		"Subscription",
		filters=base_filters,
		fields=["name", "party", "status", "current_invoice_start", "current_invoice_end", "days_until_due"],
		order_by="current_invoice_end asc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_assets(company=None, filters=None, page=0, page_size=20):
	_require_finance_manager()
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	if not frappe.db.exists("DocType", "Asset"):
		return []
	base_filters = [["company", "=", company], ["docstatus", "!=", 2]]
	base_filters.extend(_request_filters(filters))
	return erpnext_adapter.get_list(
		"Asset",
		filters=base_filters,
		fields=[
			"name",
			"asset_name",
			"asset_category",
			"purchase_date",
			"gross_purchase_amount",
			"accumulated_depreciation_amount",
			"value_after_depreciation",
			"status",
		],
		order_by="purchase_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_depreciation_schedule(company=None, page=0, page_size=20):
	_require_finance_manager()
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	if not frappe.db.exists("DocType", "Asset Depreciation Schedule"):
		return []
	cutoff = add_months(today(), 1)
	return erpnext_adapter.get_list(
		"Asset Depreciation Schedule",
		filters=[["company", "=", company], ["schedule_date", "<=", cutoff]],
		fields=[
			"name",
			"asset",
			"schedule_date",
			"depreciation_amount",
			"depreciation_method",
			"fiscal_year",
		],
		order_by="schedule_date asc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


@frappe.whitelist()
def get_asset_movements(company=None, page=0, page_size=20):
	_require_finance_manager()
	company = _resolve_company(company)
	page, page_size = _page_args(page, page_size)
	if not frappe.db.exists("DocType", "Asset Movement"):
		return []
	return erpnext_adapter.get_list(
		"Asset Movement",
		filters=[["company", "=", company], ["docstatus", "!=", 2]],
		fields=["name", "transaction_date", "purpose", "company"],
		order_by="transaction_date desc",
		limit_page_length=page_size,
		limit_start=page * page_size,
	)


# ---------------------------------------------------------------------------
# fc-s5-2: Global search
# ---------------------------------------------------------------------------


@frappe.whitelist()
def global_search(query, company=None, limit=20):
	"""Search across financial records. LIKE on name/party fields only."""
	query = _request_text(query, "Search text", required=True)
	limit = _request_page(limit, "Result limit", 20, 20)
	roles = frappe.get_roles(frappe.session.user)
	company = _resolve_company(company)
	per_dt = 5

	# Build a safe LIKE pattern — let the query builder parameterize it
	q = "%" + query.strip() + "%"

	results = {"create": [], "navigate": [], "reports": [], "records": []}

	if _has_ar_access(roles):
		invoices = erpnext_adapter.get_list(
			"Sales Invoice",
			fields=["name", "customer", "grand_total"],
			filters=[["company", "=", company], ["name", "like", q]],
			limit_page_length=per_dt,
		)
		for i in invoices:
			results["records"].append(
				{
					"doctype": "Sales Invoice",
					"name": i.get("name"),
					"label": i.get("name"),
					"subtitle": i.get("customer") or "",
					"meta": i.get("grand_total") or 0,
					"url": _record_url("Sales Invoice", i.get("name")),
				}
			)

		customers = erpnext_adapter.get_list(
			"Customer",
			fields=["name", "customer_name"],
			filters=[["name", "like", q]],
			limit_page_length=per_dt,
		)
		for c in customers:
			results["records"].append(
				{
					"doctype": "Customer",
					"name": c.get("name"),
					"label": c.get("customer_name") or c.get("name"),
					"subtitle": "Customer",
					"meta": "",
					"url": _record_url("Customer", c.get("name")),
				}
			)

		payments = erpnext_adapter.get_list(
			"Payment Entry",
			fields=["name", "party", "paid_amount"],
			filters=[["company", "=", company], ["payment_type", "=", "Receive"], ["name", "like", q]],
			limit_page_length=per_dt,
		)
		for p in payments:
			results["records"].append(
				{
					"doctype": "Payment Entry",
					"name": p.get("name"),
					"label": p.get("name"),
					"subtitle": p.get("party") or "",
					"meta": p.get("paid_amount") or 0,
					"url": _record_url("Payment Entry", p.get("name")),
				}
			)

	if _has_ap_access(roles):
		ap_invoices = erpnext_adapter.get_list(
			"Purchase Invoice",
			fields=["name", "supplier", "grand_total"],
			filters=[["company", "=", company], ["name", "like", q]],
			limit_page_length=per_dt,
		)
		for i in ap_invoices:
			results["records"].append(
				{
					"doctype": "Purchase Invoice",
					"name": i.get("name"),
					"label": i.get("name"),
					"subtitle": i.get("supplier") or "",
					"meta": i.get("grand_total") or 0,
					"url": _record_url("Purchase Invoice", i.get("name")),
				}
			)

		suppliers = erpnext_adapter.get_list(
			"Supplier",
			fields=["name", "supplier_name"],
			filters=[["name", "like", q]],
			limit_page_length=per_dt,
		)
		for s in suppliers:
			results["records"].append(
				{
					"doctype": "Supplier",
					"name": s.get("name"),
					"label": s.get("supplier_name") or s.get("name"),
					"subtitle": "Supplier",
					"meta": "",
					"url": _record_url("Supplier", s.get("name")),
				}
			)

	# Trim to limit across all record types
	results["records"] = results["records"][:limit]
	return results


@frappe.whitelist()
def get_token_liability_summary(company=None):
	"""Return aggregate and facility-level visibility of promotional token service liabilities."""
	company = _resolve_company(company)
	base_rate = 6.00
	trial_item = "CV-TOKEN-FREE"

	deal_facilities = frappe.db.sql(
		"""
		SELECT
			df.name,
			df.parent AS deal,
			df.facility_name,
			df.mfl_code,
			df.facility_level,
			df.cx_token_package_item,
			df.cx_token_package_quantity,
			df.cx_token_package_price,
			df.creation,
			d.organization_name,
			d.status AS deal_status
		FROM `tabCRM Deal Facility` df
		JOIN `tabCRM Deal` d ON d.name = df.parent
		WHERE df.cx_token_package_item = %s OR df.cx_token_package_item LIKE '%%FREE%%'
		ORDER BY df.creation DESC
		""",
		(trial_item,),
		as_dict=True,
	)

	total_facilities = len(deal_facilities)
	total_tokens = sum(int(r.get("cx_token_package_quantity") or 400) for r in deal_facilities)
	total_liability_kes = total_tokens * base_rate

	quote_rows = frappe.db.sql(
		"""
		SELECT
			name,
			party_name,
			crm_deal,
			crm_token_package_item,
			crm_token_facility_mfl,
			transaction_date,
			status,
			docstatus
		FROM `tabQuotation`
		WHERE crm_token_package_item = %s OR crm_token_package_item LIKE '%%FREE%%'
		ORDER BY transaction_date DESC
		""",
		(trial_item,),
		as_dict=True,
	)

	return {
		"company": company,
		"base_token_rate": base_rate,
		"trial_item_code": trial_item,
		"tokens_per_trial": 400,
		"liability_per_trial_kes": 400 * base_rate,
		"summary": {
			"total_trial_facilities": total_facilities,
			"total_promotional_tokens_issued": total_tokens,
			"total_promotional_liability_kes": total_liability_kes,
		},
		"trial_facilities": deal_facilities,
		"trial_quotations": quote_rows,
	}


# Keep the public boundary fail-closed even when a new endpoint does not need a
# document-specific role check. The individual handlers retain their native
# Document/company permission checks; this guard only controls entry to the
# accounting workspace itself.
_PUBLIC_FINANCE_API_NAMES = (
	"get_token_liability_summary",
	"get_accessible_companies",
	"get_finance_kpis",
	"get_pending_actions",
	"get_ar_invoices",
	"get_sales_orders",
	"get_signed_handoff_timeline",
	"get_sales_order_invoice_state",
	"make_sales_invoice_from_order",
	"get_customer_payments",
	"get_sales_invoice_payments",
	"get_customer_outstanding_invoices",
	"create_customer_payment",
	"make_payment_entry_from_invoice",
	"make_sales_order_from_quotation",
	"get_document_workflow_transitions",
	"apply_document_workflow_action",
	"get_customers",
	"get_quotations",
	"get_pipeline_summary",
	"get_ap_invoices",
	"get_purchase_orders",
	"get_supplier_payments",
	"get_suppliers",
	"get_expense_claims",
	"get_employee_advances",
	"get_expense_journals",
	"mark_expense_claim_paid",
	"get_rebate_vouchers",
	"get_sales_commissions",
	"approve_rebate_voucher",
	"reject_rebate_voucher",
	"mark_rebate_paid",
	"confirm_commission",
	"reject_commission",
	"mark_commission_paid",
	"get_bank_accounts",
	"get_bank_transactions",
	"approve_purchase_invoice",
	"get_dashboard_charts",
	"get_journal_entries",
	"get_gl_entries",
	"get_period_closing_vouchers",
	"get_subscriptions",
	"get_assets",
	"get_depreciation_schedule",
	"get_asset_movements",
	"global_search",
)


def _guard_public_finance_api(function):
	@wraps(function)
	def guarded(*args, **kwargs):
		require_access()
		return function(*args, **kwargs)

	# The functions above are initially decorated with ``frappe.whitelist``.
	# Wrapping them after module import creates a new callable, though, and Frappe
	# checks the callable returned by ``frappe.get_attr`` against its whitelist
	# registry by identity. Register the guarded callable as well or every request
	# fails with "Function ... is not whitelisted" before authorization runs.
	return frappe.whitelist()(guarded)


for _api_name in _PUBLIC_FINANCE_API_NAMES:
	if callable(globals().get(_api_name)):
		globals()[_api_name] = _guard_public_finance_api(globals()[_api_name])
