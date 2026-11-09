"""Synthetic fixture for the journey-separation Playwright run (e2e/journey-separation/).

Network Opt-In (Partner Portal `deal_won`, `/opt-in` contract journey) and Partner Coupon
(Value Express `/facility-onboarding`) must work side by side on one network. Run explicitly on
a dev site; every record carries the marker `jse2e` so `teardown` removes exactly what the run
created:

    bench --site <site> execute crm.tests.e2e_journey_separation_fixture.setup \
        --kwargs '{"run_id": "0001", "secret_file": "/secure/path"}'

`setup` creates a network with a fresh Partner Coupon, an admin user (password written to
`secret_file`, mode 600), a Partner-Coupon-only contact on a third facility, and a verified
Value Express session whose OTP is known, so only the external identity lookup is mocked in the
browser. `deal_won`, `optin_otp` and `state` let the spec drive and check the backend, and
`teardown` deletes every record created since `setup` that contains the marker.
"""

from __future__ import annotations

import email
import hashlib
import os
import random
import re
import secrets
import time

import frappe

MARKER = "jse2e"
OTP = "424242"


def _names(run_id: str) -> dict:
	run_id = frappe.utils.cstr(run_id).strip()
	if not run_id.isalnum():
		frappe.throw("run_id must be alphanumeric")
	return {
		"network": f"{MARKER}-network-{run_id}".lower(),
		"display_name": f"JSE2E Network {run_id} (synthetic)",
		"buyer_email": f"{MARKER}-buyer-{run_id}@example.test".lower(),
		"coupon_only_email": f"{MARKER}-coupononly-{run_id}@example.test".lower(),
		"admin_email": f"{MARKER}-admin-{run_id}@example.test".lower(),
		"coupon_only_customer": f"JSE2E Coupon Only {run_id}",
		"mfl_a": f"JSE2E{run_id}A".upper(),
		"mfl_b": f"JSE2E{run_id}B".upper(),
		"mfl_c": f"JSE2E{run_id}C".upper(),
	}


def _free_partner_id() -> str:
	for _ in range(50):
		candidate = str(random.randint(100000, 999999))
		if not frappe.db.exists("CRM Opt-In Network", {"partner_id": candidate}):
			return candidate
	frappe.throw("No free Partner ID found")


def _customer(name: str) -> str:
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
	return name


def setup(run_id: str, secret_file: str) -> dict:
	from crm.api.facility_onboarding import (
		_delivery_payload,
		_identity_reference,
		_otp_hash,
		_save_session,
	)

	started = frappe.utils.now()
	n = _names(run_id)
	partner_id = _free_partner_id()
	# Like a real partner network: a five-year contract schedule the Partner Portal prices against.
	price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
	schedule = [
		{"year_number": year, "price_list": price_list, "label": f"Year {year}", "enabled": True}
		for year in range(1, 6)
	]
	frappe.get_doc(
		{
			"doctype": "CRM Opt-In Network",
			"price_lists_json": frappe.as_json(schedule),
			"slug": n["network"],
			"display_name": n["display_name"],
			"partner_id": partner_id,
			"contact_email": f"{MARKER}-network-{run_id}@example.test".lower(),
			"enabled": 1,
		}
	).insert(ignore_permissions=True)

	# An admin who manages networks in the CRM UI.
	password = secrets.token_urlsafe(18)
	admin = frappe.get_doc(
		{
			"doctype": "User",
			"email": n["admin_email"],
			"first_name": "JSE2E",
			"last_name": f"Admin {run_id}",
			"user_type": "System User",
			"send_welcome_email": 0,
			"new_password": password,
			"roles": [{"role": "System Manager"}, {"role": "Sales Manager"}],
		}
	)
	admin.flags.no_welcome_mail = True
	admin.insert(ignore_permissions=True)
	fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
	with os.fdopen(fd, "w") as f:
		f.write(password)

	# Facility C: a Partner Coupon buyer only; this contact must never reach /opt-in.
	facility_c = frappe.get_doc(
		{
			"doctype": "CRM Pre-Qualified Facility",
			"mfl_code": n["mfl_c"],
			"facility_name": f"JSE2E Coupon Clinic {run_id} (synthetic)",
			"keph_level": "Level 2",
			"memberships": [
				{
					"network": n["network"],
					"customer": _customer(n["coupon_only_customer"]),
					"partner_coupon": 1,
					"status": "Active",
					"contact_name": "JSE2E Coupon Only",
					"contact_email": n["coupon_only_email"],
					"contact_phone": "+254700000001",
				}
			],
		}
	)
	facility_c.flags.skip_invitation = True
	facility_c.insert(ignore_permissions=True)

	# A verified-identity Value Express session: OTP known, HFR facilities already resolved.
	token = secrets.token_urlsafe(32)
	now = int(time.time())
	id_number = f"{MARKER}{run_id}"
	facilities = [
		{
			"facility_id": f"FID-{MARKER}-{run_id}-{suffix}".upper(),
			"mfl_code": n[f"mfl_{suffix.lower()}"],
			"facility_name": f"JSE2E Clinic {run_id}{suffix} (synthetic)",
			"classification": "Level 2",
			"facility_level": "Level 2",
			"facility_type": "Medical Clinic",
			"facility_category": "",
			"number_of_beds": 0,
			"county": "",
			"sub_county": "",
			"owner_type": "",
			"registration_number": "",
			"license_number": "",
		}
		for suffix in ("A", "B")
	]
	session = {
		"verified": False,
		"lookup_valid": True,
		"id_type": "national_id",
		"identity_hash": hashlib.sha256(id_number.encode()).hexdigest(),
		"identity_ref": _identity_reference("national_id", id_number),
		"identity_number": id_number,
		"person": {
			"first_name": "JSE2E",
			"last_name": f"Buyer {run_id}",
			"email": n["buyer_email"],
			"phone": "+254700000002",
		},
		"otp_hash": _otp_hash(OTP),
		"otp_attempts": 0,
		"otp_expires_at": now + 600,
		"otp_sent_at": now,
		"resend_count": 0,
		"delivery": {"channel": "email", "masked_destination": "j***2@example.test", "status": "sent"},
		"delivery_mask_decoy": False,
		"hfr_state": "ready",
		"facilities": facilities,
	}
	_save_session(token, session)
	frappe.db.commit()
	return {
		"started": started,
		"partner_id": partner_id,
		"network": n["network"],
		"display_name": n["display_name"],
		"buyer_email": n["buyer_email"],
		"coupon_only_email": n["coupon_only_email"],
		"admin_email": n["admin_email"],
		"session_token": token,
		"otp": OTP,
		"delivery": _delivery_payload(session, now),
		"facilities": [
			{"facility_name": f["facility_name"], "mfl_code": f["mfl_code"], "facility_id": f["facility_id"]}
			for f in facilities
		],
	}


def deal_won(run_id: str, mfl_code: str, contact_email: str) -> dict:
	"""The Partner Portal (F360) closes a deal: enrol the facility for Opt-In and invite the contact."""
	from crm.partner_portal.deal import deal_won as partner_deal_won

	n = _names(run_id)
	price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
	result = partner_deal_won(
		facility={
			"mfl_code": mfl_code,
			"facility_name": f"JSE2E Clinic {mfl_code} (synthetic)",
			"keph_level": "Level 2",
		},
		partner_id=n["network"],
		price_lists={str(year): price_list for year in range(1, 6)},
		contact_email=contact_email,
		contact_name="JSE2E Network Contact",
		contact_phone="+254700000003",
		send_email=1,
	)
	frappe.db.commit()
	queue = frappe.utils.cstr((result.get("membership") or {}).get("invite_email_queue"))
	message = _html_body(frappe.db.get_value("Email Queue", queue, "message") if queue else "").replace(
		"&amp;", "&"
	)
	return {
		"success": result.get("success"),
		"email_sent": result.get("email_sent"),
		"email_error": result.get("email_error"),
		"invitation_url": result.get("invitation_url"),
		"email_links_optin": f"/opt-in?network={n['network']}" in message,
		"email_links_express": "/cx-portal" in message,
	}


def _html_body(raw) -> str:
	"""The decoded HTML of a queued email (Email Queue stores the raw MIME message)."""
	raw = frappe.utils.cstr(raw)
	try:
		parsed = email.message_from_string(raw)
		parts = list(parsed.walk()) if parsed.is_multipart() else [parsed]
		html = " ".join(
			frappe.utils.cstr(part.get_payload(decode=True), "utf-8")
			for part in parts
			if part.get_content_type() == "text/html"
		)
		return html or raw
	except Exception:
		return raw


def optin_otp(email: str, since: str) -> str:
	"""The newest Opt-In OTP emailed to this contact after `since` ('' when none yet)."""
	parents = frappe.get_all("Email Queue Recipient", {"recipient": email}, pluck="parent")
	if not parents:
		return ""
	for row in frappe.get_all(
		"Email Queue",
		filters={"name": ["in", parents], "creation": [">", since]},
		fields=["message"],
		order_by="creation desc",
	):
		body = _html_body(row.message)
		match = re.search(r"monospace[^>]*>\s*(\d{6})\s*<", body)
		if match:
			return match.group(1)
	return ""


def state(run_id: str) -> dict:
	"""Each synthetic facility's rows in the network, for assertions."""
	n = _names(run_id)
	out = {}
	for key in ("mfl_a", "mfl_b", "mfl_c"):
		parent = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": n[key]}, "name")
		out[key[-1]] = (
			frappe.get_all(
				"CRM Facility Membership",
				filters={"parent": parent, "network": n["network"]},
				fields=[
					"name",
					"customer",
					"partner_coupon",
					"contact_email",
					"contact_name",
					"status",
					"price_list_override",
					"invite_sent_at",
				],
				order_by="idx asc",
			)
			if parent
			else []
		)
	return out


def teardown(run_id: str, since: str) -> dict:
	"""Delete every record created since `since` whose content carries the run's marker."""
	_names(run_id)
	marker = MARKER
	doctypes = frappe.get_all("DocType", filters={"istable": 0, "issingle": 0, "is_virtual": 0}, pluck="name")
	found = []
	for doctype in doctypes:
		try:
			if not frappe.db.table_exists(doctype):
				continue
			names = frappe.get_all(
				doctype, filters={"creation": [">=", since]}, pluck="name", limit_page_length=0
			)
		except Exception:
			continue
		for name in names:
			try:
				doc = frappe.get_doc(doctype, name)
				if marker in doc.as_json().lower():
					found.append((doctype, name, doc.docstatus))
			except Exception:
				continue

	deleted, failed = 0, []
	# Children and dependants first: retry until nothing more can go.
	pending = found
	for _ in range(4):
		remaining = []
		for doctype, name, docstatus in pending:
			try:
				if not frappe.db.exists(doctype, name):
					continue
				if docstatus == 1:
					frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)
				frappe.db.commit()
				deleted += 1
			except Exception:
				frappe.db.rollback()
				try:
					# Append-only records (onboarding evidence) refuse delete_doc; this run's own
					# synthetic rows are removed directly.
					frappe.db.delete(doctype, {"name": name})
					frappe.db.commit()
					deleted += 1
				except Exception:
					frappe.db.rollback()
					remaining.append((doctype, name, docstatus))
		pending = remaining
		if not pending:
			break
	frappe.db.commit()
	for doctype, name, _ in pending:
		failed.append(f"{doctype}:{name}")
	leftovers = {
		"facilities": frappe.db.count(
			"CRM Pre-Qualified Facility", {"mfl_code": ["like", f"{marker.upper()}%"]}
		),
		"memberships": frappe.db.count("CRM Facility Membership", {"contact_email": ["like", f"{marker}-%"]}),
		"networks": frappe.db.count("CRM Opt-In Network", {"slug": ["like", f"{marker}-%"]}),
		"users": frappe.db.count("User", {"name": ["like", f"{marker}-%"]}),
		"customers": frappe.db.count("Customer", {"name": ["like", "JSE2E%"]}),
	}
	return {"found": len(found), "deleted": deleted, "failed": failed, "leftovers": leftovers}
