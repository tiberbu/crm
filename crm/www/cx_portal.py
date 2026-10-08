"""Authenticated Customer Experience portal shell."""

import os

import frappe
import frappe.sessions

from crm.api.website_redirect import get_portal_route

no_cache = 1
base_template_path = ""
_BUILT_HTML = ("public", "frontend", "cx-portal.html")


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/cx-portal"
		raise frappe.Redirect

	if not get_portal_route():
		frappe.local.flags.redirect_location = "/access-restricted?resource=portal"
		raise frappe.Redirect

	context.csrf_token = frappe.sessions.get_csrf_token()
	context.portal_head = _asset_head()
	return context


def _asset_head():
	path = os.path.join(frappe.get_app_path("crm"), *_BUILT_HTML)
	try:
		# nosemgrep: frappe-security-file-traversal -- path is assembled only from a fixed asset tuple and the CRM app path; no request value is used.
		with open(path, encoding="utf-8") as stream:
			lines = stream.readlines()
	except OSError:
		frappe.log_error("Customer Experience shell: built asset HTML not found at " + path)
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
