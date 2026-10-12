import frappe
from frappe.utils import flt

from crm.utils.optin_network import set_network_link


# SYSTEM-INTERNAL — runs as Payment Entry on_submit; uses ignore_permissions
def on_payment_entry_submit(doc, method):
	"""Create CRM accruals without making the native accounting submit fail."""
	if doc.payment_type != "Receive":
		return
	warnings = []
	for ref in doc.get("references", []):
		if ref.reference_doctype != "Sales Invoice":
			warnings.append(
				"CRM rebate and commission records are created only for receipts allocated to Sales Invoices. "
				f"No CRM accrual was created for {ref.reference_doctype} {ref.reference_name}."
			)
			continue
		try:
			invoice = frappe.get_doc("Sales Invoice", ref.reference_name)
		except frappe.DoesNotExistError:
			warnings.append(
				f"CRM rebate and commission records could not be created because Sales Invoice "
				f"{ref.reference_name} is unavailable."
			)
			continue
		# Resolve CRM Deal via Sales Invoice.crm_deal custom field (created by v1_0 patch)
		crm_deal = frappe.db.get_value("Sales Invoice", invoice.name, "crm_deal")
		if not crm_deal:
			continue
		for label, create_record in (
			("rebate voucher", _maybe_create_rebate_voucher),
			("sales commission", _maybe_create_commission),
		):
			try:
				reason = create_record(doc, invoice, ref, crm_deal)
				if reason:
					warnings.append(reason)
			except Exception:
				# These are secondary CRM records. Preserve the submitted ledger entry,
				# log the trace, and return a support reference to the caller.
				error_log = frappe.log_error(
					title=f"Finance {label.title()} Creation Failed",
					message=frappe.get_traceback(),
					reference_doctype="Payment Entry",
					reference_name=doc.name,
				)
				reference = getattr(error_log, "name", "Finance Payment Hook")
				warnings.append(
					f"The Payment Entry was submitted, but its {label} could not be created. "
					f"Contact Finance support with reference {reference}."
				)

	if warnings:
		warning_map = getattr(frappe.flags, "crm_finance_payment_warnings", None)
		if not isinstance(warning_map, dict):
			warning_map = {}
			frappe.flags.crm_finance_payment_warnings = warning_map
		warning_map.setdefault(doc.name, []).extend(warnings)
		frappe.msgprint(
			"\n".join(warnings),
			title="Payment submitted with CRM follow-up",
			indicator="orange",
		)


def _network_for_deal(crm_deal):
	if not frappe.db.has_column("CRM Deal", "optin_network"):
		return ""
	return frappe.utils.cstr(frappe.db.get_value("CRM Deal", crm_deal, "optin_network") or "").strip()


def _invoice_facility_bases(invoice, allocated):
	"""Split a received invoice allocation over its facility lines, preserving the total."""
	items = list(invoice.get("items") or [])
	if not items:
		return [frappe._dict(mfl_code="", facility_name="", supplier="", basis=allocated)]

	groups = {}
	total = 0.0
	for item in items:
		line_amount = flt(item.get("base_net_amount") or item.get("net_amount") or item.get("amount"))
		if line_amount <= 0:
			continue
		mfl_code = frappe.utils.cstr(item.get("crm_optin_facility_mfl_code") or "").strip()
		facility_name = frappe.utils.cstr(item.get("facility_name") or item.get("item_name") or "").strip()
		supplier = frappe.utils.cstr(item.get("crm_rebate_supplier") or "").strip()
		key = (mfl_code, facility_name, supplier)
		groups[key] = groups.get(key, 0.0) + line_amount
		total += line_amount
	if not groups or total <= 0:
		return [frappe._dict(mfl_code="", facility_name="", supplier="", basis=allocated)]

	rows = []
	remaining = allocated
	for index, ((mfl_code, facility_name, supplier), amount) in enumerate(groups.items()):
		basis = remaining if index == len(groups) - 1 else flt(allocated * amount / total, 2)
		remaining -= basis
		rows.append(
			frappe._dict(
				mfl_code=mfl_code,
				facility_name=facility_name,
				supplier=supplier,
				basis=basis,
			)
		)
	return rows


def _maybe_create_rebate_voucher(payment_doc, invoice, ref, crm_deal):
	"""Create rate-snapshotted rebate rows for each facility share of a receipt."""
	optin_network = _network_for_deal(crm_deal)
	if not optin_network or not frappe.db.has_column("CRM Opt-In Network", "finance_rebate_structure"):
		return "No rebate was accrued because this Deal has no configured Opt-In Network rebate rule."
	rebate_structure = frappe.db.get_value("CRM Opt-In Network", optin_network, "finance_rebate_structure")
	if not rebate_structure:
		return "No rebate was accrued because the Opt-In Network has no rebate rule configured."
	rebate_pct = flt(frappe.db.get_value("CRM Rebate Structure", rebate_structure, "rebate_pct"))
	if rebate_pct <= 0:
		return "No rebate was accrued because the configured rebate rate is zero or unavailable."
	allocated = flt(ref.allocated_amount)
	if allocated <= 0:
		return "No rebate was accrued because the invoice allocation is zero."

	legacy_partner = ""
	deal_lead = frappe.db.get_value("CRM Deal", crm_deal, "lead")
	if deal_lead and frappe.db.has_column("CRM Lead", "partner"):
		legacy_partner = frappe.db.get_value("CRM Lead", deal_lead, "partner") or ""
	network_supplier = ""
	if frappe.db.has_column("CRM Opt-In Network", "finance_supplier"):
		network_supplier = frappe.utils.cstr(
			frappe.db.get_value("CRM Opt-In Network", optin_network, "finance_supplier") or ""
		).strip()
	created = 0
	missing_payee = False
	for facility in _invoice_facility_bases(invoice, allocated):
		payee = facility.supplier or network_supplier
		if not payee or not frappe.db.exists("Supplier", payee):
			missing_payee = True
			continue
		filters = {
			"payment_reference": payment_doc.name,
			"source_invoice": invoice.name,
			"facility_mfl_code": facility.mfl_code or "",
		}
		if frappe.db.exists("CRM Partner Rebate Voucher", filters):
			continue
		voucher = frappe.get_doc(
			{
				"doctype": "CRM Partner Rebate Voucher",
				"partner": legacy_partner,
				"deal": crm_deal,
				"customer": invoice.customer,
				"payment_reference": payment_doc.name,
				"source_invoice": invoice.name,
				"facility_mfl_code": facility.mfl_code,
				"facility_name": facility.facility_name,
				"payee_supplier": payee,
				"rebate_structure": rebate_structure,
				"rebate_pct": rebate_pct,
				"calculation_basis": facility.basis,
				"rebate_amount": facility.basis * (rebate_pct / 100.0),
				"currency": invoice.get("currency") or payment_doc.paid_to_account_currency,
				"status": "Pending",
			}
		)
		set_network_link(voucher, optin_network)
		voucher.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
		created += 1
	if missing_payee and not created:
		return "No rebate was accrued because neither a facility Supplier nor the Network Supplier is configured."
	if missing_payee:
		return "Some facility rebates were not accrued because a Supplier is unavailable."
	return ""


def _resolve_deal_employee(crm_deal, company):
	deal_user = frappe.utils.cstr(frappe.db.get_value("CRM Deal", crm_deal, "deal_owner") or "").strip()
	if not deal_user:
		return None, "No commission was accrued because the Deal has no linked User."
	if not frappe.db.exists("DocType", "Employee"):
		return None, "No commission was accrued because Employee records are unavailable."
	employees = frappe.get_all(
		"Employee",
		filters={"user_id": deal_user, "company": company, "status": "Active"},
		fields=["name", "user_id", "company"],
		limit=3,
	)
	if len(employees) != 1:
		return None, (
			"No commission was accrued because the Deal User must link to exactly one active Employee "
			"for the invoice Company."
		)
	return employees[0], ""


def _maybe_create_commission(payment_doc, invoice, ref, crm_deal):
	"""Create a payment-based commission for the uniquely linked Employee."""
	allocated = flt(ref.allocated_amount)
	if allocated <= 0:
		return "No commission was accrued because the invoice allocation is zero."
	employee, reason = _resolve_deal_employee(crm_deal, invoice.company)
	if not employee:
		return reason
	rule = frappe.db.get_value(
		"CRM Employee Commission Structure",
		{"employee": employee.name, "enabled": 1},
		["name", "commission_pct"],
		as_dict=True,
	)
	if not rule or flt(rule.commission_pct) <= 0:
		return "No commission was accrued because this Employee has no enabled commission rate."
	filters = {"payment_reference": payment_doc.name, "source_invoice": invoice.name, "employee": employee.name}
	if frappe.db.exists("CRM Sales Commission", filters):
		return ""
	commission_pct = flt(rule.commission_pct)
	commission = frappe.get_doc(
		{
			"doctype": "CRM Sales Commission",
			"sales_person": employee.user_id,
			"employee": employee.name,
			"deal": crm_deal,
			"customer": invoice.customer,
			"payment_reference": payment_doc.name,
			"source_invoice": invoice.name,
			"commission_pct": commission_pct,
			"calculation_basis": allocated,
			"commission_amount": allocated * (commission_pct / 100.0),
			"currency": invoice.get("currency") or payment_doc.paid_to_account_currency,
			"status": "Reported",
		}
	)
	set_network_link(commission, _network_for_deal(crm_deal))
	commission.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	return ""
