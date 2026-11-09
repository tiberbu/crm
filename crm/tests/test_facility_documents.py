"""Integration tests for crm.api.facility_documents (paged facility page tabs).

Run on an approved test site via ``scripts/run-crm-tests.sh <site> --module
crm.tests.test_facility_documents`` (always ``--app crm``). Fixtures pick a
non-group Customer Group, a leaf Territory and an existing non-stock sales Item
from the site so they do not depend on demo data.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

OWNER = "cx-facdocs-owner@example.test"
OTHER = "cx-facdocs-other@example.test"
MODULE = "crm.api.facility_documents"
MFL = "MFL-FACDOCS"


def _website_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Facility Docs", "user_type": "Website User", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	return email


def _item_code():
	code = frappe.db.exists("Item", "Test Item") or frappe.db.get_value(
		"Item", {"is_sales_item": 1, "disabled": 0, "has_variants": 0, "is_stock_item": 0}, "name"
	)
	if not code:
		raise unittest.SkipTest("No non-stock sales Item on this site")
	return code


def _customer(name):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
	return name


def _sales_order(customer, mfl):
	doc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"transaction_date": frappe.utils.nowdate(),
			"delivery_date": frappe.utils.nowdate(),
			"currency": "KES",
			"items": [{"item_code": _item_code(), "qty": 1, "rate": 100}],
		}
	)
	doc.crm_token_facility_mfl = mfl
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate = True
	doc.submit()
	return doc.name


def _sales_invoice(customer, mfl, paid=False):
	doc = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"posting_date": frappe.utils.nowdate(),
			"due_date": frappe.utils.nowdate(),
			"currency": "KES",
			"items": [{"item_code": _item_code(), "qty": 1, "rate": 100}],
		}
	)
	doc.crm_token_facility_mfl = mfl
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate = True
	doc.submit()
	if paid:
		frappe.db.set_value("Sales Invoice", doc.name, "outstanding_amount", 0)
	return doc.name


class TestFacilityDocuments(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("facility_documents_test")
		self.addCleanup(frappe.db.rollback, save_point="facility_documents_test")
		self.addCleanup(frappe.set_user, "Administrator")
		if not (frappe.db.has_column("Sales Order", "crm_token_facility_mfl") and frappe.db.has_column("Sales Invoice", "crm_token_facility_mfl")):
			self.skipTest("Facility MFL custom fields are not installed")
		self.customer = _customer("Facility Docs Test Customer")
		_website_user(OWNER)
		_website_user(OTHER)

	def _grant(self, mfls=(MFL,)):
		return (
			patch("crm.api.website_redirect.get_user_customer_names", return_value=[self.customer]),
			patch(f"{MODULE}._customer_mfls", return_value=list(mfls)),
		)

	def _call(self, method="get_facility_documents", user=OWNER, mfl=MFL, **kwargs):
		import crm.api.facility_documents as api

		frappe.set_user(user)
		try:
			return getattr(api, method)(customer=self.customer, mfl_code=mfl, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def test_customer_not_granted_is_refused(self):
		with patch("crm.api.website_redirect.get_user_customer_names", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				self._call(user=OTHER, kind="order")

	def test_guest_is_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self._call(user="Guest", kind="order")

	def test_facility_outside_customer_is_refused(self):
		grant, mfls = self._grant()
		with grant, mfls, self.assertRaises(frappe.PermissionError):
			self._call(mfl="MFL-NOT-MINE", kind="order")

	def test_counts_are_refused_without_grant(self):
		with patch("crm.api.website_redirect.get_user_customer_names", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				self._call(method="get_facility_document_counts", user=OTHER)

	def test_unknown_kind_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._call(kind="quote")

	def test_orders_are_paged_per_facility(self):
		for _ in range(25):
			_sales_order(self.customer, MFL)
		_sales_order(self.customer, "MFL-FACDOCS-OTHER")
		grant, mfls = self._grant()
		with grant, mfls:
			first = self._call(kind="order", start=0, page_length=20)
			second = self._call(kind="order", start=20, page_length=20)
		self.assertEqual(first["total"], 25)
		self.assertEqual(len(first["rows"]), 20)
		self.assertEqual(len(second["rows"]), 5)
		names = {row["name"] for row in first["rows"] + second["rows"]}
		self.assertEqual(len(names), 25)
		self.assertFalse(first["truncated"])

	def test_page_length_is_capped(self):
		grant, mfls = self._grant()
		with grant, mfls:
			page = self._call(kind="order", page_length=500)
		self.assertEqual(page["page_length"], 50)

	def test_paid_invoices_are_listed_and_outstanding_filter_works(self):
		paid = _sales_invoice(self.customer, MFL, paid=True)
		due = _sales_invoice(self.customer, MFL)
		grant, mfls = self._grant()
		with grant, mfls:
			every = self._call(kind="invoice", status="all")
			outstanding = self._call(kind="invoice", status="outstanding")
			counts = self._call(method="get_facility_document_counts")
		every_names = [row["name"] for row in every["rows"]]
		self.assertIn(paid, every_names)
		self.assertIn(due, every_names)
		self.assertEqual(every_names[0], due, "open invoices come first")
		self.assertEqual([row["name"] for row in outstanding["rows"]], [due])
		self.assertEqual(counts["invoice"], 2)
		self.assertEqual(counts["invoiceDue"], 1)

	def test_search_finds_one_order(self):
		names = [_sales_order(self.customer, MFL) for _ in range(3)]
		grant, mfls = self._grant()
		with grant, mfls:
			page = self._call(kind="order", search=names[1].lower())
		self.assertEqual([row["name"] for row in page["rows"]], [names[1]])
