"""Public Tiberbu Customer Experience landing page.

Guests see the facility-owner welcome page; logged-in users are routed to the
experience permitted for their account.

Root-resolution note: `home_page = "index"` alone is NOT enough — Frappe's
`get_home_page()` still resolves '/' to a System User's `default_workspace`
(`/desk/<workspace>`) before this page runs. The `pin_home_page_to_landing`
`before_request` hook (crm/api/route_guard.py) forces '/' -> index on every request so
this redirect actually runs for workspace-having users, closing a desk-fence bypass.
"""

import frappe
from frappe import _

from crm.api.website_redirect import get_portal_route
from crm.branding import apply_brand_context, get_configured_app_brand

no_cache = True


def get_context(context):
	# Logged-in users belong in the app, not on the marketing splash.
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = get_portal_route() or "/crm"
		raise frappe.Redirect

	brand = get_configured_app_brand()
	context.no_cache = 1
	context.no_header = True
	context.no_breadcrumbs = True
	context.title = _("Tiberbu Customer Experience")
	apply_brand_context(context, brand, surface="splash")

	context.cta_text = "Start facility onboarding"
	context.cta_link = "/facility-onboarding"
	context.cta_secondary_text = "Already have access? Sign in"
	context.cta_secondary_link = "/login?redirect-to=/cx-portal"

	return context
