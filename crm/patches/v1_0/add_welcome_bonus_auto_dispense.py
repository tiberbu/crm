"""P-76: the switch that auto-assigns the welcome bonus when a facility selects a package."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "auto_dispense_welcome_bonus",
					"fieldtype": "Check",
					"label": "Auto-assign the bonus when a package is selected",
					"description": "Grant the first-purchase bonus as soon as a facility selects a Flex package, "
					"before payment. Each facility still gets it once; its first paid invoice then grants the package only.",
					"default": "0",
					"insert_after": "welcome_bonus_tokens",
				}
			]
		}
	)
