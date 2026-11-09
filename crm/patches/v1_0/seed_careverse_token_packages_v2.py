"""Seed the standardized Careverse Token Packages (Starter, Growth, Scale) into CRM Opt-In Settings."""

import frappe


def execute():
	if "erpnext" not in frappe.get_installed_apps():
		return

	from crm.demo.seed_token_package_catalog import run

	run()

