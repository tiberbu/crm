"""Give every catalogue package a status that matches its old Enabled tick."""

import frappe


def execute():
	frappe.reload_doc("fcrm", "doctype", "crm_token_package")
	frappe.db.sql(
		"""UPDATE `tabCRM Token Package`
		SET status = IF(enabled = 1, 'Active', 'Disabled')
		WHERE IFNULL(status, '') = '' OR (enabled = 1) <> (status = 'Active')"""
	)
