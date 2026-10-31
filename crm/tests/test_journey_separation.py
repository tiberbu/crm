"""One membership row, one journey.

A facility can be a Network Opt-In contact (admin or Partner Portal, contract signing) and a
Partner Coupon buyer (Self-Onboarding, Tiberbu Express tokens) in the same network. Each
journey writes only its own CRM Facility Membership row: the Customer link marks the
Self-Onboarding row and is never added to, or removed from, a Network Opt-In row.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api.facility_onboarding import _upsert_facility_membership
from crm.api.optin import _get_all_memberships, _get_membership
from crm.api.optin_admin import save_facility
from crm.partner_portal.deal import deal_won
from crm.partner_portal.pricing import configure_facility_pricing
from crm.patches.v1_0.split_mixed_journey_memberships import execute as split_mixed_rows

NETWORK = "test-journey-separation"
MFL = "JS-99001"
CONTACT = "contact@example.test"
BUYER = "buyer@example.test"
CUSTOMER = "Synthetic Separation Buyer"
PRICES = {str(year): "Standard Selling" for year in range(1, 6)}


class TestJourneySeparation(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("CRM Opt-In Network", NETWORK):
			frappe.get_doc(
				{
					"doctype": "CRM Opt-In Network",
					"slug": NETWORK,
					"display_name": "Journey Separation Network",
					"partner_id": "990011",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
					"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
				}
			).insert(ignore_permissions=True)
		for name in frappe.get_all("CRM Pre-Qualified Facility", {"mfl_code": MFL}, pluck="name"):
			frappe.delete_doc("CRM Pre-Qualified Facility", name, force=True, ignore_permissions=True)

	def _facility(self, *rows):
		doc = frappe.get_doc(
			{
				"doctype": "CRM Pre-Qualified Facility",
				"mfl_code": MFL,
				"facility_name": "Synthetic Separation Clinic",
				"keph_level": "Level 3",
				"memberships": [
					{"network": NETWORK, "status": "Active", "contact_phone": "+254700000001", **row}
					for row in rows
				],
			}
		)
		doc.flags.skip_invitation = True
		doc.insert(ignore_permissions=True)
		return doc

	def _rows(self):
		name = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": MFL}, "name")
		return frappe.get_all(
			"CRM Facility Membership",
			filters={"parent": name, "network": NETWORK},
			fields=["name", "customer", "contact_email", "price_list_override", "partner_coupon"],
			order_by="idx asc",
		)

	def _person(self, email):
		return {"first_name": "Coupon", "last_name": "Buyer", "email": email, "phone": "+254700000002"}

	def test_partner_coupon_never_adopts_the_optin_row_with_the_same_email(self):
		self._facility({"contact_name": "Contact", "contact_email": CONTACT})
		_upsert_facility_membership(
			{"mfl_code": MFL, "facility_name": "Synthetic Separation Clinic"},
			NETWORK,
			self._person(CONTACT),
			customer=CUSTOMER,
			partner_coupon=True,
		)
		rows = self._rows()
		self.assertEqual(len(rows), 2)
		self.assertEqual([bool(r.customer) for r in rows], [False, True])
		self.assertEqual(rows[1].partner_coupon, 1)
		# The opt-in contact still opens the contract journey.
		self.assertEqual(_get_membership(CONTACT, NETWORK).membership_name, rows[0].name)

	def test_deal_won_leaves_the_partner_coupon_row_alone(self):
		self._facility(
			{"contact_name": "Buyer", "contact_email": BUYER, "customer": CUSTOMER, "partner_coupon": 1}
		)
		with (
			patch("crm.partner_portal.deal._assert_portal_access"),
			patch("crm.partner_portal.deal.normalize_pricing_payload", return_value=(PRICES, {})),
			patch("crm.partner_portal.deal._send_membership_invitation"),
		):
			deal_won(
				facility=MFL,
				partner_id=NETWORK,
				contact_email=CONTACT,
				contact_name="Network Contact",
				contact_phone="+254700000003",
				send_email=0,
			)
		rows = self._rows()
		coupon = next(r for r in rows if r.customer)
		optin = next(r for r in rows if not r.customer)
		self.assertEqual((coupon.customer, coupon.contact_email, coupon.partner_coupon), (CUSTOMER, BUYER, 1))
		self.assertFalse(coupon.price_list_override)
		self.assertEqual((optin.contact_email, optin.price_list_override), (CONTACT, "Standard Selling"))

	def test_configure_pricing_never_prices_the_partner_coupon_row(self):
		self._facility(
			{"contact_name": "Buyer", "contact_email": BUYER, "customer": CUSTOMER, "partner_coupon": 1}
		)
		with (
			patch("crm.partner_portal.pricing._assert_portal_access"),
			patch("crm.partner_portal.pricing.normalize_pricing_payload", return_value=(PRICES, {})),
		):
			configure_facility_pricing(
				facility=MFL, partner_id=NETWORK, pricing=PRICES, contact_email=CONTACT
			)
		rows = self._rows()
		coupon = next(r for r in rows if r.customer)
		optin = next(r for r in rows if not r.customer)
		self.assertFalse(coupon.price_list_override)
		self.assertEqual(optin.price_list_override, "Standard Selling")
		self.assertEqual(optin.contact_email, CONTACT)

	def test_coupon_buyer_cannot_open_the_optin_journey(self):
		self._facility(
			{"contact_name": "Buyer", "contact_email": BUYER, "customer": CUSTOMER, "partner_coupon": 1}
		)
		self.assertIsNone(_get_membership(BUYER, NETWORK))
		self.assertEqual(_get_all_memberships(BUYER, NETWORK), [])

	def test_admin_edit_keeps_both_rows(self):
		facility = self._facility(
			{"contact_name": "Contact", "contact_email": CONTACT},
			{"contact_name": "Buyer", "contact_email": BUYER, "customer": CUSTOMER, "partner_coupon": 1},
		)
		with patch("crm.api.optin_admin._is_admin", return_value=True):
			save_facility(
				{
					"name": facility.name,
					"mfl_code": MFL,
					"facility_name": facility.facility_name,
					"keph_level": "Level 3",
					"memberships": [
						{
							"network": NETWORK,
							"status": "Active",
							"contact_name": "Renamed Contact",
							"contact_email": CONTACT,
							"contact_phone": "+254700000009",
						}
					],
				}
			)
		rows = self._rows()
		self.assertEqual(len(rows), 2)
		coupon = next(r for r in rows if r.customer)
		self.assertEqual((coupon.contact_email, coupon.partner_coupon), (BUYER, 1))

	def test_patch_splits_a_mixed_row(self):
		self._facility(
			{
				"contact_name": "Contact",
				"contact_email": CONTACT,
				"customer": CUSTOMER,
				"partner_coupon": 1,
				"price_list_override": "Standard Selling",
				"price_list_overrides_json": json.dumps(PRICES),
			}
		)
		split_mixed_rows()
		split_mixed_rows()  # idempotent
		rows = self._rows()
		self.assertEqual(len(rows), 2)
		optin = next(r for r in rows if not r.customer)
		coupon = next(r for r in rows if r.customer)
		self.assertEqual((optin.price_list_override, optin.partner_coupon), ("Standard Selling", 0))
		self.assertEqual((coupon.customer, coupon.partner_coupon), (CUSTOMER, 1))
		self.assertFalse(coupon.price_list_override)
