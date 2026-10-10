"""Branded "Access Restricted" page for users blocked from Frappe Desk.

Rendered when the desk route guard (``crm.api.route_guard``) redirects a
non-allow-listed user away from ``/app`` / ``/desk``.

Route note: this ``.py`` file (underscore) pairs with ``access-restricted.html``
(hyphen). Frappe's ``www/`` auto-router serves the route from the HTML filename, so the
URL is ``/access-restricted`` — matching ``UNAUTHORIZED_ROUTE`` in the guard, and sharing
NO prefix with ``/app``/``/desk`` (redirect-loop safety).
"""

import frappe
from frappe import _

no_cache = True


RESOURCE_COPY = {
	"finance": {
		"eyebrow": _("Finance Workspace"),
		"title": _("Finance access is required"),
		"message": _(
			"This workspace is reserved for users with the Accounts User or Accounts Manager role."
		),
		"next_step": _(
			"Ask your administrator to assign Accounts User or Accounts Manager access, then sign in again."
		),
		"home_label": _("Return to CRM"),
		"home_route": "/crm",
		"resource_label": _("Finance Workspace"),
		"required_roles": _("Accounts User or Accounts Manager"),
	},
	"desk": {
		"eyebrow": _("Workspace access"),
		"title": _("Desk access is restricted"),
		"message": _(
			"Your account can use the CRM workspace, but it is not enabled for the internal Desk."
		),
		"next_step": _(
			"Use the CRM workspace or ask an administrator to add your account to the Desk access list."
		),
		"home_label": _("Open CRM"),
		"home_route": "/crm",
		"resource_label": _("Internal Desk"),
		"required_roles": _("An administrator-managed Desk access grant"),
	},
	"crm": {
		"eyebrow": _("CRM workspace"),
		"title": _("CRM access is restricted"),
		"message": _(
			"Your account is signed in, but it has not been provisioned for the CRM workspace."
		),
		"next_step": _("Ask your administrator to grant the appropriate CRM access."),
		"home_label": _("Sign out"),
		"home_route": "/logout",
		"resource_label": _("CRM"),
		"required_roles": _("A CRM application role"),
	},
	"portal": {
		"eyebrow": _("Customer Experience portal"),
		"title": _("Portal access is unavailable"),
		"message": _(
			"This account is not linked to an active Customer Experience portal profile."
		),
		"next_step": _("Contact the organization that invited you to confirm your portal access."),
		"home_label": _("Return to CRM"),
		"home_route": "/crm",
		"resource_label": _("Customer Experience portal"),
		"required_roles": _("An active portal invitation or profile"),
	},
}


def get_context(context):
	# Defense-in-depth: this page is only meaningful for a blocked, authenticated
	# non-admin. Redirect the two users who should never see it.
	user = frappe.session.user
	if user == "Administrator":
		# An admin is never blocked — send them to Desk.
		frappe.local.flags.redirect_location = "/app"
		raise frappe.Redirect
	if not user or user == "Guest":
		# Not authenticated yet — let them log in.
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	resource = str(frappe.form_dict.get("resource") or "desk").lower()
	copy = RESOURCE_COPY.get(resource, RESOURCE_COPY["desk"])
	context.resource = resource if resource in RESOURCE_COPY else "desk"
	context.resource_eyebrow = copy["eyebrow"]
	context.resource_title = copy["title"]
	context.resource_message = copy["message"]
	context.resource_next_step = copy["next_step"]
	context.resource_label = copy["resource_label"]
	context.required_roles = copy["required_roles"]
	context.home_label = copy["home_label"]
	context.home_route = copy["home_route"]
	context.signed_in_user = user
	try:
		context.user_roles = sorted(
			role for role in frappe.get_roles(user) if role not in {"All", "Guest"}
		)
	except Exception:
		context.user_roles = []

	context.no_cache = 1
	context.no_header = True
	context.no_breadcrumbs = True
	# CSRF token so the "Sign out" button can POST to the (POST-only) logout method.
	context.csrf_token = frappe.sessions.get_csrf_token()

	# Branding is optional — guard it so a brand-less copy still renders the page.
	try:
		from crm.branding import apply_brand_context, get_configured_app_brand

		brand = get_configured_app_brand()
		apply_brand_context(context, brand, surface="splash")
		context.title = f"{copy['title']} - {brand['app_name']}"
	except Exception:
		context.title = "Access Restricted"
		context.app_name = "Tiberbu CRM"
		context.brand_logo = "/assets/crm/images/tiberbu-mark.svg"
		context.brand_primary = "#bc1823"
		context.brand_primary_dark = "#8f111b"

	return context
