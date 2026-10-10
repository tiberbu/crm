import json
import os

import frappe


def before_tests():
	load_crm_user_test_records()
	patch_test_record_dependency_resolution()


def patch_test_record_dependency_resolution():
	"""Avoid loading ERPNext's global fixtures on the populated CRM site.

	CRM provisions the users it needs in ``before_tests``. Frappe's recursive
	test-record resolver would otherwise follow CRM dependencies into ERPNext's
	global bootstrap, which assumes a clean test database.
"""
	from frappe.tests.utils import generators

	if getattr(generators, "_crm_site_fixture_dependency_patch", False):
		return

	original = generators.get_missing_records_doctypes
	site_fixtures = {"User", "Price List", "Item", "Tax Category", "Company", "Quotation"}

	def get_missing_records_without_site_fixtures(doctype, visited=None):
		if visited is None:
			visited = set()
		if doctype in site_fixtures:
			return []
		visited.update(site_fixtures)
		return original(doctype, visited)

	generators.get_missing_records_doctypes = get_missing_records_without_site_fixtures
	generators._crm_site_fixture_dependency_patch = True


def load_crm_user_test_records():
	"""Load CRM user test records from crm/tests/test_records.json"""
	test_records_path = os.path.join(os.path.dirname(__file__), "test_records.json")

	if os.path.exists(test_records_path):
		with open(test_records_path) as f:
			test_records = json.load(f)

		for record in test_records:
			if not frappe.db.exists("User", record.get("email")):
				doc = frappe.get_doc(record)
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
