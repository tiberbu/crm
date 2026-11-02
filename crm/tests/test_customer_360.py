from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.customer_360 import (
	_resolve_payments,
	_build_summary,
	get_customer_360,
	search_customer_360,
)


class TestBuildSummary(UnitTestCase):
	"""Pure summary math — no mocks."""

	def test_empty_inputs_yield_zero_summary(self):
		summary = _build_summary([], [], [])
		self.assertFalse(summary["package_paid"])
		self.assertEqual(summary["paid_amount"], 0)
		self.assertEqual(summary["open_orders"], 0)
		self.assertEqual(summary["sites_total"], 0)
		self.assertEqual(summary["sites_live"], 0)
		self.assertEqual(summary["outstanding"], 0)
		self.assertEqual(summary["invoices"], 0)

	def test_fully_paid_invoice_marks_package_paid(self):
		invoices = [
			{
				"name": "SINV-1",
				"docstatus": 1,
				"grand_total": 10000,
				"outstanding": 0,
			}
		]
		summary = _build_summary([], invoices, [])
		self.assertTrue(summary["package_paid"])
		self.assertEqual(summary["paid_amount"], 10000)
		self.assertEqual(summary["outstanding"], 0)
		self.assertEqual(summary["invoices"], 1)

	def test_partially_paid_invoice_is_not_paid(self):
		invoices = [
			{
				"name": "SINV-2",
				"docstatus": 1,
				"grand_total": 12000,
				"outstanding": 4000,
			}
		]
		summary = _build_summary([], invoices, [])
		self.assertFalse(summary["package_paid"])
		self.assertEqual(summary["paid_amount"], 8000)
		self.assertEqual(summary["outstanding"], 4000)

	def test_open_orders_count_and_amount(self):
		orders = [
			{"name": "SO-1", "grand_total": 5000, "per_billed": 20},
			{"name": "SO-2", "grand_total": 3000, "per_billed": 100},
		]
		# _resolve_orders marks rows "open"; the summary consumes that flag.
		orders[0]["open"] = True
		orders[1]["open"] = False
		summary = _build_summary(orders, [], [])
		self.assertEqual(summary["open_orders"], 1)
		self.assertEqual(summary["open_amount"], 5000)

	def test_sites_live_counts_opted_in_and_go_live_only(self):
		facilities = [
			{
				"name": "F1",
				"memberships": [
					{"status": "Opted In", "go_live": True, "opted_in": True},
					{"status": "Active", "go_live": False, "opted_in": False},
					{"status": "Declined", "go_live": True, "opted_in": False},
				],
			}
		]
		summary = _build_summary([], [], facilities)
		self.assertEqual(summary["sites_total"], 2)
		self.assertEqual(summary["sites_live"], 1)


class _Fake360Context:
	"""Patches the frappe layer that customer_360 reads."""

	def __init__(
		self,
		deal_rows=None,
		org_rows=None,
		list_by_doctype=None,
		values=None,
		deal_org="Acme Corp",
		roles=("System Manager",),
		deal_readable=True,
	):
		self.deal_rows = deal_rows or {}
		self.org_rows = org_rows or {}
		self.list_by_doctype = list_by_doctype or {}
		self.values = values or {}
		self.deal_org = deal_org
		self.roles = roles
		self.deal_readable = deal_readable

	def install(self):
		frappe_dict = frappe._dict

		def fake_get_roles(*args, **kwargs):
			return list(self.roles)

		def fake_has_permission(doctype, ptype=None, pdoc=None, *args, **kwargs):
			if doctype == "CRM Deal" and ptype == "read" and pdoc:
				return self.deal_readable
			return True

		def fake_get_doc(doctype, name=None):
			if doctype == "CRM Deal":
				return frappe_dict(
					{
						"name": name,
						"organization": self.deal_org,
						"status": "Qualification",
						"deal_value": 25000,
						"currency": "USD",
						"deal_owner": "crm.admin@example.com",
						"email": "billing@acme.test",
						"phone": "+254700000001",
						"mobile_no": "",
						"creation": "2026-01-01 00:00:00",
					}
				)
			if doctype == "CRM Organization":
				return frappe_dict(
					{
						"name": name,
						"organization_name": self.deal_org,
						"industry": "Healthcare",
						"territory": "Nairobi",
						"website": "https://acme.test",
						"no_of_employees": "11-50",
						"annual_revenue": 1000000,
						"currency": "USD",
					}
				)
			raise frappe.DoesNotExistError

		def fake_get_list(doctype, filters=None, fields=None, **kwargs):
			rows = self.list_by_doctype.get(doctype, [])
			return [frappe_dict(row) for row in rows]

		def fake_db_get_value(doctype, name, fieldnames=None, as_dict=False, **kwargs):
			value = self.values.get((doctype, name))
			if value is None:
				return None
			if as_dict:
				return frappe_dict(value)
			return value

		def fake_db_exists(doctype, name):
			return (doctype, name) in self.values or doctype in self.list_by_doctype

		def fake_has_column(doctype, fieldname):
			return fieldname in (
				"optin_network",
				"crm_optin_submission",
				"crm_token_package_item",
				"crm_optin_quotation",
				"crm_quotation",
				"cx_customer",
			) or (doctype, fieldname) in self.values

		patches = [
			patch("crm.api.customer_360.frappe.get_roles", side_effect=fake_get_roles),
			patch(
				"crm.api.customer_360.frappe.has_permission",
				side_effect=fake_has_permission,
			),
			patch("crm.api.customer_360.frappe.get_doc", side_effect=fake_get_doc),
			patch("crm.api.customer_360.frappe.get_list", side_effect=fake_get_list),
			patch("crm.api.customer_360.frappe.db.get_value", side_effect=fake_db_get_value),
			patch("crm.api.customer_360.frappe.db.exists", side_effect=fake_db_exists),
			patch("crm.api.customer_360.frappe.db.has_column", side_effect=fake_has_column),
		]
		for p in patches:
			p.start()
		self._patches = patches

	def uninstall(self):
		for p in getattr(self, "_patches", []):
			p.stop()


class TestResolvePayments(UnitTestCase):
	"""Regression: Payment Entry has no `customer` column — the billing party is
	the dynamic `party`/`party_type` pair. A `customer` filter is a hard 500."""

	def test_queries_by_party_not_customer(self):
		ctx = _Fake360Context(
			list_by_doctype={
				"Payment Entry": [
					{
						"name": "PE-1",
						"posting_date": "2026-10-01",
						"paid_amount": 6960.0,
						"payment_type": "Receive",
						"party": "Acme Customer",
					}
				]
			}
		)
		calls = []
		frappe_dict = frappe._dict

		def capturing_get_list(doctype, filters=None, fields=None, **kwargs):
			calls.append((doctype, filters))
			return [frappe_dict(row) for row in ctx.list_by_doctype.get(doctype, [])]

		ctx.install()
		try:
			with patch(
				"crm.api.customer_360.frappe.get_list", side_effect=capturing_get_list
			):
				result = _resolve_payments(["Acme Customer"])
		finally:
			ctx.uninstall()

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["party"], "Acme Customer")
		self.assertEqual(result[0]["paid_amount"], 6960.0)
		pe_calls = [call for call in calls if call[0] == "Payment Entry"]
		self.assertEqual(len(pe_calls), 1)
		filters = pe_calls[0][1]
		self.assertNotIn("customer", filters)
		self.assertEqual(filters.get("party_type"), "Customer")
		self.assertEqual(filters.get("party"), ["in", ["Acme Customer"]])

	def test_empty_customer_list_skips_query(self):
		ctx = _Fake360Context()
		calls = []

		ctx.install()
		try:
			with patch(
				"crm.api.customer_360.frappe.get_list",
				side_effect=lambda *a, **k: calls.append(a) or [],
			):
				result = _resolve_payments([])
		finally:
			ctx.uninstall()
		self.assertEqual(result, [])
		self.assertEqual(calls, [])


class TestGetCustomer360Gating(UnitTestCase):
	def test_requires_an_organization_or_deal(self):
		with self.assertRaises(frappe.ValidationError):
			get_customer_360(organization=None, deal=None)

	def test_unreadable_deal_is_rejected(self):
		ctx = _Fake360Context(deal_readable=False)
		ctx.install()
		try:
			with self.assertRaises(frappe.PermissionError):
				get_customer_360(deal="CS-00001")
		finally:
			ctx.uninstall()

	def test_org_only_requires_manager_role(self):
		ctx = _Fake360Context(roles=("Sales User",))
		ctx.install()
		try:
			with self.assertRaises(frappe.PermissionError):
				get_customer_360(organization="Acme Corp")
		finally:
			ctx.uninstall()


class TestGetCustomer360DealScoped(UnitTestCase):
	def test_returns_full_shape_with_empty_relations(self):
		ctx = _Fake360Context(deal_org="Acme Corp")
		ctx.install()
		try:
			result = get_customer_360(deal="CS-00001")
		finally:
			ctx.uninstall()

		for key in (
			"organization",
			"deal",
			"partners",
			"summary",
			"orders",
			"invoices",
			"payments",
			"facilities",
			"onboarding",
			"deals",
		):
			self.assertIn(key, result)
		self.assertEqual(result["deal"]["name"], "CS-00001")
		self.assertEqual(result["organization"]["organization_name"], "Acme Corp")
		self.assertEqual(result["summary"]["package_paid"], False)
		self.assertEqual(result["partners"], [])

	def test_deal_with_optin_network_reports_network_partner(self):
		ctx = _Fake360Context(
			values={
				("CRM Deal", "CS-00001"): {
					"organization": "Acme Corp",
					"lead": None,
					"optin_network": "network-one",
				},
				("CRM Opt-In Network", "network-one"): {
					"name": "network-one",
					"display_name": "Value Express Network",
					"partner_id": "123456",
					"contact_email": "partners@network.test",
					"logo_url": "",
				},
			}
		)
		ctx.install()
		try:
			result = get_customer_360(deal="CS-00001")
		finally:
			ctx.uninstall()

		self.assertEqual(len(result["partners"]), 1)
		partner = result["partners"][0]
		self.assertEqual(partner["kind"], "network")
		self.assertEqual(partner["partner_id"], "123456")
		self.assertEqual(partner["name"], "Value Express Network")


class TestSearchCustomer360(UnitTestCase):
	def test_short_query_returns_empty_groups(self):
		ctx = _Fake360Context()
		ctx.install()
		try:
			result = search_customer_360("ac")
		finally:
			ctx.uninstall()
		self.assertEqual(result, {"organizations": [], "deals": [], "facilities": []})

	def test_non_manager_is_rejected(self):
		ctx = _Fake360Context(roles=("Sales User",))
		ctx.install()
		try:
			with self.assertRaises(frappe.PermissionError):
				search_customer_360("Acme")
		finally:
			ctx.uninstall()

	def test_returns_matching_organizations_and_deals(self):
		ctx = _Fake360Context(
			list_by_doctype={
				"CRM Organization": [
					{"name": "Acme Corp", "organization_name": "Acme Corporation"}
				],
				"CRM Deal": [
					{"name": "CS-00001", "organization": "Acme Corp", "status": "Won", "deal_value": 1000},
					{"name": "CS-00002", "organization": "Acme Corp", "status": "Qualification", "deal_value": 2000},
				],
			}
		)
		ctx.install()
		try:
			result = search_customer_360("Acme", limit=10)
		finally:
			ctx.uninstall()
		self.assertEqual(len(result["organizations"]), 1)
		self.assertEqual(result["organizations"][0]["label"], "Acme Corporation")
		self.assertGreaterEqual(len(result["deals"]), 1)

	def test_facility_results_carry_parent_org_doc_name(self):
		ctx = _Fake360Context(
			list_by_doctype={
				"CRM Pre-Qualified Facility": [
					{
						"name": "F1",
						"facility_name": "West Clinic",
						"mfl_code": "12345",
						"organization": "Acme Corporation",
					}
				],
				"CRM Organization": [
					{"name": "acme-doc", "organization_name": "Acme Corporation"}
				],
			}
		)
		ctx.install()
		try:
			result = search_customer_360("West")
		finally:
			ctx.uninstall()
		self.assertEqual(len(result["facilities"]), 1)
		facility = result["facilities"][0]
		self.assertEqual(facility["label"], "West Clinic")
		self.assertEqual(facility["organization"], "acme-doc")
