# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import landing


class TestLandingContact(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _leads(self, email):
		return frappe.get_all("CRM Lead", filters={"email": email}, pluck="name")

	def test_enquiry_creates_lead_with_escaped_note(self):
		frappe.set_user("Guest")
		result = landing.submit_contact(
			full_name="Amina Wanjiru Otieno",
			email="amina@example.test",
			phone="+254 700 000 000",
			organization="Example Clinic",
			message="Hello <b>team</b>\nplease call me.",
		)
		frappe.set_user("Administrator")

		self.assertEqual(result, {"ok": True})
		leads = self._leads("amina@example.test")
		self.assertEqual(len(leads), 1)
		lead = frappe.get_doc("CRM Lead", leads[0])
		self.assertEqual((lead.first_name, lead.last_name), ("Amina", "Wanjiru Otieno"))
		self.assertEqual(lead.organization, "Example Clinic")
		note = frappe.get_all(
			"FCRM Note", filters={"reference_docname": lead.name}, fields=["title", "content"]
		)[0]
		self.assertEqual(note.title, landing.NOTE_TITLE)
		self.assertNotIn("<b>", note.content)
		self.assertIn("&lt;b&gt;team&lt;/b&gt;<br>please call me.", note.content)

	def test_honeypot_is_accepted_but_creates_nothing(self):
		result = landing.submit_contact(
			full_name="Bot", email="bot@example.test", message="spam", website="https://spam.example.test"
		)
		self.assertEqual(result, {"ok": True})
		self.assertEqual(self._leads("bot@example.test"), [])

	def test_rejects_missing_or_invalid_fields(self):
		cases = [
			{"full_name": "", "email": "a@example.test", "message": "hi"},
			{"full_name": "A", "email": "not-an-email", "message": "hi"},
			{"full_name": "A", "email": "a@example.test", "message": "  "},
			{"full_name": "A", "email": "a@example.test", "message": "x" * (landing.MAX_MESSAGE + 1)},
		]
		for kwargs in cases:
			with self.subTest(kwargs=kwargs["full_name"] + kwargs["email"]):
				self.assertRaises(frappe.ValidationError, landing.submit_contact, **kwargs)


class TestLandingContent(IntegrationTestCase):
	def test_settings_split_phone_lines_into_tel_links(self):
		settings = frappe._dict(
			landing_contact_phones="+254 700 000 000\n\n  +254 711 111 111 ",
			landing_certificate_valid_until="2028-09-23",
		)
		with patch.object(frappe, "get_single", return_value=settings):
			result = landing.get_landing_settings()
		self.assertEqual(
			result["phones"],
			[
				{"label": "+254 700 000 000", "tel": "+254700000000"},
				{"label": "+254 711 111 111", "tel": "+254711111111"},
			],
		)
		self.assertEqual(result["certificate_valid_until"], "September 2028")
		self.assertEqual(result["certificate_url"], "")

	def test_pricing_preview_reads_catalog_metrics(self):
		catalog = [
			{
				"item_code": "PKG-A",
				"display_name": "Growth",
				"description": "For growing clinics",
				"coverage_metrics": '{"badge": "Popular", "audience": "Clinics", "features": ["a", "b"]}',
				"price_ex_vat": 15000.0,
				"currency": "KES",
				"vat_label": "VAT (16%)",
				"billing_period": "Monthly",
			},
			{
				"item_code": "PKG-FREE",
				"display_name": "Free Trial",
				"coverage_metrics": "not json",
				"price_ex_vat": 0,
			},
		]
		with patch("crm.api.facility_onboarding._catalog_packages", return_value=catalog):
			plans = landing.get_pricing_preview()
		self.assertEqual(plans[0]["price"], "15,000")
		self.assertEqual(plans[0]["period"], "month")
		self.assertEqual((plans[0]["badge"], plans[0]["features"]), ("Popular", ["a", "b"]))
		self.assertEqual(plans[1]["price"], "")
		self.assertEqual(plans[1]["features"], [])
