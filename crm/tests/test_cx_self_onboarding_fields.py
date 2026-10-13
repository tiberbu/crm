import frappe
from frappe.tests import IntegrationTestCase

from crm.patches.v1_0.add_cx_self_onboarding_fields import execute

OIS_FIELDS = (
	"onboarding_source",
	"onboarding_identity_ref",
	"cx_account_email",
	"self_onboarding_tc_document",
	"self_onboarding_tc_hash",
	"self_onboarding_tc_accepted_at",
)
SETTINGS_FIELD = "self_onboarding_tc_document"


class TestCxSelfOnboardingFields(IntegrationTestCase):
	def test_patch_leaves_legacy_submission_self_onboarding_fields_blank(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("cx_self_onboarding_fields_test")
		self.addCleanup(frappe.db.rollback, save_point="cx_self_onboarding_fields_test")
		self.addCleanup(frappe.set_user, "Administrator")

		legacy_submission = frappe.get_doc(
			{
				"doctype": "CRM Opt-In Submission",
				"naming_series": "OIS-.YYYY.-",
				"status": "Processed",
				"network_slug": "legacy-network",
				"submitter_email": "legacy-self-onboarding-fields@example.com",
				"facility_signatory_name": "Legacy Signatory",
				"facility_signatory_email": "legacy-self-onboarding-fields@example.com",
				"raw_json": "{}",
				"submitted_at": frappe.utils.now_datetime(),
			}
		)
		legacy_submission.flags.skip_auto_processing = True
		legacy_submission.insert(ignore_permissions=True)
		self.assertTrue(all(not legacy_submission.get(fieldname) for fieldname in OIS_FIELDS))

		execute()
		execute()

		self.assertEqual(
			frappe.db.get_value("CRM Opt-In Submission", legacy_submission.name, list(OIS_FIELDS)),
			(None,) * len(OIS_FIELDS),
		)

	def test_patch_adds_fields_with_safe_metadata_and_is_repeatable(self):
		execute()
		execute()

		ois_meta = frappe.get_meta("CRM Opt-In Submission", cached=False)
		self.assertEqual(ois_meta.get_field("onboarding_source").fieldtype, "Data")
		self.assertEqual(ois_meta.get_field("onboarding_source").read_only, 1)
		self.assertEqual(ois_meta.get_field("onboarding_source").no_copy, 1)
		self.assertFalse(ois_meta.get_field("onboarding_source").default)

		identity_ref = ois_meta.get_field("onboarding_identity_ref")
		self.assertEqual(identity_ref.fieldtype, "Data")
		self.assertEqual(identity_ref.hidden, 1)
		self.assertEqual(identity_ref.read_only, 1)
		self.assertEqual(identity_ref.no_copy, 1)
		self.assertFalse(identity_ref.default)

		account_email = ois_meta.get_field("cx_account_email")
		self.assertEqual(account_email.fieldtype, "Data")
		self.assertEqual(account_email.options, "Email")
		self.assertFalse(account_email.default)

		for fieldname in ("self_onboarding_tc_document", "self_onboarding_tc_hash"):
			field = ois_meta.get_field(fieldname)
			self.assertEqual(field.fieldtype, "Data")
			self.assertEqual(field.read_only, 1)
			self.assertEqual(field.no_copy, 1)
			self.assertFalse(field.default)
		self.assertEqual(field.length, 64 if fieldname.endswith("hash") else 0)

		accepted_at = ois_meta.get_field("self_onboarding_tc_accepted_at")
		self.assertEqual(accepted_at.fieldtype, "Datetime")
		self.assertEqual(accepted_at.read_only, 1)
		self.assertEqual(accepted_at.no_copy, 1)
		self.assertFalse(accepted_at.default)

		settings_field = frappe.get_meta("CRM Opt-In Settings", cached=False).get_field(SETTINGS_FIELD)
		self.assertEqual(settings_field.fieldtype, "Data")
		self.assertFalse(settings_field.default)

		for fieldname in OIS_FIELDS:
			self.assertEqual(
				frappe.db.count("Custom Field", {"dt": "CRM Opt-In Submission", "fieldname": fieldname}), 1
			)
		self.assertEqual(
			frappe.db.count(
				"Custom Field", {"dt": "CRM Opt-In Settings", "fieldname": SETTINGS_FIELD}
			),
			1,
		)

	def test_patch_is_registered_after_model_sync(self):
		with open(frappe.get_app_path("crm", "patches.txt")) as handle:
			lines = [line.strip() for line in handle]
		patch_name = "crm.patches.v1_0.add_cx_self_onboarding_fields"
		self.assertIn(patch_name, lines)
		self.assertGreater(lines.index(patch_name), lines.index("[post_model_sync]"))
