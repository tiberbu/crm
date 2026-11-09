"""Integration tests for the portal commercial projection (S2 attribution, S3 guard, S4 plan).

These run against a real site via the standard ``frappe.tests`` harness. On the
reference bench the crm suite cannot bootstrap, so they are exercised in CI / an
approved site via ``scripts/run-crm-tests.sh``.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

OWNER = "cx-port-test-owner@example.test"
OTHER = "cx-port-test-other@example.test"


def _website_user(email):
	if frappe.db.exists("User", email):
		return frappe.get_doc("User", email)
	return frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Portal Test",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)


def _customer(name):
	if frappe.db.exists("Customer", name):
		return name
	frappe.get_doc({"doctype": "Customer", "customer_name": name}).insert(ignore_permissions=True)
	return name


def _sales_order(customer, header_mfl=None, item_mfls=None, docstatus=1, per_billed=0, **extra):
	doc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"transaction_date": frappe.utils.nowdate(),
			"delivery_date": frappe.utils.nowdate(),
			"currency": "KES",
			"items": [
				{"item_code": "Test Item", "qty": 1, "rate": 100}
				for _ in range(max(1, len(item_mfls or [])))
			],
			**extra,
		}
	)
	if header_mfl and frappe.db.has_column("Sales Order", "crm_token_facility_mfl"):
		doc.crm_token_facility_mfl = header_mfl
	for row, mfl in zip(doc.items or [], item_mfls or [], strict=False):
		if mfl and frappe.db.has_column("Sales Order Item", "crm_optin_facility_mfl_code"):
			row.crm_optin_facility_mfl_code = mfl
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	if docstatus == 1:
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate = True
		doc.submit()
	if per_billed and frappe.db.has_column("Sales Order", "per_billed"):
		frappe.db.set_value("Sales Order", doc.name, "per_billed", per_billed)
	return doc.name


def _submission(mfl, **extra):
	ois = frappe.get_doc(
		{
			"doctype": "CRM Opt-In Submission",
			"naming_series": "OIS-.YYYY.-",
			"status": "Processed",
			"network_slug": frappe.db.get_value("CRM Opt-In Network", {}, "name"),
			"submitter_email": OWNER,
			"facility_signatory_name": "Portal Test %s" % mfl,
			"facility_signatory_email": OWNER,
			"raw_json": json.dumps({"facilities": [{"mfl_code": mfl, "facility_name": "Portal Clinic %s" % mfl}]}),
			"submitted_at": frappe.utils.now_datetime(),
			**extra,
		}
	)
	ois.flags.skip_auto_processing = True
	ois.insert(ignore_permissions=True)
	return ois.name


class PortalCommercialBase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("portal_commercial_test")
		self.addCleanup(frappe.db.rollback, save_point="portal_commercial_test")
		self.addCleanup(frappe.set_user, "Administrator")
		self.customer = _customer("Portal Test Customer")
		self.other_customer = _customer("Portal Test Other Customer")
		_website_user(OWNER)
		_website_user(OTHER)


class TestOrderAttribution(PortalCommercialBase):
	def _billing(self, customer=None):
		from crm.api.portal_commercial import account_billing

		customer = customer or self.customer
		return account_billing(customer, [], {})

	def test_order_without_header_tag_is_attributed_to_item_mfl(self):
		order = _sales_order(self.customer, header_mfl=None, item_mfls=["MFL-A"])
		rows = self._billing()["orders"]
		row = next(r for r in rows if r["name"] == order)
		self.assertEqual(row["facility_mfls"], ["MFL-A"])
		self.assertEqual(row["display_status"], "Awaiting invoice")

	def test_header_tag_takes_precedence(self):
		order = _sales_order(self.customer, header_mfl="MFL-H", item_mfls=["MFL-I"])
		rows = self._billing()["orders"]
		row = next(r for r in rows if r["name"] == order)
		self.assertEqual(row["facility_mfls"], ["MFL-H"])

	def test_multi_facility_order_appears_for_each(self):
		from crm.api.portal_commercial import for_facility

		order = _sales_order(self.customer, item_mfls=["MFL-A", "MFL-B"])
		rows = self._billing()["orders"]
		row = next(r for r in rows if r["name"] == order)
		self.assertEqual(sorted(row["facility_mfls"]), ["MFL-A", "MFL-B"])
		self.assertTrue(for_facility(rows, "mfl-a"))
		self.assertTrue(for_facility(rows, "MFL-B"))

	def test_fully_billed_order_stays_in_history(self):
		order = _sales_order(self.customer, item_mfls=["MFL-A"], per_billed=100)
		rows = self._billing()["orders"]
		row = next(r for r in rows if r["name"] == order)
		self.assertEqual(row["display_status"], "Invoiced")


class TestInvoiceAttribution(PortalCommercialBase):
	def _billing(self):
		from crm.api.portal_commercial import account_billing

		return account_billing(self.customer, [], {})

	def test_draft_invoice_excluded(self):
		from crm.api.portal_commercial import enrich_invoices

		frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer,
				"posting_date": frappe.utils.nowdate(),
				"items": [{"item_code": "Test Item", "qty": 1, "rate": 100}],
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)
		raw = frappe.get_all("Sales Invoice", {"customer": self.customer, "docstatus": 0}, ["name"])
		self.assertTrue(raw)
		# enrich_invoices is fed only docstatus==1 rows by account_billing; verify the filter
		enriched = self._billing()["invoices"]
		for name in raw:
			self.assertFalse(any(r["name"] == name for r in enriched), "draft invoice must not appear")

	def test_has_outstanding_reflects_amount(self):
		from crm.api.portal_commercial import account_billing, for_facility

		# A submitted invoice with an outstanding amount, attributed via item MFL.
		inv = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer,
				"posting_date": frappe.utils.nowdate(),
				"items": [
					{
						"item_code": "Test Item",
						"qty": 1,
						"rate": 100,
					}
				],
			}
		)
		inv.items[0].crm_optin_facility_mfl_code = "MFL-A" if frappe.db.has_column(
			"Sales Invoice Item", "crm_optin_facility_mfl_code"
		) else None
		inv.insert(ignore_permissions=True, ignore_mandatory=True)
		inv.flags.ignore_permissions = True
		inv.flags.ignore_validate = True
		inv.submit()
		rows = for_facility(self._billing()["invoices"], "MFL-A")
		self.assertTrue(rows)
		self.assertTrue(any(r["amount"] > 0 for r in rows))


class TestScheduleGuard(PortalCommercialBase):
	def test_schedule_governed_order_refuses_manual_invoice(self):
		from crm.api import customer_experience as cx

		order = _sales_order(self.customer, item_mfls=["MFL-A"])
		if frappe.db.has_column("Sales Order", "crm_optin_year"):
			frappe.db.set_value("Sales Order", order, "crm_optin_year", 1)
		if frappe.db.has_column("Sales Order", "crm_optin_billing_key"):
			frappe.db.set_value("Sales Order", order, "crm_optin_billing_key", "KEY-1")
		# permission first for a different customer
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			cx.start_token_payment(order)
		# then the schedule guard for the owner (order is not linked to OWNER's grant, so we
		# assert the governed helper directly to isolate the I7 behaviour)
		frappe.set_user("Administrator")
		self.assertTrue(cx._order_is_schedule_governed(order))
		# a non-governed order is not governed
		plain = _sales_order(self.customer, item_mfls=["MFL-A"])
		self.assertFalse(cx._order_is_schedule_governed(plain))


class TestCommercialProjection(PortalCommercialBase):
	def _network_ois(self, mfl="MFL-N"):
		plans = [
			{
				"year_number": 1,
				"invoice_schedule_frequency": "Quarterly",
				"facilities": [{"mfl_code": mfl, "monthly_kes": 100.0, "annual_kes": 1200.0}],
			}
		]
		schedule = [
			{
				"year_number": 1,
				"quarter_number": 1,
				"period_label": "Year 1 · Quarter 1",
				"invoice_date": "2027-01-30",
				"invoice_due_date": "2027-03-01",
				"amount_incl_vat": 400.0,
				"status": "Pending",
				"preview": True,
			}
		]
		return _submission(
			mfl,
			pricing_plans_json=json.dumps(plans),
			billing_schedule_json=json.dumps(schedule),
			quote_names_json=json.dumps(["NO-QUOTE"]),
		)

	def test_network_plan_is_time_bound(self):
		from crm.api.portal_commercial import build_commercial, network_plans_by_mfl, facility_quotes

		ois = self._network_ois()
		nctx = network_plans_by_mfl([ois])
		ctx = nctx.get("mfl-n")
		self.assertIsNotNone(ctx)
		commercial = build_commercial("MFL-N", ctx, {}, [], [], facility_quotes("", "MFL-N", ctx, {}), False)
		self.assertEqual(commercial["plan_type"], "time_bound")
		self.assertEqual(commercial["journey"], "network_optin")
		self.assertEqual(commercial["plan"]["source"], "optin_contract")
		self.assertFalse(commercial["has_tokens"])

	def test_unknown_when_no_package_no_ois(self):
		from crm.api.portal_commercial import build_commercial

		commercial = build_commercial("MFL-X", None, {}, [], [], [], False)
		self.assertEqual(commercial["plan_type"], "unknown")
		self.assertEqual(commercial["plan"]["source"], "none")

	def test_malformed_json_yields_unavailable(self):
		from crm.api.portal_commercial import build_commercial

		# Force an exception inside the builder by giving a non-dict network ctx plan.
		class Boom:
			def get(self, *a, **k):
				raise RuntimeError("boom")

		commercial = build_commercial("MFL-N", Boom(), {}, [], [], [], False)
		self.assertTrue(commercial["unavailable"])


class TestFixedPlanAutoRepeat(PortalCommercialBase):
	"""Review must-fix 4: Fixed ``next_invoice`` reads Auto Repeat correctly."""

	def test_fixed_plan_reads_auto_repeat_next_date(self):
		from crm.api.portal_commercial import build_commercial

		order = _sales_order(self.customer, item_mfls=["MFL-F"])
		if not frappe.db.exists("DocType", "Auto Repeat"):
			self.skipTest("Auto Repeat doctype not installed")
		try:
			ar = frappe.get_doc(
				{
					"doctype": "Auto Repeat",
					"reference_doctype": "Sales Order",
					"reference_document": order,
					"frequency": "Monthly",
					"repeat_day": "1",
					"start_date": frappe.utils.add_days(frappe.utils.nowdate(), 30),
				}
			)
			ar.insert(ignore_permissions=True, ignore_mandatory=True)
		except Exception:
			self.skipTest("Auto Repeat could not be created in this environment")
		next_date = frappe.utils.add_days(frappe.utils.nowdate(), 30)
		frappe.db.set_value("Auto Repeat", ar.name, "next_schedule_date", next_date)

		pkg = {
			"plan": "Fixed",
			"billing_period": "Monthly",
			"display_name": "Fixed Plan",
			"item_code": "PKG-X",
			"token_quantity": 0,
		}
		commercial = build_commercial(
			"MFL-F",
			None,
			pkg,
			[{"name": order, "grand_total": 500, "crm_token_package_item": "PKG-X"}],
			[],
			[],
			False,
			facility_row={"package_currency": "KES", "package_gross_total": 500},
		)
		self.assertEqual(commercial["plan_type"], "time_bound")
		next_invoice = commercial["plan"]["next_invoice"]
		self.assertIsNotNone(next_invoice, "Auto Repeat next date must be projected")
		self.assertEqual(next_invoice["label"], "Next renewal")
		self.assertEqual(next_invoice["date"], str(next_date))


class TestPublicProjection(PortalCommercialBase):
	"""Review must-fix 8/9/10: allow-list payloads, OIS attribution, open invoice."""

	def test_order_payload_exposes_no_internal_fields(self):
		from crm.api.portal_commercial import account_billing

		_sales_order(self.customer, item_mfls=["MFL-A"], crm_token_package_item="PKG-A")
		rows = account_billing(self.customer, [], {})["orders"]
		self.assertTrue(rows)
		forbidden = {
			"docstatus",
			"per_billed",
			"delivery_date",
			"status",
			"crm_optin_year",
			"crm_optin_quarter",
			"crm_optin_billing_key",
			"crm_optin_quotation",
			"crm_optin_submission",
			"crm_order_frequency",
			"crm_recurrence_period",
		}
		for row in rows:
			leaked = forbidden & set(row)
			self.assertFalse(leaked, "internal order fields leaked: %s" % sorted(leaked))
			self.assertIn("name", row)
			self.assertIn("facility_mfls", row)

	def test_invoice_payload_exposes_no_internal_fields(self):
		from crm.api.portal_commercial import account_billing

		inv = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer,
				"posting_date": frappe.utils.nowdate(),
				"items": [{"item_code": "Test Item", "qty": 1, "rate": 100}],
			}
		)
		if frappe.db.has_column("Sales Invoice Item", "crm_optin_facility_mfl_code"):
			inv.items[0].crm_optin_facility_mfl_code = "MFL-A"
		inv.insert(ignore_permissions=True, ignore_mandatory=True)
		inv.flags.ignore_permissions = True
		inv.flags.ignore_validate = True
		inv.submit()
		rows = account_billing(self.customer, [], {})["invoices"]
		self.assertTrue(rows)
		forbidden = {
			"company",
			"crm_deal",
			"optin_network",
			"crm_checkout_reference",
			"crm_optin_submission",
			"crm_optin_year",
			"crm_optin_quarter",
			"crm_optin_billing_key",
			"outstanding_amount",
		}
		for row in rows:
			leaked = forbidden & set(row)
			self.assertFalse(leaked, "internal invoice fields leaked: %s" % sorted(leaked))
			self.assertIn("name", row)
			self.assertIn("amount", row)

	def test_ois_order_without_mfl_attributed_via_submission(self):
		from crm.api.customer_experience import _order_rows

		ois = self._network_ois("MFL-O")
		order = _sales_order(self.customer, header_mfl=None, item_mfls=None)
		if not frappe.db.has_column("Sales Order", "crm_optin_submission"):
			self.skipTest("Sales Order.crm_optin_submission not installed")
		frappe.db.set_value("Sales Order", order, "crm_optin_submission", ois)
		rows = _order_rows(frappe.get_doc("CRM Opt-In Submission", ois))
		row = next(r for r in rows if r["name"] == order)
		self.assertEqual(row["facility_mfls"], ["MFL-O"])

	def test_invoice_summary_prefers_open_invoice(self):
		from crm.api.website_redirect import _facility_invoice_summary

		summary = _facility_invoice_summary(
			[
				{"name": "INV-PAID", "amount": 0, "currency": "KES"},
				{"name": "INV-OPEN", "amount": 100, "currency": "KES"},
			]
		)
		self.assertEqual(summary["invoice_name"], "INV-OPEN")
		self.assertTrue(summary["has_outstanding"])
		self.assertEqual(summary["outstanding_amount"], 100)

	def test_invoice_summary_none_when_all_paid(self):
		from crm.api.website_redirect import _facility_invoice_summary

		summary = _facility_invoice_summary([{"name": "INV-PAID", "amount": 0, "currency": "KES"}])
		self.assertIsNone(summary["invoice_name"])
		self.assertFalse(summary["has_outstanding"])
