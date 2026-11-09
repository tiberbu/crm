# CX facility page — tabbed records and registry notice removal

Status: **Implemented** (S1–S5) · Date: 2026-11-09 · Scope: CX portal facility page
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
- **History is capped without any warning.** All rows arrive in one `get_portal_context`
  payload and are filtered per facility in the browser. The facility's rows come from
  `account_billing` (`portal_commercial.py`), which reads at most **200** orders, 200 invoices
  and 200 payments **per customer account**, and the facility row keeps at most **100** orders.
  Accounts with many facilities, or a long history, lose older records with no notice.

  *Correction (found during build):* the first draft of this doc said paid invoices were not
  listed and payments stopped at 50. Those limits belong to the account-level lists
  (`open_invoices`, `_customer_payments`) used elsewhere in the portal. The facility page already
  received paid invoices; the real gap is the 200/100 caps above.

  Adding tabs on top of this payload would only put capped lists in nicer containers.
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
│ │ Reference · date · links      Status   Amount   Action             │ │
│ │ …20 rows…                                                          │ │
│ │ Showing 1–20 of 100              ‹ Previous   1 / 5   Next ›       │ │
│ └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

- **Tabs:** Overview (Facility profile) · Quotes (only when `showQuote`) · Orders · Invoices ·
  Payments · Billing (the current "Billing information" card).
- **Counts** appear in tab labels from server totals. Invoices also shows the number due.
- **Panel content:** one row per document (reference, date, links, status, amount, action), the
  same row markup as before, laid out so that on mobile the status, amount and action wrap under
  the reference. Each list has a search box, a status filter and 20 rows per page, newest first. The Invoices tab
  opens with the "Needs action" (outstanding) filter on, and the user can switch to All.
- **Stepper** becomes a status strip. Clicking a stage selects its tab.
- **Cross-document links** (invoice → order, order → quote) switch to the target tab, open the
  page that contains the row, and highlight it. They no longer scroll the whole page.
- **Opening on a tab:** `FacilitySingleView` takes an `initialTab` prop. The dashboard's invoice
  "Review →" opens the facility on Invoices, and the go-live "Review invoice" button switches to
  Invoices. *Deviation:* there is no `?tab=` URL parameter, because the CX portal has no router
  and the facility view itself is not URL-addressable, so a tab-only parameter would not survive
  a refresh.
- Row actions stay the same: review order, create invoice, pay (M-Pesa / Paystack), pending
  verification state.
- Also fix the Facility profile card's stray `mx-4 my-5` margins, which misalign it with
  sibling cards.

### Data contract (built)

`crm.api.facility_documents.get_facility_documents` (GET/POST, signed-in portal users)

| Arg | Notes |
|---|---|
| `customer`, `mfl_code` | The customer must be granted to the user (`get_user_customer_names`), and the MFL must belong to that customer through a facility membership or a deal facility row. Otherwise `PermissionError`. |
| `kind` | `order` \| `invoice` \| `payment` (quotes stay in the portal context: they are few) |
| `start`, `page_length` | `page_length` ≤ 50, default 20 |
| `status` | invoices: `outstanding` \| `all` (default `all`) |
| `search` | optional; matches the document name, invoice number, payment reference and linked documents |

Returns `{ rows, total, start, page_length, counts: {all, outstanding}, truncated }`. Rows come
from the same loaders and attribution as `account_billing` (`account_orders`,
`account_invoices`, `_account_payment_rows`, now with a `limit` argument), so they have the same
shape as the rows the page already rendered. History is read up to 5,000 rows per customer;
`truncated` reports when that ceiling is hit. Invoices sort open-first by due date, then paid
newest first; orders and payments sort newest first.

`crm.api.facility_documents.get_facility_document_counts(customer, mfl_code)` returns
`{order, invoice, invoiceDue, payment}` for the tab labels, with the same authorization check.

**Which facilities use it:** facilities that carry a `customer` (customer-linked accounts) page
on the server. Opt-in-only facilities (no customer yet) page the rows already in the portal
context in the browser, using the same helpers.

### Component choice (Context7-checked)

Context7's frappe-ui docs describe the current `Tabs` API: value-based `v-model`, a
`TabItem.condition`, and `#tab-label` / `#tab-panel` slots. This repo pins
**frappe-ui 1.0.0-beta.24**, whose `Tabs.vue` is **index-based** (`:value="i"`), uses a
`#tab-item` slot, and renders a `TabsContent` for every tab. Do not copy the main-branch
examples.

Use frappe-ui `Tabs` as the beta.24 API defines it: reka-ui gives keyboard roving focus and ARIA
for free. Apply CX styling through `#tab-item`. Map index ↔ tab key in one small pure helper
(`utils/facilityTabs.js`: tab list from the facility state, index ↔ key, local filtering and
paging). Unit-test that helper. beta.24 unmounts inactive panels, so each list's search, filter,
page and server rows live in a map `BillingJourney` provides, and switching tabs keeps them. If the pin is upgraded later, only the helper changes. Do not hand-roll another tablist:
`FinanceSectionTabs.vue` has no arrow-key navigation.

---

## Stories

| # | Story | Status |
|---|---|---|
| S1 | Remove the registry notice and the CX sync badge, and reword the no-FID line (F1.1–F1.3) | Done |
| S2 | `get_facility_documents` and `get_facility_document_counts` paged endpoints, with authorization and Python tests | Done |
| S3 | Tabbed facility page: tabs with counts, paged and searchable lists, invoice filter, stepper → tab, cross-links → tab + page + highlight, `initialTab` | Done |
| S4 | Slim the `get_portal_context` facility rows to actionable records plus `record_counts` | Done |
| S5 | Show the Quote → Order → Invoice → Payment stepper only until the first purchase cycle is complete; afterwards each tab shows an action badge | Done |

## Delivery notes

- **S4: slim context rows.** For customer-linked facilities, `get_portal_context` now sends
  only what the page reads outside its tabs (`portal_commercial.slim_facility_records`):
  - `orders`: draft orders, invoiceable orders, and the latest package order;
  - `invoices`: outstanding invoices only;
  - `payments`: M-Pesa reports pending verification only;
  - `record_counts`: `{order, order_draft, invoice, invoice_due, payment, payment_pending}` over the full attributed history.

  The plan projection (`commercial`) and `invoice_summary` are still computed from the full lists
  on the server before slimming. The journey stepper (`stageStates`) and the tab labels read
  `record_counts`. Opt-in-only facility rows (no customer) are unchanged, because they page locally.
  Account-level lists (`open_orders`, `open_invoices`, `payments`) used by the dashboard and the
  Billing view are unchanged.
- `JourneyStage.vue` (show-5 / "Show all" expander) is removed; `FacilityDocumentList.vue` replaces it.

## S5: stepper only for the first purchase (maintainer request, 2026-11-09)

**Problem.** The stepper picks one "current" stage for the whole facility. A returning customer
can have a draft order, an unpaid invoice and a payment awaiting verification at the same time.
One "current step" then misleads, and it repeats a lesson the customer has already learned.

**Round-table outcome (UX, PM, Architect, Dev, Analyst).**
- The stepper is onboarding: it teaches the first purchase, and its job ends there.
- "Completed once" means **a paid invoice or a recorded payment exists** for the facility. A paid
  invoice includes a zero-amount (free) invoice. Drafts, unpaid invoices and M-Pesa reports
  pending verification do not count.
- After that, status lives on the tabs. Each tab shows what is waiting: Orders "*n* to review"
  (drafts), Invoices "*n* due", Payments "*n* pending" (M-Pesa reports awaiting verification).
  Three documents at three stages show three badges, not one step.
- Rejected: one stepper per document (it rebuilds the stacked layout); a "latest document"
  stepper (it hides the other documents); keeping the stepper with a caption (the same noise).

**Built.** `journeyCompleted({ invoices, payments, counts })` in `utils/portalCommercial.js`
decides. With slim context rows it reads `record_counts` (`invoice > invoice_due` or
`payment > payment_pending`), otherwise the rows. `BillingJourney` renders the stepper only when
it returns false. `facilityTabs()` returns a `badge` per tab: `orderDraft` and `paymentPending`
come from the context row, which always carries drafts and pending reports, and `invoiceDue`
comes from the counts.

**Checked.** On 28 real dev facilities, 14 have completed a cycle and no longer see the stepper.
For all 28, the slimmed row plus counts gives the same answer as the full history.

## Verification (2026-11-09)

- Frontend unit tests: `yarn test:run`, 307 passed (S5 adds `journeyCompleted` and tab badge tests), including 8 new `facilityTabs` tests and a `stageStates` counts test.
- Facility page browser suite (`npx playwright test -c playwright.facility.config.ts
  e2e/regression/facility-single-view.spec.ts`), run against the built bundle with the API faked: all
  passed. It covers 100 orders, invoices and payments on both the server and local paths (page height
  under 4,000px, 20 rows per page, search, invoice filter, state kept across tabs, a cross-link
  to a later page), server paging requests, a 375px layout with no horizontal scroll,
  "Review invoice" → Invoices, and no verification wording or badge for a `Manual` FID.
- Python: `crm.tests.test_facility_documents` (9) and `crm.tests.test_facility_documents_pure`
  (10, including `slim_facility_records`), all passed. They ran on the dev site through the scratch runner, with commits stubbed, network and jobs blocked,
  everything rolled back, and the before/after row-count snapshot unchanged.
- The `account_billing` refactor gives identical output: a digest of 7 customers / 86 rows was the same before and after.
- Live comparison as real portal users (read-only, rolled back): 28 customer-linked facilities,
  server counts and invoice lists matched the portal context, 0 mismatches.
- S4 checks on the dev site (read-only, rolled back):
  - with the real `stageStates`, stepper states on full rows and on slimmed rows plus counts were
    identical for 28 real facilities, with and without a quote stage;
  - `record_counts` equalled the server counts for all 28;
  - across 25 portal users, the facilities payload went from 104 KB to 93 KB. Dev history is
    small; the saving grows with history, because paid records no longer travel.
- Pre-existing, unrelated: `e2e/regression/facility-onboarding-network.spec.ts` (6 tests)
  also fails on `develop` without these changes ("Start your onboarding" button not found).

## Decisions (approved by the maintainer, 2026-11-09)

1. **F1.2:** keep the reworded no-FID line: *"Add this facility's HFR Facility ID to enable deployment and setup."*
2. **F1.3:** remove the `Manual` / `HFR Verified` badge from the customer page. Desk views keep it.
3. **Tabs:** Facility profile becomes the **Overview** tab, which is the default tab.
4. **History:** under *All*, customers see paid invoices and fully billed orders.
