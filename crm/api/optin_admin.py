"""
crm/api/optin_admin.py — Internal admin API for Opt-In Network and Facility management.

RBAC:
  - System Manager / Sales Manager: full access to all networks and facilities.
  - Network Coordinator: read/write only for networks where they appear in the
    coordinators child table. Determined by _get_coordinator_networks(user).
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from typing import Any

import frappe
from frappe import _
from frappe.utils.jinja import get_jenv
from jinja2.exceptions import TemplateSyntaxError

_OPTIN_TERMS_EXPRESSIONS = {
	"network.display_name",
	"date",
	"contact.email",
	"pricing_table",
	"grand_total_monthly_display",
	"grand_total_annual_display",
}


def _is_admin(user=None):
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	return "System Manager" in roles or "Sales Manager" in roles or user == "Administrator"


def _get_coordinator_networks(user=None):
	"""Return list of network slugs where user is a coordinator. Empty = no access."""
	user = user or frappe.session.user
	rows = frappe.get_list(
		"CRM Network Coordinator",
		filters={"user": user, "parenttype": "CRM Opt-In Network"},
		fields=["parent"],
		ignore_permissions=True,  # SYSTEM-INTERNAL
	)
	return [r.parent for r in rows]


def _assert_network_access(network_slug):
	"""Raise PermissionError if current user has no access to this network."""
	if _is_admin():
		return
	allowed = _get_coordinator_networks()
	if network_slug not in allowed:
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _validate_opted_in_price_list_override(existing_membership, requested_override):
	"""Keep facility pricing immutable once its membership has opted in.

	The contact editor omits the override for opted-in facilities, but this guard
	also protects older clients and direct API callers from changing the effective
	price list outside the quotation workflow.
	"""
	if not existing_membership or existing_membership.get("status") != "Opted In":
		return

	existing_override = frappe.utils.cstr(existing_membership.get("price_list_override") or "").strip()
	requested_override = frappe.utils.cstr(requested_override or "").strip()
	if requested_override != existing_override:
		frappe.throw(
			_(
				"The facility price list is locked after Opt-In. Update pricing from the quotation before the facility signs."
			),
			frappe.ValidationError,
		)


def _require_optin_settings_manager():
	"""Only system administrators may change the global Opt-In agreement."""
	if (
		"System Manager" not in frappe.get_roles(frappe.session.user)
		and frappe.session.user != "Administrator"
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _normalize_optin_terms_template(terms):
	"""Keep the supported dynamic values while preserving other braces as legal text."""

	def replace_expression(match):
		expression = match.group(1).strip()
		if expression in _OPTIN_TERMS_EXPRESSIONS:
			return "{{ %s }}" % expression
		return "&#123;&#123;%s&#125;&#125;" % match.group(1)

	terms = re.sub(r"{{(.*?)}}", replace_expression, terms, flags=re.DOTALL)
	terms = re.sub(
		r"{%(.*?)%}",
		lambda match: "&#123;&#37;%s&#37;&#125;" % match.group(1),
		terms,
		flags=re.DOTALL,
	)
	terms = re.sub(
		r"{#(.*?)#}",
		lambda match: "&#123;&#35;%s&#35;&#125;" % match.group(1),
		terms,
		flags=re.DOTALL,
	)
	return terms


# ---------------------------------------------------------------------------
# Network CRUD
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_networks(
	page: Any = 0,
	page_size: Any = 20,
	search: Any = None,
	enabled: Any = None,
	opted_in: Any = None,
	facility_level: Any = None,
	facility: Any = None,
):
	"""Return permission-scoped Opt-In Networks with contact counts and filters."""
	page = max(int(page or 0), 0)
	page_size = min(max(int(page_size or 20), 1), 100)

	if _is_admin() or frappe.has_permission("CRM Opt-In Network", "read"):
		filters = {}
	else:
		allowed = _get_coordinator_networks()
		if not allowed:
			return {"rows": [], "total": 0}
		filters = {"name": ["in", allowed]}

	enabled = frappe.utils.cstr(enabled).strip()
	if enabled in ("0", "1"):
		filters["enabled"] = frappe.utils.cint(enabled)

	# Opt-in status is derived from membership rows, not the network's enabled
	# flag. Keep this filter separate so a configured-but-unused network is
	# clearly distinguishable from one with at least one completed submission.
	opted_in = frappe.utils.cstr(opted_in).strip()
	if opted_in in ("0", "1"):
		opted_memberships = frappe.get_list(
			"CRM Facility Membership",
			filters={
				"parenttype": "CRM Pre-Qualified Facility",
				"status": "Opted In",
			},
			fields=["network"],
			limit_page_length=0,
			ignore_permissions=True,  # SYSTEM-INTERNAL: resolves status filter
		)
		opted_networks = {row.network for row in opted_memberships if row.network}
		all_networks = frappe.get_list(
			"CRM Opt-In Network",
			filters=filters,
			fields=["name"],
			limit_page_length=0,
		)
		candidate_names = {row.name for row in all_networks}
		matching_names = (
			candidate_names & opted_networks if opted_in == "1" else candidate_names - opted_networks
		)
		if not matching_names:
			return {"rows": [], "total": 0}
		filters["name"] = ["in", list(matching_names)]

	facility_level = frappe.utils.cstr(facility_level).strip()
	facility = frappe.utils.cstr(facility).strip()
	if facility_level or facility:
		facility_filters = {}
		if facility_level:
			facility_filters["keph_level"] = facility_level
		facility_or_filters = None
		if facility:
			facility_like = "%%%s%%" % facility
			facility_or_filters = [
				["facility_name", "like", facility_like],
				["mfl_code", "like", facility_like],
				["organization", "like", facility_like],
			]
		facilities = frappe.get_list(
			"CRM Pre-Qualified Facility",
			filters=facility_filters,
			or_filters=facility_or_filters,
			fields=["name"],
			limit_page_length=0,
			ignore_permissions=True,  # SYSTEM-INTERNAL: only resolves filter scope
		)
		if not facilities:
			return {"rows": [], "total": 0}
		memberships = frappe.get_list(
			"CRM Facility Membership",
			filters={
				"parenttype": "CRM Pre-Qualified Facility",
				"parent": ["in", [row.name for row in facilities]],
			},
			fields=["network"],
			limit_page_length=0,
			ignore_permissions=True,  # SYSTEM-INTERNAL: only resolves filter scope
		)
		matching_networks = {row.network for row in memberships if row.network}
		if not matching_networks:
			return {"rows": [], "total": 0}
		if filters.get("name"):
			matching_networks &= set(filters["name"][1])
		if not matching_networks:
			return {"rows": [], "total": 0}
		filters["name"] = ["in", list(matching_networks)]

	search = frappe.utils.cstr(search).strip()
	search_or_filters = None
	if search:
		search_like = "%%%s%%" % search
		search_or_filters = [
			["display_name", "like", search_like],
			["slug", "like", search_like],
			["contact_email", "like", search_like],
		]

	rows = frappe.get_list(
		"CRM Opt-In Network",
		filters=filters,
		fields=[
			"name",
			"slug",
			"display_name",
			"enabled",
			"contact_email",
			"footer_legal_name",
			"logo_url",
			"primary_colour",
			"price_list_override",
		],
		or_filters=search_or_filters,
		order_by="display_name asc",
		limit_start=page * page_size,
		limit_page_length=page_size,
	)
	network_names = [row.name for row in rows]
	contact_counts = {}
	contact_memberships = []
	if network_names:
		contact_memberships = frappe.get_list(
			"CRM Facility Membership",
			filters={
				"parenttype": "CRM Pre-Qualified Facility",
				"network": ["in", network_names],
			},
			fields=["network", "status"],
			limit_page_length=0,
			ignore_permissions=True,  # SYSTEM-INTERNAL: only counts visible networks
		)
		for membership in contact_memberships:
			contact_counts[membership.network] = contact_counts.get(membership.network, 0) + 1
	opted_in_counts = {}
	for membership in contact_memberships:
		if membership.get("status") == "Opted In":
			opted_in_counts[membership.network] = opted_in_counts.get(membership.network, 0) + 1
	for row in rows:
		row["contact_count"] = contact_counts.get(row.name, 0)
		row["opted_in_count"] = opted_in_counts.get(row.name, 0)
		row["opted_in"] = bool(row["opted_in_count"])
		row["optin_status"] = "Opted In" if row["opted_in"] else "Not Opted In"

	total = len(
		frappe.get_list(
			"CRM Opt-In Network",
			filters=filters,
			or_filters=search_or_filters,
			fields=["name"],
			limit_page_length=0,
		)
	)
	return {"rows": rows, "total": total}


@frappe.whitelist()
def save_network(data: Any):
	"""Create or update a CRM Opt-In Network. data is a JSON-serialisable dict."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if isinstance(data, str):
		data = json.loads(data)

	price_list_override = frappe.utils.cstr(data.get("price_list_override") or "").strip()
	if price_list_override and not frappe.db.exists(
		"Price List", {"name": price_list_override, "selling": 1, "enabled": 1}
	):
		frappe.throw(_("Select an enabled selling price list."))
	data["price_list_override"] = price_list_override

	name = data.get("name")
	if name and frappe.db.exists("CRM Opt-In Network", name):
		doc = frappe.get_doc("CRM Opt-In Network", name)
	else:
		doc = frappe.new_doc("CRM Opt-In Network")

	for field in (
		"slug",
		"display_name",
		"enabled",
		"contact_email",
		"footer_legal_name",
		"logo_url",
		"primary_colour",
		"price_list_override",
		"custom_header_copy",
	):
		if field in data:
			setattr(doc, field, data[field])

	child_fields = {
		"partner_logos": ("partner_name", "logo", "website"),
		"coordinators": ("user",),
		"network_signers": ("full_name", "email", "phone"),
	}
	for fieldname, allowed_fields in child_fields.items():
		if fieldname in data:
			rows = data[fieldname] or []
			if not isinstance(rows, list):
				frappe.throw(_("{0} must be a list.").format(fieldname))
			if any(not isinstance(row, dict) for row in rows):
				frappe.throw(_("{0} contains an invalid row.").format(fieldname))
			if fieldname == "network_signers":
				signer_emails = [frappe.utils.cstr(row.get("email") or "").strip().lower() for row in rows]
				if any(not email for email in signer_emails):
					frappe.throw(_("Every network signatory must have an email address."))
				if len(signer_emails) != len(set(signer_emails)):
					frappe.throw(_("Each network signatory email must be unique."))
			doc.set(
				fieldname,
				[
					{field: frappe.utils.cstr(row.get(field) or "").strip() for field in allowed_fields}
					for row in rows
				],
			)

	doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()
	return {"name": doc.name}


@frappe.whitelist()
def delete_network(name: Any):
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	name = frappe.utils.cstr(name)
	# Check no facilities reference this network
	count = len(
		frappe.get_list(
			"CRM Facility Membership",
			filters={"network": name, "parenttype": "CRM Pre-Qualified Facility"},
			fields=["name"],
			limit_page_length=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
	)
	if count:
		frappe.throw(_("Cannot delete network: facilities are assigned to it. Remove all memberships first."))
	frappe.delete_doc("CRM Opt-In Network", name, ignore_permissions=True)
	frappe.db.commit()
	return {"deleted": name}


# ---------------------------------------------------------------------------
# Opt-In terms and conditions
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_optin_terms():
	"""List agreements that can be selected as the Opt-In default."""
	_require_optin_settings_manager()
	active = frappe.db.get_single_value("CRM Opt-In Settings", "active_tc_document") or ""
	rows = frappe.get_list(
		"Terms and Conditions",
		fields=["name", "title", "modified"],
		order_by="modified desc",
		limit_page_length=0,
	)
	return {
		"active": active,
		"rows": [
			{
				"name": row.name,
				"title": row.title or row.name,
				"modified": row.modified,
				"active": row.name == active,
			}
			for row in rows
		],
	}


@frappe.whitelist()
def get_optin_terms(name: Any):
	_require_optin_settings_manager()
	doc = frappe.get_doc("Terms and Conditions", frappe.utils.cstr(name).strip())
	return {"name": doc.name, "title": doc.title, "terms": doc.terms or ""}


@frappe.whitelist()
def save_optin_terms(name: Any = None, title: Any = None, terms: Any = None):
	"""Create or update an Opt-In agreement and return its document name."""
	_require_optin_settings_manager()
	title = frappe.utils.cstr(title).strip()
	terms = frappe.utils.cstr(terms)
	if not title:
		frappe.throw(_("A document title is required."))
	if not terms.strip():
		frappe.throw(_("Terms and Conditions content is required."))

	original_terms = terms
	terms = _normalize_optin_terms_template(terms)
	try:
		get_jenv(restrict_globals=True).from_string(terms)
	except TemplateSyntaxError as error:
		frappe.throw(
			_("Could not save the agreement because a template delimiter is incomplete on line {0}.").format(
				error.lineno or 1
			)
		)

	name = frappe.utils.cstr(name).strip()
	if name:
		doc = frappe.get_doc("Terms and Conditions", name)
		doc.title = title
		doc.terms = terms
		doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	else:
		doc = frappe.get_doc(
			{"doctype": "Terms and Conditions", "title": title, "selling": 1, "terms": terms}
		)
		doc.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()
	return {"name": doc.name, "terms": terms, "normalized": terms != original_terms}


@frappe.whitelist()
def set_default_optin_terms(name: Any):
	"""Set the agreement that every new Opt-In submission must render and accept."""
	_require_optin_settings_manager()
	name = frappe.utils.cstr(name).strip()
	if not frappe.db.exists("Terms and Conditions", name):
		frappe.throw(_("Terms and Conditions document not found."))
	settings = frappe.get_single("CRM Opt-In Settings")
	settings.active_tc_document = name
	settings.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()
	return {"name": name}


@frappe.whitelist()
def get_optin_settings():
	"""Return non-secret global configuration used by the Opt-In process."""
	_require_optin_settings_manager()
	settings = frappe.get_single("CRM Opt-In Settings")
	return {
		"default_price_list": settings.default_price_list or "",
		"sales_tax_template": settings.sales_tax_template or "",
		"active_tc_document": settings.active_tc_document or "",
		"default_lead_owner": settings.default_lead_owner or "",
		"tiberbu_signatory": settings.tiberbu_signatory or "",
		"tiberbu_signatory_name": settings.get("tiberbu_signatory_name") or "",
		"tiberbu_signatory_email": settings.get("tiberbu_signatory_email") or "",
		"tiberbu_signatory_phone": settings.get("tiberbu_signatory_phone") or "",
		"tiberbu_approver_name": settings.get("tiberbu_approver_name") or "",
		"tiberbu_approver_email": settings.get("tiberbu_approver_email") or "",
		"tiberbu_approver_phone": settings.get("tiberbu_approver_phone") or "",
		"tiberbu_signing_requirement": settings.get("tiberbu_signing_requirement") or "All must sign",
		"tiberbu_contacts": [
			{
				"role": frappe.utils.cstr(row.get("role") or "").strip(),
				"full_name": frappe.utils.cstr(row.get("full_name") or "").strip(),
				"email": frappe.utils.cstr(row.get("email") or "").strip().lower(),
				"phone": frappe.utils.cstr(row.get("phone") or "").strip(),
			}
			for row in (settings.get("tiberbu_contacts") or [])
		],
	}


@frappe.whitelist()
def update_optin_settings(settings: Any):
	"""Update the non-secret global defaults for all new Opt-In submissions."""
	_require_optin_settings_manager()
	if isinstance(settings, str):
		settings = json.loads(settings)

	default_price_list = frappe.utils.cstr(settings.get("default_price_list")).strip()
	sales_tax_template = frappe.utils.cstr(settings.get("sales_tax_template")).strip()
	active_tc_document = frappe.utils.cstr(settings.get("active_tc_document")).strip()
	default_lead_owner = frappe.utils.cstr(settings.get("default_lead_owner")).strip()
	tiberbu_signatory = frappe.utils.cstr(settings.get("tiberbu_signatory")).strip()
	tiberbu_signatory_name = frappe.utils.cstr(settings.get("tiberbu_signatory_name")).strip()
	tiberbu_signatory_email = frappe.utils.cstr(settings.get("tiberbu_signatory_email")).strip().lower()
	tiberbu_signatory_phone = frappe.utils.cstr(settings.get("tiberbu_signatory_phone")).strip()
	tiberbu_approver_name = frappe.utils.cstr(settings.get("tiberbu_approver_name")).strip()
	tiberbu_approver_email = frappe.utils.cstr(settings.get("tiberbu_approver_email")).strip().lower()
	tiberbu_approver_phone = frappe.utils.cstr(settings.get("tiberbu_approver_phone")).strip()
	tiberbu_signing_requirement = frappe.utils.cstr(
		settings.get("tiberbu_signing_requirement") or "All must sign"
	).strip()
	if tiberbu_signing_requirement not in ("All must sign", "At least one must sign"):
		frappe.throw(_("Choose whether all Tiberbu signatories or at least one must sign."))
	tiberbu_contacts = settings.get("tiberbu_contacts")
	if tiberbu_contacts is not None:
		if not isinstance(tiberbu_contacts, list) or any(
			not isinstance(row, dict) for row in tiberbu_contacts
		):
			frappe.throw(_("Tiberbu contacts must be a list of contact rows."))
		normalized_contacts = []
		seen_contacts = set()
		for row in tiberbu_contacts:
			role = frappe.utils.cstr(row.get("role") or "").strip().title()
			name = frappe.utils.cstr(row.get("full_name") or "").strip()
			email = frappe.utils.cstr(row.get("email") or "").strip().lower()
			phone = frappe.utils.cstr(row.get("phone") or "").strip()
			if role not in ("Signatory", "Approver") or not name or not email:
				frappe.throw(_("Each Tiberbu contact needs a role, name, and email."))
			key = (role, email)
			if key in seen_contacts:
				frappe.throw(_("Each Tiberbu contact email must be unique within its role."))
			seen_contacts.add(key)
			normalized_contacts.append({"role": role, "full_name": name, "email": email, "phone": phone})
	else:
		normalized_contacts = None

	if default_price_list and not frappe.db.exists(
		"Price List", {"name": default_price_list, "selling": 1, "enabled": 1}
	):
		frappe.throw(_("Select an enabled selling price list."))
	if sales_tax_template:
		from crm.utils.quotation_tax import get_vat_tax_configuration

		get_vat_tax_configuration(tax_template=sales_tax_template)
	if active_tc_document and not frappe.db.exists("Terms and Conditions", active_tc_document):
		frappe.throw(_("Terms and Conditions document not found."))
	for field, user in (("Default Lead Owner", default_lead_owner), ("Tiberbu Signatory", tiberbu_signatory)):
		if user and not frappe.db.exists("User", {"name": user, "enabled": 1}):
			frappe.throw(_("{0} must be an enabled user.").format(field))
	if any((tiberbu_signatory_name, tiberbu_signatory_email, tiberbu_signatory_phone)) and not all(
		(tiberbu_signatory_name, tiberbu_signatory_email)
	):
		frappe.throw(_("Default Tiberbu signatory name and email are required when using a contact."))
	if any((tiberbu_approver_name, tiberbu_approver_email, tiberbu_approver_phone)) and not all(
		(tiberbu_approver_name, tiberbu_approver_email, tiberbu_approver_phone)
	):
		frappe.throw(
			_("Tiberbu Approver name, email, and phone are required for dual-channel notifications.")
		)

	doc = frappe.get_single("CRM Opt-In Settings")
	doc.default_price_list = default_price_list
	doc.sales_tax_template = sales_tax_template
	doc.active_tc_document = active_tc_document
	doc.default_lead_owner = default_lead_owner
	doc.tiberbu_signatory = tiberbu_signatory
	doc.tiberbu_signatory_name = tiberbu_signatory_name
	doc.tiberbu_signatory_email = tiberbu_signatory_email
	doc.tiberbu_signatory_phone = tiberbu_signatory_phone
	doc.tiberbu_approver_name = tiberbu_approver_name
	doc.tiberbu_approver_email = tiberbu_approver_email
	doc.tiberbu_approver_phone = tiberbu_approver_phone
	doc.tiberbu_signing_requirement = tiberbu_signing_requirement
	if normalized_contacts is not None and frappe.get_meta("CRM Opt-In Settings").has_field(
		"tiberbu_contacts"
	):
		doc.set("tiberbu_contacts", normalized_contacts)
	doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()


@frappe.whitelist()
def list_optin_tax_templates():
	"""List the enabled company VAT templates available to Opt-In Settings."""
	_require_optin_settings_manager()
	from crm.utils.quotation_tax import list_company_tax_templates

	return [{"value": row.name, "label": row.name} for row in list_company_tax_templates()]


# ---------------------------------------------------------------------------
# Negotiated price lists and item prices
# ---------------------------------------------------------------------------


def _is_standard_selling_price_list(name):
	"""Return whether ``name`` is ERPNext's generic selling list."""
	return frappe.utils.cstr(name or "").strip().casefold() == "standard selling"


def _get_negotiated_price_list(name):
	name = frappe.utils.cstr(name).strip()
	if not name:
		frappe.throw(_("A price list is required."))
	price_list = frappe.get_doc("Price List", name)
	if _is_standard_selling_price_list(price_list.name) or not price_list.selling or not price_list.enabled:
		frappe.throw(_("Select an enabled selling price list other than Standard Selling."))
	return price_list


def _price_list_assignments():
	"""Return effective price-list assignments for network facility memberships."""
	membership_fields = ["parent", "network"]
	try:
		if frappe.db.has_column("CRM Facility Membership", "price_list_override"):
			membership_fields.append("price_list_override")
	except Exception:
		pass
	memberships = frappe.get_list(
		"CRM Facility Membership",
		filters={"parenttype": "CRM Pre-Qualified Facility"},
		fields=membership_fields,
		limit_page_length=0,
		ignore_permissions=True,  # SYSTEM-INTERNAL: scope metadata for managers
	)
	networks = frappe.get_list(
		"CRM Opt-In Network",
		fields=["name", "slug", "price_list_override"],
		limit_page_length=0,
		ignore_permissions=True,  # SYSTEM-INTERNAL: scope metadata for managers
	)
	network_lists = {
		network.name: {
			"slug": network.get("slug") or network.name,
			"price_list": network.get("price_list_override") or "",
		}
		for network in networks
	}
	default_price_list = (
		frappe.db.get_single_value("CRM Opt-In Settings", "default_price_list") or "Negotiated Year 1"
	)
	assignments = {}
	for membership in memberships:
		network = network_lists.get(membership.network, {})
		price_list = membership.get("price_list_override") or network.get("price_list") or default_price_list
		if not price_list or not membership.parent:
			continue
		assignment = assignments.setdefault(
			price_list,
			{"facilities": set(), "networks": set(), "facility_networks": set()},
		)
		assignment["facilities"].add(membership.parent)
		assignment["networks"].add(network.get("slug") or membership.network)
		assignment["facility_networks"].add((membership.parent, network.get("slug") or membership.network))
	return assignments


@frappe.whitelist()
def list_negotiated_price_lists():
	"""Return enabled Opt-In selling price lists for configuration."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows = frappe.get_list(
		"Price List",
		filters=[
			["selling", "=", 1],
			["enabled", "=", 1],
			["name", "!=", "Standard Selling"],
		],
		fields=["name", "currency", "creation", "modified", "owner", "modified_by"],
		order_by="name asc",
		limit_page_length=0,
	)
	# Keep the exclusion case-insensitive even on sites whose database collation
	# treats the ``!=`` filter as case-sensitive.
	rows = [row for row in rows if not _is_standard_selling_price_list(row.name)]

	assignments = _price_list_assignments()

	return [
		{
			"value": row.name,
			"label": row.name,
			"currency": row.currency,
			"creation": row.creation,
			"modified": row.modified,
			"owner": row.owner,
			"modified_by": row.modified_by,
			"facility_count": len(assignments.get(row.name, {}).get("facilities", set())),
			"network_count": len(assignments.get(row.name, {}).get("networks", set())),
		}
		for row in rows
	]


@frappe.whitelist()
def list_price_list_facilities(price_list: Any, page: Any = None, page_length: Any = None):
	"""Return facilities using a negotiated list, including their network scope.

	The original no-pagination response remains a list for existing callers. New
	callers can pass ``page``/``page_length`` to receive a bounded page and total,
	which keeps large catalogue views responsive without changing the data scope.
	"""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	price_list = _get_negotiated_price_list(price_list)
	assignment = _price_list_assignments().get(price_list.name, {})
	pairs = assignment.get("facility_networks", set())
	if not pairs:
		return []
	facility_names = {facility for facility, _network in pairs}
	facilities = {
		row.name: row
		for row in frappe.get_list(
			"CRM Pre-Qualified Facility",
			filters={"name": ["in", list(facility_names)]},
			fields=["name", "facility_name", "organization", "mfl_code", "keph_level"],
			limit_page_length=0,
			ignore_permissions=True,  # SYSTEM-INTERNAL: manager catalogue scope
		)
	}
	rows = [
		{
			"name": facility_name,
			"facility_name": facilities[facility_name].facility_name,
			"organization": facilities[facility_name].organization or facilities[facility_name].facility_name,
			"mfl_code": facilities[facility_name].mfl_code,
			"keph_level": facilities[facility_name].keph_level,
			"network": network,
			"price_list": price_list.name,
		}
		for facility_name, network in sorted(
			pairs,
			key=lambda pair: (
				facilities.get(pair[0], {}).get("facility_name", pair[0]),
				pair[1],
			),
		)
		if facility_name in facilities
	]
	if page is None and page_length is None:
		return rows

	page = max(frappe.utils.cint(page) or 1, 1)
	page_length = min(max(frappe.utils.cint(page_length) or 50, 1), 100)
	start = (page - 1) * page_length
	end = start + page_length
	return {
		"rows": rows[start:end],
		"total": len(rows),
		"page": page,
		"page_length": page_length,
		"has_more": end < len(rows),
	}


@frappe.whitelist()
def get_facility_sample_quote(facility: Any, network: Any = None, price_list: Any = None):
	"""Return a non-persisted quotation preview for a facility and price list."""
	facility = frappe.utils.cstr(facility).strip()
	network = frappe.utils.cstr(network).strip()
	if not facility:
		frappe.throw(_("A facility is required."))
	if not _is_admin() and network:
		_assert_network_access(network)
	if not _is_admin() and not network:
		frappe.throw(_("A network is required."), frappe.PermissionError)

	facility_doc = frappe.get_doc("CRM Pre-Qualified Facility", facility)
	membership = next(
		(member for member in facility_doc.memberships or [] if not network or member.network == network),
		None,
	)
	if not membership:
		frappe.throw(_("This facility is not attached to the selected network."))

	network_doc = None
	if network:
		network_rows = frappe.get_list(
			"CRM Opt-In Network",
			filters={"slug": network, "enabled": 1},
			fields=["name", "slug", "display_name", "price_list_override"],
			limit_page_length=1,
			ignore_permissions=True,  # SYSTEM-INTERNAL: access was checked above
		)
		if not network_rows:
			frappe.throw(_("Network not found."))
		network_doc = network_rows[0]

	settings_default = frappe.db.get_single_value("CRM Opt-In Settings", "default_price_list")
	selected_price_list = (
		frappe.utils.cstr(price_list).strip()
		or membership.get("price_list_override")
		or (network_doc.get("price_list_override") if network_doc else "")
		or settings_default
		or "Negotiated Year 1"
	)
	if not frappe.db.exists("Price List", {"name": selected_price_list, "selling": 1, "enabled": 1}):
		frappe.throw(_("The selected price list is not enabled."))

	from crm.api.optin import _keph_to_item_code
	from crm.api.quotes import _get_item_price
	from crm.utils.quotation_tax import calculate_vat_totals

	item_code = _keph_to_item_code(facility_doc.keph_level)
	monthly_net = _get_item_price(item_code, selected_price_list)
	monthly_totals = calculate_vat_totals(monthly_net)
	annual_net = round(monthly_net * 12, 2)
	annual_totals = calculate_vat_totals(annual_net)
	return {
		"facility": facility_doc.facility_name,
		"organization": facility_doc.organization or facility_doc.facility_name,
		"mfl_code": facility_doc.mfl_code,
		"keph_level": facility_doc.keph_level,
		"network": network_doc.display_name if network_doc else network,
		"price_list": selected_price_list,
		"item_code": item_code,
		"item_name": frappe.db.get_value("Item", item_code, "item_name") or item_code,
		"monthly_net": monthly_totals.net_total,
		"monthly_vat": monthly_totals.vat_amount,
		"monthly_gross": monthly_totals.grand_total,
		"annual_net": annual_totals.net_total,
		"annual_vat": annual_totals.vat_amount,
		"annual_gross": annual_totals.grand_total,
		"vat_rate": monthly_totals.vat_rate,
		"vat_label": monthly_totals.vat_label,
	}


@frappe.whitelist()
def list_item_prices(price_list: Any):
	"""Return all selling item prices configured on a negotiated price list."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	price_list = _get_negotiated_price_list(price_list)
	return frappe.get_list(
		"Item Price",
		filters={"price_list": price_list.name, "selling": 1},
		fields=["name", "item_code", "item_name", "uom", "currency", "price_list_rate"],
		order_by="item_code asc",
		limit_page_length=0,
	)


def _log_price_list_event(price_list: str, content: str) -> None:
	"""Write a price-list audit comment in the same transaction as the change."""
	if not price_list or not content:
		return
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "Price List",
			"reference_name": price_list,
			"content": content,
		}
	).insert(ignore_permissions=True)  # SYSTEM-INTERNAL: manager catalogue audit


@frappe.whitelist()
def update_item_price(price_list: Any, item_price: Any, target_price_list: Any = None, rate: Any = None):
	"""Move or remove an Item Price from the selected negotiated list.

	An empty target removes the Item Price. A non-empty target moves it to another
	enabled negotiated selling list. Both operations are audited and committed as
	one transaction; a failed audit leaves the price unchanged.
	"""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	source = _get_negotiated_price_list(price_list)
	item_price_name = frappe.utils.cstr(item_price or "").strip()
	if not item_price_name:
		frappe.throw(_("An item price is required."))

	item_price_doc = frappe.get_doc("Item Price", item_price_name)
	if item_price_doc.price_list != source.name or not frappe.utils.cint(item_price_doc.selling):
		frappe.throw(_("This item price is not part of the selected price list."))

	target_name = frappe.utils.cstr(target_price_list or "").strip()
	if target_name == source.name:
		frappe.throw(_("Choose another price list or Remove from this list."))

	if not target_name:
		frappe.delete_doc("Item Price", item_price_name, ignore_permissions=True)
		_log_price_list_event(
			source.name,
			_("Removed item price %(item)s from %(price_list)s.")
			% {"item": item_price_doc.item_code, "price_list": source.name},
		)
		frappe.db.commit()
		return {
			"action": "removed",
			"item_price": item_price_name,
			"source": source.name,
		}

	target = _get_negotiated_price_list(target_name)
	duplicate = frappe.db.exists(
		"Item Price",
		{"price_list": target.name, "item_code": item_price_doc.item_code, "selling": 1},
	)
	if duplicate and duplicate != item_price_name:
		frappe.throw(
			_("An item price for %(item)s already exists in %(price_list)s.")
			% {"item": item_price_doc.item_code, "price_list": target.name}
		)

	if rate is not None and rate != "":
		try:
			rate = float(rate)
		except (TypeError, ValueError):
			frappe.throw(_("Enter a valid price."))
		if not math.isfinite(rate) or rate < 0:
			frappe.throw(_("Enter a non-negative finite price."))
		item_price_doc.price_list_rate = rate

	previous = source.name
	item_price_doc.price_list = target.name
	item_price_doc.currency = target.currency or item_price_doc.currency or "KES"
	item_price_doc.save(ignore_permissions=True)
	_log_price_list_event(
		previous,
		_("Moved item price %(item)s to %(price_list)s.")
		% {"item": item_price_doc.item_code, "price_list": target.name},
	)
	_log_price_list_event(
		target.name,
		_("Added item price %(item)s from %(price_list)s.")
		% {"item": item_price_doc.item_code, "price_list": previous},
	)
	frappe.db.commit()
	return {
		"action": "moved",
		"item_price": item_price_name,
		"source": previous,
		"target": target.name,
	}


@frappe.whitelist()
def list_sellable_items(search: Any = None):
	"""Return CRM-selectable ERPNext service items for negotiated pricing."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters = {"disabled": 0, "is_sales_item": 1}
	if search:
		filters["item_name"] = ["like", "%%%s%%" % frappe.utils.cstr(search).strip()]
	return frappe.get_list(
		"Item",
		filters=filters,
		fields=["name as value", "item_name", "stock_uom"],
		order_by="item_name asc",
		limit_page_length=200,
	)


@frappe.whitelist()
def create_sellable_item(item_code: Any, item_name: Any, stock_uom: Any = "Nos"):
	"""Create a sales item from the Opt-In catalogue without exposing ERPNext CRUD."""
	if not _is_admin():
		frappe.throw("Not permitted", frappe.PermissionError)
	item_code = frappe.utils.cstr(item_code or "").strip()
	item_name = frappe.utils.cstr(item_name or "").strip()
	stock_uom = frappe.utils.cstr(stock_uom or "Nos").strip() or "Nos"
	if not item_code or not item_name:
		frappe.throw("Item code and item name are required.")
	if frappe.db.exists("Item", item_code):
		frappe.throw("An item with this code already exists.")

	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_group": "Services",
			"stock_uom": stock_uom,
			"is_sales_item": 1,
			"is_stock_item": 0,
		}
	)
	item.insert(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()
	return {"value": item.name, "item_name": item.item_name, "stock_uom": item.stock_uom}


@frappe.whitelist()
def create_negotiated_price_list(name: Any):
	"""Create an empty, KES-denominated Opt-In selling price list."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	name = frappe.utils.cstr(name).strip()
	if _is_standard_selling_price_list(name):
		frappe.throw(_("Standard Selling is reserved for ERPNext defaults. Choose another name."))
	if frappe.db.exists("Price List", name):
		frappe.throw(_("A price list with this name already exists."))
	price_list = frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": name,
			"currency": "KES",
			"selling": 1,
			"buying": 0,
			"enabled": 1,
		}
	)
	price_list.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"name": price_list.name}


@frappe.whitelist()
def duplicate_negotiated_price_list(source: Any, name: Any):
	"""Copy an Opt-In selling price list and all of its item prices."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	source = _get_negotiated_price_list(source)
	name = frappe.utils.cstr(name).strip()
	if _is_standard_selling_price_list(name):
		frappe.throw(_("Standard Selling is reserved for ERPNext defaults. Choose another name."))
	if frappe.db.exists("Price List", name):
		frappe.throw(_("A price list with this name already exists."))

	price_list = frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": name,
			"currency": source.currency or "KES",
			"selling": 1,
			"buying": 0,
			"enabled": 1,
		}
	)
	price_list.insert(ignore_permissions=True)

	# Keep the fields that describe an Item Price across ERPNext v15/v16. The
	# common fields are enough for the editor, while dates/customer/batch context
	# preserve a complete copy when those optional columns exist on the site.
	item_price_fields = [
		"item_code",
		"uom",
		"packing_unit",
		"item_name",
		"brand",
		"item_description",
		"customer",
		"supplier",
		"batch_no",
		"currency",
		"price_list_rate",
		"valid_from",
		"lead_time_days",
		"valid_upto",
		"note",
		"reference",
	]
	# Meta.get_fieldnames() is not available on Frappe v15/v16 Meta objects.
	# `fields` is the stable metadata surface across both versions.
	available_fields = set()
	for field in getattr(frappe.get_meta("Item Price"), "fields", []):
		fieldname = frappe.utils.cstr(getattr(field, "fieldname", "")).strip()
		if fieldname:
			available_fields.add(fieldname)
	source_rows = frappe.get_list(
		"Item Price",
		filters={"price_list": source.name, "selling": 1},
		fields=["name", *[field for field in item_price_fields if field in available_fields]],
		order_by="item_code asc, name asc",
		limit_page_length=0,
		ignore_permissions=True,  # SYSTEM-INTERNAL
	)
	for source_row in source_rows:
		values = {
			field: source_row.get(field)
			for field in item_price_fields
			if field in available_fields and source_row.get(field) is not None
		}
		values.update({"doctype": "Item Price", "price_list": price_list.name, "selling": 1, "buying": 0})
		if not values.get("currency"):
			values["currency"] = price_list.currency or "KES"
		if not values.get("uom"):
			values["uom"] = frappe.db.get_value("Item", values["item_code"], "stock_uom") or "Nos"
		frappe.get_doc(values).insert(ignore_permissions=True)

	frappe.db.commit()
	return {"name": price_list.name, "source": source.name, "copied": len(source_rows)}


@frappe.whitelist()
def save_item_price(price_list: Any, item_code: Any, rate: Any):
	"""Create or update a selling Item Price in a negotiated price list."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	price_list = _get_negotiated_price_list(price_list)
	item_code = frappe.utils.cstr(item_code).strip()
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Item not found."))
	try:
		rate = float(rate)
	except (TypeError, ValueError):
		frappe.throw(_("Enter a valid price."))
	if not math.isfinite(rate) or rate < 0:
		frappe.throw(_("Enter a non-negative finite price."))

	existing = frappe.db.exists(
		"Item Price", {"price_list": price_list.name, "item_code": item_code, "selling": 1}
	)
	item_price = frappe.get_doc("Item Price", existing) if existing else frappe.new_doc("Item Price")
	item_price.price_list = price_list.name
	item_price.item_code = item_code
	item_price.price_list_rate = rate
	item_price.currency = price_list.currency or "KES"
	item_price.selling = 1
	item_price.buying = 0
	item_price.uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
	item_price.save(ignore_permissions=True)
	frappe.db.commit()
	return {"name": item_price.name}


@frappe.whitelist()
def save_item_prices(price_list: Any, prices: Any):
	"""Create/update several Item Prices in one atomic Opt-In catalogue action."""
	if not _is_admin():
		frappe.throw("Not permitted", frappe.PermissionError)
	if isinstance(prices, str):
		try:
			prices = json.loads(prices)
		except (TypeError, ValueError):
			frappe.throw("Prices must be a list.")
	if not isinstance(prices, list):
		frappe.throw("Prices must be a list.")

	price_list = _get_negotiated_price_list(price_list)
	saved = 0
	seen = set()
	for row in prices:
		if not isinstance(row, dict):
			continue
		item_code = frappe.utils.cstr(row.get("item_code") or "").strip()
		if not item_code or item_code in seen:
			continue
		seen.add(item_code)
		if not frappe.db.exists("Item", item_code):
			frappe.throw("Item not found: %s" % item_code)
		try:
			rate = float(row.get("rate"))
		except (TypeError, ValueError):
			frappe.throw("Enter a valid price for %s." % item_code)
		if not math.isfinite(rate) or rate < 0:
			frappe.throw("Enter a non-negative finite price for %s." % item_code)

		existing = frappe.db.exists(
			"Item Price", {"price_list": price_list.name, "item_code": item_code, "selling": 1}
		)
		item_price = frappe.get_doc("Item Price", existing) if existing else frappe.new_doc("Item Price")
		item_price.price_list = price_list.name
		item_price.item_code = item_code
		item_price.price_list_rate = rate
		item_price.currency = price_list.currency or "KES"
		item_price.selling = 1
		item_price.buying = 0
		item_price.uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
		item_price.save(ignore_permissions=True)  # SYSTEM-INTERNAL
		saved += 1

	frappe.db.commit()
	return {"name": price_list.name, "saved": saved}


# ---------------------------------------------------------------------------
# Facility CRUD
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_facilities(
	network: Any = None,
	status: Any = None,
	opted_in: Any = None,
	facility: Any = None,
	facility_level: Any = None,
	organization: Any = None,
	contact: Any = None,
	invite_status: Any = None,
	page: Any = 0,
	page_size: Any = 20,
):
	"""Return a permission-scoped, paginated facility list with contact filters."""
	page = max(int(page or 0), 0)
	page_size = min(max(int(page_size or 20), 1), 100)

	if not _is_admin() and not frappe.has_permission("CRM Pre-Qualified Facility", "read"):
		allowed_networks = _get_coordinator_networks()
		if not allowed_networks:
			return {"rows": [], "total": 0}
		# If network filter is set, check it's in allowed list
		if network and network not in allowed_networks:
			return {"rows": [], "total": 0}
		target_networks = [network] if network else allowed_networks
	else:
		target_networks = [network] if network else None

	# Get facility names that have memberships in target networks
	mem_filters = {"parenttype": "CRM Pre-Qualified Facility"}
	if target_networks:
		mem_filters["network"] = ["in", target_networks]
	status = frappe.utils.cstr(status).strip()
	if status:
		mem_filters["status"] = status

	# The contact list is principally an opt-in view. Keep the old `status`
	# argument for API compatibility, but expose a categorical filter that does
	# not leak the internal Active/Declined enrollment states to the UI.
	opted_in = frappe.utils.cstr(opted_in).strip().lower()

	contact = frappe.utils.cstr(contact).strip()
	contact_or_filters = None
	if contact:
		contact_like = "%%%s%%" % contact
		contact_or_filters = [
			["contact_name", "like", contact_like],
			["contact_email", "like", contact_like],
			["contact_phone", "like", contact_like],
		]

	membership_fields = [
		"name",
		"parent",
		"network",
		"status",
		"contact_name",
		"contact_email",
		"contact_phone",
		"invite_email_queue",
		"invite_sent_at",
	]
	try:
		if frappe.db.has_column("CRM Facility Membership", "price_list_override"):
			membership_fields.insert(3, "price_list_override")
	except Exception:
		pass

	mem_rows = frappe.get_list(
		"CRM Facility Membership",
		filters=mem_filters,
		or_filters=contact_or_filters,
		fields=membership_fields,
		ignore_permissions=True,  # SYSTEM-INTERNAL
		limit_page_length=0,
	)

	if not mem_rows:
		return {"rows": [], "total": 0}

	if opted_in in ("1", "true"):
		mem_rows = [row for row in mem_rows if row.get("status") == "Opted In"]
	elif opted_in in ("0", "false"):
		mem_rows = [row for row in mem_rows if row.get("status") != "Opted In"]
	if not mem_rows:
		return {"rows": [], "total": 0}

	# Email Queue is deliberately resolved in one read. This keeps invitation
	# filters and the displayed state consistent without an N+1 lookup per row.
	queue_names = {row.invite_email_queue for row in mem_rows if row.invite_email_queue}
	queue_statuses = {}
	if queue_names:
		queue_statuses = {
			row.name: row.status
			for row in frappe.get_list(
				"Email Queue",
				filters={"name": ["in", list(queue_names)]},
				fields=["name", "status"],
				ignore_permissions=True,  # SYSTEM-INTERNAL: status for linked invitation queues only
			)
		}

	def invitation_status(membership):
		return queue_statuses.get(membership.invite_email_queue, "Not Sent")

	invite_status = frappe.utils.cstr(invite_status).strip()
	if invite_status:
		wanted_invite_status = invite_status.casefold()
		mem_rows = [row for row in mem_rows if invitation_status(row).casefold() == wanted_invite_status]
		if not mem_rows:
			return {"rows": [], "total": 0}

	# Group memberships by parent facility
	from collections import defaultdict

	mem_by_parent = defaultdict(list)
	for m in mem_rows:
		mem_by_parent[m.parent].append(m)

	parent_names = list(mem_by_parent.keys())

	facility_filters = {"name": ["in", parent_names]}
	facility_level = frappe.utils.cstr(facility_level).strip()
	if facility_level:
		facility_filters["keph_level"] = facility_level

	organization = frappe.utils.cstr(organization).strip()
	if organization:
		facility_filters["organization"] = ["like", "%%%s%%" % organization]

	facility = frappe.utils.cstr(facility).strip()
	facility_or_filters = None
	if facility:
		facility_like = "%%%s%%" % facility
		facility_or_filters = [
			["facility_name", "like", facility_like],
			["mfl_code", "like", facility_like],
			["organization", "like", facility_like],
		]

	matching_facility_rows = frappe.get_list(
		"CRM Pre-Qualified Facility",
		filters=facility_filters,
		or_filters=facility_or_filters,
		fields=["name"],
		order_by="facility_name asc",
		limit_page_length=0,
		ignore_permissions=True,  # SYSTEM-INTERNAL
	)
	matching_names = [row.name for row in matching_facility_rows]
	if not matching_names:
		return {"rows": [], "total": 0}

	page_names = matching_names[page * page_size : (page + 1) * page_size]
	fac_rows_by_name = {
		row.name: row
		for row in frappe.get_list(
			"CRM Pre-Qualified Facility",
			filters={"name": ["in", page_names]},
			fields=["name", "mfl_code", "facility_name", "organization", "keph_level"],
			ignore_permissions=True,  # SYSTEM-INTERNAL
		)
	}

	result = []
	for facility_name in page_names:
		fac = fac_rows_by_name[facility_name]
		result.append(
			{
				"name": fac.name,
				"mfl_code": fac.mfl_code,
				"facility_name": fac.facility_name,
				"organization": fac.organization or fac.facility_name,
				"keph_level": fac.keph_level,
				"memberships": [
					{
						"network": m.network,
						"name": m.name,
						"price_list_override": m.get("price_list_override") or "",
						"status": m.status,
						"contact_name": m.contact_name,
						"contact_email": m.contact_email,
						"contact_phone": m.contact_phone,
						"invite_email_queue": m.invite_email_queue,
						"invite_sent_at": m.invite_sent_at,
						"invite_status": invitation_status(m),
					}
					for m in mem_by_parent[fac.name]
				],
			}
		)

	return {"rows": result, "total": len(matching_names)}


@frappe.whitelist()
def save_facility(data: Any):
	"""
	Create or update a CRM Pre-Qualified Facility with its memberships.
	data shape: {
	  name?: str,  # existing doc name (for update)
	  mfl_code: str,
	  facility_name: str,
	  organization?: str,  # blank defaults to the facility name
	  keph_level: str,
	  memberships: [{network, price_list_override?, status, contact_name, contact_email, contact_phone}]
	  ``price_list_override`` is optional on edits so contact updates cannot clear
	  pricing accidentally; CSV/admin callers may send an explicit blank to clear it.
	}
	Max 2 memberships enforced.
	"""
	if isinstance(data, str):
		data = json.loads(data)

	# RBAC: coordinators can only save facilities in their networks
	mem_networks = [m.get("network") for m in (data.get("memberships") or [])]
	if not _is_admin():
		allowed = _get_coordinator_networks()
		for net in mem_networks:
			if net and net not in allowed:
				frappe.throw(_("Not permitted for network %s") % net, frappe.PermissionError)

	memberships = data.get("memberships") or []
	if len(memberships) > 2:
		frappe.throw(_("A facility may belong to at most 2 networks."))

	for membership in memberships:
		price_list_override = frappe.utils.cstr(membership.get("price_list_override") or "").strip()
		if price_list_override and not frappe.db.exists(
			"Price List", {"name": price_list_override, "selling": 1, "enabled": 1}
		):
			frappe.throw(_("Select an enabled selling price list for the facility override."))

	name = data.get("name")
	mfl_code = frappe.utils.cstr(data.get("mfl_code") or "").strip()

	is_new_facility = False
	if name and frappe.db.exists("CRM Pre-Qualified Facility", name):
		doc = frappe.get_doc("CRM Pre-Qualified Facility", name)
	elif mfl_code:
		# Check for existing by mfl_code
		existing = frappe.get_all(
			"CRM Pre-Qualified Facility",
			filters={"mfl_code": mfl_code},
			pluck="name",
			limit=1,
		)
		doc = (
			frappe.get_doc("CRM Pre-Qualified Facility", existing[0])
			if existing
			else frappe.new_doc("CRM Pre-Qualified Facility")
		)
	else:
		doc = frappe.new_doc("CRM Pre-Qualified Facility")
	is_new_facility = doc.is_new()
	existing_networks = {m.network for m in (doc.memberships or [])}
	existing_memberships = {m.network: m for m in (doc.memberships or [])}

	doc.mfl_code = mfl_code or doc.mfl_code
	doc.facility_name = frappe.utils.cstr(data.get("facility_name") or doc.facility_name or "")
	if "organization" in data:
		doc.organization = frappe.utils.cstr(data.get("organization") or "").strip()
	doc.keph_level = frappe.utils.cstr(data.get("keph_level") or doc.keph_level or "")

	# Rebuild memberships: keep existing rows not in the new set (other network), update/add for this set
	new_network_set = {m.get("network") for m in memberships if m.get("network")}
	# Remove membership rows for networks being replaced
	doc.memberships = [m for m in (doc.memberships or []) if m.network not in new_network_set]
	try:
		membership_has_override = frappe.db.has_column("CRM Facility Membership", "price_list_override")
	except Exception:
		membership_has_override = False
	for mem_data in memberships:
		net = frappe.utils.cstr(mem_data.get("network") or "").strip()
		if not net:
			continue
		membership_values = {
			"network": net,
			"status": mem_data.get("status") or "Active",
			"contact_name": frappe.utils.cstr(mem_data.get("contact_name") or ""),
			"contact_email": frappe.utils.cstr(mem_data.get("contact_email") or "").lower(),
			"contact_phone": frappe.utils.cstr(mem_data.get("contact_phone") or ""),
		}
		if membership_has_override:
			# Preserve an existing override when the caller omits the field, while
			# pre-opt-in edits and CSV/admin callers may clear or replace it explicitly.
			if "price_list_override" in mem_data:
				if net in existing_memberships:
					_validate_opted_in_price_list_override(
						existing_memberships[net], mem_data.get("price_list_override")
					)
				membership_values["price_list_override"] = frappe.utils.cstr(
					mem_data.get("price_list_override") or ""
				).strip()
			elif net in existing_memberships:
				membership_values["price_list_override"] = frappe.utils.cstr(
					existing_memberships[net].get("price_list_override") or ""
				).strip()
		doc.append(
			"memberships",
			membership_values,
		)

	doc.save(ignore_permissions=True)  # SYSTEM-INTERNAL
	frappe.db.commit()

	# New parent facilities send their invitations in after_insert. For an existing
	# facility, explicitly invite memberships newly added through this admin flow.
	if not is_new_facility:
		for membership in doc.memberships or []:
			if membership.network in new_network_set and membership.network not in existing_networks:
				from crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility import (
					_send_membership_invitation,
				)

				try:
					_send_membership_invitation(doc, membership)
				except Exception:
					frappe.log_error(
						frappe.get_traceback(),
						"optin_admin.save_facility: invitation email failed",
					)

	return {"name": doc.name}


@frappe.whitelist()
def delete_facility(name: Any):
	name = frappe.utils.cstr(name)
	if not _is_admin():
		# Check coordinator has access to this facility's networks
		fac = frappe.get_doc("CRM Pre-Qualified Facility", name)
		allowed = _get_coordinator_networks()
		fac_networks = [m.network for m in (fac.memberships or [])]
		if not any(n in allowed for n in fac_networks):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
	frappe.delete_doc("CRM Pre-Qualified Facility", name, ignore_permissions=True)
	frappe.db.commit()
	return {"deleted": name}


def _get_invitation_status(queue_name):
	if not queue_name:
		return "Not sent"
	return frappe.db.get_value("Email Queue", queue_name, "status") or "Not sent"


@frappe.whitelist()
def resend_facility_invitation(facility_name: Any, membership_name: Any):
	"""Resend an opt-in invitation for one facility membership and return queue state."""
	facility_name = frappe.utils.cstr(facility_name).strip()
	membership_name = frappe.utils.cstr(membership_name).strip()
	facility = frappe.get_doc("CRM Pre-Qualified Facility", facility_name)
	membership = next((m for m in (facility.memberships or []) if m.name == membership_name), None)
	if not membership:
		frappe.throw(_("Facility membership not found."))

	_assert_network_access(membership.network)

	from crm.fcrm.doctype.crm_pre_qualified_facility.crm_pre_qualified_facility import (
		_send_membership_invitation,
	)

	queue = _send_membership_invitation(facility, membership)
	return {
		"queue_name": queue.name,
		"status": _get_invitation_status(queue.name),
		"sent_at": frappe.utils.now_datetime(),
	}


# ---------------------------------------------------------------------------
# HFR Lookup
# ---------------------------------------------------------------------------


@frappe.whitelist()
def lookup_hfr(mfl_code: Any):
	"""
	Look up a facility in the Health Facility Registry by MFL code.
	Delegates to crm.api.hfr.search_facility which reads CRM HFR Settings
	(hfr_url, hfr_fetch_path, JWT credentials). Returns {mfl_code, facility_name, keph_level}.
	"""
	mfl_code = frappe.utils.cstr(mfl_code).strip()
	if not mfl_code:
		frappe.throw(_("MFL code is required"))

	from crm.api.hfr import search_facility

	results = search_facility(mfl_code, search_by="mfl_code")
	if not results:
		frappe.throw(_("Facility MFL %s not found in HFR") % mfl_code)

	hit = results[0]
	keph_level_raw = frappe.utils.cstr(hit.get("level") or "").strip()
	if keph_level_raw and not keph_level_raw.lower().startswith("level"):
		keph_level = "Level %s" % keph_level_raw
	else:
		keph_level = keph_level_raw

	return {
		"mfl_code": hit.get("mfl_code") or mfl_code,
		"facility_name": hit.get("name") or "",
		"keph_level": keph_level,
	}


# ---------------------------------------------------------------------------
# CSV Import
# ---------------------------------------------------------------------------


@frappe.whitelist()
def import_facilities_csv(csv_data: Any, network_slug: Any, dry_run: Any = 0):
	"""
	Parse and import a CSV of pre-qualified facilities for a network.

	Expected CSV columns (order flexible, matched by header name):
	  mfl_code, facility_name (optional — auto-filled from HFR if blank),
	  keph_level (optional — auto-filled from HFR if blank),
	  organization (optional — defaults to facility_name), price_list_override
	  (optional — defaults to the network price list), contact_name, contact_email,
	  contact_phone

	Returns:
	  {
	    imported: int,
	    valid_count: int,
	    error_count: int,
	    rows: [{row, mfl_code, facility_name, organization, price_list_override, contact_email, error}],
	    errors: [{row: int, mfl_code: str, message: str}],
	    dry_run: bool
	  }
	"""
	_assert_network_access(network_slug)

	dry_run = bool(frappe.utils.cint(dry_run))

	if isinstance(csv_data, str):
		raw = csv_data
	else:
		raw = frappe.utils.cstr(csv_data)

	# Excel commonly writes a UTF-8 BOM. Strip it before DictReader sees the
	# header or otherwise `mfl_code` becomes an unrecognised column.
	reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")))

	def normalize_header(value):
		return re.sub(r"\s+", "_", frappe.utils.cstr(value or "").lstrip("\ufeff").strip().lower())

	headers = {normalize_header(header) for header in reader.fieldnames or [] if header}
	required_headers = {"mfl_code", "contact_name", "contact_email", "contact_phone"}
	missing_headers = sorted(required_headers - headers)
	if missing_headers:
		frappe.throw(_("CSV is missing required columns: {0}").format(", ".join(missing_headers)))

	def normalize_row(row):
		# DictReader uses None as the key when a row has more columns than its
		# header. Ignore the overflow value and report normal field errors
		# instead of failing the entire upload with an AttributeError.
		return {
			normalize_header(key): frappe.utils.cstr(value or "").strip()
			for key, value in row.items()
			if key is not None
		}

	errors = []
	preview_rows = []
	imported = 0
	seen_mfl_codes = set()

	for idx, raw_row in enumerate(reader, start=2):  # row 1 is header
		row = normalize_row(raw_row)
		if not any(row.values()):
			continue

		mfl_code = row.get("mfl_code", "")
		contact_name = row.get("contact_name", "")
		contact_email = row.get("contact_email", "").lower()
		contact_phone = row.get("contact_phone", "")
		price_list_override = row.get("price_list_override", "")
		facility_name = row.get("facility_name", "")
		keph_level = row.get("keph_level", "")
		preview = {
			"row": idx,
			"mfl_code": mfl_code,
			"facility_name": facility_name,
			"organization": row.get("organization", ""),
			"price_list_override": price_list_override,
			"contact_email": contact_email,
			"error": None,
		}
		error = None

		if not mfl_code:
			error = "mfl_code is required"
		elif mfl_code in seen_mfl_codes:
			error = "duplicate mfl_code in this CSV"
		if not error and not contact_name:
			error = "contact_name is required"
		if not error and not contact_email:
			error = "contact_email is required"
		if not error and not contact_phone:
			error = "contact_phone is required"
		if (
			not error
			and price_list_override
			and not frappe.db.exists("Price List", {"name": price_list_override, "selling": 1, "enabled": 1})
		):
			error = "price_list_override must be an enabled selling price list"

		# HFR enrichment if fields missing. It is safe in preview mode because
		# it does not write; it also ensures the count matches what can import.
		if not error and (not facility_name or not keph_level):
			try:
				hfr = lookup_hfr(mfl_code)
				facility_name = facility_name or hfr.get("facility_name") or ""
				keph_level = keph_level or hfr.get("keph_level") or ""
			except Exception:
				# A facility name remains mandatory, but an absent KEPH level
				# has the established Level 3 fallback used by this importer.
				if not facility_name:
					error = "facility_name could not be resolved (not in CSV and HFR lookup failed)"

		organization = row.get("organization", "") or facility_name
		preview.update({"facility_name": facility_name, "organization": organization})

		if not error and not facility_name:
			error = "facility_name could not be resolved (not in CSV and HFR lookup failed)"

		if not error:
			seen_mfl_codes.add(mfl_code)

		if not error and not dry_run:
			try:
				save_facility(
					{
						"mfl_code": mfl_code,
						"facility_name": facility_name,
						"organization": organization,
						"keph_level": keph_level or "Level 3",
						"memberships": [
							{
								"network": network_slug,
								"price_list_override": price_list_override,
								"status": "Active",
								"contact_name": contact_name,
								"contact_email": contact_email,
								"contact_phone": contact_phone,
							}
						],
					}
				)
			except Exception as exc:
				error = frappe.utils.cstr(exc)

		if error:
			preview["error"] = error
			errors.append({"row": idx, "mfl_code": mfl_code, "message": error})
		else:
			imported += 1
		preview_rows.append(preview)

	return {
		"imported": imported,
		"valid_count": imported,
		"error_count": len(errors),
		"rows": preview_rows,
		"errors": errors,
		"dry_run": dry_run,
	}


@frappe.whitelist()
def csv_template():
	"""Return the CSV template as a string for download."""
	return "mfl_code,facility_name,organization,price_list_override,keph_level,contact_name,contact_email,contact_phone\n22999,Example Hospital,Example Hospital Group,,Level 4,Jane Wanjiku,jane@hospital.co.ke,0722000000\n"
