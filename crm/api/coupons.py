"""Admin API for the coupon domain: manage, assign, redeem and release coupons."""

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr, now_datetime

from crm.utils import coupons
from crm.utils.coupon_math import derived_status


def _text(value):
	return cstr(value or "").strip()


def _is_admin(user=None):
	from crm.api.optin_admin import _is_admin as _admin

	return _admin(user)


def _assert_coupon_access(coupon_name):
	from crm.api.optin_admin import _assert_network_access

	network = frappe.db.get_value("CRM Coupon", coupon_name, "network")
	if network:
		_assert_network_access(network)
	elif not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _get_coupon(name):
	row = frappe.db.get_value(
		"CRM Coupon",
		name,
		[
			"name",
			"coupon_title",
			"network",
			"value_type",
			"value",
			"max_tokens",
			"valid_from",
			"valid_to",
			"status",
			"max_redemptions",
			"per_facility_limit",
			"redeemed_count",
			"targeting",
			"facility_levels",
			"coupon_code",
			"client_label",
			"description",
			"revoked_on",
			"revoked_by",
			"revocation_reason",
		],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Coupon {0} does not exist.").format(name), frappe.ValidationError)
	row["derived_status"] = derived_status(
		row.status,
		row.valid_from,
		row.valid_to,
		frappe.utils.getdate(),
		row.max_redemptions,
		row.redeemed_count,
	)
	return row


@frappe.whitelist()
def get_coupon(name: Any):
	"""The full coupon for the admin editor, plus its derived status."""
	name = _text(name)
	_assert_coupon_access(name)
	return _get_coupon(name)


@frappe.whitelist()
def list_coupons(network: Any = None):
	"""The coupons a user may see: admins all, coordinators only their networks."""
	from crm.api.optin_admin import _assert_network_access, _get_coordinator_networks

	network = _text(network)
	if network:
		_assert_network_access(network)
		filters = {"network": network}
	elif not _is_admin():
		mine = _get_coordinator_networks()
		if not mine:
			return {"coupons": []}
		filters = {"network": ["in", mine]}
	else:
		filters = {}
	fields = [
		"name",
		"coupon_title",
		"network",
		"value_type",
		"value",
		"max_tokens",
		"valid_from",
		"valid_to",
		"status",
		"max_redemptions",
		"redeemed_count",
		"targeting",
		"coupon_code",
		"client_label",
		"modified",
	]
	rows = frappe.get_all(
		"CRM Coupon", filters=filters, fields=fields, ignore_permissions=True, order_by="modified desc"
	)
	for row in rows:
		row["derived_status"] = derived_status(
			row.status,
			row.valid_from,
			row.valid_to,
			frappe.utils.getdate(),
			row.max_redemptions,
			row.redeemed_count,
		)
	return {"coupons": rows}


@frappe.whitelist()
def save_coupon(name: Any, payload: Any):
	"""Create or edit a coupon. Coordinators may only touch a coupon on their own network."""
	from crm.api.optin_admin import _get_coordinator_networks

	payload = frappe._dict(payload or {})
	name = _text(name)
	network = _text(payload.get("network")) or None
	if not name:
		if not network and not _is_admin():
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		if network and not _is_admin() and network not in _get_coordinator_networks():
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		coupon = frappe.new_doc("CRM Coupon")
	else:
		_assert_coupon_access(name)
		coupon = frappe.get_doc("CRM Coupon", name)

	coupon.coupon_title = _text(payload.get("coupon_title")) or coupon.name
	coupon.network = network
	coupon.value_type = _text(payload.get("value_type"))
	coupon.value = payload.get("value")
	coupon.max_tokens = int(payload.get("max_tokens") or 0)
	coupon.valid_from = payload.get("valid_from") or None
	coupon.valid_to = payload.get("valid_to") or None
	coupon.max_redemptions = int(payload.get("max_redemptions") or 0)
	coupon.targeting = _text(payload.get("targeting")) or None
	coupon.facility_levels = payload.get("facility_levels") or ""
	coupon.coupon_code = payload.get("coupon_code") or ""
	coupon.client_label = payload.get("client_label") or ""
	coupon.description = payload.get("description") or ""
	coupon.insert(ignore_permissions=True) if coupon.is_new() else coupon.save(ignore_permissions=True)
	return {"name": coupon.name}


@frappe.whitelist()
def revoke_coupon(name: Any, reason: Any = None):
	"""Revoke a coupon (terminal). Revoked coupons stop new redemptions; granted tokens are never clawed back."""
	name = _text(name)
	_assert_coupon_access(name)
	row = frappe.db.get_value("CRM Coupon", name, "status")
	if not row:
		frappe.throw(_("Coupon {0} does not exist.").format(name), frappe.ValidationError)
	if row == "Revoked":
		return {"name": name, "status": "Revoked"}
	doc = frappe.get_doc("CRM Coupon", name)
	doc.status = "Revoked"
	doc.revoked_on = now_datetime()
	doc.revoked_by = frappe.session.user
	doc.revocation_reason = _text(reason)
	doc.save(ignore_permissions=True)
	return {"name": name, "status": "Revoked"}


@frappe.whitelist()
def list_redemptions(coupon: Any = None, network: Any = None):
	"""Redemption records, filtered by coupon or network (a coordinator sees only their networks)."""
	from crm.api.optin_admin import _get_coordinator_networks

	coupon = _text(coupon)
	network = _text(network)
	if coupon:
		_assert_coupon_access(coupon)
		filters = {"coupon": coupon}
	elif network:
		from crm.api.optin_admin import _assert_network_access

		_assert_network_access(network)
		filters = {"network": network}
	else:
		if not _is_admin():
			mine = _get_coordinator_networks()
			if not mine:
				return {"redemptions": []}
			filters = {"network": ["in", mine]}
		else:
			filters = {}
	rows = frappe.get_all(
		"CRM Coupon Redemption",
		filters=filters,
		fields=[
			"name",
			"coupon",
			"network",
			"facility_mfl",
			"facility_fid",
			"customer",
			"sales_order",
			"sales_invoice",
			"status",
			"tokens_awarded",
			"redeemed_on",
			"granted_on",
			"status_reason",
		],
		ignore_permissions=True,
		order_by="redeemed_on desc",
	)
	for row in rows:
		row["coupon_title"] = (
			frappe.db.get_value("CRM Coupon", row.coupon, "coupon_title") if row.coupon else None
		)
	return {"redemptions": rows}


@frappe.whitelist()
def assign_coupon(coupon: Any, facility_mfls: Any, facility_fids: Any = None):
	"""Assign a CRM coupon to facilities (one row per MFL). Idempotent."""
	coupon = _text(coupon)
	_assert_coupon_access(coupon)
	row = frappe.db.get_value("CRM Coupon", coupon, ["network", "status", "targeting"], as_dict=True)
	if not row or row.network:
		frappe.throw(_("Assignments are for CRM coupons (no network)."), frappe.ValidationError)
	if row.status != "Active":
		frappe.throw(_("Only an active coupon can be assigned."), frappe.ValidationError)
	if row.targeting != "Assigned Facilities":
		frappe.throw(
			_("Assignments require a coupon with Assigned Facilities targeting."), frappe.ValidationError
		)
	facility_mfls = [m.strip() for m in cstr(facility_mfls or "").replace("\n", ",").split(",") if m.strip()]
	facility_fids = facility_fids or {}
	assigned, already = [], []
	for mfl in facility_mfls:
		existing = frappe.db.exists("CRM Coupon Assignment", {"coupon": coupon, "facility_mfl": mfl})
		if existing:
			already.append(mfl)
			continue
		frappe.get_doc(
			{
				"doctype": "CRM Coupon Assignment",
				"coupon": coupon,
				"facility_mfl": mfl,
				"facility_fid": facility_fids.get(mfl) if isinstance(facility_fids, dict) else None,
				"source": "Manual",
			}
		).insert(ignore_permissions=True)
		assigned.append(mfl)
	return {"assigned": assigned, "already": already}


@frappe.whitelist()
def list_assignments(coupon: Any):
	coupon = _text(coupon)
	_assert_coupon_access(coupon)
	rows = frappe.get_all(
		"CRM Coupon Assignment",
		filters={"coupon": coupon},
		fields=["coupon", "facility_mfl", "facility_fid"],
		ignore_permissions=True,
	)
	return {"assignments": rows}


@frappe.whitelist()
def remove_assignment(coupon: Any, facility_mfl: Any):
	coupon = _text(coupon)
	facility_mfl = _text(facility_mfl)
	_assert_coupon_access(coupon)
	existing = frappe.db.exists("CRM Coupon Assignment", {"coupon": coupon, "facility_mfl": facility_mfl})
	if not existing:
		frappe.throw(_("No assignment to remove."), frappe.ValidationError)
	frappe.delete_doc("CRM Coupon Assignment", existing, ignore_permissions=True)
	return {"name": existing}


@frappe.whitelist()
def redeem_code(code: Any, customer: Any, facility_mfl: Any, facility_fid: Any = None):
	"""Redeem a Coupon Code on behalf of a logged-in portal user's facility. Creates the assignment."""
	from crm.api.website_redirect import require_portal_user

	code = _text(code).upper()
	customer = _text(customer)
	facility_mfl = _text(facility_mfl)
	if code not in require_portal_user():
		frappe.throw(_("This code is not linked to your account."), frappe.PermissionError)
	coupon = frappe.db.get_value("CRM Coupon", {"coupon_code": code}, "name")
	if not coupon:
		frappe.throw(_("That coupon code is not valid."))
	row = frappe.db.get_value("CRM Coupon", coupon, ["network", "status", "targeting"], as_dict=True)
	if row.network or row.targeting != "Coupon Code":
		frappe.throw(_("That coupon code is not redeemable."))
	if row.status != "Active":
		frappe.throw(_("That coupon is no longer active."))
	if frappe.db.exists("CRM Coupon Assignment", {"coupon": coupon, "facility_mfl": facility_mfl}):
		return {"coupon": coupon, "assignment": "already"}
	frappe.get_doc(
		{
			"doctype": "CRM Coupon Assignment",
			"coupon": coupon,
			"facility_mfl": facility_mfl,
			"facility_fid": _text(facility_fid) or None,
			"source": "Code",
		}
	).insert(ignore_permissions=True)
	return {"coupon": coupon, "assignment": "created"}


@frappe.whitelist()
def release_redemption(name: Any, reason: Any = None):
	"""Release a Reserved redemption (admin lever for an order that will never be paid)."""
	name = _text(name)
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	coupons.release_redemption(name, reason)
	return {"status": frappe.db.get_value("CRM Coupon Redemption", name, "status")}


@frappe.whitelist()
def get_facility_coupons(customer: Any, facility_mfl: Any, facility_fid: Any = None):
	"""The facility's current coupon (if it would apply) plus its redemption history, for the staff form."""
	facility_mfl = _text(facility_mfl)
	if not _is_admin() and not facility_mfl:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	resolved = coupons.resolve_coupon(customer, facility_mfl, _text(facility_fid), 0)
	rows = frappe.get_all(
		"CRM Coupon Redemption",
		filters={"facility_mfl": facility_mfl},
		fields=["name", "coupon", "status", "tokens_awarded", "redeemed_on", "granted_on", "status_reason"],
		ignore_permissions=True,
		order_by="redeemed_on desc",
	)
	coupon_data = None
	if resolved and resolved.get("coupon"):
		coupon_data = _get_coupon(resolved["coupon"])
	return {"coupon": coupon_data, "redemptions": rows}
