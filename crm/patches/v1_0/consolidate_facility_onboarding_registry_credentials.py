"""Use the existing CRM HFR Settings credentials for facility onboarding.

Older development revisions stored a duplicate service account on CRM Opt-In
Settings. Preserve those values and copy them into the canonical HFR singleton
only when the canonical fields are empty. The onboarding adapter no longer
reads the duplicate credential fields.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "CRM HFR Settings") or not frappe.db.exists(
		"DocType", "CRM Opt-In Settings"
	):
		return

	hfr = frappe.get_single("CRM HFR Settings")
	onboarding = frappe.get_single("CRM Opt-In Settings")
	changed = False

	if not hfr.hfr_url and onboarding.get("facility_onboarding_hie_url"):
		hfr.hfr_url = onboarding.facility_onboarding_hie_url
		changed = True
	if not hfr.hfr_username and onboarding.get("facility_onboarding_hie_username"):
		hfr.hfr_username = onboarding.facility_onboarding_hie_username
		changed = True
	if not hfr.get_password("hfr_password", raise_exception=False):
		password = onboarding.get_password("facility_onboarding_hie_password", raise_exception=False)
		if password:
			hfr.hfr_password = password
			changed = True
	if not hfr.hfr_jwt_expiry and onboarding.get("facility_onboarding_jwt_expiry"):
		hfr.hfr_jwt_expiry = onboarding.facility_onboarding_jwt_expiry
		changed = True

	if changed:
		hfr.save(ignore_permissions=True)

	# Keep legacy fields for rollback/data recovery, but remove them from normal
	# settings forms so there is one authoritative credential location.
	for fieldname in (
		"facility_onboarding_hie_url",
		"facility_onboarding_hie_username",
		"facility_onboarding_hie_password",
		"facility_onboarding_jwt_expiry",
	):
		custom_field = frappe.db.get_value(
			"Custom Field",
			{"dt": "CRM Opt-In Settings", "fieldname": fieldname},
			"name",
		)
		if custom_field:
			frappe.db.set_value("Custom Field", custom_field, "hidden", 1, update_modified=False)

	frappe.clear_cache(doctype="CRM Opt-In Settings")
