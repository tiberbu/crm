"""Coupon resolution, claim and lifecycle (CRM side).

Resolves which coupon an order gets, computes and stamps its value, and claims/releases the
redemption. The mediator re-validates the line at grant time (design §5), so CRM owns the count
and the mediator owns the grant.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, now_datetime

from crm.utils import token_bonus
from crm.utils.coupon_math import coupon_tokens, derived_status


class CouponUnavailable(frappe.ValidationError):
	def __init__(self):
		super().__init__(_("This coupon has just become unavailable. Please review your order again."))


def _text(value):
	return cstr(value or "").strip()


def _hook(name):
	methods = frappe.get_hooks(name)
	return frappe.get_attr(methods[-1]) if methods else None


def _today():
	return getdate()


def purchased_tokens(doc) -> int:
	"""Tokens a token order buys: each package line's tokens per unit x qty (a Custom line is 1 x tokens).

	Moved verbatim from ``customer_experience._order_tokens`` (which becomes a one-line delegate).
	Excludes ``crm_bonus_type`` lines, so the base can never include the welcome bonus or the coupon.
	"""
	per_unit = {
		_text(row.item_code): int(row.token_quantity or 0)
		for row in frappe.get_single("CRM Opt-In Settings").get("token_packages") or []
	}
	return sum(
		per_unit.get(_text(row.item_code), 0) * int(row.qty or 0)
		for row in doc.items
		if not row.get("crm_bonus_type")
	)


PLAN_FLEX, PLAN_FIXED = "Flex", "Fixed"


def applies_to_plan(applies_to, plan) -> bool:
	"""P-108/P-109: a coupon applies to a Flex order if it is Flex or Both, to a Fixed order if Fixed or Both."""
	applies_to = _text(applies_to) or PLAN_FLEX
	return applies_to == "Both" or applies_to == plan


def PLAN_MISMATCH(plan):
	if plan == PLAN_FIXED:
		return _("This coupon is for Flex token packages only, so it cannot be used on a Fixed plan order.")
	return _("This coupon is for Fixed plans only, so it cannot be used on a Flex token order.")


def _derived(coupon) -> str:
	return derived_status(
		coupon.status,
		coupon.valid_from,
		coupon.valid_to,
		_today(),
		coupon.max_redemptions,
		coupon.redeemed_count,
	)


def _other_confirmed_orders(facility_mfl, exclude_order):
	filters = {"crm_token_facility_mfl": facility_mfl, "docstatus": 1}
	if exclude_order:
		filters["name"] = ["!=", exclude_order]
	return frappe.get_all("Sales Order", filters=filters, pluck="name", ignore_permissions=True)


def _facility_has_coupon_line(facility_mfl, exclude_order=None) -> bool:
	"""A confirmed order of this facility already carries a partner or CRM coupon line (pre-migration backstop)."""
	others = _other_confirmed_orders(facility_mfl, exclude_order)
	if not others:
		return False
	return bool(
		frappe.db.exists(
			"Sales Order Item",
			{
				"parent": ["in", others],
				"crm_bonus_type": ["in", [token_bonus.PARTNER_COUPON, token_bonus.CRM_COUPON]],
			},
		)
		# A Fixed discount uses the facility's coupon too (P-111).
		or frappe.db.exists("Sales Order Item", {"parent": ["in", others], "crm_coupon": ["is", "set"]})
	)


def coupon_grant_status(fid) -> dict:
	"""The mediator's record of this facility's coupon grant; empty until the hook is registered."""
	fid = _text(fid)
	method = _hook("crm_coupon_grant_status")
	if not (method and fid):
		return {"dispensed": False, "status": None}
	outcome = method(fid) or {}
	return {**outcome, "dispensed": bool(outcome.get("dispensed"))}


def resolve_coupon(customer, facility_mfl, facility_fid, purchased, exclude_order=None, plan=PLAN_FLEX):
	"""The coupon a facility's next confirmed order should carry, or None.

	``plan`` is the order's plan. A Flex order gets ``{"type", "coupon", "tokens", "label", "plan"}``
	(``coupon`` is None for a fallback-setting line); a Fixed order gets ``{"type", "coupon",
	"discount_percent", "label", "plan"}``. Only coupons that apply to the plan are considered.
	"""
	facility_mfl = _text(facility_mfl)
	if not facility_mfl:
		return None

	# 1. Already used? (any of three conditions)
	if frappe.db.exists("CRM Coupon Redemption", {"facility_guard": facility_mfl}):
		return None
	if coupon_grant_status(facility_fid).get("dispensed"):
		return None
	if _facility_has_coupon_line(facility_mfl, exclude_order):
		return None

	# 2. Partner coupon (the network the client entered at onboarding)
	network = token_bonus._coupon_network(customer, facility_mfl)
	if network:
		coupons = frappe.get_all(
			"CRM Coupon",
			filters={"network": network},
			fields=[
				"name",
				"status",
				"valid_from",
				"valid_to",
				"max_redemptions",
				"redeemed_count",
				"value_type",
				"value",
				"max_tokens",
				"client_label",
				"applies_to",
				"fixed_discount_percent",
			],
			ignore_permissions=True,
		)
		label = frappe.db.get_value("CRM Opt-In Network", network, "display_name") or network
		active = [c for c in coupons if _derived(c) == "Active" and applies_to_plan(c.applies_to, plan)]
		if not coupons:
			# Fallback: a network that has never had a coupon uses the global amount (tokens, so Flex only).
			tokens = token_bonus.bonus_settings()[token_bonus.PARTNER_COUPON]
			if tokens > 0 and plan == PLAN_FLEX:
				return {"type": token_bonus.PARTNER_COUPON, "coupon": None, "tokens": tokens, "label": label, "plan": plan}
			return None
		if active:
			return _benefit(active[0], token_bonus.PARTNER_COUPON, plan, purchased, active[0].client_label or label)
		return None

	# 3. CRM coupons (no network): assigned first, then the best value for this plan.
	best = None
	for coupon in _crm_coupon_candidates(facility_mfl):
		if not applies_to_plan(coupon.get("applies_to"), plan):
			continue
		benefit = _benefit(coupon, token_bonus.CRM_COUPON, plan, purchased, coupon["client_label"] or coupon["coupon_title"])
		if not benefit:
			continue
		size = benefit.get("tokens") or benefit.get("discount_percent") or 0
		key = (0 if coupon["_assigned"] else 1, -size, coupon["name"])
		if best is None or key < best[0]:
			best = (key, benefit)
	return best[1] if best else None


def _benefit(coupon, coupon_type, plan, purchased, label):
	"""What a coupon gives on an order of ``plan``, or None when it gives nothing."""
	if plan == PLAN_FIXED:
		percent = float(coupon.get("fixed_discount_percent") or 0)
		if percent <= 0:
			return None
		return {"type": coupon_type, "coupon": coupon["name"], "discount_percent": percent, "label": label, "plan": plan}
	tokens = coupon_tokens(coupon.get("value_type"), coupon.get("value"), coupon.get("max_tokens"), purchased)
	if tokens <= 0:
		return None
	return {"type": coupon_type, "coupon": coupon["name"], "tokens": tokens, "label": label, "plan": plan}


def _crm_coupon_candidates(facility_mfl):
	"""Redeemable no-network coupons targeting this facility (assigned, then facility level)."""
	assigned = {
		row.coupon
		for row in frappe.get_all(
			"CRM Coupon Assignment",
			filters={"facility_mfl": facility_mfl},
			fields=["coupon"],
			ignore_permissions=True,
		)
	}
	level = _facility_level(facility_mfl)
	all_coupons = frappe.get_all(
		"CRM Coupon",
		filters={"network": ["in", ["", None]]},
		fields=[
			"name",
			"status",
			"valid_from",
			"valid_to",
			"max_redemptions",
			"redeemed_count",
			"value_type",
			"value",
			"max_tokens",
			"targeting",
			"facility_levels",
			"client_label",
			"coupon_title",
			"applies_to",
			"fixed_discount_percent",
		],
		ignore_permissions=True,
	)
	candidates = []
	for coupon in all_coupons:
		if _derived(coupon) != "Active":
			continue
		is_assigned = coupon.name in assigned
		is_level = (
			coupon.targeting == "Facility Level" and level and _level_matches(coupon.facility_levels, level)
		)
		if not (is_assigned or is_level):
			continue
		if coupon.targeting == "Coupon Code" and not is_assigned:
			continue  # a code coupon only applies once the code is redeemed (an assignment exists)
		coupon["_assigned"] = is_assigned
		candidates.append(coupon)
	return candidates


def _facility_level(facility_mfl):
	row = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": facility_mfl}, "keph_level")
	return _text(row)


def _level_matches(facility_levels, level) -> bool:
	want = level.casefold()
	for line in cstr(facility_levels or "").splitlines():
		if line.strip().casefold() == want:
			return True
	return False


def public_offer(network):
	"""The live coupon offer for a network, for the guest onboarding page.

	Returns ``{applies_to, value_type, value, max_tokens, fixed_discount_percent, label}`` or None.
	Never returns counts or limits. A
	revoked or expired coupon shows no offer (the network still validates and onboarding proceeds).
	"""
	network = _text(network)
	if not network:
		return None
	label = frappe.db.get_value("CRM Opt-In Network", network, "display_name") or network
	coupons = frappe.get_all(
		"CRM Coupon",
		filters={"network": network},
		fields=[
			"name",
			"status",
			"valid_from",
			"valid_to",
			"max_redemptions",
			"redeemed_count",
			"value_type",
			"value",
			"max_tokens",
			"client_label",
			"applies_to",
			"fixed_discount_percent",
		],
		ignore_permissions=True,
	)
	active = [c for c in coupons if _derived(c) == "Active"]
	if active:
		coupon = active[0]
		return {
			"applies_to": coupon.applies_to or PLAN_FLEX,
			"value_type": coupon.value_type,
			"value": coupon.value,
			"max_tokens": coupon.max_tokens,
			"fixed_discount_percent": coupon.fixed_discount_percent or 0,
			"label": coupon.client_label or label,
		}
	if not coupons:
		amount = token_bonus.bonus_settings()[token_bonus.PARTNER_COUPON]
		if amount > 0:
			return {
				"applies_to": PLAN_FLEX,
				"value_type": "flat_tokens",
				"value": amount,
				"max_tokens": 0,
				"fixed_discount_percent": 0,
				"label": label,
			}
	return None


# --- Claim, release and outcome -----------------------------------------------------------


def _order_plan(doc) -> str:
	plan = token_bonus.package_plan(getattr(doc, "crm_token_package_item", None))
	return PLAN_FIXED if plan == PLAN_FIXED else PLAN_FLEX


def claim_on_submit(doc, method=None):
	"""Sales Order ``before_submit``: claim the coupon for a confirmed order in the submit transaction.

	A Flex order's coupon is a complimentary token line; a Fixed order's coupon is a discount on the
	package line (P-110). Either way the coupon must apply to the order's plan (P-109).
	"""
	token_rows = [
		row
		for row in doc.items
		if row.get("crm_bonus_type") in (token_bonus.PARTNER_COUPON, token_bonus.CRM_COUPON)
	]
	discount_rows = [row for row in doc.items if row.get("crm_coupon") and not row.get("crm_bonus_type")]
	if not (token_rows or discount_rows):
		return
	if len(token_rows) > 1 or (token_rows and discount_rows):
		frappe.throw(CouponUnavailable())
	if len({row.crm_coupon for row in discount_rows}) > 1:
		frappe.throw(CouponUnavailable())
	plan = _order_plan(doc)
	if token_rows and plan != PLAN_FLEX:
		# Complimentary tokens only ever come with a Flex purchase (P-107).
		frappe.throw(PLAN_MISMATCH(PLAN_FIXED))
	if discount_rows and plan != PLAN_FIXED:
		frappe.throw(PLAN_MISMATCH(PLAN_FLEX))
	row = (token_rows or discount_rows)[0]
	mfl = _text(doc.crm_token_facility_mfl)
	fid = _text(doc.crm_token_facility_fid) or token_bonus._order_fid(doc)

	# Idempotent: a live redemption for this order already exists.
	if frappe.db.exists(
		"CRM Coupon Redemption", {"sales_order": doc.name, "status": ["in", ["Reserved", "Granted"]]}
	):
		return

	purchased = purchased_tokens(doc)
	discount_percent = discount_amount = 0
	if row.get("crm_coupon"):
		coupon = frappe.db.get_value(
			"CRM Coupon",
			row.crm_coupon,
			[
				"status",
				"valid_from",
				"valid_to",
				"max_redemptions",
				"redeemed_count",
				"value_type",
				"value",
				"max_tokens",
				"network",
				"applies_to",
				"fixed_discount_percent",
			],
			as_dict=True,
			for_update=True,
		)
		if (
			not coupon
			or derived_status(
				coupon.status,
				coupon.valid_from,
				coupon.valid_to,
				_today(),
				coupon.max_redemptions,
				coupon.redeemed_count,
			)
			!= "Active"
		):
			frappe.throw(CouponUnavailable())
		if not applies_to_plan(coupon.applies_to, plan):
			frappe.throw(PLAN_MISMATCH(plan))
		if plan == PLAN_FIXED:
			discount_percent = flt(coupon.fixed_discount_percent)
			if discount_percent <= 0:
				frappe.throw(CouponUnavailable())
			restamped = False
			for line in discount_rows:
				# Server value wins over anything stamped earlier.
				if abs(flt(line.discount_percentage) - discount_percent) > 0.0001:
					token_bonus._set_line_discount(line, discount_percent)
					restamped = True
				discount_amount += flt(line.discount_amount) * flt(line.qty)
			if restamped:
				doc.calculate_taxes_and_totals()
			tokens = 0
		else:
			tokens = coupon_tokens(coupon.value_type, coupon.value, coupon.max_tokens, purchased)
			if tokens <= 0:
				frappe.throw(CouponUnavailable())
			row.crm_bonus_tokens = tokens  # server value wins over anything stamped earlier
		coupon_name = row.crm_coupon
		coupon_network = coupon.network
		count_after = cint(coupon.redeemed_count) + 1
	else:
		tokens = cint(row.crm_bonus_tokens)
		coupon_name = None
		coupon_network = token_bonus._coupon_network(doc.customer, mfl)
		count_after = None

	try:
		redemption = frappe.get_doc(
			{
				"doctype": "CRM Coupon Redemption",
				"coupon": coupon_name,
				"network": coupon_network,
				"bonus_type": row.crm_bonus_type or token_bonus.FIXED_DISCOUNT,
				"plan": plan,
				"discount_percent": discount_percent,
				"discount_amount": discount_amount,
				"facility_mfl": mfl,
				"facility_fid": fid or None,
				"customer": doc.customer,
				"sales_order": doc.name,
				"status": "Reserved",
				"purchased_tokens": purchased,
				"tokens_awarded": tokens,
				"redeemed_on": now_datetime(),
				# Only token coupons have a metering ledger entry.
				"ledger_key": "coupon:{}".format(fid) if fid and plan == PLAN_FLEX else None,
			}
		)
		redemption.insert(ignore_permissions=True)
	except (frappe.UniqueValidationError, frappe.QueryDeadlockError):
		frappe.throw(CouponUnavailable())

	if coupon_name:
		frappe.db.set_value("CRM Coupon", coupon_name, "redeemed_count", count_after, update_modified=False)


def release_on_cancel(doc, method=None):
	"""Sales Order ``on_cancel``: release the Reserved claim (Granted rows are untouched)."""
	rows = frappe.get_all(
		"CRM Coupon Redemption",
		{"sales_order": doc.name, "status": "Reserved"},
		pluck="name",
		ignore_permissions=True,
	)
	for name in rows:
		_close(name, "Released", "Order cancelled")


def release_redemption(name, reason=None):
	"""Admin lever for an order that will never be paid. Reserved only."""
	status = frappe.db.get_value("CRM Coupon Redemption", name, "status")
	if status != "Reserved":
		frappe.throw(_("Only a Reserved redemption can be released."))
	_close(name, "Released", reason or "Released by an administrator")


def _close(redemption_name, new_status, reason):
	"""One helper for every count-releasing transition out of Reserved."""
	if not redemption_name:
		return
	row = frappe.db.get_value("CRM Coupon Redemption", redemption_name, ["status", "coupon"], as_dict=True)
	if not row or row.status != "Reserved":
		return
	coupon = row.coupon
	if coupon:
		count = cint(frappe.db.get_value("CRM Coupon", coupon, "redeemed_count", for_update=True))
	else:
		count = 0
	doc = frappe.get_doc("CRM Coupon Redemption", redemption_name)
	doc.status = new_status
	doc.status_reason = reason
	doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL: lifecycle transition
	if coupon:
		frappe.db.set_value("CRM Coupon", coupon, "redeemed_count", max(count - 1, 0), update_modified=False)


def record_grant_outcome(redemption, outcome, *, tokens=None, invoice=None, reason=None):
	"""Called by the mediator. Idempotent: a no-op unless the row is Reserved."""
	if not redemption:
		return
	row = frappe.db.get_value("CRM Coupon Redemption", redemption, "status")
	if row != "Reserved":
		return
	if outcome == "Granted":
		doc = frappe.get_doc("CRM Coupon Redemption", redemption)
		doc.status = "Granted"
		doc.granted_on = now_datetime()
		if invoice:
			doc.sales_invoice = invoice
		if tokens is not None:
			doc.tokens_awarded = int(tokens)
		doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL: the count already reflects the claim
	else:  # Lapsed
		_close(
			redemption, "Lapsed", reason or "The coupon was revoked or expired before the invoice was paid."
		)
		if invoice:
			frappe.db.set_value("CRM Coupon Redemption", redemption, "sales_invoice", invoice)


def _paid_invoice_for_order(sales_order):
	"""The order's fully paid Sales Invoice, or None."""
	invoices = frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": sales_order, "docstatus": 1},
		pluck="parent",
		ignore_permissions=True,
	)
	for name in dict.fromkeys(invoices):
		invoice = frappe.db.get_value("Sales Invoice", name, ["status", "is_return", "outstanding_amount"], as_dict=True)
		if invoice and invoice.status == "Paid" and not cint(invoice.is_return) and flt(invoice.outstanding_amount) <= 0.005:
			return name
	return None


def _settle_fixed_redemption(row):
	"""A Fixed discount is used once its order's invoice is fully paid (P-110)."""
	try:
		invoice = _paid_invoice_for_order(row.sales_order)
		if invoice:
			record_grant_outcome(row.name, "Granted", tokens=0, invoice=invoice)
	except Exception:
		frappe.log_error(
			title="Coupon reconcile: Fixed discount row failed",
			message=frappe.as_json({"redemption": row.name, "error": frappe.get_traceback()}),
			reference_doctype="CRM Coupon Redemption",
			reference_name=row.name,
		)


def settle_fixed_discount_for_invoice(invoice_name) -> list[str]:
	"""Called by the metering app when a Fixed invoice activates a subscription: mark its discount used."""
	orders = set(
		frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": invoice_name, "sales_order": ["is", "set"]},
			pluck="sales_order",
			ignore_permissions=True,
		)
	)
	settled = []
	for name in frappe.get_all(
		"CRM Coupon Redemption",
		filters={"sales_order": ["in", list(orders) or [""]], "status": "Reserved", "plan": PLAN_FIXED},
		pluck="name",
		ignore_permissions=True,
	):
		record_grant_outcome(name, "Granted", tokens=0, invoice=invoice_name)
		settled.append(name)
	return settled


def _order_invoice_fully_paid(sales_order) -> bool:
	return bool(frappe.db.exists("Sales Invoice", {"sales_order": sales_order, "status": "Paid"}))


def reconcile_redemptions():
	"""Daily repair of a lost mediator outcome call, plus dropping stale draft lines."""
	rows = frappe.get_all(
		"CRM Coupon Redemption",
		filters={"status": "Reserved"},
		fields=["name", "facility_fid", "sales_order", "coupon", "plan"],
		ignore_permissions=True,
	)
	for row in rows:
		if row.plan == PLAN_FIXED:
			_settle_fixed_redemption(row)
			continue
		try:
			status = coupon_grant_status(row.facility_fid)
			if status.get("dispensed"):
				source = status.get("source_name")
				invoices = frappe.get_all(
					"Sales Invoice", {"sales_order": row.sales_order}, pluck="name", ignore_permissions=True
				)
				if source in invoices:
					record_grant_outcome(row.name, "Granted", invoice=source)
				else:
					_close(
						row.name, "Released", "The facility's coupon entitlement was used by another order."
					)
			elif status.get("status") in ("Pending", "Failed"):
				pass  # the mediator retries
			else:
				if _coupon_revoked_or_expired(row.coupon) and _order_invoice_fully_paid(row.sales_order):
					_close(
						row.name, "Lapsed", "The coupon was revoked or expired before the invoice was paid."
					)
		except Exception:
			frappe.log_error(
				title="Coupon reconcile: row failed",
				message=frappe.as_json({"redemption": row.name, "error": frappe.get_traceback()}),
				reference_doctype="CRM Coupon Redemption",
				reference_name=row.name,
			)

	coupons = frappe.get_all(
		"CRM Coupon",
		fields=["name", "status", "valid_from", "valid_to", "max_redemptions", "redeemed_count"],
		ignore_permissions=True,
	)
	for coupon in coupons:
		if derived_status(
			coupon.status,
			coupon.valid_from,
			coupon.valid_to,
			_today(),
			coupon.max_redemptions,
			coupon.redeemed_count,
		) in ("Revoked", "Expired"):
			try:
				token_bonus.drop_coupon_lines_from_drafts(coupon.name)
			except Exception:
				frappe.log_error(
					title="Coupon reconcile: draft drop failed",
					message=frappe.as_json({"coupon": coupon.name, "error": frappe.get_traceback()}),
					reference_doctype="CRM Coupon",
					reference_name=coupon.name,
				)


def _coupon_revoked_or_expired(coupon_name) -> bool:
	if not coupon_name:
		return False
	coupon = frappe.db.get_value(
		"CRM Coupon",
		coupon_name,
		["status", "valid_from", "valid_to", "max_redemptions", "redeemed_count"],
		as_dict=True,
	)
	if not coupon:
		return False
	return derived_status(
		coupon.status,
		coupon.valid_from,
		coupon.valid_to,
		_today(),
		coupon.max_redemptions,
		coupon.redeemed_count,
	) in ("Revoked", "Expired")
