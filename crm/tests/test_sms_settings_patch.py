from unittest.mock import Mock, patch

from frappe.tests import UnitTestCase

from crm.patches.v1_0.seed_africas_talking_sms_settings import execute


class TestAfricaSTalkingSMSSettingsPatch(UnitTestCase):
	def test_seeds_native_gateway_when_sms_settings_is_empty(self):
		settings = Mock()
		settings.get.side_effect = lambda key, default=None: {
			"sms_gateway_url": "",
			"parameters": [],
		}.get(key, default)

		with (
			patch("crm.patches.v1_0.seed_africas_talking_sms_settings.frappe.db.exists", return_value=True),
			patch(
				"crm.patches.v1_0.seed_africas_talking_sms_settings.frappe.get_single",
				return_value=settings,
			),
		):
			execute()

		self.assertEqual(settings.sms_gateway_url, "https://api.africastalking.com/version1/messaging")
		self.assertEqual(settings.message_parameter, "message")
		self.assertEqual(settings.receiver_parameter, "to")
		self.assertEqual(settings.use_post, 1)
		self.assertEqual(settings.append.call_count, 6)
		settings.save.assert_called_once_with(ignore_permissions=True)

	def test_does_not_replace_an_existing_sms_provider(self):
		settings = Mock()
		settings.get.side_effect = lambda key, default=None: {
			"sms_gateway_url": "https://existing.example/sms",
			"parameters": [],
		}.get(key, default)

		with (
			patch("crm.patches.v1_0.seed_africas_talking_sms_settings.frappe.db.exists", return_value=True),
			patch(
				"crm.patches.v1_0.seed_africas_talking_sms_settings.frappe.get_single",
				return_value=settings,
			),
		):
			execute()

		settings.append.assert_not_called()
		settings.save.assert_not_called()
