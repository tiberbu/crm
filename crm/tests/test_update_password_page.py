import os
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

import crm
from crm.www import update_password

WWW_DIR = os.path.join(os.path.dirname(crm.__file__), "www")


class TestUpdatePasswordPage(UnitTestCase):
	def test_hyphenated_pages_have_a_controller_frappe_can_load(self):
		# Frappe loads a page's controller from <name with "-" replaced by "_">.py, so a
		# controller saved only as update-password.py never runs and the emailed reset key
		# never reaches the template.
		for filename in os.listdir(WWW_DIR):
			stem, ext = os.path.splitext(filename)
			if ext != ".py" or "-" not in stem:
				continue
			with self.subTest(page=stem):
				self.assertTrue(
					os.path.exists(os.path.join(WWW_DIR, stem.replace("-", "_") + ".py")),
					f"{filename} is never loaded by Frappe; name it {stem.replace('-', '_')}.py",
				)

	def test_reset_key_from_emailed_link_reaches_the_page(self):
		context = frappe._dict()
		request = frappe._dict(args={"key": "reset-key-from-email"})
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch("crm.www.update_password.get_configured_app_brand", return_value={"app_name": "CRM"}),
			patch("crm.www.update_password.apply_brand_context"),
			patch("crm.www.update_password.frappe.sessions.get_csrf_token", return_value="csrf"),
		):
			update_password.get_context(context)

		self.assertEqual(context.reset_key, "reset-key-from-email")
		self.assertFalse(context.password_expired)
