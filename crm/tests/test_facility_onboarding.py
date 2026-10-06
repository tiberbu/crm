from unittest.mock import Mock, patch

from frappe.tests import UnitTestCase

from crm.api.facility_onboarding import _onboarding_config


class TestFacilityOnboardingRegistryConfig(UnitTestCase):
	def test_onboarding_reuses_crm_hfr_credentials(self):
		hfr = Mock(
			hfr_enabled=1,
			hfr_url="https://registry.example.test",
			hfr_username="canonical-user",
			hfr_jwt_expiry=3600,
		)
		hfr.get_password.return_value = "canonical-password"
		optin = {
			"facility_onboarding_hie_url": "https://legacy.example.test",
			"facility_onboarding_hie_username": "legacy-user",
			"facility_onboarding_hfr_owner_path": "/owner-facilities",
			"facility_onboarding_hfr_facility_path": "/facility",
			"facility_onboarding_client_registry_path": "/client",
		}

		def get_single(doctype):
			return hfr if doctype == "CRM HFR Settings" else optin

		with patch("crm.api.facility_onboarding.frappe.get_single", side_effect=get_single):
			config = _onboarding_config()

		self.assertEqual(config["base_url"], "https://registry.example.test")
		self.assertEqual(config["username"], "canonical-user")
		self.assertEqual(config["password"], "canonical-password")
		self.assertEqual(config["jwt_expiry"], 3600)
		self.assertEqual(config["owner_path"], "/owner-facilities")
		self.assertEqual(config["client_path"], "/client")
