"""Utility helpers for Partner Portal APIs."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _


def decode_json(value: Any, default: Any = None) -> Any:
	"""Safely decode JSON string, returning default on failure."""
	if default is None:
		default = {}
	if isinstance(value, dict | list):
		return value
	if not value:
		return default
	try:
		result = json.loads(value)
		return result if isinstance(result, type(default)) else default
	except (TypeError, ValueError, json.JSONDecodeError):
		return default


def resolve_network(partner_id: Any) -> Any:
	"""Resolve an enabled CRM Opt-In Network by partner_id, name, or slug."""
	val = frappe.utils.cstr(partner_id or "").strip()
	if not val:
		frappe.throw(_("Partner ID or Network identifier is required."), frappe.ValidationError)

	# Try six-digit / public partner_id first
	try:
		if frappe.db.has_column("CRM Opt-In Network", "partner_id"):
			network_name = frappe.db.get_value(
				"CRM Opt-In Network",
				{"partner_id": val, "enabled": 1},
				"name",
			)
			if network_name:
				return frappe.get_doc("CRM Opt-In Network", network_name)
	except Exception:
		pass

	# Try DocType primary key name
	if frappe.db.exists("CRM Opt-In Network", val):
		doc = frappe.get_doc("CRM Opt-In Network", val)
		if doc.enabled:
			return doc

	# Try slug
	network_name = frappe.db.get_value(
		"CRM Opt-In Network",
		{"slug": val, "enabled": 1},
		"name",
	)
	if network_name:
		return frappe.get_doc("CRM Opt-In Network", network_name)

	frappe.throw(
		_("Partner network '{0}' not found or inactive.").format(val),
		frappe.DoesNotExistError,
	)


def resolve_or_create_facility(facility_input: Any, auto_create: bool = True) -> Any:
	"""Resolve an existing CRM Pre-Qualified Facility or create a new one."""
	mfl_code = ""
	facility_name = ""
	name = ""
	keph_level = "Level 3"
	organization = ""

	if isinstance(facility_input, dict):
		mfl_code = frappe.utils.cstr(facility_input.get("mfl_code") or "").strip()
		facility_name = frappe.utils.cstr(facility_input.get("facility_name") or "").strip()
		name = frappe.utils.cstr(facility_input.get("name") or "").strip()
		keph_level = frappe.utils.cstr(facility_input.get("keph_level") or "Level 3").strip()
		organization = frappe.utils.cstr(facility_input.get("organization") or facility_name).strip()
	else:
		raw_str = frappe.utils.cstr(facility_input or "").strip()
		if not raw_str:
			frappe.throw(_("Facility identifier is required."), frappe.ValidationError)
		mfl_code = raw_str
		facility_name = raw_str
		name = raw_str
		keph_level = "Level 3"
		organization = raw_str

	existing_name = None
	if mfl_code and frappe.db.exists("CRM Pre-Qualified Facility", {"mfl_code": mfl_code}):
		existing_name = frappe.db.get_value("CRM Pre-Qualified Facility", {"mfl_code": mfl_code}, "name")
	elif name and frappe.db.exists("CRM Pre-Qualified Facility", name):
		existing_name = name
	elif not mfl_code and facility_name and frappe.db.exists("CRM Pre-Qualified Facility", {"facility_name": facility_name}):
		existing_name = frappe.db.get_value("CRM Pre-Qualified Facility", {"facility_name": facility_name}, "name")

	if existing_name:
		return frappe.get_doc("CRM Pre-Qualified Facility", existing_name)

	if not auto_create:
		frappe.throw(_("Facility '{0}' not found.").format(facility_input), frappe.DoesNotExistError)

	doc = frappe.new_doc("CRM Pre-Qualified Facility")
	doc.mfl_code = mfl_code or frappe.generate_hash(length=8)
	doc.facility_name = facility_name or doc.mfl_code
	doc.keph_level = keph_level or "Level 3"
	doc.organization = organization or doc.facility_name
	doc.flags.skip_invitation = True
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


def resolve_keph_item_code(keph_level: str | None) -> str:
	"""Map a KEPH level (e.g. 'Level 3') to standard item code 'CV-HIMS-KEPH-3'."""
	level = frappe.utils.cstr(keph_level or "").strip()
	if not level:
		return "CV-HIMS-KEPH-3"
	if level.lower().startswith("level "):
		code_part = level[6:].strip().upper()
	else:
		code_part = level.upper()
	item_code = "CV-HIMS-KEPH-%s" % code_part
	if frappe.db.exists("Item", item_code):
		return item_code
	return "CV-HIMS-KEPH-3"


def ensure_price_list(price_list_name: str, currency: str = "KES") -> str:
	"""Ensure an enabled selling Price List exists, creating it if needed."""
	price_list_name = frappe.utils.cstr(price_list_name).strip()
	if not price_list_name:
		frappe.throw(_("Price list name cannot be empty."), frappe.ValidationError)
	if frappe.db.exists("Price List", price_list_name):
		return price_list_name

	doc = frappe.new_doc("Price List")
	doc.price_list_name = price_list_name
	doc.currency = currency or "KES"
	doc.selling = 1
	doc.buying = 0
	doc.enabled = 1
	doc.insert(ignore_permissions=True)
	return doc.name


def set_item_price_rate(price_list: str, item_code: str, rate: float, currency: str = "KES"):
	"""Insert or update an Item Price rate for a given price list and item code."""
	rate = float(rate or 0)
	existing = frappe.get_list(
		"Item Price",
		filters={"price_list": price_list, "item_code": item_code, "selling": 1},
		fields=["name"],
		limit=1,
		ignore_permissions=True,
	)
	if existing:
		frappe.db.set_value("Item Price", existing[0].name, "price_list_rate", rate, update_modified=False)
	else:
		doc = frappe.new_doc("Item Price")
		doc.price_list = price_list
		doc.item_code = item_code
		doc.price_list_rate = rate
		doc.currency = currency or "KES"
		doc.selling = 1
		doc.insert(ignore_permissions=True)


def _is_numeric(val: Any) -> bool:
	if isinstance(val, int | float):
		return True
	try:
		float(str(val).strip())
		return True
	except (ValueError, TypeError):
		return False


def normalize_pricing_payload(
	pricing_input: Any,
	facility_doc: Any = None,
	network_doc: Any = None,
	currency: str = "KES",
) -> tuple[dict[str, str], list[dict[str, Any]]]:
	"""
	Normalize custom pricing for Years 1-5.

	Supports:
	- Dict of year -> price_list name or numeric rate: {"1": "Negotiated Year 1", "2": 25000}
	- List of year items: [{"year": 1, "rate": 25000}, {"year": 2, "price_list": "Negotiated Year 2"}]
	- Numeric rates or Price List names.

	Returns:
	- price_lists_dict: {"1": "...", "2": "...", ...}
	- pricing_by_year: list of pricing detail dicts per year.
	"""
	raw = decode_json(pricing_input, {})
	year_data: dict[str, Any] = {}

	if isinstance(raw, list):
		for idx, item in enumerate(raw, start=1):
			if isinstance(item, dict):
				yr = str(item.get("year") or item.get("year_number") or idx)
				year_data[yr] = item
			elif _is_numeric(item) or isinstance(item, str):
				year_data[str(idx)] = item
	elif isinstance(raw, dict):
		for k, v in raw.items():
			year_data[str(k)] = v

	fac_identifier = (
		frappe.utils.cstr(getattr(facility_doc, "mfl_code", "") or getattr(facility_doc, "name", "") or "FAC").strip()
	)
	default_item_code = resolve_keph_item_code(getattr(facility_doc, "keph_level", "Level 3"))

	price_lists_dict: dict[str, str] = {}
	pricing_by_year: list[dict[str, Any]] = []

	for year in range(1, 6):
		yr_str = str(year)
		entry = year_data.get(yr_str)
		resolved_pl = ""
		effective_item_code = default_item_code
		rate_value = None

		if entry is not None:
			if isinstance(entry, dict):
				custom_rate = entry.get("rate")
				custom_item = entry.get("item_code") or default_item_code
				pl_candidate = entry.get("price_list")

				if custom_rate is not None and _is_numeric(custom_rate):
					resolved_pl = pl_candidate or f"Custom - {fac_identifier} - Year {year}"
					ensure_price_list(resolved_pl, currency=currency)
					set_item_price_rate(resolved_pl, custom_item, float(custom_rate), currency=currency)
					effective_item_code = custom_item
					rate_value = float(custom_rate)
				elif pl_candidate:
					resolved_pl = ensure_price_list(str(pl_candidate).strip(), currency=currency)
			elif _is_numeric(entry):
				rate_value = float(entry)
				resolved_pl = f"Custom - {fac_identifier} - Year {year}"
				ensure_price_list(resolved_pl, currency=currency)
				set_item_price_rate(resolved_pl, default_item_code, rate_value, currency=currency)
			elif isinstance(entry, str) and entry.strip():
				clean_str = entry.strip()
				if _is_numeric(clean_str):
					rate_value = float(clean_str)
					resolved_pl = f"Custom - {fac_identifier} - Year {year}"
					ensure_price_list(resolved_pl, currency=currency)
					set_item_price_rate(resolved_pl, default_item_code, rate_value, currency=currency)
				else:
					resolved_pl = ensure_price_list(clean_str, currency=currency)

		if not resolved_pl:
			# Fallback to standard negotiated year price list or previous year
			candidate = f"Negotiated Year {year}"
			if frappe.db.exists("Price List", candidate):
				resolved_pl = candidate
			elif price_lists_dict.get(str(year - 1)):
				resolved_pl = price_lists_dict[str(year - 1)]
			else:
				resolved_pl = ensure_price_list(f"Custom - {fac_identifier} - Year {year}", currency=currency)

		price_lists_dict[yr_str] = resolved_pl

		# Resolve rate from Item Price if not explicitly given
		if rate_value is None:
			price_rows = frappe.get_list(
				"Item Price",
				filters={"price_list": resolved_pl, "item_code": effective_item_code, "selling": 1},
				fields=["price_list_rate"],
				limit=1,
				ignore_permissions=True,
			)
			if price_rows:
				rate_value = float(price_rows[0].price_list_rate)
			else:
				# Check any item price in the list
				any_rows = frappe.get_list(
					"Item Price",
					filters={"price_list": resolved_pl, "selling": 1},
					fields=["item_code", "price_list_rate"],
					limit=1,
					ignore_permissions=True,
				)
				if any_rows:
					effective_item_code = any_rows[0].item_code
					rate_value = float(any_rows[0].price_list_rate)
				else:
					rate_value = 0.0

		monthly_rate = round(rate_value, 2)
		annual_rate = round(monthly_rate * 12, 2)

		pricing_by_year.append(
			{
				"year_number": year,
				"price_list": resolved_pl,
				"item_code": effective_item_code,
				"rate": monthly_rate,
				"monthly_rate": monthly_rate,
				"annual_rate": annual_rate,
				"currency": currency,
			}
		)

	return price_lists_dict, pricing_by_year


def check_idempotency(key: str | None) -> dict | None:
	"""Check if request with this idempotency key has already completed."""
	if not key:
		return None
	clean_key = str(key).strip()
	cached = frappe.cache().get_value(f"partner_portal:idempotency:{clean_key}")
	if cached:
		try:
			return json.loads(cached)
		except Exception:
			return None
	return None


def store_idempotency(key: str | None, response_data: dict, ttl: int = 86400):
	"""Store idempotent result in cache."""
	if not key:
		return
	clean_key = str(key).strip()
	try:
		frappe.cache().set_value(
			f"partner_portal:idempotency:{clean_key}",
			json.dumps(response_data, default=str),
			expires_in_sec=ttl,
		)
	except Exception:
		pass
