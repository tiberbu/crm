# CX facility page — tabbed records and registry notice removal

Status: **Approved — ready to build** · Date: 2026-11-09 · Scope: CX portal facility page
(`frontend/src/pages/FacilityPortal/FacilitySingleView.vue` and `components/BillingJourney.vue`).

Reviewed in a BMAD round-table (UX, PM, Architect, Dev, Analyst). Two problems:

1. Quotes, Orders, Invoices, Payments and Billing information are stacked as full-width
   sections on one long page. This does not scale, and the page shows only part of the history.
2. The facility profile footer says
   *"FID … is saved, but this profile has not been verified against the Health Facility Registry."*
   The statement is wrong and must be removed.

---

## 1. Remove the "not verified against the Health Facility Registry" statement

### What is wrong

`FacilitySingleView.vue:959-964` shows a warning strip whenever
`hfr_sync_status !== 'HFR Verified'`. That field does not mean "verified". It records
**how the FID got onto the row**:

| Value | Set by | Meaning |
|---|---|---|
| `HFR Verified` | `crm/api/hfr.py:132`, `add_facility_from_hfr` (`customer_experience.py:1086, 1138`), `record_facility_id(source="hfr")` | FID came from a registry lookup in this app |
| `Manual` (field default) | `record_facility_id(source="manual")`, staff entry, backfill patches | FID was typed in or carried over |

Every FID, whichever way it was entered, is issued by the regulator-run registry.
Facilities that were added by looking up the owner's ID and querying the registry are
registry-sourced. So telling a customer the profile "has not been verified" is
false, and it hurts trust.

### Fix

- **F1.1** Delete the saved-FID branch of the warning strip. No customer-facing text may say
  the profile is unverified, pending verification, or not checked against the registry.
- **F1.2** The strip should appear **only** when there is no FID at all, and must not use the word
  "verified": *"Add this facility's HFR Facility ID to enable deployment and setup."* The
  **Contact network support** button stays.
- **F1.3** Remove the `hfr_sync_status` badge (`FacilitySingleView.vue:927-930`) from the CX
  page. It shows `Manual` with an amber dot, which carries the same false message. The
  `Synced <date>` text can stay. Desk views (Lead, Deal, Organization) keep the badge,
  because there it is useful to staff as data provenance.
- **F1.4** No backend or data change is needed. `hfr_sync_status` stays as an internal provenance field.
- The FID stays prominent on the page. This follows the rule that every facility screen shows the HFR Facility ID.

**Acceptance:** for a facility with an FID, whatever its `hfr_sync_status`, the page shows no
verification wording and no amber badge. For a facility with no FID, the page shows the F1.2 line.

---

## 2. Replace stacked sections with tabs

### What is wrong at 100 records each

- **Page length.** Four `JourneyStage` cards plus Billing information plus the Facility profile are
  stacked under the HMIS block. Each stage shows 5 rows and has a *Show all N* button that
  expands the list in place. Expand one stage with 100 rows and the page gains about 100 × 56px ≈ 5,600px.
  Expand all four and the page is more than 20,000px. The Facility profile ends up far down the page.
- **Cross-links scroll the page.** `jumpTo()` expands a stage and scrolls to an element. With long
  lists, the user loses their place.
- **History is incomplete without any warning.** All rows arrive in one `get_portal_context`
  payload and are filtered per facility in the browser:
  - Payments: `limit_page_length=50` **per account** (`website_redirect.py:1177`). In a
    multi-facility account, older payments are dropped.
  - Invoices: only rows with `outstanding_amount > 0` (`website_redirect.py:1097-1100`). Paid
    invoices are not listed.
  - Orders: only `per_billed < 100`, capped at 200 (`customer_experience.py:174-180`).

  Adding tabs on top of this payload would only put truncated lists in nicer containers.
  The tabs need data that can be paged.
- **Mobile.** The design pattern requires tables to have a card or responsive alternative. Long
  lists of cards with no paging do not meet that requirement.

### Target layout

```
┌ Facility header · FID · MFL · summary cards ───────────────────────────┐
│ HMIS implementation (setup journey / live site)  — unchanged           │
│ Go-live token allocation — unchanged                                   │
├────────────────────────────────────────────────────────────────────────┤
│ Journey stepper  Quote ✓ — Order ✓ — Invoice ● — Payment ○  (compact)  │
├────────────────────────────────────────────────────────────────────────┤
│ [Overview] [Quotes 3] [Orders 12] [Invoices 100 · 2 due] [Payments 98] [Billing] │
│ ┌ panel ─────────────────────────────────────────────────────────────┐ │
│ │ search · status filter (Invoices default: "Needs action")          │ │
│ │ Ref        Date        Status     Amount     Action                │ │
│ │ …20 rows…                                                          │ │
│ │                         ‹ 1 2 3 4 5 ›   Showing 1–20 of 100        │ │
│ └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

- **Tabs:** Overview (Facility profile) · Quotes (only when `showQuote`) · Orders · Invoices ·
  Payments · Billing (the current "Billing information" card).
- **Counts** appear in tab labels from server totals. Invoices also shows the number due.
- **Panel content:** a table on desktop with columns Ref, Date, Status, Amount, Action. On mobile, the same rows
  appear as cards. Each list has a search box, a status filter and 20 rows per page, newest first. The Invoices tab
  opens with the "Needs action" (outstanding) filter on, and the user can switch to All.
- **Stepper** becomes a status strip. Clicking a stage selects its tab.
- **Cross-document links** (invoice → order, order → quote) switch to the target tab, open the
  page that contains the row, and highlight it. They no longer scroll the whole page.
- **Deep link:** the selected tab is stored in the route query (`?tab=invoices`). Token
  alerts, "Pay" prompts and refreshes then land on the right tab.
- Row actions stay the same: review order, create invoice, pay (M-Pesa / Paystack), pending
  verification state.
- Also fix the Facility profile card's stray `mx-4 my-5` margins, which misalign it with
  sibling cards.

### Data contract (new)

`crm.api.customer_experience.get_facility_documents`

| Arg | Notes |
|---|---|
| `mfl_code` | Facility the portal user is entitled to (same ownership check as `get_portal_context`) |
| `kind` | `quote` \| `order` \| `invoice` \| `payment` |
| `start`, `page_length` | `page_length` ≤ 50, default 20 |
| `status` | optional; for invoices `outstanding` \| `all` |
| `search` | optional, matches document name |

Returns `{ rows, total, counts }`. Rows use the same shape as `_order_rows`,
`_invoice_rows` and `_customer_payments`, so the existing row templates and helpers
(`portalCommercial`, `portalOrderState`) can be reused. Include paid invoices and
fully billed orders when `status=all`. `get_portal_context` keeps returning only what the
summary cards and stepper need (counts, open invoice, outstanding total), so the first load
gets lighter rather than heavier. Each tab fetches its first page the first time it is opened.

### Component choice (Context7-checked)

Context7's frappe-ui docs describe the current `Tabs` API: value-based `v-model`, a
`TabItem.condition`, and `#tab-label` / `#tab-panel` slots. This repo pins
**frappe-ui 1.0.0-beta.24**, whose `Tabs.vue` is **index-based** (`:value="i"`), uses a
`#tab-item` slot, and renders a `TabsContent` for every tab. Do not copy the main-branch
examples.

Use frappe-ui `Tabs` as the beta.24 API defines it: reka-ui gives keyboard roving focus and ARIA
for free. Apply CX styling through `#tab-item`. Map index ↔ tab key in one small pure helper
(`utils/facilityTabs.js`: tab list from the facility state, and query ↔ index). Unit-test that
helper. If the pin is upgraded later, only the helper changes. Do not hand-roll another tablist:
`FinanceSectionTabs.vue` has no arrow-key navigation.

---

## Stories

| # | Story | Size |
|---|---|---|
| S1 | Remove the registry notice and the CX sync badge, and reword the no-FID line (F1.1–F1.3) | XS, can ship alone |
| S2 | `get_facility_documents` paged endpoint, with entitlement check and Python tests | M |
| S3 | Tabbed facility page: tabs, query-param state, paged table/card lists, stepper → tab, cross-links → tab + highlight | M |
| S4 | Slim `get_portal_context` to summary data and remove the per-facility client filtering it replaces | S |

## Verification plan

- `cd frontend && yarn test:run`, with new unit tests for `utils/facilityTabs.js`.
- Python: `scripts/run-crm-tests.sh <test-site> --module crm.tests.test_facility_documents`
  (always `--app crm`, never on the reference site).
- Browser check on a dev site with a seeded facility that has 100 orders, 100 invoices
  (mixed paid and outstanding) and 100 payments. Check page height, paging, deep links, cross-links,
  mobile cards at 375px, and that no verification wording appears for `Manual` FIDs.

## Decisions (approved by the maintainer, 2026-11-09)

1. **F1.2:** keep the reworded no-FID line: *"Add this facility's HFR Facility ID to enable deployment and setup."*
2. **F1.3:** remove the `Manual` / `HFR Verified` badge from the customer page. Desk views keep it.
3. **Tabs:** Facility profile becomes the **Overview** tab, which is the default tab.
4. **History:** under *All*, customers see paid invoices and fully billed orders.
