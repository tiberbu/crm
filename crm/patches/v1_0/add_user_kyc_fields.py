"""Add KYC and verified identification fields to User for CX portal integration."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	fields = [
		{
			"fieldname": "national_id",
			"fieldtype": "Data",
			"label": "National ID",
			"insert_after": "phone",
		},
		{
			"fieldname": "national_id_verified",
			"fieldtype": "Check",
			"label": "National ID Verified",
			"default": "0",
			"insert_after": "national_id",
		},
		{
			"fieldname": "identification_type",
			"fieldtype": "Data",
			"label": "Identification Type",
			"default": "National ID",
			"insert_after": "national_id_verified",
		},
		{
			"fieldname": "hfr_owner_licence",
			"fieldtype": "Data",
			"label": "HFR Owner Licence",
			"insert_after": "identification_type",
		},
		{
			"fieldname": "hfr_registration_number",
			"fieldtype": "Data",
			"label": "HFR Registration Number",
			"insert_after": "hfr_owner_licence",
		},
	]
	create_custom_fields({"User": fields}, ignore_validate=True)

