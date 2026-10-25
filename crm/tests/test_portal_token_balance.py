"""Live facility token balances in the CX portal and repeat top-ups (openmeter_mediator ADR-004)."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from crm.api import customer_experience as cx
from crm.api.website_redirect import _attach_token_balances

FID = "FID-99-TEST-1"


def _hooks(*methods):
	return lambda name, *a, **k: list(methods) if name == "crm_get_facility_token_balances" else []


class TestAttachTokenBalances(UnitTestCase):
	def _accounts(self):
		return [{"facilities": [{"hfr_facility_id": FID}, {"hfr_facility_id": ""}]}, {"facilities": []}]

	def test_balances_are_attached_by_fid(self):
		accounts = self._accounts()
		hook = MagicMock(return_value={FID: {"status": "ok", "balance": 1234.5}})
		with patch("crm.api.website_redirect.frappe.get_hooks", side_effect=_hooks("app.balances")), patch(
			"crm.api.website_redirect.frappe.get_attr", return_value=hook
		):
			_attach_token_balances(accounts)
		hook.assert_called_once_with([FID])
		self.assertEqual(accounts[0]["facilities"][0]["token_balance"]["balance"], 1234.5)
		self.assertNotIn("token_balance", accounts[0]["facilities"][1])

	def test_without_a_metering_app_nothing_changes(self):
		accounts = self._accounts()
		with patch("crm.api.website_redirect.frappe.get_hooks", side_effect=_hooks()):
			_attach_token_balances(accounts)
		self.assertNotIn("token_balance", accounts[0]["facilities"][0])

	def test_a_failing_hook_is_logged_not_raised(self):
		accounts = self._accounts()
		with patch("crm.api.website_redirect.frappe.get_hooks", side_effect=_hooks("app.balances")), patch(
			"crm.api.website_redirect.frappe.get_attr", return_value=MagicMock(side_effect=RuntimeError("down"))
		), patch("crm.api.website_redirect.frappe.log_error") as log_error:
			_attach_token_balances(accounts)
		log_error.assert_called_once()
		self.assertNotIn("token_balance", accounts[0]["facilities"][0])


class TestOpenPurchaseKey(UnitTestCase):
	def _invoices(self, states):
		"""states: purchase key -> (invoice name, docstatus, outstanding)."""

		def existing(doctype, key, **filters):
			return states[key][0] if key in states else None

		def get_value(doctype, name, fields, as_dict=False):
			for invoice, docstatus, outstanding in states.values():
				if invoice == name:
					return frappe._dict(docstatus=docstatus, outstanding_amount=outstanding)

		return patch.object(cx, "_existing_document", side_effect=existing), patch.object(
			cx.frappe.db, "get_value", side_effect=get_value
		)

	def test_first_or_unpaid_purchase_keeps_the_period_key(self):
		a, b = self._invoices({"base": ("SINV-1", 1, 500)})
		with a, b:
			self.assertEqual(cx._open_purchase_key("base"), "base")
		a, b = self._invoices({})
		with a, b:
			self.assertEqual(cx._open_purchase_key("base"), "base")

	def test_a_paid_purchase_moves_to_a_new_key(self):
		import hashlib

		second = hashlib.sha256(b"base|2").hexdigest()[:40]
		a, b = self._invoices({"base": ("SINV-1", 1, 0)})
		with a, b:
			self.assertEqual(cx._open_purchase_key("base"), second)
		a, b = self._invoices({"base": ("SINV-1", 1, 0), second: ("SINV-2", 1, 750)})
		with a, b:
			self.assertEqual(cx._open_purchase_key("base"), second)
