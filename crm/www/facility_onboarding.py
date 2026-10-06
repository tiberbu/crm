"""Guest-facing facility invitation landing page.

The page is intentionally a thin shell around the compiled Vue entry. The
landing surface explains the invitation and hands off to the existing Opt-In
wizard; it does not create a second enrollment flow.
"""

import os

import frappe
import frappe.sessions

no_cache = 1
base_template_path = ""

_BUILT_HTML = ("public", "frontend", "facility-onboarding.html")


def get_context(context):
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
