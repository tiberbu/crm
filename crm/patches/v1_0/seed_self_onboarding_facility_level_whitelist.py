"""Seed the supported HFR Facility Levels for token self-onboarding."""

from __future__ import annotations

import frappe

SETTING_FIELD = "self_onboarding_allowed_facility_levels"
ALLOWED_LEVELS = ("Level 2", "Level 3B", "Level 3C")


def execute():
	"""Add the initial allow-list without removing administrator-configured levels."""
	doctype = "CRM Opt-In Settings"
	if not frappe.db.exists("DocType", doctype):
		return
	if not frappe.get_meta(doctype).has_field(SETTING_FIELD):
		frappe.throw(
			"CRM Opt-In Settings.%s is missing; cannot seed facility eligibility levels." % SETTING_FIELD
		)

	settings = frappe.get_single(doctype)
	configured_lines = [
		line.strip()
		for line in (settings.get(SETTING_FIELD) or "").splitlines()
		if line.strip()
	]
	required_by_key = {level.casefold(): level for level in ALLOWED_LEVELS}
	configured = []
	configured_keys = set()
	for level in configured_lines:
		key = level.casefold()
		if key in configured_keys:
			continue
		configured.append(required_by_key.get(key, level))
		configured_keys.add(key)
	for level in ALLOWED_LEVELS:
		key = level.casefold()
		if key not in configured_keys:
			configured.append(level)
			configured_keys.add(key)

	value = "\n".join(configured)
	if value != (settings.get(SETTING_FIELD) or ""):
		settings.set(SETTING_FIELD, value)
		settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL: migration default
		frappe.clear_cache(doctype=doctype)
