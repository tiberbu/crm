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
				create_record(doc, invoice, ref, crm_deal)
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


def _maybe_create_rebate_voucher(payment_doc, invoice, ref, crm_deal):
	"""Create a rebate voucher from the canonical Network's configured rate."""
	# Idempotency: skip if a voucher already exists for this payment + deal
	if frappe.db.exists(
		"CRM Partner Rebate Voucher",
		{
			"payment_reference": payment_doc.name,
			"deal": crm_deal,
		},
	):
		return

	if not frappe.db.has_column("CRM Deal", "optin_network"):
		return
	optin_network = frappe.db.get_value("CRM Deal", crm_deal, "optin_network")
	if not optin_network or not frappe.db.has_column("CRM Opt-In Network", "finance_rebate_structure"):
		return
	rebate_structure = frappe.db.get_value("CRM Opt-In Network", optin_network, "finance_rebate_structure")
	if not rebate_structure:
		return
	rebate_pct = frappe.db.get_value("CRM Rebate Structure", rebate_structure, "rebate_pct")
	if not rebate_pct:
		return
	allocated = flt(ref.allocated_amount)
	if allocated <= 0:
		return
	rebate_amount = allocated * (rebate_pct / 100.0)
	legacy_partner = ""
	deal_lead = frappe.db.get_value("CRM Deal", crm_deal, "lead")
	if deal_lead and frappe.db.has_column("CRM Lead", "partner"):
		legacy_partner = frappe.db.get_value("CRM Lead", deal_lead, "partner") or ""

	voucher = frappe.get_doc(
		{
			"doctype": "CRM Partner Rebate Voucher",
			"partner": legacy_partner,
			"deal": crm_deal,
			"customer": invoice.customer,
			"payment_reference": payment_doc.name,
			"rebate_structure": rebate_structure,
			"rebate_pct": rebate_pct,
			"rebate_amount": rebate_amount,
			"currency": payment_doc.paid_to_account_currency,
			"status": "Pending",
		}
	)
	set_network_link(voucher, frappe.db.get_value("CRM Deal", crm_deal, "optin_network"))
	voucher.insert(ignore_permissions=True)  # SYSTEM-INTERNAL


def _maybe_create_commission(payment_doc, invoice, ref, crm_deal):
	"""Create a CRM Sales Commission if the deal has commission_pct set."""
	# Idempotency: skip if a commission already exists for this payment + deal
	if frappe.db.exists(
		"CRM Sales Commission",
		{
			"payment_reference": payment_doc.name,
			"deal": crm_deal,
		},
	):
		return

	deal_vals = frappe.db.get_value("CRM Deal", crm_deal, ["deal_owner", "commission_pct"], as_dict=True)
	if not deal_vals:
		return
	sales_person = deal_vals.deal_owner
	commission_pct = flt(deal_vals.commission_pct)
	if not sales_person or commission_pct <= 0:
		return
	allocated = flt(ref.allocated_amount)
	if allocated <= 0:
		return
	commission_amount = allocated * (commission_pct / 100.0)

	commission = frappe.get_doc(
		{
			"doctype": "CRM Sales Commission",
			"sales_person": sales_person,
			"deal": crm_deal,
			"customer": invoice.customer,
			"payment_reference": payment_doc.name,
			"commission_pct": commission_pct,
			"commission_amount": commission_amount,
			"currency": payment_doc.paid_to_account_currency,
			"status": "Reported",
		}
	)
	set_network_link(commission, frappe.db.get_value("CRM Deal", crm_deal, "optin_network"))
	commission.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
