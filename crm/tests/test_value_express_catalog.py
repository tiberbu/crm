"""Value Express catalogue: Fixed by facility level, Custom amounts, bonus rules and enquiry emails."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import customer_experience as cx
from crm.api import facility_onboarding as fo
from crm.api.landing import submit_contact
from crm.tests.test_express_draft_order import _portal_customer, _receivable_account

FIXED_ITEM = "VE-TEST-FIXED-L2"
CUSTOM_ITEM = "VE-TEST-CUSTOM"
CUSTOMER = "Value Express Test Customer"


def _vat(net_total, *args, **kwargs):
	"""VAT templates are site configuration (covered elsewhere); a flat 16% keeps these tests site-independent."""
	vat = round(net_total * 0.16, 2)
	return frappe._dict(
		net_total=net_total, vat_amount=vat, grand_total=round(net_total + vat, 2), vat_rate=16.0, vat_label="VAT (16%)"
	)


def _item(code):
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": frappe.db.get_value("UOM", {"name": "Nos"}) or frappe.db.get_value("UOM", {}, "name"),
				"is_stock_item": 0,
				"is_sales_item": 1,
			}
		).insert(ignore_permissions=True)


class TestValueExpressCatalog(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("value_express_test")
		self.addCleanup(frappe.db.rollback, save_point="value_express_test")
		if "erpnext" not in frappe.get_installed_apps():
			self.skipTest("ERPNext is required for token packages")
		vat = patch("crm.utils.quotation_tax.calculate_vat_totals", side_effect=_vat)
		vat.start()
		self.addCleanup(vat.stop)
		self.flex = [p for p in fo._token_packages() if p["price"] > 0]
		if not self.flex:
			self.skipTest("No priced Flex token package on this site")
		settings = frappe.get_single("CRM Opt-In Settings")
		price_list = settings.token_price_list
		for code in (FIXED_ITEM, CUSTOM_ITEM):
			_item(code)
		frappe.get_doc(
			{"doctype": "Item Price", "item_code": FIXED_ITEM, "price_list": price_list, "price_list_rate": 15000, "selling": 1}
		).insert(ignore_permissions=True)
		# Only this test's Fixed and Custom rows count, whatever the site already has (rolled back).
		for row in settings.token_packages:
			if row.plan != "Flex":
				row.enabled = 0
		common = {"description": "Test", "coverage_summary": "Test", "billing_period": "Monthly", "enabled": 1}
		settings.append(
			"token_packages",
			{**common, "item_code": FIXED_ITEM, "display_name": "Fixed Level 2", "plan": "Fixed", "facility_levels": "Level 2", "token_quantity": 0},
		)
		settings.append(
			"token_packages",
			{**common, "item_code": CUSTOM_ITEM, "display_name": "Custom", "plan": "Custom", "token_quantity": 1},
		)
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
		for target in ("crm.utils.quotation_tax.apply_quotation_taxes", "crm.automation.optin_billing._apply_order_tax_template"):
			stub = patch(target)
			stub.start()
			self.addCleanup(stub.stop)

	def test_catalog_separates_flex_fixed_and_custom(self):
		data = fo.get_catalog()["data"]
		self.assertTrue(all(p["plan"] == "Flex" for p in data["packages"]))
		self.assertNotIn(FIXED_ITEM, [p["item_code"] for p in fo._token_packages()])
		fixed = next(p for p in data["fixed_packages"] if p["item_code"] == FIXED_ITEM)
		self.assertEqual((fixed["facility_levels"], fixed["price_ex_vat"]), (["Level 2"], 15000))
		offer = data["custom_offer"]
		self.assertEqual(offer["item_code"], CUSTOM_ITEM)
		self.assertEqual(offer["min_tokens"], 1000)
		self.assertEqual([t["from_amount"] for t in offer["tiers"]], sorted(t["from_amount"] for t in offer["tiers"]))

	def test_fixed_must_match_the_facility_level(self):
		facilities = [{"facility_id": "F1", "facility_level": "Level 2"}, {"facility_id": "F2", "facility_level": "Level 3B"}]
		resolved = fo._packages_for_facilities({"F1"}, {"F1": FIXED_ITEM}, None, facilities)
		self.assertEqual(resolved["F1"]["plan"], "Fixed")
		with self.assertRaises(frappe.ValidationError):
			fo._packages_for_facilities({"F2"}, {"F2": FIXED_ITEM}, None, facilities)

	def test_custom_amount_is_repriced_on_the_server(self):
		tiers = fo._custom_offer(fo._catalog_packages())["tiers"]
		amount = int(tiers[0]["from_amount"]) + 1000
		resolved = fo._packages_for_facilities({"F1"}, '{"F1": {"custom_amount": %d}}' % amount, None, [])["F1"]
		rate = tiers[0]["rate"]
		self.assertEqual(resolved["item_code"], CUSTOM_ITEM)
		self.assertEqual((resolved["qty"], resolved["rate"]), (int(amount // rate), rate))
		self.assertLessEqual(resolved["price"], amount)
		with self.assertRaises(frappe.ValidationError):
			fo._packages_for_facilities({"F1"}, {"F1": {"custom_amount": 10}}, None, [])

	def test_custom_draft_order_is_invoiced_per_token_without_bonus(self):
		package = fo._custom_package(fo._custom_offer(fo._catalog_packages())["min_amount"] + 500, fo._catalog_packages())
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		receivable = None
		if frappe.db.get_value("Company", company, "default_currency") != package["currency"]:
			receivable = {"company": company, "account": _receivable_account(company, package["currency"])}
			frappe.get_doc(
				{"doctype": "Currency Exchange", "date": "2000-01-01", "from_currency": package["currency"], "to_currency": frappe.db.get_value("Company", company, "default_currency"), "exchange_rate": 0.0077, "for_selling": 1}
			).insert(ignore_permissions=True)
		customer = _portal_customer("ve-custom-owner@example.test", CUSTOMER, receivable)
		name = cx.create_express_draft_order(customer, "90091", package)["data"]["sales_order"]
		order = frappe.get_doc("Sales Order", name)
		lines = [row for row in order.items if not row.get("crm_bonus_type")]
		self.assertEqual((lines[0].item_code, lines[0].qty, lines[0].rate), (CUSTOM_ITEM, package["qty"], package["rate"]))
		self.assertFalse([row for row in order.items if row.get("crm_bonus_type")])
		self.assertEqual(cx._order_tokens(order), package["qty"])
		self.assertEqual(order.net_total, package["price"])

	def test_enquiry_is_emailed_to_the_contact_email(self):
		frappe.db.set_single_value("CRM Opt-In Settings", "landing_contact_email", "team@example.test")
		with patch("frappe.sendmail") as sendmail:
			submit_contact(full_name="Ama Test", email="ama@example.test", message="Hello <b>team</b>", topic="Getting started")
		lead = frappe.db.get_value("CRM Lead", {"email": "ama@example.test"}, "name")
		kwargs = sendmail.call_args.kwargs
		self.assertEqual((kwargs["recipients"], kwargs["reply_to"], kwargs["reference_name"]), (["team@example.test"], "ama@example.test", lead))
		self.assertNotIn("<b>team</b>", kwargs["message"])

	def test_enquiry_survives_missing_mail_setup_and_needs_a_contact_email(self):
		frappe.db.set_single_value("CRM Opt-In Settings", "landing_contact_email", "team@example.test")
		with patch("frappe.sendmail", side_effect=frappe.OutgoingEmailError("no account")):
			self.assertEqual(submit_contact(full_name="Kofi Test", email="kofi@example.test", message="Hi"), {"ok": True})
		self.assertTrue(frappe.db.exists("CRM Lead", {"email": "kofi@example.test"}))
		frappe.db.set_single_value("CRM Opt-In Settings", "landing_contact_email", "")
		with patch("frappe.sendmail") as sendmail:
			submit_contact(full_name="Esi Test", email="esi@example.test", message="Hi")
		sendmail.assert_not_called()

	def test_landing_offer_lists_flex_cards_fixed_levels_and_custom(self):
		from crm.api.landing import get_value_express_offer

		offer = get_value_express_offer()
		self.assertEqual([c["price"] for c in offer["flex"]], sorted(c["price"] for c in offer["flex"]))
		self.assertEqual(offer["from_price"], offer["flex"][0]["price"])
		fixed = next(f for f in offer["fixed"] if f["item_code"] == FIXED_ITEM)
		self.assertEqual((fixed["label"], fixed["price"]), ("Level 2", 15000))
		self.assertEqual(offer["calculator"]["fixed"]["Level 2"], 15000)
		self.assertEqual(offer["custom"]["item_code"], CUSTOM_ITEM)
		# Value Express is outpatient: inpatient-only service points are not priced.
		self.assertTrue(all("opd" in (p.get("applies_to") or ["opd"]) for p in offer["calculator"]["service_points"]))
