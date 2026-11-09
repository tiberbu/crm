import frappe
from frappe.tests import IntegrationTestCase

from crm.patches.v1_0.add_facility_onboarding_otp_channel import execute

FIELD = "facility_onboarding_preferred_otp_channel"


class TestOtpChannelSetting(IntegrationTestCase):
	def test_patch_adds_select_defaulting_to_email_and_is_repeatable(self):
		execute()
		execute()
		meta = frappe.get_meta("CRM Opt-In Settings", cached=False)
		field = meta.get_field(FIELD)
		self.assertEqual(field.fieldtype, "Select")
		self.assertEqual(field.default, "Email")
		self.assertEqual(field.options.split("\n"), ["Email", "SMS"])
		self.assertEqual(
			frappe.db.count("Custom Field", {"dt": "CRM Opt-In Settings", "fieldname": FIELD}), 1
		)

	def test_patch_is_registered_after_model_sync(self):
		with open(frappe.get_app_path("crm", "patches.txt")) as handle:
			lines = [line.strip() for line in handle]
		self.assertIn("crm.patches.v1_0.add_facility_onboarding_otp_channel", lines)
		self.assertGreater(
			lines.index("crm.patches.v1_0.add_facility_onboarding_otp_channel"),
			lines.index("[post_model_sync]"),
		)
