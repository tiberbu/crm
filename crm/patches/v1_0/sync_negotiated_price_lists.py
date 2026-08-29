"""Synchronise the canonical negotiated Item Prices on sites that ran the original seed."""

from __future__ import annotations

import frappe

from crm.patches.v1_0.seed_negotiated_price_lists import _seed_items, _seed_price_lists


def execute():
	# ERPNext owns Item, Price List, and Item Price. The CRM app may also be
	# installed without it, in which case negotiated ERPNext pricing is inapplicable.
	if "erpnext" not in frappe.get_installed_apps():
		return

	_seed_items()
	_seed_price_lists()
