"""
Split CRM Facility Membership rows that carry both journeys.

A membership row belongs to exactly one journey: Self-Onboarding (Partner Coupon) rows
carry a Customer, Network Opt-In rows do not. Before the journeys were separated, the
Partner Portal could write negotiated pricing onto a coupon row, and Self-Onboarding
could stamp a Customer onto an opt-in row, leaving rows with both a Customer and Year 1-5
pricing. Each such row is split in place:

1. The original row stays the Network Opt-In row: it keeps its pricing, status, contact
   and invitation history, and loses the Customer and Partner Coupon flag.
2. A new row in the same network carries the Customer and Partner Coupon flag for the
   Self-Onboarding journey.

Safe to run repeatedly: split rows no longer match.
"""

import frappe


def execute():
	if not frappe.db.table_exists("CRM Facility Membership"):
		return
	for column in ("customer", "price_list_override", "price_list_overrides_json"):
		if not frappe.db.has_column("CRM Facility Membership", column):
			return
	has_coupon = frappe.db.has_column("CRM Facility Membership", "partner_coupon")

	rows = frappe.db.sql(
		"""SELECT name, parent
		   FROM `tabCRM Facility Membership`
		   WHERE parenttype = 'CRM Pre-Qualified Facility'
		     AND IFNULL(customer, '') != ''
		     AND (IFNULL(price_list_override, '') != ''
		          OR IFNULL(price_list_overrides_json, '') NOT IN ('', '{}'))""",
		as_dict=True,
	)
	by_parent = {}
	for row in rows:
		if row.parent and frappe.db.exists("CRM Pre-Qualified Facility", row.parent):
			by_parent.setdefault(row.parent, set()).add(row.name)

	for parent, names in by_parent.items():
		facility = frappe.get_doc("CRM Pre-Qualified Facility", parent)
		for membership in list(facility.memberships):
			if membership.name not in names:
				continue
			coupon_row = {
				"network": membership.network,
				"customer": membership.customer,
				"status": membership.status or "Active",
				"go_live": membership.get("go_live") or 0,
				"contact_name": membership.contact_name,
				"contact_email": membership.contact_email,
				"contact_phone": membership.contact_phone,
			}
			membership.customer = None
			if has_coupon:
				coupon_row["partner_coupon"] = membership.get("partner_coupon") or 0
				membership.partner_coupon = 0
			facility.append("memberships", coupon_row)
		facility.flags.skip_invitation = True
		facility.save(ignore_permissions=True)
