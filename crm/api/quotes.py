"""
crm/api/quotes.py — Quote lifecycle API targeting ERPNext Quotation doctype.

All whitelisted method paths are unchanged from the CRM Quote era so the
Vue frontend requires no URL changes.

Lifecycle mapping:
  Draft   = Quotation docstatus=0
  Sent    = Quotation docstatus=0  +  crm_sent=1
  Accepted = Quotation docstatus=1  (submit)
  Rejected = Quotation docstatus=2  (cancel)

CRM-specific data stored on Quotation via custom fields:
  crm_deal, crm_partner, crm_payment_terms, contract_term_yrs,
  contract_start_date, crm_sent, previous_version, discount_applied,
  vat_amount, renewal_schedule (Table → CRM Quote Renewal Schedule)

Pricing follows ERPNext's native Item Price architecture: each line's default
rate is the price_list_rate on the quote's selling_price_list (Standard Selling
by default; Negotiated Year 1-5 for multi-year deals). The exec negotiates each
line rate manually on top of that default — there is no automated tier/discount
compute engine.

Line items stored as QuotationItem rows:
  - item_code = an ERPNext Item, qty, rate = negotiated unit price
  - facility_name / package_tier custom fields carry OIS provenance when present
"""

import json

import frappe
from frappe.utils import add_days, date_diff, getdate, nowdate

from crm.api._email import create_transactional_communication
from crm.api._timeline import log_deal_event
from crm.utils.optin_bundles import split_period_amount
from crm.utils.optin_network import set_network_link
from crm.utils.price_list_history import append_change, ensure_initial, snapshot
from crm.utils.quotation_tax import apply_quotation_taxes, quotation_tax_summary

DEFAULT_PRICE_LIST = "Standard Selling"

# Frontend-facing status values derived from docstatus + crm_sent
_STATUS_ACCEPTED = "Accepted"
_STATUS_REJECTED = "Rejected"
_STATUS_SENT = "Sent"
_STATUS_DRAFT = "Draft"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _normalise_quote_totals(row):
	"""Expose one accurate, VAT-aware total shape to every quote surface.

	Quotation records created before native tax rows were enabled can contain a
	``grand_total`` that is net-only.  When the accounting fields are present,
	derive the display values through the configured VAT template.  Older test
	fixtures and installations without those fields retain their stored values.
	"""
	if not any(fieldname in row for fieldname in ("net_total", "vat_amount", "total_taxes_and_charges")):
		return row
	try:
		summary = quotation_tax_summary(row)
		row["net_total"] = summary.net_total
		row["vat_amount"] = summary.vat_amount
		row["grand_total"] = summary.grand_total
		row["vat_label"] = summary.vat_label
		return row
	except Exception:
		# A missing/misconfigured tax template must not make a quote list
		# unavailable.  Repair the common legacy net-only shape when a VAT amount
		# is already stored; otherwise preserve the native grand total.
		net_total = float(row.get("net_total") or 0)
		vat_amount = float(row.get("vat_amount") or row.get("total_taxes_and_charges") or 0)
		grand_total = float(row.get("grand_total") or 0)
		if vat_amount and grand_total <= net_total:
			grand_total = round(net_total + vat_amount, 2)
		row["net_total"] = net_total
		row["vat_amount"] = vat_amount
		row["grand_total"] = grand_total
		return row


def _is_admin(roles):
	return "System Manager" in roles or frappe.session.user == "Administrator"


def _resolve_item_code(crm_sku):
	"""Return the ERPNext item_code linked to a CRM Product, falling back to the sku itself."""
	if not crm_sku:
		return crm_sku
	erpnext_code = frappe.db.get_value("CRM Product", crm_sku, "erpnext_item_code")
	if erpnext_code and frappe.db.exists("Item", erpnext_code):
		return erpnext_code
	return crm_sku


def _item_uom(item_code):
	return frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"


def _get_item_price(item_code, price_list):
	"""
	Return the selling price_list_rate for an Item on a given Price List, honouring
	Item Price validity dates. A requested list is strict: it never silently pulls
	a Standard Selling rate into a negotiated quote. The default list is used only
	when no list was requested.
	This is the single source of default line pricing (ERPNext Item Price architecture).
	"""
	if not item_code:
		return 0.0

	def _lookup(pl):
		rows = frappe.get_list(
			"Item Price",
			filters=[
				["item_code", "=", item_code],
				["price_list", "=", pl],
				["selling", "=", 1],
			],
			fields=["price_list_rate", "valid_from", "valid_upto"],
			order_by="valid_from desc",
			limit_page_length=0,
		)
		today = getdate(nowdate())
		for r in rows:
			vf = getdate(r.valid_from) if r.valid_from else None
			vu = getdate(r.valid_upto) if r.valid_upto else None
			if (vf is None or vf <= today) and (vu is None or vu >= today):
				return float(r.price_list_rate or 0)
		# no date-valid row → fall back to the newest row regardless of dates
		return float(rows[0].price_list_rate) if rows else None

	rate = _lookup(price_list) if price_list else _lookup(DEFAULT_PRICE_LIST)
	return float(rate or 0)


def _derive_status(doc):
	"""Map ERPNext docstatus + crm_sent to the frontend-facing status string."""
	ds = int(doc.get("docstatus") or 0)
	if ds == 1:
		return _STATUS_ACCEPTED
	if ds == 2:
		return _STATUS_REJECTED
	if doc.get("crm_sent"):
		return _STATUS_SENT
	return _STATUS_DRAFT


def _get_optin_submission_for_update(deal):
	"""Lock a Deal while deciding whether its contractual quote remains editable."""
	if not deal:
		return ""
	return frappe.db.get_value("CRM Deal", deal, "optin_submission", for_update=True) or ""


def _facility_signatory_has_signed(deal):
	"""Return whether the facility signatory has completed the linked contract.

	Opt-In quotes remain negotiable until that milestone. Check both the normalized
	status and captured signature fields so legacy contracts with stale Select
	values cannot be edited after a real signature was recorded. ``None`` means
	the state could not be verified and callers must fail closed.
	"""
	deal = frappe.utils.cstr(deal or "").strip()
	if not deal:
		return False
	try:
		contracts = frappe.get_list(
			"CRM Contract",
			filters={"deal": deal},
			fields=["name"],
			order_by="creation desc",
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
		if not contracts:
			return False
		rows = frappe.get_list(
			"CRM Contract Signatory",
			filters={
				"parent": contracts[0].name,
				"parenttype": "CRM Contract",
				"signatory_role": "Facility Signatory",
			},
			fields=["status", "signature_data", "signed_at"],
			limit=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
		if not rows:
			return False
		row = rows[0]
		status = " ".join(frappe.utils.cstr(row.get("status") or "").lower().split())
		return status in ("signed", "completed", "complete", "fully signed") or bool(
			row.get("signature_data") or row.get("signed_at")
		)
	except Exception:
		# Signature lookup is intentionally fail-closed. Logging must not turn a
		# harmless missing/legacy contract DocType into a second user-facing error.
		try:
			frappe.log_error(
				frappe.get_traceback(),
				"Could not verify facility contract signature state",
			)
		except Exception:
			pass
		return None


def _quote_price_list_is_editable(doc):
	"""Whether a quote's price list can still be changed by a Sales Manager."""
	if int(doc.get("docstatus") or 0) != 0:
		return False
	deal = frappe.utils.cstr(doc.get("crm_deal") or "").strip()
	return _facility_signatory_has_signed(deal) is False


def _resolve_leaf_tree_node(doctype, configured_name, group_field, parent_field, fallback_name):
	"""Return a selectable tree node, creating one only when the tree has no leaf."""
	if configured_name and frappe.db.get_value(doctype, configured_name, "is_group") == 0:
		return configured_name

	leaves = frappe.get_list(
		doctype,
		filters={"is_group": 0},
		fields=["name"],
		order_by="lft asc",
		limit_page_length=1,
	)
	if leaves:
		return leaves[0].name

	doc = frappe.get_doc(
		{
			"doctype": doctype,
			group_field: fallback_name,
			parent_field: configured_name if frappe.db.exists(doctype, configured_name) else None,
			"is_group": 0,
		}
	)
	doc.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	return doc.name


def _ensure_customer(customer_name, *, commit=True):
	"""
	Resolve an ERPNext Customer for a CRM Deal, creating it if absent. Deals with
	no organisation fall back to a "Default Customer" that is likewise created on
	demand — so create_quote never fails on a missing party.
	"""
	target = customer_name or "Default Customer"
	if frappe.db.exists("Customer", target):
		return target

	customer_group = _resolve_leaf_tree_node(
		"Customer Group",
		frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups",
		"customer_group_name",
		"parent_customer_group",
		"Default Customer Group",
	)
	territory = _resolve_leaf_tree_node(
		"Territory",
		frappe.db.get_single_value("Selling Settings", "territory") or "All Territories",
		"territory_name",
		"parent_territory",
		"Default Territory",
	)
	cust = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": target,
			"customer_type": "Company",
			"customer_group": customer_group,
			"territory": territory,
		}
	)
	cust.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	if commit:
		frappe.db.commit()
	return cust.name


def _get_deal_price_list(deal, requested_price_list=None):
	"""Resolve a quote's baseline, preferring the Deal's configured Opt-In Network."""
	if requested_price_list:
		return requested_price_list

	network_name = frappe.db.get_value("CRM Deal", deal, "optin_network")
	if network_name:
		network = frappe.get_list(
			"CRM Opt-In Network",
			filters={"name": network_name, "enabled": 1},
			fields=["price_list_override"],
			limit_page_length=1,
		)
		if network and network[0].price_list_override:
			return network[0].price_list_override
	return DEFAULT_PRICE_LIST


def _apply_manual_rates(doc, rates):
	"""
	Make the exec's manual line rates authoritative. ERPNext's set_missing_values()
	re-fetches price_list_rate for any zero/unset rate, which would clobber a
	deliberately negotiated rate — including a waived 0 (free line). Call this AFTER
	set_missing_values() and BEFORE calculate_taxes_and_totals(), passing rates in
	doc.items order, so the "purely manual" rate always wins.
	"""
	doc.ignore_pricing_rule = 1
	for row, rate in zip(doc.items or [], rates, strict=False):
		rate = float(rate or 0)
		row.price_list_rate = rate
		row.rate = rate
		row.margin_type = ""
		row.margin_rate_or_amount = 0
		row.rate_with_margin = 0
		row.discount_percentage = 0
		row.discount_amount = 0


# ── Whitelisted API methods ────────────────────────────────────────────────────


def _require_manager():
	"""Gate mutating quote actions to Sales Manager / System Manager / Administrator."""
	roles = frappe.get_roles(frappe.session.user)
	if not (_is_admin(roles) or "Sales Manager" in roles):
		frappe.throw("Not permitted: requires Sales Manager or System Manager", frappe.PermissionError)


@frappe.whitelist()
def create_quote(deal, price_list=None):
	"""
	Create a blank Draft Quotation for a CRM Deal and return its name. This is the
	single entry point for starting a quote on any deal (OIS deals auto-build via
	crm.api.optin.build_ois_quote; non-OIS deals call this). The exec then adds
	catalogue lines and negotiates rates inline via save_quote_lines.
	"""
	_require_manager()
	if not frappe.db.exists("CRM Deal", deal):
		frappe.throw("CRM Deal not found: %s" % deal)

	price_list = _get_deal_price_list(deal, price_list)
	customer_name = _ensure_customer(frappe.db.get_value("CRM Deal", deal, "organization") or "")

	doc = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": customer_name,
			"company": frappe.db.get_single_value("Global Defaults", "default_company"),
			"transaction_date": nowdate(),
			"valid_till": add_days(nowdate(), 30),
			"currency": "KES",
			"selling_price_list": price_list,
			"order_type": "Sales",
			"crm_deal": deal,
			"crm_payment_terms": "Annual Upfront",
			"vat_amount": 0,
			"items": [],
		}
	)
	set_network_link(doc, frappe.db.get_value("CRM Deal", deal, "optin_network"))
	doc.flags.ignore_permissions = True  # SYSTEM-INTERNAL
	doc.flags.ignore_validate = True
	doc.flags.ignore_mandatory = True
	doc.set_missing_values()
	apply_quotation_taxes(doc)
	ensure_initial(doc, price_list)
	doc.insert(ignore_mandatory=True, ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name, "status": _derive_status(doc), "price_list": price_list}


@frappe.whitelist()
def list_quotes(deal):
	"""Return all Quotations for a given CRM Deal, shaped for the QuotingTab."""
	fields = [
		"name",
		"transaction_date as quote_date",
		"valid_till as valid_until",
		"contract_start_date",
		"net_total",
		"total_taxes_and_charges",
		"grand_total",
		"docstatus",
		"crm_sent",
		"crm_payment_terms as payment_terms",
		"contract_term_yrs",
		"previous_version",
		"currency",
		"creation",
	]
	for fieldname in (
		"selling_price_list",
		"crm_optin_submission",
		"crm_optin_year",
		"crm_optin_bundle_key",
		"vat_amount",
		"company",
		"taxes_and_charges",
	):
		if frappe.db.has_column("Quotation", fieldname):
			fields.append(fieldname)
	rows = frappe.get_list(
		"Quotation",
		filters=[["crm_deal", "=", deal]],
		fields=fields,
		order_by="creation desc",
	)
	# OIS billing dates are persisted on the submission after processing. Attach
	# the relevant year's rows so the CRM Quote surface can present the same
	# authoritative schedule as the portal without recalculating dates in Vue.
	_schedule_by_year = {}
	if any("crm_optin_submission" in row for row in rows) and frappe.db.exists(
		"DocType", "CRM Opt-In Submission"
	):
		try:
			submission_names = sorted(
				{
					frappe.utils.cstr(row.get("crm_optin_submission") or "").strip()
					for row in rows
					if frappe.utils.cstr(row.get("crm_optin_submission") or "").strip()
				}
			)
			if submission_names and frappe.db.has_column("CRM Opt-In Submission", "billing_schedule_json"):
				submissions = frappe.get_list(
					"CRM Opt-In Submission",
					filters=[["name", "in", submission_names]],
					fields=["name", "billing_schedule_json"],
					limit_page_length=0,
					ignore_permissions=True,  # SYSTEM-INTERNAL: quote presentation
				)
				for submission in submissions:
					try:
						schedules = json.loads(submission.get("billing_schedule_json") or "[]")
					except (TypeError, ValueError, json.JSONDecodeError):
						schedules = []
					_schedule_by_year[submission.name] = {
						int(item.get("year_number")): [item for item in schedules if isinstance(item, dict)]
						for item in schedules
						if isinstance(item, dict) and int(item.get("year_number") or 0) > 0
					}
		except Exception:
			# Schedule presentation is additive; a legacy/mid-migration site should
			# still be able to load its Quote list.
			_schedule_by_year = {}
	invoice_by_quotation = _invoices_for_quotations([r.name for r in rows])
	# Derive frontend status from docstatus + crm_sent
	for r in rows:
		_normalise_quote_totals(r)
		r["status"] = _derive_status(r)
		r["erpnext_sales_invoice"] = invoice_by_quotation.get(r["name"])
		submission_name = frappe.utils.cstr(r.get("crm_optin_submission") or "").strip()
		year_number = frappe.utils.cint(r.get("crm_optin_year") or 1) or 1
		schedule = (
			_schedule_by_year.get(submission_name, {}).get(year_number, []) if submission_name else []
		)
		for schedule_row in schedule:
			# Rows created before amount fields were introduced still have reliable
			# dates. Fill their display amounts from this year's VAT-aware quote totals.
			if "amount_incl_vat" in schedule_row:
				continue
			quarter = frappe.utils.cint(schedule_row.get("quarter_number")) or 1
			schedule_row.update(
				{
					"period_label": "Quarter %s" % quarter,
					"amount_excl_vat": split_period_amount(r.get("net_total"), quarter),
					"amount_vat": split_period_amount(r.get("vat_amount"), quarter),
					"amount_incl_vat": split_period_amount(r.get("grand_total"), quarter),
					"monthly_excl_vat": round(float(r.get("net_total") or 0) / 12, 2),
					"monthly_vat": round(float(r.get("vat_amount") or 0) / 12, 2),
					"monthly_incl_vat": round(float(r.get("grand_total") or 0) / 12, 2),
				}
			)
		r["invoice_schedule"] = schedule
	# Bundle quotes are presented in contractual year order even though native
	# quotation creation timestamps put later-year records after Year 1.
	if any(frappe.utils.cint(r.get("crm_optin_year")) for r in rows):
		rows.sort(key=lambda r: (frappe.utils.cint(r.get("crm_optin_year")) or 999, r.get("creation") or ""))
	return rows


def _invoices_for_quotations(quotation_names):
	"""Return the newest Sales Invoice name for each quotation in one query."""
	quotation_names = [name for name in quotation_names if name]
	if not quotation_names:
		return {}

	rows = frappe.get_list(
		"Sales Invoice",
		filters=[["crm_quotation", "in", quotation_names]],
		fields=["name", "crm_quotation"],
		order_by="creation desc",
	)
	invoices = {}
	for row in rows:
		invoices.setdefault(row.crm_quotation, row.name)
	return invoices


@frappe.whitelist()
def list_all_quotes(status=None, from_date=None, to_date=None, search=None, page=0, page_size=20):
	"""Paginated global Quotation list with RBAC scoping."""
	roles = frappe.get_roles(frappe.session.user)
	user = frappe.session.user
	filters = []

	if not (_is_admin(roles) or "Finance Manager" in roles or "Accounts Manager" in roles):
		if "Sales Manager" in roles:
			team_users = frappe.get_list(
				"User", filters=[["name", "!=", "Administrator"]], pluck="name", limit=500
			)
			team_deals = frappe.get_list(
				"CRM Deal",
				filters=[["deal_owner", "in", team_users]],
				pluck="name",
				limit=2000,
			) or ["__none__"]
			filters.append(["crm_deal", "in", team_deals])
		elif "Partner RM" in roles:
			own_partners = frappe.get_list("CRM Partner", filters={"partner_rm": user}, pluck="name") or [
				"__none__"
			]
			partner_deals = frappe.get_list(
				"CRM Deal",
				filters=[["partner", "in", own_partners]],
				pluck="name",
				limit=2000,
			) or ["__none__"]
			filters.append(["crm_deal", "in", partner_deals])
		else:
			own_deals = frappe.get_list("CRM Deal", filters={"deal_owner": user}, pluck="name") or [
				"__none__"
			]
			filters.append(["crm_deal", "in", own_deals])

	# Status filtering — map frontend status tokens to docstatus / crm_sent
	if status and status not in ("All",):
		if status == "Draft":
			filters += [["docstatus", "=", 0], ["crm_sent", "=", 0]]
		elif status == "Sent":
			filters += [["docstatus", "=", 0], ["crm_sent", "=", 1]]
		elif status == "Accepted":
			filters.append(["docstatus", "=", 1])
		elif status == "Rejected":
			filters.append(["docstatus", "=", 2])
		elif status == "Expired":
			filters += [["docstatus", "=", 0], ["valid_till", "<", nowdate()]]

	if from_date:
		filters.append(["transaction_date", ">=", from_date])
	if to_date:
		filters.append(["transaction_date", "<=", to_date])
	if search:
		filters.append(["name", "like", "%%%s%%" % search])

	global_fields = [
		"name",
		"crm_deal as deal",
		"party_name as customer",
		"crm_partner as partner",
		"transaction_date as quote_date",
		"valid_till as valid_until",
		"net_total",
		"total_taxes_and_charges",
		"grand_total",
		"docstatus",
		"crm_sent",
		"crm_payment_terms as payment_terms",
		"contract_term_yrs",
		"owner",
		"creation",
	]
	for fieldname in ("vat_amount", "company", "taxes_and_charges"):
		if frappe.db.has_column("Quotation", fieldname):
			global_fields.append(fieldname)
	rows = frappe.get_list(
		"Quotation",
		filters=filters,
		fields=global_fields,
		order_by="transaction_date desc",
		limit_page_length=int(page_size),
		limit_start=int(page) * int(page_size),
	)

	invoice_by_quotation = _invoices_for_quotations([r.name for r in rows])
	for r in rows:
		_normalise_quote_totals(r)
		r["status"] = _derive_status(r)
		r["erpnext_sales_invoice"] = invoice_by_quotation.get(r["name"])

	total = frappe.db.count("Quotation", filters)
	kpis = _quote_kpis()

	return {"rows": rows, "total": total, "kpis": kpis}


def _quote_kpis():
	try:
		from frappe.utils import get_first_day

		month_start = get_first_day(nowdate())

		draft_count = frappe.db.count("Quotation", [["docstatus", "=", 0], ["crm_sent", "=", 0]])
		sent_count = frappe.db.count("Quotation", [["docstatus", "=", 0], ["crm_sent", "=", 1]])

		accepted_rows = frappe.get_list(
			"Quotation",
			filters=[["docstatus", "=", 1], ["transaction_date", ">=", month_start]],
			fields=[{"SUM": "grand_total", "as": "total"}],
			limit=1,
		)
		accepted_value = float((accepted_rows[0].total or 0) if accepted_rows else 0)

		pipeline_rows = frappe.get_list(
			"Quotation",
			filters=[["docstatus", "=", 0]],
			fields=[{"SUM": "grand_total", "as": "total"}],
			limit=1,
		)
		pipeline_value = float((pipeline_rows[0].total or 0) if pipeline_rows else 0)

		return {
			"draft_count": draft_count,
			"sent_count": sent_count,
			"accepted_this_month": accepted_value,
			"pipeline_value": pipeline_value,
		}
	except Exception:
		return {"draft_count": 0, "sent_count": 0, "accepted_this_month": 0, "pipeline_value": 0}


@frappe.whitelist()
def send_quote(quote_name):
	"""Email the quote PDF to the deal's primary contact and mark crm_sent=1."""
	doc = frappe.get_doc("Quotation", quote_name)
	if doc.docstatus != 0:
		frappe.throw("Can only send a Draft quote (not yet submitted or cancelled)")

	rep_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

	# Resolve recipient from the linked CRM Deal
	recipient_email = None
	deal_name = doc.get("crm_deal")
	if deal_name:
		deal = frappe.get_doc("CRM Deal", deal_name)
		for c in deal.contacts or []:
			if c.is_primary:
				recipient_email = frappe.db.get_value("Contact", c.contact, "email_id")
				break
	if not recipient_email:
		recipient_email = frappe.db.get_value("Customer", doc.party_name, "customer_primary_email") or ""

	pdf_data = frappe.get_print("Quotation", quote_name, "Careverse Quote Standard", as_pdf=True)

	if recipient_email:
		subject = "Quotation %s — Tiberbu CareVerse HMIS" % quote_name
		message = "Please find attached the quotation %s from Tiberbu Healthnet Solutions." % quote_name
		communication_name = ""
		if deal_name:
			links = [("Quotation", quote_name)]
			try:
				ois_rows = frappe.get_list(
					"CRM Opt-In Submission",
					filters={"deal": deal_name},
					fields=["name"],
					order_by="creation desc",
					limit=1,
					ignore_permissions=True,  # SYSTEM-INTERNAL: activity linking
				)
				if ois_rows:
					links.append(("CRM Opt-In Submission", ois_rows[0].get("name")))
			except Exception:
				pass
			communication_name = create_transactional_communication(
				"CRM Deal",
				deal_name,
				subject=subject,
				content=message,
				recipients=[recipient_email],
				links=links,
				attachments=[{"fname": "%s.pdf" % quote_name, "fcontent": pdf_data}],
			)
		frappe.sendmail(
			recipients=[recipient_email],
			subject=subject,
			message=message,
			attachments=[{"fname": "%s.pdf" % quote_name, "fcontent": pdf_data}],
			sender=frappe.db.get_single_value("Email Account", "email_id") or "sales@tiberbu.com",
			sender_full_name=rep_name,
			**({"communication": communication_name} if communication_name else {}),
			**({"reference_doctype": "CRM Deal", "reference_name": deal_name} if deal_name else {}),
			now=True,
		)

	frappe.db.set_value("Quotation", quote_name, "crm_sent", 1)
	frappe.db.commit()
	return {"status": "sent", "quote_name": quote_name, "sent_to": recipient_email or ""}


@frappe.whitelist()
def accept_quote(quote_name):
	"""
	Submit the Quotation (docstatus → 1) and create a Sales Invoice via the
	native ERPNext make_sales_invoice mapper.
	"""
	doc = frappe.get_doc("Quotation", quote_name)
	if doc.docstatus != 0 or not doc.get("crm_sent"):
		frappe.throw("Only Sent quotes (crm_sent=1, docstatus=0) can be accepted")

	doc.flags.ignore_permissions = True  # SYSTEM-INTERNAL
	doc.submit()
	frappe.db.commit()

	from crm.integrations.erpnext.invoice_adapter import create_sales_invoice_from_quotation

	result = create_sales_invoice_from_quotation(quote_name)
	invoice_name = result.get("invoice_name", "")

	return {"status": "accepted", "quote_name": quote_name, "invoice_name": invoice_name}


@frappe.whitelist()
def reject_quote(quote_name):
	"""Cancel the Quotation (docstatus → 2)."""
	doc = frappe.get_doc("Quotation", quote_name)
	if doc.docstatus == 1:
		frappe.throw("Accepted (submitted) quotes cannot be rejected. Cancel the Sales Invoice first.")
	if doc.docstatus == 2:
		frappe.throw("Quote is already cancelled")
	doc.flags.ignore_permissions = True  # SYSTEM-INTERNAL
	doc.cancel()
	frappe.db.commit()
	return {"status": "rejected", "quote_name": quote_name}


@frappe.whitelist()
def list_price_lists():
	"""Selling price lists offered in the quote editor's price-list selector."""
	rows = frappe.get_list(
		"Price List",
		filters=[["selling", "=", 1], ["enabled", "=", 1], ["name", "!=", DEFAULT_PRICE_LIST]],
		fields=["name", "currency"],
		order_by="name asc",
	)
	return [
		{"value": r.name, "label": r.name, "currency": r.currency}
		for r in rows
		if frappe.utils.cstr(r.name).strip().casefold() != DEFAULT_PRICE_LIST.casefold()
	]


@frappe.whitelist()
def set_quote_price_list(quote, price_list):
	"""
	Switch a Draft/Sent (docstatus=0) Quotation to another selling price list and
	re-default every line rate from that list's Item Price (ERPNext Item Price
	architecture). Exec-negotiated overrides are intentionally reset to the new
	list's baseline; the exec re-negotiates from there. Recomputes totals + VAT.
	"""
	_require_manager()

	doc = frappe.get_doc("Quotation", quote)
	if int(doc.docstatus or 0) != 0:
		frappe.throw("Cannot update price list on a submitted or cancelled Quotation")
	deal_name = frappe.utils.cstr(doc.get("crm_deal") or "").strip()
	# Lock the deal while checking the contract milestone. A quote can be
	# re-priced after the Opt-In summary is submitted, but never after the
	# facility has signed the contract.
	_get_optin_submission_for_update(deal_name)
	facility_signed = _facility_signatory_has_signed(deal_name)
	if facility_signed is not False:
		if facility_signed:
			frappe.throw("Cannot update the price list after the facility has signed")
		frappe.throw("Could not verify the facility signature status. Please try again.")

	price_list = frappe.utils.cstr(price_list or "").strip()
	if (
		not price_list
		or price_list.casefold() == DEFAULT_PRICE_LIST.casefold()
		or not frappe.db.exists("Price List", {"name": price_list, "selling": 1, "enabled": 1})
	):
		frappe.throw("Select an enabled selling price list")

	previous_price_list = doc.get("selling_price_list") or DEFAULT_PRICE_LIST
	ensure_initial(doc, previous_price_list)
	doc.selling_price_list = price_list
	# Re-baseline every line to the new list's Item Price. A true miss resolves to
	# 0 and remains visible for the exec to price explicitly from this list.
	baseline_rates = [_get_item_price(row.item_code, price_list) for row in (doc.items or [])]

	doc.flags.ignore_permissions = True  # SYSTEM-INTERNAL
	doc.flags.ignore_validate = True
	doc.flags.ignore_mandatory = True
	doc.set_missing_values()
	_apply_manual_rates(doc, baseline_rates)
	apply_quotation_taxes(doc)
	append_change(doc, previous_price_list, price_list)
	doc.save(ignore_permissions=True)
	if deal_name and previous_price_list != price_list:
		log_deal_event(
			deal_name,
			"Price list changed on quotation %s: %s → %s before facility signature"
			% (doc.name, previous_price_list, price_list),
		)
	frappe.db.commit()
	price_snapshot = snapshot(doc)

	return {
		"price_list": price_list,
		"initial_price_list": price_snapshot["initial"],
		"price_list_history": price_snapshot["history"],
		"net_total": float(doc.net_total or 0),
		"vat_amount": float(doc.vat_amount or 0),
		"grand_total": float(doc.grand_total or 0),
	}


@frappe.whitelist()
def get_quote_lines(quote):
	"""
	Return the raw ordered QuotationItem rows of a Quotation for inline exec
	editing on the Deal → Quoting tab. Returns exactly what is stored — so
	OIS-sourced quotes with KEPH-level item codes render 1:1.
	"""
	if not frappe.has_permission("Quotation", "read", quote):
		frappe.throw("Not permitted", frappe.PermissionError)
	doc = frappe.get_doc("Quotation", quote)

	lines = []
	for it in doc.items or []:
		qty = float(it.qty or 0)
		rate = float(it.rate or 0)
		lines.append(
			{
				"item_code": it.item_code,
				"item_name": it.item_name or it.item_code,
				"description": it.description or "",
				"facility_name": it.get("facility_name") or "",
				"package_tier": it.get("package_tier") or "",
				"qty": qty,
				"rate": rate,
				"amount": float(it.amount or (qty * rate)),
			}
		)

	if not doc.net_total:
		doc.net_total = sum(line["amount"] for line in lines)
	tax_summary = quotation_tax_summary(doc)
	price_snapshot = snapshot(doc)

	return {
		"name": doc.name,
		"status": _derive_status(doc),
		"editable": int(doc.docstatus or 0) == 0
		and not frappe.db.get_value("CRM Deal", doc.get("crm_deal"), "optin_submission"),
		"price_list_editable": _quote_price_list_is_editable(doc),
		"currency": doc.currency or "KES",
		"price_list": doc.get("selling_price_list") or DEFAULT_PRICE_LIST,
		"optin_network": doc.get("optin_network") or "",
		"initial_price_list": price_snapshot["initial"],
		"price_list_history": price_snapshot["history"],
		"payment_terms": doc.get("crm_payment_terms") or "Annual Upfront",
		"valid_until": str(doc.valid_till or ""),
		"lines": lines,
		"net_total": tax_summary.net_total,
		"vat_amount": tax_summary.vat_amount,
		"grand_total": tax_summary.grand_total,
		"vat_rate": tax_summary.vat_rate,
		"vat_label": tax_summary.vat_label,
	}


@frappe.whitelist()
def save_quote_lines(quote, lines):
	"""
	Persist exec-adjusted negotiated rates / quantities / added or removed lines
	on a Draft or Sent (docstatus=0) Quotation, then recompute totals.

	Requires Sales Manager or System Manager. This is the negotiated-rate control
	the exec uses before sending the contract — it sets QuotationItem.rate
	directly. A line submitted with no rate defaults to the quote price list's
	Item Price (ERPNext Item Price architecture).
	"""
	_require_manager()

	if isinstance(lines, str):
		lines = json.loads(lines)

	doc = frappe.get_doc("Quotation", quote)
	if int(doc.docstatus or 0) != 0:
		frappe.throw("Cannot edit a submitted or cancelled Quotation")
	if _get_optin_submission_for_update(doc.get("crm_deal")):
		frappe.throw("Cannot edit a quote after its Opt-In summary is submitted")

	price_list = doc.get("selling_price_list") or DEFAULT_PRICE_LIST

	new_items = []
	for row in lines or []:
		item_code = frappe.utils.cstr(row.get("item_code") or "").strip()
		if not item_code:
			continue
		qty = float(row.get("qty") or 0)
		if qty <= 0:
			continue
		# Distinguish "no rate supplied" (default from Item Price) from a deliberate
		# negotiated 0 (a waived / free line — a legitimate manual concession).
		raw_rate = row.get("rate")
		if raw_rate in (None, ""):
			rate = _get_item_price(item_code, price_list)
		else:
			rate = float(raw_rate)
		new_items.append(
			{
				"item_code": item_code,
				"item_name": row.get("item_name") or item_code,
				"description": row.get("description") or "",
				"qty": qty,
				"rate": rate,
				"uom": _item_uom(item_code),
				"facility_name": row.get("facility_name") or "",
				"package_tier": row.get("package_tier") or "",
			}
		)

	if not new_items:
		frappe.throw("Quote must have at least one valid line item")

	doc.set("items", new_items)
	doc.flags.ignore_permissions = True  # SYSTEM-INTERNAL
	doc.flags.ignore_validate = True
	doc.flags.ignore_mandatory = True  # OIS quotes are created without a price list
	doc.set_missing_values()
	# Manual rates are authoritative — re-apply after set_missing_values so ERPNext
	# does not re-fetch price_list_rate over a negotiated (incl. waived 0) rate.
	_apply_manual_rates(doc, [it["rate"] for it in new_items])
	apply_quotation_taxes(doc)
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"name": doc.name,
		"status": _derive_status(doc),
		"net_total": float(doc.net_total or 0),
		"vat_amount": float(doc.vat_amount or 0),
		"grand_total": float(doc.grand_total or 0),
	}


@frappe.whitelist()
def list_catalogue_items(search=None, price_list=None):
	"""
	Catalogue for the inline quote 'add line' picker, sourced from ERPNext Items
	that carry a selling Item Price on the given (or default) price list. Each
	item's default rate comes from Item Price — the exec then negotiates it.
	Any sellable Item with a price is quotable, not just the 15 CRM Products.
	"""
	price_list = frappe.utils.cstr(price_list or "").strip() or DEFAULT_PRICE_LIST

	item_filters = [["disabled", "=", 0], ["is_sales_item", "=", 1]]
	if search:
		item_filters.append(["item_name", "like", "%%%s%%" % search])

	items = frappe.get_list(
		"Item",
		filters=item_filters,
		fields=["name as item_code", "item_name", "stock_uom"],
		order_by="item_name asc",
		limit_page_length=100,
	)

	rates = _catalogue_item_rates([item.item_code for item in items], price_list)
	out = []
	for it in items:
		rate = rates.get(it.item_code, 0)
		if not rate:
			continue  # only surface items that have a sellable price
		out.append(
			{
				"item_code": it.item_code,
				"label": it.item_name or it.item_code,
				"uom": it.stock_uom or "Nos",
				"rate": rate,
			}
		)
	return out


def _catalogue_item_rates(item_codes, price_list):
	"""Resolve catalogue item rates in bulk for one selected price list.

	The former picker performed one or two Item Price queries for every catalogue
	item. The quote editor can expose 100 items, so opening it could issue hundreds
	of database reads. This batches valid-date resolution into one Item Price query.
	"""
	item_codes = [item_code for item_code in item_codes if item_code]
	if not item_codes:
		return {}

	# A selected negotiated list is strict. Including Standard Selling here was
	# the source of the catalogue showing unrelated items after a list switch.
	price_lists = [price_list]

	price_rows = frappe.get_list(
		"Item Price",
		filters=[
			["item_code", "in", item_codes],
			["price_list", "in", price_lists],
			["selling", "=", 1],
		],
		fields=["item_code", "price_list", "price_list_rate", "valid_from", "valid_upto"],
		order_by="valid_from desc",
		limit_page_length=0,
	)
	rows_by_item_and_list = {}
	for row in price_rows:
		rows_by_item_and_list.setdefault((row.item_code, row.price_list), []).append(row)

	today = getdate(nowdate())

	def best_rate(rows):
		for row in rows:
			valid_from = getdate(row.valid_from) if row.valid_from else None
			valid_upto = getdate(row.valid_upto) if row.valid_upto else None
			if (valid_from is None or valid_from <= today) and (valid_upto is None or valid_upto >= today):
				return float(row.price_list_rate or 0)
		return float(rows[0].price_list_rate or 0) if rows else None

	rates = {}
	for item_code in item_codes:
		rate = best_rate(rows_by_item_and_list.get((item_code, price_list), []))
		rates[item_code] = float(rate or 0)
	return rates


@frappe.whitelist()
def check_quote_expiry():
	"""Daily scheduled job — notify deal owners of expired Draft/Sent Quotations."""
	expired = frappe.get_list(
		"Quotation",
		filters=[
			["docstatus", "=", 0],
			["valid_till", "<", nowdate()],
		],
		fields=["name", "crm_deal", "party_name as customer", "valid_till as valid_until"],
	)
	for q in expired:
		deal_owner = frappe.db.get_value("CRM Deal", q.crm_deal, "deal_owner") if q.crm_deal else None
		if not deal_owner:
			continue

		frappe.publish_realtime(
			"crm_notification",
			{
				"message": "Quotation %s has expired (valid until %s)" % (q.name, q.valid_until),
				"user": deal_owner,
			},
		)

		owner_email = frappe.db.get_value("User", deal_owner, "email")
		if owner_email:
			subject = "Quotation %s has expired" % q.name
			message = (
				"Quotation %s for customer %s expired on %s. "
				"Please create a new version or follow up with the customer."
				% (q.name, q.customer, q.valid_until)
			)
			communication_name = create_transactional_communication(
				"CRM Deal",
				q.crm_deal,
				subject=subject,
				content=message,
				recipients=[owner_email],
				links=[("Quotation", q.name)],
			)
			frappe.sendmail(
				recipients=[owner_email],
				subject=subject,
				message=message,
				**({"communication": communication_name} if communication_name else {}),
				reference_doctype="CRM Deal",
				reference_name=q.crm_deal,
				now=True,
			)
