# Africa's Talking SMS configuration

CRM contract invitations, contract OTPs, and contract approval notifications
already call Frappe's native `frappe.core.doctype.sms_settings.sms_settings.send_sms`.
No CRM-specific provider doctype or SDK dependency is required for Africa's
Talking.

## Recommended Frappe configuration

Use Africa's Talking's standard single/multi-recipient messaging endpoint. The
native Frappe gateway loops over recipients and sends each request immediately,
which is appropriate for the one-recipient OTP and signing notifications used by
CRM.

In **SMS Settings**, configure:

| Frappe field | Value |
| --- | --- |
| SMS Gateway URL | `https://api.africastalking.com/version1/messaging` |
| Message Parameter | `message` |
| Receiver Parameter | `to` |
| Use POST | Enabled |

Add these **Static Parameters**. Mark `apiKey`, `Accept`, and `Content-Type` as
headers; leave the remaining rows as request-body parameters:

| Parameter | Value | Header |
| --- | --- | --- |
| `apiKey` | Africa's Talking application API key | Yes |
| `Accept` | `application/json` | Yes |
| `Content-Type` | `application/x-www-form-urlencoded` | Yes |
| `username` | Africa's Talking application username (or `sandbox`) | No |
| `from` | Registered Africa's Talking sender ID or shortcode | No |
| `bulkSMSMode` | `1` | No |

Keep the API key in the protected SMS Settings parameter table; never commit it
to this repository or put it in a CRM fixture.

The linked Africa's Talking bulk endpoint (`/version1/messaging/bulk`) accepts a
JSON `phoneNumbers` array and `senderId`. Frappe's native gateway does not have
a list-valued receiver parameter, so that endpoint would require a custom
provider override. The standard `/version1/messaging` endpoint supports the
native `send_sms` contract and is the safer, smaller integration for CRM.

For production, use an Africa's Talking sender ID approved for the target market.
For sandbox tests, use the `sandbox` username and the sandbox API key, and send
only to numbers registered in the sandbox application.

Reference: [Africa's Talking SMS documentation](https://developers.africastalking.com/docs/sms/sending/bulk)
and the [official Python SDK](https://github.com/AfricasTalkingLtd/africastalking-python).
