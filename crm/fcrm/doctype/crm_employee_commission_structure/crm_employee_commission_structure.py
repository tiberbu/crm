import frappe
from frappe.model.document import Document


class CRMEmployeeCommissionStructure(Document):
	def validate(self):
		if self.commission_pct is None or not 0 <= float(self.commission_pct) <= 100:
			frappe.throw("Commission percentage must be between 0 and 100.")
