import frappe
from frappe import _
from frappe.model.document import Document

MAX_THRESHOLD = 100_000_000


class CRMFacilityTokenAlert(Document):
	def validate(self):
		self.mfl_code = (self.mfl_code or "").strip()
		self.hfr_facility_id = (self.hfr_facility_id or "").strip()
		if not 1 <= (self.threshold or 0) <= MAX_THRESHOLD:
			frappe.throw(_("Set a threshold between 1 and {0} tokens.").format(f"{MAX_THRESHOLD:,}"))
		duplicate = frappe.db.exists(
			"CRM Facility Token Alert",
			{"user": self.user, "mfl_code": self.mfl_code, "name": ("!=", self.name)},
		)
		if duplicate:
			frappe.throw(_("This owner already has a token alert for that facility."), frappe.DuplicateEntryError)
