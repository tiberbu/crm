# Multi-year Opt-In quoting and quarterly billing

**Status:** Implementation baseline — review and staged deployment required

**Scope:** CRM Opt-In portal, quotation/contract hand-off, quarterly order and
invoice scheduling, optional-service information, and migration of existing
Opt-Ins.

The implementation is additive and keeps the existing one-price-list,
one-quotation path working. JSON bundle metadata is used first so the migration
is safe on CRM-only sites and on Frappe v15 installations where the optional
ERPNext fields may not exist yet. Existing-submission synchronization is
available as a Sales Manager-only, per-network action; it adds missing yearly
quotations without changing accepted line values or executed contracts.

## Confirmed business rules

1. A selected subscription term produces one ERPNext **Quotation per year**.
   Each yearly quotation contains subscription lines only.
2. The Opt-In Submission remains the single customer acceptance and signing
   process. It owns the collection of yearly quotations and one CRM Contract.
3. Optional hardware and services are informational at Opt-In/contract time.
   They are shown in a clear internal-use table, are not added to the yearly
   subscription quotations, and are not invoiced automatically. Internal teams
   may quote or invoice them later as required.
4. The customer can select at least three years. The proposed UI offers the
   years configured by the network, with three years as the default selection.
   Existing one-price-list networks and old invitations retain their current
   one-quotation behavior.
5. Billing is quarterly for each selected year. For each yearly quotation, the
   system creates four Sales Orders and four Sales Invoices (one order/invoice
   pair per quarter) in the native ERPNext flow. A five-year selection therefore
   produces five yearly quotations and twenty order/invoice pairs.
6. The first invoice date is configured per network. The default is three months
   after the Opt-In Submission date. Every invoice's due date is 30 days after
   its invoice date. Subsequent quarters follow the same three-month cadence.
7. Existing Opt-Ins are represented as a truthful Year 1 bundle. A later sync
   action may add missing years without changing existing signatures.

## Current one-value assumptions found in the repository

The following are concrete compatibility seams that the implementation must
preserve rather than replace in place:

- `CRM Opt-In Network.price_list_override` is a single Link.
- `CRM Facility Membership.price_list_override` is a single Link.
- `CRM Opt-In Submission.contract` stores one contract.
- `CRM Contract.quote` stores one quotation.
- `crm.api.optin.get_pricing()` still returns the first plan in its legacy keys,
  with all selected plans in additive `plans` and `selected_years` keys.
- `crm.api.optin._process_submission()` still creates the primary Quotation,
  then adds one native Quotation for every additional selected year.
- `crm.api.lifecycle` still returns singular primary links and now also exposes
  `quotations` and `sales_invoices` collections.
- Existing single-quote consumers continue to use the primary quote; the
  Opt-In pricing and Deal quote surfaces expose the yearly collection.
- Legacy non-Opt-In quotation acceptance still uses the single-quotation path
  (`accept_quote` → native `make_sales_invoice`) and is unchanged. The new
  multi-year Opt-In flow uses the scheduled quarterly billing service described
  below; it does not call `accept_quote` and does not create an invoice at
  acceptance time.

These paths are used by existing one-year submissions and must stay valid.

## Additive data model (implemented baseline)

ERPNext remains the source of truth for Items, Item Prices, Price Lists,
Quotations, Sales Orders, Sales Invoices, and Payment Entries. CRM adds only
the grouping, provenance, and schedule metadata needed to represent one Opt-In
bundle.

### Network configuration

The first migration stores the ordered yearly configuration as JSON in
`CRM Opt-In Network.price_lists_json` and keeps the existing
`price_list_override` field as the Year 1 fallback. This avoids making a new
child DocType mandatory during a rolling deployment. Each entry has:

| Field | Purpose |
|---|---|
| `year_number` | Explicit year identity (1, 2, 3, …) |
| `price_list` | Link to an enabled selling Price List |
| `label` | Human-facing label in the portal |
| `enabled` | Allows a year to be temporarily unavailable |
| `idx` | Display order |

The resolver uses the JSON rows when configured, then the legacy pointer, then
the settings default. Year identity is explicit and is never inferred from a
price-list name.

Facility membership stores the equivalent year-to-price-list map in
`price_list_overrides_json`; a missing row inherits the network row for that
year. The existing single `price_list_override` remains readable.

Add a network-level `first_invoice_offset_months` setting (default `3`). It is
the number of calendar months after the Opt-In Submission date on which the
first invoice is issued. It must be validated as a positive integer. The
quarterly schedule then advances by three calendar months; each invoice due date
is its issue date plus 30 days.

### Submission and contract quote bundle

The baseline stores the bundle snapshot as JSON on the Submission and Contract
(`pricing_plans_json`, `quote_names_json`, `optional_items_json`, and
`billing_schedule_json`). This is deliberately additive; the existing
`contract` and `quote` links remain the primary compatibility links. Each quote
still has native ERPNext quotation items and is tagged with:

- Submission/Contract parent
- Quotation link
- Year number
- Price List
- Net, VAT, and grand totals snapshot
- Quotation status and invoice/order summary
- Stable bundle key for idempotency

Retain `CRM Opt-In Submission.contract` and `CRM Contract.quote` as the primary
or first-quotation compatibility links. Existing records are not rewritten into
a new required relationship.

### Quotation metadata

Add optional custom fields to ERPNext Quotation:

- Opt-In Submission
- bundle key
- term year
- source Price List snapshot
- network link (already present where applicable)

The quote line remains a native Quotation Item. Subscription lines retain the
existing facility and KEPH provenance fields.

### Quarterly billing schedule

Use the JSON schedule under the Submission bundle rather than a new Package
Billing parent initially. Each row represents one year/quarter pair:

- year number and quarter number
- scheduled order date
- Sales Order link
- invoice date and Sales Invoice link
- invoice due date
- status/error message

Sales Orders and Sales Invoices receive additive CRM links for the Submission,
yearly Quotation, year number, quarter number, and stable billing key. Native
ERPNext due-date and payment-reference behavior remains authoritative.

This is sufficient for reporting and retries. A separate Package Billing
DocType is only warranted later if package-level amendments, consolidated
invoices, or independent renewal lifecycles are required.

### Why the current acceptance path cannot be reused unchanged

`crm.api.quotes.accept_quote` currently submits one Quotation and immediately
calls ERPNext's native `make_sales_invoice` mapper. That path is intentionally
single-document and immediate:

- it submits the quotation instead of creating a future order schedule;
- it creates one invoice now, not four dated quarterly order/invoice pairs;
- it commits inside the adapter, which would break the Opt-In bundle's
  all-or-nothing/idempotent scheduling boundary; and
- it has no year/quarter idempotency key or network-configured first issue date.

The multi-year flow therefore leaves yearly quotations in their normal
CRM-managed state and uses `crm.automation.optin_billing.process_due_optin_billing`
from the scheduler. At each due date it creates the native Sales Order from the
relevant yearly quotation, maps the native Sales Invoice from that order, sets
the configured posting and due dates, and records links/status in the schedule.
The existing acceptance endpoint remains unchanged for non-Opt-In quotations
and legacy one-year records.

For clarity, the current path does **not** create multiple invoices per
quotation. One successful `accept_quote` call submits one quotation and inserts
one Sales Invoice. The endpoint then rejects another acceptance attempt because
the quotation is no longer a draft. The lower-level invoice adapter itself does
not provide an idempotency key, so calling it directly more than once could
insert duplicate invoices; the scheduled implementation must guard against that
with a unique year/quarter schedule row and a document lock.

The annual quotation should remain an annual commercial commitment. It should
not be changed to quantity four merely to make the mapper produce four orders:
that would distort the quotation and contract presentation. Each quarterly
Sales Order/Invoice should instead receive the calculated quarter amount from
the yearly quotation and be linked back to the quotation and its schedule row.

## Optional-service handling

The portal should load optional items from enabled ERPNext Items with valid
selling Item Price records. The server must validate item identity, enabled
status, selling eligibility, and the selected price list; browser-supplied rates
are never trusted.

The Opt-In Submission stores an informational child table containing:

- ERPNext Item
- description
- quantity or requested quantity
- indicative price/list (if shown)
- internal notes

These rows appear in the contract as “Optional services and hardware — quoted
separately”. They do not become Quotation Items, Sales Orders, or automatic
Invoices. Internal sales teams can create a separate quote/invoice later.

The recurrence policy for optional items is intentionally not applied because
they are informational only.

## End-to-end flow

### New prospect

1. `get_settings` returns configured year/price-list options and the network's
   first-invoice offset while retaining
   `default_price_list` for old clients.
2. The portal selects three or more configured years and optional information
   rows.
3. One `get_pricing` request returns all selected yearly subscription prices,
   totals, and optional-item display data. The server batches Item Price reads.
4. Submission validation canonicalizes facilities, year selections, prices,
   and Terms & Conditions before any CRM records are created.
5. One synchronous transaction creates Lead, Contact, Organization, Deal, one
   Quotation per selected year, and one Opt-In Submission quote bundle.
6. One Contract is generated from the bundle. It contains all yearly schedules
   and the optional-service information table. There is one signatory/OTP
   workflow, not one workflow per quotation.
7. Contract completion sends one fully executed PDF containing the complete
   selected pricing schedule.
8. Quarterly Sales Orders and Sales Invoices are generated from the schedule at
   their scheduled issue dates. They are not created immediately by quote
   acceptance. The first issue date is Opt-In date plus the configured network
   offset (default three months), and each invoice due date is issue date plus
   30 days.

### Existing opted-in member synchronization

The additive fields and immutable-contract guards are in this baseline. A
Sales Manager-only “Sync configured pricing” action on the Network page resolves
the current network/facility configuration and reports a per-submission result:

1. Resolve network and facility yearly configuration using child rows first,
   then legacy single overrides.
2. For each existing submission, identify missing year/price-list quotations by
   bundle key.
3. Create only missing draft/sent quotations and billing schedule rows.
4. Do not modify signed signatory rows, signature timestamps, contract status,
   or existing quotation amounts.
5. If the contract is unsigned, append missing pricing schedules to the
   existing contract and log the change.
6. If the contract is fully executed, leave it immutable and report the row as
   locked. Additional years then require a new amendment/new Opt-In version
   rather than rewriting signed content.
7. Make the operation idempotent and show a result summary: created, skipped,
   locked, and failed rows.

## API compatibility strategy

The first implementation should extend existing endpoints with optional
arguments and additive response keys:

- Existing requests without year selections return the current one-year shape.
- New requests include `plans`/`quotes`, `selected_years`, and optional-service
  information while still returning legacy aggregate fields.
- Invitation tokens carry the Submission/Contract bundle identity; legacy tokens
  carrying one `price_list` remain readable.
- Existing `build_ois_quote` and lifecycle consumers resolve the primary quote;
  new consumers use the quote collection.
- All writes use a stable `(submission, year, price_list)` idempotency key and
  one transaction/savepoint policy.

## UI plan (premium frappe-ui, desktop-preserving)

### Opt-In Pricing

- Prominent “Choose your subscription term” control with 3/4/5-year options
  (or all years configured by the network).
- One compact summary showing selected years, total commitment, annual totals,
  VAT, and optional information count.
- Year selector lets the reviewer inspect each selected year's facility rows;
  the commitment summary remains visible while switching years.
- Optional services in a separate, clearly labelled information section.
- Sticky mobile summary/footer so totals and Continue remain visible.

### Network configuration

- Reorderable year-to-price-list table with validation for duplicate years and
  disabled/non-selling lists.
- Facility override table supports multiple years and clearly displays inherited
  versus overridden pricing.
- Sync action reports a non-destructive result before and after execution.

### Quote page

- One quote stack grouped by year, with each quotation’s status, price list,
  totals, edit history, and invoice/order schedule.
- Shared contract/signatory panel remains one level above the quote stack.
- Price-list edits remain available only for unsigned yearly quotations and are
  logged in Deal Activity.

### Contract and Opt-In review

- Contract header shows selected term and total commitment.
- Yearly price schedules are visually separated but part of one signed document.
- Optional services table is marked informational and excluded from subscription
  totals.
- Opt-In list/dashboard shows quote count, selected years, commitment, billing
  progress, and one contract/signing status.

## Migration and cleanup sequence

1. Add optional custom fields and JSON bundle metadata; no existing fields are
   removed or made mandatory.
2. Backfill existing submissions to a Year 1 pricing/quote/schedule snapshot
   only when each new field is empty.
3. Backfill accepted contract HTML snapshots only when empty, preserving signed
   content and historical quotation totals.
4. Add the Standard Selling cleanup patch after catalogue schema migration:
   delete only `Item Price` rows for `Standard Selling` whose linked Item name
   starts with `Careverse HMIS Subscription`; never delete the Item record or
   negotiated Item Prices. Update the seed so those rows are not recreated.
5. Make every patch safe on CRM-only installations and safe to run repeatedly.

## Regression and acceptance coverage

### Backend

- Existing one-year Opt-In still creates one quotation and one contract.
- New three-, four-, and five-year submissions create the expected quotation
  bundle and one signing workflow.
- Missing price, disabled list, duplicate year, and optional-item tampering are
  rejected before partial CRM data is committed.
- Quarterly schedule dates and invoice due dates are deterministic and retryable.
- Synchronization is idempotent and never modifies signed rows.
- Invoice/payment links resolve to the correct yearly quotation and network.
- CRM-only installs skip ERPNext-dependent migrations cleanly.
- Frappe/ERPNext v15 and v16 quotation and tax behavior is covered.

### Frontend

- Legacy response shape renders unchanged.
- Year selector, commitment totals, optional information, and quote stack are
  usable on mobile and desktop.
- Network/facility inherited-vs-override states are understandable.
- Quote/contract print previews contain all selected years and omit optional
  services from totals.

### Manual acceptance paths

1. Existing one-price-list invitation → submit → quote → contract → sign.
2. New three-year prospect with optional hardware/services.
3. Four quarterly order/invoice cycles for one selected year.
4. Network adds Year 4 later → sync an unsigned submission.
5. Attempt the same sync twice.
6. Attempt sync after a fully executed contract.
7. Facility and network user-permission views across multiple quotations.

## Deployment notes

- Run migrations before configuring yearly plans. The migration is idempotent
  and does not delete Items or negotiated Item Prices.
- Run the optional-service cleanup after the catalogue patch. It removes only
  Standard Selling Item Price rows whose Item name starts with
  `Careverse HMIS Subscription`; the Item records remain available for history.
- Validate one, three, and five-year submissions in UAT before enabling the
  billing scheduler. Fully executed contracts are read-only and retain their
  accepted HTML snapshot; pending contracts render the currently active T&C.
- Any future sync/amendment action must create missing years only and must never
  rewrite a fully executed contract or existing signatures.
