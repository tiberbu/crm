"""Plan-scoped coupons (P-108): every coupon existing before this change gives tokens, so it is Flex.

Redemptions made before it were token redemptions, so their plan is Flex.
"""

import frappe


def execute():
	frappe.reload_doc("fcrm", "doctype", "crm_coupon")
	frappe.reload_doc("fcrm", "doctype", "crm_coupon_redemption")
	frappe.db.sql("update `tabCRM Coupon` set applies_to = 'Flex' where ifnull(applies_to, '') = ''")
	frappe.db.sql("update `tabCRM Coupon Redemption` set plan = 'Flex' where ifnull(plan, '') = ''")
