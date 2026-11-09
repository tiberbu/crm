"""Add token calculator parameters to CRM Opt-In Settings."""

from __future__ import annotations

import json
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"CRM Opt-In Settings": [
				{
					"fieldname": "section_token_calculator",
					"fieldtype": "Section Break",
					"label": "Token Calculator Parameters",
					"insert_after": "token_packages",
				},
				{
					"fieldname": "token_calc_monthly_platform_fee",
					"fieldtype": "Int",
					"label": "Monthly Platform Access Fee (tokens)",
					"default": "500",
					"insert_after": "section_token_calculator",
					"description": "Fixed access deduction applied at the start of each funded month.",
				},
				{
					"fieldname": "token_calc_bill_value_per_token",
					"fieldtype": "Currency",
					"label": "Bill Value per Token (KES)",
					"default": "750",
					"insert_after": "token_calc_monthly_platform_fee",
					"description": "Patient bill value represented by 1 token (e.g. 1 token per KES 750).",
				},
				{
					"fieldname": "token_calc_default_avg_bill",
					"fieldtype": "Currency",
					"label": "Default Average Patient Bill (KES)",
					"default": "1500",
					"insert_after": "token_calc_bill_value_per_token",
					"description": "Default baseline average total bill per patient encounter.",
				},
				{
					"fieldname": "token_calc_default_operating_days",
					"fieldtype": "Int",
					"label": "Default Operating Days / Month",
					"default": "24",
					"insert_after": "token_calc_default_avg_bill",
					"description": "Default clinic operating days per month.",
				},
				{
					"fieldname": "token_calc_parameters_json",
					"fieldtype": "Code",
					"options": "JSON",
					"label": "Calculator Service Points & Presets (JSON)",
					"insert_after": "token_calc_default_operating_days",
					"description": "Full parameter specification for service-point deductions, encounter frequencies, and facility presets.",
				},
			],
		}
	)

	frappe.clear_cache(doctype="CRM Opt-In Settings")

	# Seed default calculator values if not already present
	settings = frappe.get_single("CRM Opt-In Settings")
	changed = False
	if not settings.get("token_calc_monthly_platform_fee"):
		settings.set("token_calc_monthly_platform_fee", 500)
		changed = True
	if not settings.get("token_calc_bill_value_per_token"):
		settings.set("token_calc_bill_value_per_token", 750)
		changed = True
	if not settings.get("token_calc_default_avg_bill"):
		settings.set("token_calc_default_avg_bill", 1500)
		changed = True
	if not settings.get("token_calc_default_operating_days"):
		settings.set("token_calc_default_operating_days", 24)
		changed = True
	if not settings.get("token_calc_parameters_json"):
		from crm.api.facility_onboarding import _default_calculator_config

		settings.set("token_calc_parameters_json", json.dumps(_default_calculator_config(), indent=2))
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
