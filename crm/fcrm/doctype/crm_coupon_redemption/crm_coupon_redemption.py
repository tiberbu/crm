import frappe
from frappe.model.document import Document


class CRMCouponRedemption(Document):
	def validate(self):
		# A facility holds at most one live redemption, across all coupons. MariaDB allows many NULLs
		# in a unique index, so a Released or Lapsed row (guard set to None) frees the facility.
		if self.status in ("Reserved", "Granted"):
			self.facility_guard = self.facility_mfl
		else:
			self.facility_guard = None
