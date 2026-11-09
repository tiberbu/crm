import re
import secrets

import frappe
from frappe import _
from frappe.model.document import Document


class CRMOptInNetwork(Document):
	def before_insert(self):
		self.partner_id = _normalise_partner_id(self.partner_id)
		if not self.partner_id:
			self.partner_id = _generate_partner_id()
		_validate_partner_id(self.partner_id, self.name)

	def validate(self):
		self.partner_id = _normalise_partner_id(self.partner_id)
		if not self.partner_id:
			frappe.throw(_("Partner ID is required for an Opt-In Network."), frappe.ValidationError)
		_validate_partner_id(self.partner_id, self.name)

		if not self.is_new():
			previous = frappe.db.get_value(self.doctype, self.name, "partner_id")
			if previous and previous != self.partner_id:
				frappe.throw(
					_("Partner ID cannot be changed after the Network is created."),
					frappe.ValidationError,
				)


def _normalise_partner_id(value):
	return frappe.utils.cstr(value or "").strip()


def _validate_partner_id(partner_id, network_name=None):
	if not re.fullmatch(r"\d{6}", partner_id or ""):
		frappe.throw(_("Partner ID must contain exactly six digits."), frappe.ValidationError)

	existing = frappe.db.get_value(
		"CRM Opt-In Network",
		{"partner_id": partner_id, "name": ["!=", network_name or ""]},
		"name",
	)
	if existing:
		frappe.throw(_("Partner ID {0} is already assigned to another Network.").format(partner_id))


def _generate_partner_id():
	for _attempt in range(100):
		candidate = str(secrets.randbelow(900000) + 100000)
		if not frappe.db.exists("CRM Opt-In Network", {"partner_id": candidate}):
			return candidate
	frappe.throw(_("Could not generate a unique six-digit Partner ID. Try again."))
