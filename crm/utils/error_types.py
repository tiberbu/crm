"""Shared exception aliases for Frappe classes that may be missing by release.

Single home for version-sensitive exception references. If a future Frappe
ships one of these classes, the alias picks it up automatically and the
error types follow Frappe's instead of the fallback below.
"""

from __future__ import annotations

import frappe

# frappe.ConfigurationError does not exist in the current Frappe release;
# configuration errors therefore surface as frappe.ValidationError.
ConfigurationError = getattr(frappe, "ConfigurationError", frappe.ValidationError)
