import frappe
from frappe.tests import IntegrationTestCase

from crm.setup import onboarding_catalogue as catalogue

SETTINGS = catalogue.SETTINGS


class TestDefaultOnboardingCatalogue(IntegrationTestCase):
	def setUp(self):
		if "erpnext" not in frappe.get_installed_apps():
			self.skipTest("ERPNext is required for the token catalogue")
		catalogue.after_install()  # make sure the Opt-In Settings fields exist
		frappe.db.sql("delete from `tabCRM Token Package` where parent=%s", SETTINGS)
		frappe.db.sql(
			"delete from `tabSingles` where doctype=%s and field in %s",
			(SETTINGS, (*catalogue.DEFAULTS, "token_price_list")),
		)
		frappe.clear_document_cache(SETTINGS, SETTINGS)

	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_document_cache(SETTINGS, SETTINGS)

	def test_seeds_missing_packages_extra_tokens_and_contacts(self):
		catalogue.ensure_default_catalogue()

		settings = frappe.get_single(SETTINGS)
		self.assertEqual(
			[row.item_code for row in settings.token_packages],
			[package["item_code"] for package in catalogue.PACKAGES],
		)
		self.assertTrue(all(row.status == "Active" and row.enabled for row in settings.token_packages))
		for fieldname, value in catalogue.DEFAULTS.items():
			self.assertEqual(settings.get(fieldname), value, fieldname)
		for package in catalogue.PACKAGES:
			rate = frappe.db.get_value(
				"Item Price",
				{"item_code": package["item_code"], "price_list": settings.token_price_list},
				"price_list_rate",
			)
			self.assertEqual(rate, package["rate"], package["item_code"])

	def test_keeps_values_an_admin_already_set_and_fills_zero_tokens(self):
		settings = frappe.get_single(SETTINGS)
		settings.landing_contact_email = "help@example.test"
		settings.partner_coupon_tokens = 75
		settings.append(
			"token_packages",
			{"item_code": catalogue.PACKAGES[0]["item_code"], "display_name": "Only one", "enabled": 1},
		)
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)

		catalogue.ensure_default_catalogue()
		catalogue.ensure_default_catalogue()

		settings = frappe.get_single(SETTINGS)
		self.assertEqual(settings.landing_contact_email, "help@example.test")
		self.assertEqual(settings.partner_coupon_tokens, 75)
		self.assertEqual([row.display_name for row in settings.token_packages], ["Only one"])
		self.assertEqual(settings.welcome_bonus_tokens, catalogue.DEFAULTS["welcome_bonus_tokens"])
