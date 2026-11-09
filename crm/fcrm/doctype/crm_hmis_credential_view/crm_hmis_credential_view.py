# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CRMHMISCredentialView(Document):
	"""Audit of a one-time view of a facility's temporary HMIS owner password.

	Holds who viewed it and when, never the password. A `Viewed` row blocks a
	second view for the same FID and setup record; support sets it to
	`Re-armed` to allow one more view.
	"""
