"""Configure the native Frappe SMS gateway for Africa's Talking."""

import frappe

_GATEWAY_URL = "https://api.africastalking.com/version1/messaging"
_STATIC_PARAMETERS = (
	{"parameter": "apiKey", "value": "CHANGE_ME", "header": 1},
	{"parameter": "Accept", "value": "application/json", "header": 1},
	{
		"parameter": "Content-Type",
		"value": "application/x-www-form-urlencoded",
		"header": 1,
	},
	{"parameter": "username", "value": "CHANGE_ME", "header": 0},
	{"parameter": "from", "value": "CHANGE_ME", "header": 0},
	{"parameter": "bulkSMSMode", "value": "1", "header": 0},
)


def execute():
	"""Overwrite SMS Settings with the documented Africa's Talking configuration."""
	if not frappe.db.exists("DocType", "SMS Settings"):
		return

	settings = frappe.get_single("SMS Settings")
	settings.sms_gateway_url = _GATEWAY_URL
	settings.message_parameter = "message"
	settings.receiver_parameter = "to"
	settings.use_post = 1
	# This is an explicit first-migrate provider choice. Clear old static
	# parameters so credentials for another gateway cannot leak into requests.
	settings.set("parameters", [])
	for parameter in _STATIC_PARAMETERS:
		settings.append("parameters", parameter)

	settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL
