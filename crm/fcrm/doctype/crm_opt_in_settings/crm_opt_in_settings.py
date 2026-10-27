# Copyright (c) 2026, Tiberbu Healthnet Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CRMOptInSettings(Document):
	def validate(self):
		self.sync_token_package_status()

	def sync_token_package_status(self):
		"""Keep each package's `enabled` equal to `status == Active`.

		Whichever of the two was changed in this save wins, so code and Desk edits that still
		tick Enabled keep working.
		"""
		before = self.get_doc_before_save()
		previous = {row.name: row.get("status") for row in (before.get("token_packages") if before else None) or []}
		for row in self.get("token_packages") or []:
			status = row.get("status")
			# A new row's status is only a choice when it differs from the Active default.
			status_changed = status != previous[row.name] if row.name in previous else status not in (None, "", "Active")
			if not status_changed and bool(row.enabled) != (row.get("status") == "Active"):
				row.status = "Active" if row.enabled else ("Discontinued" if row.get("status") == "Discontinued" else "Disabled")
			row.status = row.get("status") or "Active"
			row.enabled = int(row.status == "Active")
			if row.status == "Discontinued" and not row.get("discontinued_on"):
				row.discontinued_on = frappe.utils.today()
