"""Coupon resolution, claim and lifecycle (CRM side).

Resolves which coupon an order gets, computes and stamps its value, and claims/releases the
redemption. The mediator re-validates the line at grant time (design §5), so CRM owns the count
and the mediator owns the grant.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, getdate, now_datetime

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
	return sum(per_unit.get(_text(row.item_code), 0) * int(row.qty or 0) for row in doc.items if not row.get("crm_bonus_type"))


def _derived(coupon) -> str:
	return derived_status(
		coupon.status, coupon.valid_from, coupon.valid_to, _today(), coupon.max_redemptions, coupon.redeemed_count
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
			{"parent": ["in", others], "crm_bonus_type": ["in", [token_bonus.PARTNER_COUPON, token_bonus.CRM_COUPON]]},
		)
	)


def coupon_grant_status(fid) -> dict:
	"""The mediator's record of this facility's coupon grant; empty until the hook is registered."""
	fid = _text(fid)
	method = _hook("crm_coupon_grant_status")
	if not (method and fid):
		return {"dispensed": False, "status": None}
	outcome = method(fid) or {}
	return {**outcome, "dispensed": bool(outcome.get("dispensed"))}


def resolve_coupon(customer, facility_mfl, facility_fid, purchased, exclude_order=None):
	"""The coupon a facility's next confirmed order should carry, or None.

	Returns ``{"type", "coupon", "tokens", "label"}``; ``coupon`` is None for a fallback-setting line.
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
			fields=["name", "status", "valid_from", "valid_to", "max_redemptions", "redeemed_count", "value_type", "value", "max_tokens", "client_label"],
			ignore_permissions=True,
		)
		label = frappe.db.get_value("CRM Opt-In Network", network, "display_name") or network
		active = [c for c in coupons if _derived(c) == "Active"]
		if not coupons:
			# Fallback: a network that has never had a coupon uses the global amount.
			tokens = token_bonus.bonus_settings()[token_bonus.PARTNER_COUPON]
			if tokens > 0:
				return {"type": token_bonus.PARTNER_COUPON, "coupon": None, "tokens": tokens, "label": label}
			return None
		if active:
			coupon = active[0]
			tokens = coupon_tokens(coupon.value_type, coupon.value, coupon.max_tokens, purchased)
			if tokens > 0:
				return {
					"type": token_bonus.PARTNER_COUPON,
					"coupon": coupon.name,
					"tokens": tokens,
					"label": coupon.client_label or label,
				}
		return None

	# 3. CRM coupons (no network): assigned first, then facility level.
	candidates = _crm_coupon_candidates(facility_mfl)
	best = None
	for coupon in candidates:
		tokens = coupon_tokens(coupon["value_type"], coupon["value"], coupon["max_tokens"], purchased)
		if tokens <= 0:
			continue
		key = (0 if coupon["_assigned"] else 1, -tokens, coupon["name"])
		if best is None or key < best[0]:
			best = (key, coupon, tokens)
	if best is None:
		return None
	_, coupon, tokens = best
	return {
		"type": token_bonus.CRM_COUPON,
		"coupon": coupon["name"],
		"tokens": tokens,
		"label": coupon["client_label"] or coupon["coupon_title"],
	}


def _crm_coupon_candidates(facility_mfl):
	"""Redeemable no-network coupons targeting this facility (assigned, then facility level)."""
	assigned = {
		row.coupon
		for row in frappe.get_all("CRM Coupon Assignment", filters={"facility_mfl": facility_mfl}, fields=["coupon"], ignore_permissions=True)
	}
	level = _facility_level(facility_mfl)
	all_coupons = frappe.get_all(
		"CRM Coupon",
		filters={"network": ["in", ["", None]]},
		fields=["name", "status", "valid_from", "valid_to", "max_redemptions", "redeemed_count", "value_type", "value", "max_tokens", "targeting", "facility_levels", "client_label", "coupon_title"],
		ignore_permissions=True,
	)
	candidates = []
	for coupon in all_coupons:
		if _derived(coupon) != "Active":
			continue
		is_assigned = coupon.name in assigned
		is_level = coupon.targeting == "Facility Level" and level and _level_matches(coupon.facility_levels, level)
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

	Returns ``{value_type, value, max_tokens, label}`` or None. Never returns counts or limits. A
	revoked or expired coupon shows no offer (the network still validates and onboarding proceeds).
	"""
	network = _text(network)
	if not network:
		return None
	label = frappe.db.get_value("CRM Opt-In Network", network, "display_name") or network
	coupons = frappe.get_all(
		"CRM Coupon",
		filters={"network": network},
		fields=["name", "status", "valid_from", "valid_to", "max_redemptions", "redeemed_count", "value_type", "value", "max_tokens", "client_label"],
		ignore_permissions=True,
	)
	active = [c for c in coupons if _derived(c) == "Active"]
	if active:
		coupon = active[0]
		return {
			"value_type": coupon.value_type,
			"value": coupon.value,
			"max_tokens": coupon.max_tokens,
			"label": coupon.client_label or label,
		}
	if not coupons:
		amount = token_bonus.bonus_settings()[token_bonus.PARTNER_COUPON]
		if amount > 0:
			return {"value_type": "flat_tokens", "value": amount, "max_tokens": 0, "label": label}
	return None


# --- Claim, release and outcome -----------------------------------------------------------


def claim_on_submit(doc, method=None):
	"""Sales Order ``before_submit``: claim the coupon for a confirmed order in the submit transaction."""
	rows = [row for row in doc.items if row.get("crm_bonus_type") in (token_bonus.PARTNER_COUPON, token_bonus.CRM_COUPON)]
	if not rows:
		return
	if len(rows) > 1:
		frappe.throw(CouponUnavailable())
	row = rows[0]
	mfl = _text(doc.crm_token_facility_mfl)
	fid = _text(doc.crm_token_facility_fid) or token_bonus._order_fid(doc)

	# Idempotent: a live redemption for this order already exists.
	if frappe.db.exists("CRM Coupon Redemption", {"sales_order": doc.name, "status": ["in", ["Reserved", "Granted"]]}):
		return

	purchased = purchased_tokens(doc)
	if row.get("crm_coupon"):
		coupon = frappe.db.get_value(
			"CRM Coupon",
			row.crm_coupon,
			["status", "valid_from", "valid_to", "max_redemptions", "redeemed_count", "value_type", "value", "max_tokens", "network"],
			as_dict=True,
			for_update=True,
		)
		if not coupon or derived_status(
			coupon.status, coupon.valid_from, coupon.valid_to, _today(), coupon.max_redemptions, coupon.redeemed_count
		) != "Active":
			frappe.throw(CouponUnavailable())
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
				"bonus_type": row.crm_bonus_type,
				"facility_mfl": mfl,
				"facility_fid": fid or None,
				"customer": doc.customer,
				"sales_order": doc.name,
				"status": "Reserved",
				"purchased_tokens": purchased,
				"tokens_awarded": tokens,
				"redeemed_on": now_datetime(),
				"ledger_key": "coupon:{}".format(fid) if fid else None,
			}
		)
		redemption.insert(ignore_permissions=True)
	except (frappe.UniqueValidationError, frappe.QueryDeadlockError):
		frappe.throw(CouponUnavailable())

	if coupon_name:
		frappe.db.set_value("CRM Coupon", coupon_name, "redeemed_count", count_after, update_modified=False)


def release_on_cancel(doc, method=None):
	"""Sales Order ``on_cancel``: release the Reserved claim (Granted rows are untouched)."""
	rows = frappe.get_all("CRM Coupon Redemption", {"sales_order": doc.name, "status": "Reserved"}, pluck="name", ignore_permissions=True)
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
		_close(redemption, "Lapsed", reason or "The coupon was revoked or expired before the invoice was paid.")
		if invoice:
			frappe.db.set_value("CRM Coupon Redemption", redemption, "sales_invoice", invoice)


def _order_invoice_fully_paid(sales_order) -> bool:
	return bool(frappe.db.exists("Sales Invoice", {"sales_order": sales_order, "status": "Paid"}))


def reconcile_redemptions():
	"""Daily repair of a lost mediator outcome call, plus dropping stale draft lines."""
	rows = frappe.get_all(
		"CRM Coupon Redemption",
		filters={"status": "Reserved"},
		fields=["name", "facility_fid", "sales_order", "coupon"],
		ignore_permissions=True,
	)
	for row in rows:
		try:
			status = coupon_grant_status(row.facility_fid)
			if status.get("dispensed"):
				source = status.get("source_name")
				invoices = frappe.get_all("Sales Invoice", {"sales_order": row.sales_order}, pluck="name", ignore_permissions=True)
				if source in invoices:
					record_grant_outcome(row.name, "Granted", invoice=source)
				else:
					_close(row.name, "Released", "The facility's coupon entitlement was used by another order.")
			elif status.get("status") in ("Pending", "Failed"):
				pass  # the mediator retries
			else:
				if _coupon_revoked_or_expired(row.coupon) and _order_invoice_fully_paid(row.sales_order):
					_close(row.name, "Lapsed", "The coupon was revoked or expired before the invoice was paid.")
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
		if derived_status(coupon.status, coupon.valid_from, coupon.valid_to, _today(), coupon.max_redemptions, coupon.redeemed_count) in ("Revoked", "Expired"):
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
		"CRM Coupon", coupon_name, ["status", "valid_from", "valid_to", "max_redemptions", "redeemed_count"], as_dict=True
	)
	if not coupon:
		return False
	return derived_status(coupon.status, coupon.valid_from, coupon.valid_to, _today(), coupon.max_redemptions, coupon.redeemed_count) in ("Revoked", "Expired")
