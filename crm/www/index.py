"""Public CareverseHIMS Value Express landing page.

Guests see the Value Express sales page; logged-in users are routed to the
experience permitted for their account.

Root-resolution note: `home_page = "index"` alone is NOT enough — Frappe's
`get_home_page()` still resolves '/' to a System User's `default_workspace`
(`/desk/<workspace>`) before this page runs. The `pin_home_page_to_landing`
`before_request` hook (crm/api/route_guard.py) forces '/' -> index on every request so
this redirect actually runs for workspace-having users, closing a desk-fence bypass.
"""

import hashlib
import os
from functools import lru_cache

import frappe
from frappe import _

from crm.api.landing import CONTACT_TOPICS, get_landing_settings, get_value_express_offer
from crm.api.website_redirect import get_portal_route
from crm.branding import apply_brand_context, get_configured_app_brand

no_cache = True

ONBOARDING = "/facility-onboarding"


CSS_FILES = ("value-express.css", "value-express-landing.css")


def _css_version() -> str:
	"""A content hash for the stylesheet links: the CDN caches /assets for a year, so a changed
	file needs a new URL to reach visitors. Keyed on the files' mtimes so an edit is picked up
	without restarting the workers."""
	paths = tuple(frappe.get_app_path("crm", "public", "css", name) for name in CSS_FILES)
	return _css_digest(tuple((path, os.stat(path).st_mtime_ns) for path in paths))


@lru_cache(maxsize=4)
def _css_digest(stamps: tuple) -> str:
	digest = hashlib.sha256()
	for path, _mtime in stamps:
		with open(path, "rb") as css:
			digest.update(css.read())
	return digest.hexdigest()[:10]


def _amount(value) -> str:
	return "{:,.0f}".format(float(value or 0))


def get_context(context):
	# Logged-in users belong in the app, not on the marketing splash.
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = get_portal_route() or "/crm"
		raise frappe.Redirect

	brand = get_configured_app_brand()
	context.no_cache = 1
	context.no_header = True
	context.no_breadcrumbs = True
	context.title = _("CareverseHIMS Value Express: get digital, get SHA ready")
	apply_brand_context(context, brand, surface="splash")

	context.onboarding_url = ONBOARDING
	context.signin_link = "/login?redirect-to=/cx-portal"
	context.landing = get_landing_settings()
	context.contact_topics = CONTACT_TOPICS
	context.amount = _amount
	context.css_version = _css_version()
	try:
		context.offer = get_value_express_offer()
	except Exception:
		# Prices are a hint here; never let catalogue problems take the landing page down.
		frappe.log_error(title="Landing page Value Express offer")
		context.offer = {"flex": [], "fixed": [], "custom": None, "from_price": 0, "currency": "KES", "calculator": {}}
	return context
