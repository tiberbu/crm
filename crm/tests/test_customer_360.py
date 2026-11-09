from typing import ClassVar
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.api.customer_360 import (
	_build_summary,
	_resolve_payments,
	_scope_rows,
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
			return (
				fieldname
				in (
					"optin_network",
					"crm_optin_submission",
					"crm_token_package_item",
					"crm_optin_quotation",
					"crm_quotation",
					"cx_customer",
				)
				or (doctype, fieldname) in self.values
			)

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
			with patch("crm.api.customer_360.frappe.get_list", side_effect=capturing_get_list):
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
				"CRM Organization": [{"name": "Acme Corp", "organization_name": "Acme Corporation"}],
				"CRM Deal": [
					{"name": "CS-00001", "organization": "Acme Corp", "status": "Won", "deal_value": 1000},
					{
						"name": "CS-00002",
						"organization": "Acme Corp",
						"status": "Qualification",
						"deal_value": 2000,
					},
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
				"CRM Organization": [{"name": "acme-doc", "organization_name": "Acme Corporation"}],
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


class _FacilityScopeContext:
	"""A two-facility owner with records attributed to each facility and one account-level invoice.

	F1 (MFL 11111, FID-01-TEST): invoice SI-1 (header), order SO-1 (item line), payment PE-1.
	F2 (MFL 22222): invoice SI-2 (header), quote Q-1 (header), payment PE-2.
	SI-3 carries no facility at all (account-level).
	"""

	FACILITIES: ClassVar[dict] = {
		"F1": {
			"name": "F1",
			"facility_name": "West Clinic",
			"mfl_code": "11111",
			"hfr_facility_id": "FID-01-TEST",
			"organization": "Acme Corporation",
			"keph_level": "Level 2",
			"is_self_onboarded": 0,
		},
		"F2": {
			"name": "F2",
			"facility_name": "East Clinic",
			"mfl_code": "22222",
			"hfr_facility_id": "",
			"organization": "Acme Corporation",
			"keph_level": "Level 3",
			"is_self_onboarded": 0,
		},
		"F9": {
			"name": "F9",
			"facility_name": "Orphan Clinic",
			"mfl_code": "99999",
			"hfr_facility_id": "",
			"organization": "",
			"keph_level": "",
			"is_self_onboarded": 0,
		},
	}

	def __init__(self, roles=("System Manager",)):
		self.roles = roles
		self.calls = []

	def _get_list(self, doctype, filters=None, fields=None, **kwargs):
		d = frappe._dict
		fields = fields or []
		joined = " ".join(fields)
		self.calls.append((doctype, filters, fields, kwargs))
		if doctype == "CRM Pre-Qualified Facility":
			if isinstance(filters, dict) and isinstance(filters.get("name"), str):
				row = self.FACILITIES.get(filters["name"])
				return [d(row)] if row else []
			if isinstance(filters, dict) and "organization" in filters:
				return [d(self.FACILITIES["F1"]), d(self.FACILITIES["F2"])]
			if isinstance(filters, dict) and "name" in filters:
				return [d(self.FACILITIES[n]) for n in filters["name"][1] if n in self.FACILITIES]
			return [d(row) for row in self.FACILITIES.values()]
		if doctype == "CRM Organization":
			return [d({"name": "acme-doc", "organization_name": "Acme Corporation"})]
		if doctype == "CRM Deal":
			if isinstance(filters, list):  # CRM Deal Facility child filter
				child = filters[0]
				if child[1] == "mfl_code" and "11111" in child[3]:
					return [d({"name": "D1"})]
				if child[1] == "mfl_code" and "22222" in child[3]:
					return [d({"name": "D2"})]
				return []
			if fields == ["cx_customer"]:
				return [d({"cx_customer": "CUST-1"})]
			if fields == ["name"]:
				return [d({"name": "D1"}), d({"name": "D2"})]
			names = (filters or {}).get("name")
			rows = [
				d({"name": "D1", "status": "Won", "deal_value": 100, "currency": "KES"}),
				d({"name": "D2", "status": "Qualification", "deal_value": 200, "currency": "KES"}),
			]
			if names:
				rows = [row for row in rows if row.name in names[1]]
			return rows
		if doctype == "Quotation":
			if "item_mfl" in joined:
				return []
			return [
				d(
					{
						"name": "Q-1",
						"transaction_date": "2026-11-01",
						"grand_total": 500,
						"currency": "KES",
						"status": "Open",
						"docstatus": 1,
						"crm_token_facility_mfl": "22222",
					}
				)
			]
		if doctype == "Sales Order":
			if "item_mfl" in joined:
				return [d({"name": "SO-1", "item_mfl": "11111"})]
			return [
				d(
					{
						"name": "SO-1",
						"transaction_date": "2026-11-01",
						"grand_total": 1000,
						"currency": "KES",
						"status": "To Bill",
						"per_billed": 0,
					}
				)
			]
		if doctype == "Sales Invoice":
			if "item_mfl" in joined:
				return []

			def inv(name, mfl, outstanding):
				return d(
					{
						"name": name,
						"creation": "2026-11-01",
						"grand_total": 1000,
						"currency": "KES",
						"outstanding_amount": outstanding,
						"due_date": None,
						"docstatus": 1,
						"status": "Paid" if not outstanding else "Unpaid",
						"crm_token_facility_mfl": mfl,
					}
				)

			return [inv("SI-1", "11111", 0), inv("SI-2", "22222", 400), inv("SI-3", "", 250)]
		if doctype == "Payment Entry":
			if "reference_name" in joined:
				return [
					d({"name": "PE-1", "reference_name": "SI-1"}),
					d({"name": "PE-2", "reference_name": "SI-2"}),
				]
			return [
				d(
					{
						"name": "PE-1",
						"posting_date": "2026-11-02",
						"paid_amount": 1000,
						"payment_type": "Receive",
						"party": "CUST-1",
					}
				),
				d(
					{
						"name": "PE-2",
						"posting_date": "2026-11-03",
						"paid_amount": 600,
						"payment_type": "Receive",
						"party": "CUST-1",
					}
				),
			]
		return []

	def install(self):
		d = frappe._dict

		def get_doc(doctype, name=None):
			if doctype == "CRM Pre-Qualified Facility":
				return d({"name": name, "memberships": []})
			if doctype == "CRM Organization":
				return d({"name": name, "organization_name": "Acme Corporation"})
			raise frappe.DoesNotExistError

		patches = [
			patch("crm.api.customer_360.frappe.get_roles", return_value=list(self.roles)),
			patch("crm.api.customer_360.frappe.has_permission", return_value=True),
			patch("crm.api.customer_360.frappe.get_doc", side_effect=get_doc),
			patch("crm.api.customer_360.frappe.get_list", side_effect=self._get_list),
			patch("crm.api.customer_360.frappe.db.get_value", return_value=None),
			patch(
				"crm.api.customer_360.frappe.db.exists",
				side_effect=lambda doctype, name=None: doctype == "CRM Organization" and name == "acme-doc",
			),
			patch("crm.api.customer_360.frappe.db.has_column", return_value=True),
			patch("crm.api.customer_360.facility_mfls_for_fid", return_value=["11111", "11111-OLD"]),
		]
		for p in patches:
			p.start()
		self._patches = patches
		return self

	def uninstall(self):
		for p in self._patches:
			p.stop()


class TestScopeRows(UnitTestCase):
	def test_keeps_matching_rows_case_insensitively_and_counts_unattributed(self):
		rows = [
			{"name": "A", "facility_mfls": ["abc"]},
			{"name": "B", "facility_mfls": ["XYZ"]},
			{"name": "C", "facility_mfls": []},
		]
		kept, unattributed = _scope_rows(rows, {"abc"})
		self.assertEqual([row["name"] for row in kept], ["A"])
		self.assertEqual(unattributed, 1)

	def test_summary_counts_quotes(self):
		self.assertEqual(_build_summary([], [], [], [{"name": "Q"}])["quotes"], 1)
		self.assertEqual(_build_summary([], [], [])["quotes"], 0)


class TestGetCustomer360FacilityScope(UnitTestCase):
	def _run(self, **kwargs):
		ctx = _FacilityScopeContext().install()
		try:
			return get_customer_360(**kwargs)
		finally:
			ctx.uninstall()

	def test_facility_defaults_to_facility_scope_with_only_its_records(self):
		result = self._run(facility="F1")
		scope = result["scope"]
		self.assertEqual(scope["mode"], "facility")
		self.assertEqual(scope["facility"]["hfr_facility_id"], "FID-01-TEST")
		self.assertEqual(scope["facility"]["organization"], "acme-doc")
		self.assertTrue(scope["can_widen"])
		self.assertEqual([row["name"] for row in result["invoices"]], ["SI-1"])
		self.assertEqual([row["name"] for row in result["orders"]], ["SO-1"])
		self.assertEqual(result["quotes"], [])
		self.assertEqual([row["name"] for row in result["payments"]], ["PE-1"])
		self.assertEqual([row["name"] for row in result["facilities"]], ["F1"])
		self.assertEqual([row["name"] for row in result["deals"]], ["D1"])
		self.assertEqual(scope["unattributed"], {"orders": 0, "quotes": 0, "invoices": 1})
		# Summary is computed on the scoped rows only.
		self.assertEqual(result["summary"]["invoices"], 1)
		self.assertEqual(result["summary"]["outstanding"], 0)
		self.assertEqual(result["organization"]["name"], "acme-doc")

	def test_other_facility_sees_its_own_quote_and_invoice(self):
		result = self._run(facility="F2")
		self.assertEqual([row["name"] for row in result["invoices"]], ["SI-2"])
		self.assertEqual([row["name"] for row in result["quotes"]], ["Q-1"])
		self.assertEqual([row["name"] for row in result["payments"]], ["PE-2"])
		self.assertEqual(result["summary"]["outstanding"], 400)

	def test_organization_scope_widens_to_every_record_with_attribution(self):
		result = self._run(facility="F1", scope="organization")
		self.assertEqual(result["scope"]["mode"], "organization")
		self.assertEqual(result["scope"]["facility"]["name"], "F1")
		self.assertEqual({row["name"] for row in result["invoices"]}, {"SI-1", "SI-2", "SI-3"})
		by_name = {row["name"]: row["facility_mfls"] for row in result["invoices"]}
		self.assertEqual(by_name, {"SI-1": ["11111"], "SI-2": ["22222"], "SI-3": []})
		self.assertEqual({row["name"] for row in result["facilities"]}, {"F1", "F2"})
		self.assertEqual(len(result["payments"]), 2)
		self.assertEqual(result["scope"]["unattributed"], {"orders": 0, "quotes": 0, "invoices": 0})

	def test_organization_entry_is_unchanged_and_carries_facility_mfls(self):
		result = self._run(organization="acme-doc")
		self.assertEqual(result["scope"]["mode"], "organization")
		self.assertIsNone(result["scope"]["facility"])
		self.assertFalse(result["scope"]["can_widen"])
		self.assertEqual(len(result["invoices"]), 3)
		self.assertEqual(result["orders"][0]["facility_mfls"], ["11111"])
		self.assertEqual(result["quotes"][0]["facility_mfls"], ["22222"])

	def test_facility_without_owner_stays_in_facility_scope(self):
		result = self._run(facility="F9", scope="organization")
		self.assertEqual(result["scope"]["mode"], "facility")
		self.assertFalse(result["scope"]["can_widen"])
		self.assertIsNone(result["organization"])
		self.assertEqual([row["name"] for row in result["facilities"]], ["F9"])

	def test_unknown_facility_is_rejected(self):
		with self.assertRaises(frappe.DoesNotExistError):
			self._run(facility="NOPE")

	def test_facility_entry_requires_manager_role(self):
		ctx = _FacilityScopeContext(roles=("Sales User",)).install()
		try:
			with self.assertRaises(frappe.PermissionError):
				get_customer_360(facility="F1")
		finally:
			ctx.uninstall()

	def test_search_matches_facility_id_and_returns_it(self):
		ctx = _FacilityScopeContext().install()
		try:
			result = search_customer_360("FID-01")
		finally:
			ctx.uninstall()
		facility_calls = [c for c in ctx.calls if c[0] == "CRM Pre-Qualified Facility"]
		self.assertIn("hfr_facility_id", facility_calls[0][3]["or_filters"])
		row = next(r for r in result["facilities"] if r["name"] == "F1")
		self.assertEqual(row["hfr_facility_id"], "FID-01-TEST")
		self.assertEqual(row["organization"], "acme-doc")

	def test_facility_deal_lookup_qualifies_its_sort_column(self):
		"""Regression: the CRM Deal Facility join makes a bare `creation` ambiguous (MySQL 1052)."""
		ctx = _FacilityScopeContext().install()
		try:
			get_customer_360(facility="F1")
		finally:
			ctx.uninstall()
		joined = [c for c in ctx.calls if c[0] == "CRM Deal" and isinstance(c[1], list)]
		self.assertTrue(joined)
		for call in joined:
			self.assertIn("`tabCRM Deal`.", call[3].get("order_by", ""))
