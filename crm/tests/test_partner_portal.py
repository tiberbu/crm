"""Unit tests for Partner Portal APIs.

Tests:
1. configure_facility_pricing (POST) with standard Price Lists and custom rates.
2. configure_facility_pricing idempotency.
3. get_facility_pricing (GET) single retrieval and search.
4. deal_won (POST) facility enrollment under network with custom pricing and opt-in invitation email.
5. deal_won idempotency and validation guards.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.partner_portal.deal import deal_won
from crm.partner_portal.pricing import (
	configure_facility_pricing,
	get_facility_pricing,
)
from crm.partner_portal.utils import (
	ensure_price_list,
	normalize_pricing_payload,
	resolve_network,
	resolve_or_create_facility,
	set_item_price_rate,
)


class TestPartnerPortal(UnitTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.test_network_slug = "test-partner-portal-network"
		cls.test_partner_id = "889977"

		# Ensure test partner network
		if not frappe.db.exists("CRM Opt-In Network", cls.test_network_slug):
			net = frappe.new_doc("CRM Opt-In Network")
			net.name = cls.test_network_slug
			net.slug = cls.test_network_slug
			net.display_name = "Test Partner Network"
			net.partner_id = cls.test_partner_id
			net.enabled = 1
			net.insert(ignore_permissions=True)
		else:
			frappe.db.set_value(
				"CRM Opt-In Network",
				cls.test_network_slug,
				{"partner_id": cls.test_partner_id, "enabled": 1},
			)

		# Ensure standard negotiated price lists exist
		for y in range(1, 6):
			pl_name = f"Negotiated Year {y}"
			ensure_price_list(pl_name)
			set_item_price_rate(pl_name, "CV-HIMS-KEPH-3", 25000.0 + (y * 1000))

		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")

	def test_resolve_network_by_partner_id_and_slug(self):
		net_by_id = resolve_network(self.test_partner_id)
		self.assertEqual(net_by_id.name, self.test_network_slug)

		net_by_slug = resolve_network(self.test_network_slug)
		self.assertEqual(net_by_slug.partner_id, self.test_partner_id)

		with self.assertRaises(frappe.DoesNotExistError):
			resolve_network("non-existent-partner-999999")

	def test_resolve_or_create_facility(self):
		mfl = "MFL-TEST-001"
		fac = resolve_or_create_facility(
			{
				"mfl_code": mfl,
				"facility_name": "Test Facility One",
				"keph_level": "Level 3",
				"organization": "Test Health Org",
			}
		)
		self.assertEqual(fac.mfl_code, mfl)
		self.assertEqual(fac.facility_name, "Test Facility One")

		# Resolving again with string returns the existing facility
		resolved = resolve_or_create_facility(mfl)
		self.assertEqual(resolved.name, fac.name)

	def test_configure_facility_pricing_standard_pricelists(self):
		mfl = "MFL-TEST-PL-01"
		pricing_input = {
			"1": "Negotiated Year 1",
			"2": "Negotiated Year 2",
			"3": "Negotiated Year 3",
			"4": "Negotiated Year 4",
			"5": "Negotiated Year 5",
		}

		res = configure_facility_pricing(
			facility={"mfl_code": mfl, "facility_name": "Standard PL Facility"},
			partner_id=self.test_partner_id,
			pricing=pricing_input,
		)

		self.assertTrue(res["success"])
		self.assertEqual(res["price_lists"]["1"], "Negotiated Year 1")
		self.assertEqual(res["price_lists"]["5"], "Negotiated Year 5")
		self.assertEqual(len(res["pricing_by_year"]), 5)

		# Verify persisted membership overrides
		fac = frappe.get_doc("CRM Pre-Qualified Facility", res["facility"]["name"])
		membership = next(m for m in fac.memberships if m.network == self.test_network_slug)
		self.assertEqual(membership.price_list_override, "Negotiated Year 1")
		overrides = json.loads(membership.price_list_overrides_json)
		self.assertEqual(overrides["2"], "Negotiated Year 2")

	def test_configure_facility_pricing_custom_rates(self):
		mfl = "MFL-TEST-CUSTOM-RATES"
		rates_input = {
			"1": 30000,
			"2": 32000,
			"3": 34000,
			"4": 36000,
			"5": 38000,
		}

		res = configure_facility_pricing(
			facility={"mfl_code": mfl, "facility_name": "Custom Rates Facility", "keph_level": "Level 4"},
			partner_id=self.test_partner_id,
			pricing=rates_input,
		)

		self.assertTrue(res["success"])
		self.assertEqual(len(res["pricing_by_year"]), 5)
		year_1 = res["pricing_by_year"][0]
		self.assertEqual(year_1["year_number"], 1)
		self.assertEqual(year_1["rate"], 30000.0)
		self.assertEqual(year_1["monthly_rate"], 30000.0)
		self.assertEqual(year_1["annual_rate"], 360000.0)

		year_5 = res["pricing_by_year"][4]
		self.assertEqual(year_5["rate"], 38000.0)

		# Verify custom price list and Item Price doc created
		pl_y1 = res["price_lists"]["1"]
		item_prices = frappe.get_list(
			"Item Price",
			filters={"price_list": pl_y1, "selling": 1},
			fields=["price_list_rate"],
		)
		self.assertTrue(len(item_prices) > 0)
		self.assertEqual(float(item_prices[0].price_list_rate), 30000.0)

	def test_configure_facility_pricing_idempotency(self):
		key = f"idem-key-{frappe.generate_hash(length=10)}"
		payload = {
			"facility": "MFL-IDEM-01",
			"partner_id": self.test_partner_id,
			"pricing": {"1": "Negotiated Year 1", "2": "Negotiated Year 2"},
			"idempotency_key": key,
		}

		first_call = configure_facility_pricing(**payload)
		self.assertTrue(first_call["success"])
		self.assertNotIn("cached", first_call)

		second_call = configure_facility_pricing(**payload)
		self.assertTrue(second_call["success"])
		self.assertTrue(second_call.get("cached"))
		self.assertEqual(first_call["facility"]["name"], second_call["facility"]["name"])

	def test_get_facility_pricing_search_and_retrieval(self):
		mfl = "MFL-GET-TEST-01"
		configure_facility_pricing(
			facility={"mfl_code": mfl, "facility_name": "Get Search Facility Alpha"},
			partner_id=self.test_partner_id,
			pricing={"1": 22000, "2": 24000, "3": 26000, "4": 28000, "5": 30000},
		)

		# Query specific facility
		single_res = get_facility_pricing(facility=mfl, partner_id=self.test_partner_id)
		self.assertTrue(single_res["success"])
		self.assertEqual(single_res["facility"]["mfl_code"], mfl)
		self.assertEqual(len(single_res["pricing_by_year"]), 5)
		self.assertEqual(single_res["pricing_by_year"][0]["rate"], 22000.0)

		# Query specific year
		y2_res = get_facility_pricing(facility=mfl, partner_id=self.test_partner_id, year=2)
		self.assertEqual(len(y2_res["pricing_by_year"]), 1)
		self.assertEqual(y2_res["pricing_by_year"][0]["year_number"], 2)
		self.assertEqual(y2_res["pricing_by_year"][0]["rate"], 24000.0)

		# Search by keyword
		search_res = get_facility_pricing(search="Search Facility Alpha")
		self.assertTrue(search_res["success"])
		self.assertGreaterEqual(search_res["total"], 1)
		found = any(r["facility"]["mfl_code"] == mfl for r in search_res["results"])
		self.assertTrue(found)

	def test_deal_won_api_full_flow(self):
		mfl = f"MFL-DEAL-WON-{frappe.generate_hash(length=6)}"
		contact_email = f"contact_{frappe.generate_hash(length=4)}@example.com"
		contact_person = "Dr. John Doe"

		pricing_input = {
			"1": 27500,
			"2": 29000,
			"3": 31000,
			"4": 33000,
			"5": 35000,
		}

		res = deal_won(
			facility={
				"mfl_code": mfl,
				"facility_name": f"Deal Won Medical Centre {mfl}",
				"keph_level": "Level 3",
			},
			partner_id=self.test_partner_id,
			price_lists=pricing_input,
			contact_email=contact_email,
			contact_person=contact_person,
			contact_phone="+254711223344",
			send_email=1,
		)

		self.assertTrue(res["success"])
		self.assertTrue(res["deal_won"])
		self.assertEqual(res["facility"]["mfl_code"], mfl)
		self.assertEqual(res["membership"]["contact_email"], contact_email)
		self.assertEqual(res["membership"]["contact_name"], contact_person)
		self.assertTrue(res["invitation_url"].startswith(frappe.utils.get_url()))
		self.assertIn("/opt-in?", res["invitation_url"])
		self.assertNotIn("facility-onboarding", res["invitation_url"])
		self.assertIn(self.test_network_slug, res["invitation_url"])

		# Verify email dispatch was attempted / recorded
		self.assertTrue(res["email_sent"])
		self.assertIsNotNone(res["membership"]["invite_email_queue"])

		# Verify database record
		fac = frappe.get_doc("CRM Pre-Qualified Facility", res["facility"]["name"])
		membership = next(m for m in fac.memberships if m.network == self.test_network_slug)
		self.assertEqual(membership.status, "Active")
		self.assertEqual(membership.contact_email, contact_email)
		self.assertEqual(membership.contact_name, contact_person)
		self.assertIsNotNone(membership.invite_sent_at)
		self.assertIsNotNone(membership.invite_email_queue)

	def test_deal_won_idempotency(self):
		key = f"deal-idem-{frappe.generate_hash(length=8)}"
		mfl = f"MFL-IDEM-DEAL-{frappe.generate_hash(length=4)}"
		payload = {
			"facility": {"mfl_code": mfl, "facility_name": f"Idempotent Deal Hospital {mfl}"},
			"partner_id": self.test_partner_id,
			"price_lists": {"1": "Negotiated Year 1", "2": "Negotiated Year 2"},
			"contact_email": "admin@idemhospital.com",
			"contact_person": "Jane Doe",
			"idempotency_key": key,
			"send_email": 0,
		}

		res1 = deal_won(**payload)
		self.assertTrue(res1["success"])
		self.assertNotIn("cached", res1)

		res2 = deal_won(**payload)
		self.assertTrue(res2["success"])
		self.assertTrue(res2.get("cached"))
		self.assertEqual(res1["facility"]["name"], res2["facility"]["name"])

	def test_crm_api_partner_portal_router_exports(self):
		from crm.api.partner_portal import (
			configure_facility_pricing as api_configure,
		)
		from crm.api.partner_portal import (
			deal_won as api_deal_won,
		)
		from crm.api.partner_portal import (
			get_facility_pricing as api_get_pricing,
		)

		self.assertEqual(api_configure, configure_facility_pricing)
		self.assertEqual(api_deal_won, deal_won)
		self.assertEqual(api_get_pricing, get_facility_pricing)

	def test_deal_won_validation_guards(self):
		mfl = "MFL-VAL-01"

		# Missing email
		with self.assertRaises(frappe.ValidationError):
			deal_won(
				facility=mfl,
				partner_id=self.test_partner_id,
				contact_person="Jane Doe",
				contact_email="",
			)

		# Invalid email format
		with self.assertRaises(frappe.ValidationError):
			deal_won(
				facility=mfl,
				partner_id=self.test_partner_id,
				contact_person="Jane Doe",
				contact_email="not-an-email",
			)

		# Missing contact person
		with self.assertRaises(frappe.ValidationError):
			deal_won(
				facility=mfl,
				partner_id=self.test_partner_id,
				contact_person="",
				contact_email="jane@example.com",
			)

		# Non-existent partner
		with self.assertRaises(frappe.DoesNotExistError):
			deal_won(
				facility=mfl,
				partner_id="000000",
				contact_person="Jane Doe",
				contact_email="jane@example.com",
			)
