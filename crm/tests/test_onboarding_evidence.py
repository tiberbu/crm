import frappe
from frappe.tests import IntegrationTestCase

from crm.fcrm.doctype.crm_onboarding_evidence.crm_onboarding_evidence import evidence_ref, record_event


class TestOnboardingEvidence(IntegrationTestCase):
	def test_record_event_inserts_row(self):
		name = record_event(
			"lookup",
			session_ref=evidence_ref("token"),
			subject_ref=evidence_ref("id-number"),
			detail="two facilities resolved",
		)
		row = frappe.get_doc("CRM Onboarding Evidence", name)
		self.assertEqual(row.event, "lookup")
		self.assertEqual(row.outcome, "ok")
		self.assertTrue(row.occurred_at)

	def test_rows_are_append_only(self):
		row = frappe.get_doc("CRM Onboarding Evidence", record_event("otp_sent", channel="email"))
		row.detail = "changed"
		with self.assertRaises(frappe.PermissionError):
			row.save(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("CRM Onboarding Evidence", row.name, ignore_permissions=True, force=True)

	def test_sensitive_detail_is_rejected(self):
		for detail in ("owner@example.com", "id 12345678", "otp 123456", "x" * 141):
			with self.assertRaises(frappe.ValidationError, msg=detail):
				record_event("lookup", detail=detail)

	def test_unknown_event_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			record_event("not_an_event")

	def test_evidence_ref_is_stable_and_not_the_input(self):
		self.assertEqual(evidence_ref("abc"), evidence_ref("abc"))
		self.assertNotEqual(evidence_ref("abc"), evidence_ref("abd"))
		self.assertNotIn("abc", evidence_ref("abc"))
		self.assertLessEqual(len(evidence_ref("abc")), 64)
