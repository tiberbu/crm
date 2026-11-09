# Customer 360 — facility scope, clearable search, closable results (spec, 2026-11-09)

Builds on `_bmad-output/customer-360/planning-artifacts/customer-360-spec-2026-11-02.md` and
`docs/customer-360-view.md`. Roundtable: `../implementation-artifacts/party-2026-11-09-customer-360-facility-scope.md`.

## Problem

On Customer 360 (`/crm/customer-360`):

1. The search box cannot be cleared.
2. The search results pop-up cannot be closed (and, after the first pick, new searches never show
   results because the panel was tied to "nothing selected").
3. Choosing a **facility** opens the owner organisation's whole 360. The admin wants that facility's
   invoices, quotes, orders and billing by default, with a way to see the owner's full picture.

## Decisions

| # | Decision |
|---|---|
| D1 | A clear button (`×`, "Clear search") in the search box's `#suffix` slot while it has text. Clearing empties the text and closes results; the loaded 360 stays. |
| D2 | Results render as a dropdown anchored under the search box with a close button ("Close results"). Esc and a click outside close it; focusing the box with a ≥3-character query reopens it. Typing a new query always reopens it. |
| D3 | Picking a facility opens the 360 in **facility scope**. The page state lives in the URL: `?organization=` · `?deal=` · `?facility=<name>&scope=facility|organization`. |
| D4 | Facility scope shows a scope bar: facility name, Facility ID (or "Not linked yet"), MFL code, and a `TabButtons` control **This facility** \| **All facilities** (default This facility). Without an owner organisation only the facility lens is offered, with "No owner organization on file". |
| D5 | Scoping is server-side. Every order, quote and invoice is attributed with the CX portal rule `crm.utils.portal_commercial.attribute_facilities` (header facility → item-line facility codes → Opt-In Submission facility snapshot → the account's only facility). Facility scope keeps rows attributed to the facility's MFL codes (its own, plus every MFL recorded for its Facility ID). Summary tiles are computed on the scoped rows. |
| D6 | Rows that cannot be attributed to any facility are left out of facility scope and counted in `scope.unattributed`; the page says "N records aren't tied to one facility" with a link to All facilities. |
| D7 | Payments follow their invoices: in facility scope a Payment Entry is kept when it references an in-scope invoice. |
| D8 | Facility scope: Facilities = this facility; Deals = deals whose facility table lists the facility (by MFL or Facility ID), or every owner deal when the owner has exactly one facility; Onboarding = those deals' requests; Partners = the facility's membership networks plus those deals' partners. |
| D9 | New **Quotes** section (both scopes): Quotations linked by `crm_deal` or by billing customer (`quotation_to = Customer`). |
| D10 | Orders are also read by billing customer (Value Express draft orders carry no OIS/quote link). Billing customers = the deals' `cx_customer` plus the in-view facilities' membership `customer`. The organisation view therefore gains those orders/invoices; the facility view is always a subset of it. |
| D11 | Facility ID everywhere a facility is shown (search results, scope bar, Facilities section); search matches facility name, MFL code and Facility ID. Organisation view gets a **Facility** column on orders, quotes and invoices. |
| D12 | The Deal › Customer 360 tab is unchanged (deal scope). |
| D13 | RBAC unchanged: deal entry needs CRM Deal read; organisation and facility entries are manager-gated. No `ignore_permissions`; item rows are read via `frappe.get_list` on the parent. |

## Data contract

`crm.api.customer_360.get_customer_360(organization=None, deal=None, facility=None, scope=None)`

Existing keys are unchanged. Added:

```
quotes:   [ { name, transaction_date, valid_till, grand_total, currency, status, docstatus, facility_mfls } ]
orders[], invoices[]: + facility_mfls: [mfl]
facilities[]: + hfr_facility_id
summary: + quotes
scope: {
  mode: "facility" | "organization",
  facility: { name, facility_name, mfl_code, hfr_facility_id, organization } | null,
  can_widen: bool,            # an owner organisation exists
  unattributed: { orders, quotes, invoices }   # only counted in facility scope
}
```

`scope` defaults to `"facility"` when `facility` is given; `"organization"` otherwise.

`search_customer_360` facility rows add `hfr_facility_id` and match name, MFL code or Facility ID.

## Stories

| Story | Primary file | Notes |
|---|---|---|
| S1 backend scope + quotes + attribution | `crm/api/customer_360.py` | tests in `crm/tests/test_customer_360.py` |
| S2 pure scope helpers | `frontend/src/utils/customer360.js` | `facilityLabelFor`, `unattributedCount`, `parseScopeQuery`; unit tests |
| S3 sections: quotes, facility column, FID | `frontend/src/components/Customer360/Customer360Sections.vue` | |
| S4 page: clear, closable dropdown, scope bar, URL | `frontend/src/pages/Customer360.vue` | |
| S5 Playwright journey + fixture | `e2e/tests/customer360.spec.ts`, `crm/tests/e2e_customer360_fixture.py` | live dev site |
| S6 docs | `docs/customer-360-view.md` | |

## Acceptance

- Typing then pressing the clear button empties the box and closes results; the loaded 360 stays.
- The results dropdown closes with its close button, Esc and an outside click, and reopens for a new query after a pick.
- Picking facility A of a two-facility owner shows only A's orders, quotes and invoices, its payments, and A in Facilities; the URL has `facility=` and `scope=facility`.
- Switching to All facilities shows both facilities' records plus the account-level ones, with a Facility column.
- The unattributed note appears in facility scope when account-level records exist.
- The organisation and deal entries render as before (plus quotes and the facility column).

## Round 2 — tabbed layout (2026-11-09)

After reviewing the PR, the maintainer asked for a layout that stays short with many records.
Decisions T1–T7 are in `../implementation-artifacts/party-2026-11-09-customer-360-tabs.md`: KPI
tiles above the tabs, frappe-ui `Tabs` (Overview · Orders · Quotes · Billing · Facilities · Deals,
each with a count), 10-row pagination, `?tab=` in the URL. No API change.
Files: `Customer360Sections.vue` (primary), new `Customer360Pager.vue`, `customer360.js`
(`TABS`, `tabFromQuery`, `paginate`, `needsAttention`), `Customer360.vue` (tab ↔ URL).
