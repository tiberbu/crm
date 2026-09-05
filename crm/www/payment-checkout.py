"""Guest invoice checkout shell for OIS signatories."""

import os

import frappe
import frappe.sessions

no_cache = 1
base_template_path = ""
_BUILT_HTML = ("public", "frontend", "payment-checkout.html")


def get_context(context):
	context.checkout_ois = frappe.form_dict.get("ois") or ""
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.checkout_head = _asset_head()
	return context


def _asset_head():
	path = os.path.join(frappe.get_app_path("crm"), *_BUILT_HTML)
	try:
		with open(path, encoding="utf-8") as stream:
			lines = stream.readlines()
	except OSError:
		frappe.log_error("checkout shell: built asset HTML not found at " + path)
		return ""
	kept = []
	for line in lines:
		tag = line.strip()
		if any(skip in tag for skip in ("registerSW", "vite-plugin-pwa", 'rel="manifest"')):
			continue
		if tag.startswith('<script type="module"') or tag.startswith('<link rel="modulepreload"') or tag.startswith('<link rel="stylesheet"'):
			kept.append(tag)
	return "\n    ".join(kept)
