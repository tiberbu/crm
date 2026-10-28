"""Guest-facing Value Express self-facility onboarding shell (`/facility-onboarding`).

Serves the public self-service facility onboarding wizard (identity verification,
HFR facility lookup, Value Express package selection, and Tiberbu Express account
provisioning). Partner-invited Network Opt-In contract journeys use `/opt-in` instead.
"""

import os

import frappe
import frappe.sessions

from crm.branding import apply_brand_context, get_configured_app_brand

no_cache = 1
base_template_path = ""

_BUILT_HTML = ("public", "frontend", "facility-onboarding.html")


def get_context(context):
	brand = get_configured_app_brand()
	apply_brand_context(context, brand, surface="facility_onboarding")
	context.invitation_network = frappe.form_dict.get("network") or ""
	context.invitation_facility = frappe.form_dict.get("facility") or ""
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.invitation_head = _asset_head()
	return context


def _asset_head():
	path = os.path.join(frappe.get_app_path("crm"), *_BUILT_HTML)
	try:
		# nosemgrep: frappe-security-file-traversal -- path is assembled only from a fixed asset tuple and the CRM app path; no request value is used.
		with open(path, encoding="utf-8") as f:
			lines = f.readlines()
	except OSError:
		frappe.log_error("facility onboarding shell: built asset HTML not found at " + path)
		return ""

	kept = []
	for line in lines:
		tag = line.strip()
		if any(skip in tag for skip in ("registerSW", "vite-plugin-pwa", 'rel="manifest"')):
			continue
		if (
			tag.startswith('<script type="module"')
			or tag.startswith('<link rel="modulepreload"')
			or tag.startswith('<link rel="stylesheet"')
		):
			kept.append(tag)
	return "\n    ".join(kept)
