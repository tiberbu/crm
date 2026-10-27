"""Let a client mark a token order as one-time or recurring when confirming it in the portal."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "crm_order_frequency",
					"fieldtype": "Select",
					"label": "Token Order Frequency",
					"options": "One-time\nRecurring",
					"default": "One-time",
					"insert_after": "crm_token_package_item",
					"no_copy": 1,
				},
				{
					"fieldname": "crm_recurrence_period",
					"fieldtype": "Select",
					"label": "Recurs Every",
					"options": "\nMonthly\nQuarterly\nYearly",
					"insert_after": "crm_order_frequency",
					"depends_on": "eval:doc.crm_order_frequency=='Recurring'",
					"no_copy": 1,
				},
			]
		}
	)
