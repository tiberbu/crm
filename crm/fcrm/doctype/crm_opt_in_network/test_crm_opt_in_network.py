from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from crm.fcrm.doctype.crm_opt_in_network.crm_opt_in_network import (
	CRMOptInNetwork,
	_generate_partner_id,
	_validate_partner_id,
)


class TestCRMOptInNetwork(UnitTestCase):
	def test_generated_partner_id_is_six_digits(self):
		with patch.object(frappe.db, "exists", return_value=False):
			with patch(
				"crm.fcrm.doctype.crm_opt_in_network.crm_opt_in_network.secrets.randbelow",
				return_value=234567,
			):
				self.assertEqual(_generate_partner_id(), "334567")

	def test_supplied_partner_id_must_be_six_digits_and_unique(self):
		with patch.object(frappe.db, "get_value", return_value=None):
			_validate_partner_id("012345", "NETWORK-1")

		with self.assertRaises(frappe.ValidationError):
			_validate_partner_id("12345", "NETWORK-1")

		with patch.object(frappe.db, "get_value", return_value="NETWORK-2"):
			with self.assertRaises(frappe.ValidationError):
				_validate_partner_id("123456", "NETWORK-1")

	def test_partner_id_cannot_change_after_network_creation(self):
		doc = SimpleNamespace(
			partner_id="654321",
			name="NETWORK-1",
			doctype="CRM Opt-In Network",
			is_new=lambda: False,
		)
		with (
			patch.object(frappe.db, "get_value", return_value="123456"),
			patch(
				"crm.fcrm.doctype.crm_opt_in_network.crm_opt_in_network._validate_partner_id"
			),
		):
			with self.assertRaises(frappe.ValidationError):
				CRMOptInNetwork.validate(doc)
