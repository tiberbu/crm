"""Default legacy facility ownership to the facility itself."""

import frappe


def execute():
    if not frappe.db.table_exists("CRM Pre-Qualified Facility") or not frappe.db.has_column(
        "CRM Pre-Qualified Facility", "organization"
    ):
        return

    facilities = frappe.get_all(
        "CRM Pre-Qualified Facility",
        fields=["name", "facility_name", "organization"],
        limit_page_length=0,
    )
    for facility in facilities:
        if frappe.utils.cstr(facility.organization).strip() or not facility.facility_name:
            continue
        frappe.db.set_value(
            "CRM Pre-Qualified Facility",
            facility.name,
            "organization",
            facility.facility_name,
            update_modified=False,
        )
