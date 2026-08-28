from frappe.tests import UnitTestCase
from frappe.utils import add_days, today

from crm.api.optin import _get_optin_deal_forecast_fields


class TestOptInForecastFields(UnitTestCase):
	def test_deal_forecast_uses_accepted_annual_prices(self):
		fields = _get_optin_deal_forecast_fields(
			[
				{"annual_kes": 12_000},
				{"annual_kes": 36_000.5},
			]
		)

		self.assertEqual(fields["expected_deal_value"], 48_000.5)
		self.assertEqual(fields["expected_closure_date"], add_days(today(), 30))
