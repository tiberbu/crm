"""Seed the native Frappe SMS gateway shape for Africa's Talking."""

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
	{"parameter": "username", "value": "sandbox", "header": 0},
	{"parameter": "from", "value": "CHANGE_ME", "header": 0},
	{"parameter": "bulkSMSMode", "value": "1", "header": 0},
)


def execute():
	"""Seed an empty SMS Settings record without replacing another provider."""
	if not frappe.db.exists("DocType", "SMS Settings"):
		return

	settings = frappe.get_single("SMS Settings")
	if frappe.utils.cstr(settings.get("sms_gateway_url") or "").strip():
		return

	settings.sms_gateway_url = _GATEWAY_URL
	settings.message_parameter = "message"
	settings.receiver_parameter = "to"
	settings.use_post = 1

	existing_parameters = {
		frappe.utils.cstr(row.get("parameter") or "").strip() for row in (settings.get("parameters") or [])
	}
	for parameter in _STATIC_PARAMETERS:
		if parameter["parameter"] not in existing_parameters:
			settings.append("parameters", parameter)

	settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL
