import frappe
from frappe import _
from frappe.model.document import Document


class CRMOnboardingRequest(Document):
	def validate(self):
		"""Keep external Tiberbu approver notifications dual-channel."""
		contact_fields = (
			self.get("tiberbu_approver_name"),
			self.get("tiberbu_approver_email"),
			self.get("tiberbu_approver_phone"),
		)
		if any(contact_fields) and not all(contact_fields):
			frappe.throw(
				_("Tiberbu Approver name, email, and phone are required when using an external contact.")
			)
