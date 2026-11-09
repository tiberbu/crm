# Finance Cockpit — Brownfield UX Gap and Action Audit

- **Status:** Audit for planning; no product implementation in this pass
- **Reviewed:** 2026-10-10
- **Baseline:** `upstream/develop` at `76f461a09611d17869a41d1e05252e8ba2ff46c9`
- **Scope:** Quotation, Sales Order, Sales Invoice, Payment Entry, their list/detail/create journeys, and the shared Finance Cockpit UI and Frappe API surfaces they depend on.

## Executive summary

Finance Cockpit already has useful native foundations: Frappe-session access, company-scoped APIs, ERPNext quotation/order/invoice/payment records, create-from flows, a payment allocation composer, invoice balance and submitted-payment history, native print formats, and a signed Opt-In handoff timeline. The work should preserve and connect these capabilities rather than replace them with a parallel accounting system.

The experience still behaves mainly as separate DocType pages. Important transaction context is lost between steps; configured Frappe workflows are not presented as the approval model; the Opt-In first-invoice date is not part of the Quotation → Sales Order mapper; invoice-originated payment creation lands in a read-only Payment Entry layout; and related-document navigation often leaves the cockpit. The shared list layer also has two renderers and does not yet apply the Affiliation module’s cohesive list pattern across the wider blast radius.

The target is a session-authenticated sales-transaction workspace: a person can understand the current state, source data, approvals, balances, relationships, and valid next action for a transaction without needing to reason in raw DocTypes. ERPNext/Frappe remains authoritative for data, permissions, workflow transitions, statuses, calculations, and persisted documents.

## Review basis and scope

- Reviewed the latest fetched `upstream/develop`; the worktree HEAD matches it exactly.
- Traced the four requested transaction sections through their shared list/detail/form components and the corresponding Python endpoints.
- Checked the Opt-In billing schedule and the installed ERPNext mapper/Frappe workflow implementations.
- Compared interaction patterns in CareVerse HQ’s `AffiliationsListView` and `MobileCardView`. The reference is React/Ant Design; borrow its interaction and hierarchy patterns, not its components or dependencies.
- Inspected existing Finance Cockpit specifications, sprint notes, and searchable frontend/backend test coverage.
- This is a source audit, not runtime UAT. No application code was changed and no tests were run.

In-scope shared components include `FinanceTable`, `CrudSection`, `FinanceDetail`, `FinanceForm`, `CreateFromPicker`, `PaymentAllocationForm`, `StatusBadge`, `SectionCard`, and `HandoffTimeline`. The 18 files directly using `FinanceTable` and the five `CrudSection` consumers mean shared UI work also needs regression coverage for payables, expenses, banking, assets, partner, and ledger lists—even though those workflows are not part of this sales-transaction redesign.

The existing [premium list-view spec](../_bmad-output/implementation-artifacts/spec-finance-cockpit-premium-list-views.md) is a useful draft for the shared list language. It does not yet cover the full transaction, approval, source-data, or related-record journeys in this audit.

## Current capabilities to preserve

| Surface | What already works | Evidence |
|---|---|---|
| Frappe access | The Finance page rejects Guest and gates the workspace to Accounts User/Accounts Manager; finance API boundaries also enforce access, company scope, and document permissions. Requests use Frappe resources/session rather than a separate token layer. | [`finance_cockpit.py`](../crm/www/finance_cockpit.py#L10), [`access.py`](../crm/finance/access.py#L14), [`api.py`](../crm/finance/api.py#L2595) |
| Quotation | Finance can inspect native quotation fields and statuses; a submitted quotation can be mapped to a Sales Order through ERPNext’s native mapper. | [`Quotes.vue`](../frontend/src/pages/FinanceCockpit/sections/Quotes.vue#L1), [`FinanceDetail.vue`](../frontend/src/pages/FinanceCockpit/components/crud/FinanceDetail.vue#L133), [ERPNext quotation mapper](../../../apps/erpnext/erpnext/selling/doctype/quotation/quotation.py#L356) |
| Sales Order | The list includes delivery date, billing status, and native status. Detail checks for existing invoices and server-side invoice generation is guarded against duplicates. | [`Orders.vue`](../frontend/src/pages/FinanceCockpit/sections/Orders.vue#L1), [`api.py`](../crm/finance/api.py#L1257) |
| Sales Invoice | The receivables list surfaces due date, overdue days, total, and outstanding balance. Detail already shows outstanding balance and a retryable payment-history panel; a submitted invoice can seed a Payment Entry. | [`Invoices.vue`](../frontend/src/pages/FinanceCockpit/sections/Invoices.vue#L1), [`FinanceDetail.vue`](../frontend/src/pages/FinanceCockpit/components/crud/FinanceDetail.vue#L248), [`api.py`](../crm/finance/api.py#L1371) |
| Payment Entry | The Payments section has an amount-first allocation composer with customer balance context, invoice allocation, review, and server-side balance validation. | [`PaymentAllocationForm.vue`](../frontend/src/pages/FinanceCockpit/components/crud/PaymentAllocationForm.vue#L105), [`api.py`](../crm/finance/api.py#L1427) |
| Print/email | Native formats exist for all four documents; print URLs preserve ERPNext letterhead, and single-record detail offers “Print” and “Email copy” using the configured format/letterhead. | [`print_formats.py`](../crm/finance/print_formats.py#L10), [`printFormats.js`](../frontend/src/pages/FinanceCockpit/constants/printFormats.js#L1), [`SendDocumentDialog.vue`](../frontend/src/pages/FinanceCockpit/components/crud/SendDocumentDialog.vue#L73) |
| Opt-In handoff | The backend reads the Year 1/Q1 schedule and the dashboard timeline exposes the signed handoff and its next step. | [`api.py`](../crm/finance/api.py#L1072), [`HandoffTimeline.vue`](../frontend/src/pages/FinanceCockpit/components/HandoffTimeline.vue#L1) |

## Gaps and recommended actions

Priority guide: **P0** = settle before interaction/API design; **P1** = core journey work; **P2** = quality and release hardening.

| ID / priority | Gap and evidence | What to do |
|---|---|---|
| G1 · P0 | **The product model is still four DocType sections, not one transaction journey.** The shell navigates among independent Quotes, Orders, Invoices, and Payments sections. The signed-handoff timeline is a useful special case, but it is limited to Year 1/Q1 facility handoffs. | Define a transaction-centered information architecture: lifecycle overview, actionable queues, and a consistent record view that carries source, customer, amount, status, dates, approval, and related-record context forward. Keep DocType names as record metadata, not the primary mental model. |
| G2 · P0 | **Configured workflows are not the cockpit action model.** Detail exposes hard-coded Submit/Cancel based on `docstatus`; generic forms call `frappe.client.submit`; payment creation inserts and submits directly. No Finance Cockpit call to `get_transitions` / `apply_workflow` was found. Frappe’s native workflow API returns allowed transitions and applies configured transition behavior. | At runtime, resolve available native workflow transitions for the current user/document and display those actions plus the current workflow state. Use Frappe’s `apply_workflow` path when a workflow is configured; retain native submit/cancel only when no workflow applies. Show transition history/reason where available. Never invent or persist a cockpit-only status. |
| G3 · P1 | **Quote → Order does not hydrate the Opt-In first invoice date into `delivery_date`.** `Orders.vue` calls ERPNext’s standard quotation mapper. That mapper copies quotation data and recalculates totals, but it does not read `CRM Opt-In Submission.billing_schedule_json`. The schedule is currently returned separately by the handoff API. | Add a session- and permission-checked server mapping/preparation method that composes the native ERPNext mapped document with the linked Opt-In Year/Quarter schedule. Seed Sales Order `delivery_date` from the first invoice date as requested, expose the schedule/date provenance in the review step, and let the user correct it only under the agreed business rule. Handle absent/unconfigured schedule explicitly. |
| G4 · P1 | **Create-from source selection is blind.** `CreateFromPicker` requests only `name` and one subtitle field, then shows a label such as record ID plus customer. It does not help distinguish records by value, transaction/validity date, delivery/scheduled date, status, or line summary. | Show a compact source preview before mapping: customer/party, native status, date/validity, total/currency, linked Opt-In schedule where applicable, and a short item summary. Keep the picker company-scoped and use Frappe permissions for records/actions. |
| G5 · P1 | **Order → Invoice persists before the user reviews the mapped invoice.** The “Generate invoice” action calls `make_sales_invoice_from_order`, which maps and inserts a draft on the server and returns only its name/docstatus. Unlike Quote → Order, it does not enter a seeded review form first. | Split preparation from persistence: show the mapped invoice, dates/terms/taxes/items and totals for review; then create the draft explicitly. If immediate draft generation is an intentional one-click workflow, label it as such and show a confirmation/progress/result state before moving to the invoice detail. Keep the server duplicate guard and transaction locking. |
| G6 · P1 | **Invoice → Payment is not an editable payment workflow.** Invoice detail maps a Payment Entry into generic `FinanceForm`; the Payment Entry layout marks party, posting date, mode, paid amount, unallocated amount, and references read-only. `FieldRenderer` honors those flags. This conflicts with the separate amount-first payment composer, which supports partial allocations and references. | Route “Create payment” from an invoice into a payment composer seeded with that invoice/customer/company/currency and current outstanding amount. Allow a partial amount, payment date/mode/reference, and allocation review; show the live remaining balance. Keep server-side revalidation against current outstanding balance immediately before insert/submit. |
| G7 · P1 | **Payment visibility means submitted allocations, not all relevant payment records.** Invoice payment history and the Payments list filter `Payment Entry.docstatus = 1`; pending/draft or workflow-review payments are omitted. The invoice detail’s current history is valuable but therefore incomplete for an approval-aware portal. | Separate ledger-applied payments from pending payment documents. Return all records the current Frappe user may read, with native docstatus/workflow state and allocated amount; label pending vs applied clearly. Continue to derive the authoritative invoice balance from ERPNext `outstanding_amount`, not by summing client-side rows. |
| G8 · P1 | **Related-document navigation is fragmented and often exits to Desk.** Sales Order billing links open `/app/sales-invoice`; invoice payment history links open `/app/payment-entry`; Payment Entry references render as plain text; invoice-related links only cover CRM Deal/Quote. Quote detail does not present its downstream order/payment chain. | Build one related-transactions panel for all four documents, with native status, key date/amount, permission-aware cockpit navigation, and the next valid action. Keep Desk links as an explicit fallback. Make detail/create states addressable in the URL and preserve browser back/refresh behavior. |
| G9 · P1 | **Two shared list renderers create inconsistent visual and interaction systems.** `FinanceTable` is used by 18 files; `CrudSection` is used by five core CRUD/list sections. The current mobile `CrudSection` card is derived from only the first two columns, first currency/status fields, and modified/owner; it omits other important fields such as delivery date, overdue age, billing state, and row actions. | Centralize Finance typography, spacing, surfaces, filter/action bar, semantic status, focus, loading/empty/error, pagination, and mobile-card contracts. Bring both shared renderers onto the same primitives, then inventory and regression-test every consumer; avoid per-section one-off styling. |
| G10 · P1 | **Lists expose work queues but not full lifecycle visibility.** Quotes and Orders include drafts/submitted records; the invoice AR endpoint intentionally returns only submitted invoices with positive outstanding balances; the Payments endpoint returns only submitted Receive entries. Thus “All” does not mean all records/states across the four sections. | Keep task queues focused, but add clearly named saved views or tabs for Drafts/Approval, Outstanding, Paid/Closed, and Cancelled where permitted. Show active filter count and a one-step clear action; explain why a record is absent from a queue rather than implying it does not exist. |
| G11 · P1 | **The access/ownership boundary is unresolved for a sales-transaction portal.** The page/API gate is Accounts User/Accounts Manager; Quotations are explicitly read-only for Finance and have no Create action. | Decide whether Sales roles use this portal or whether quote creation remains in CRM/Opt-In. If Sales is in scope, make action availability derive from native Frappe document permissions and configured workflows per doctype; keep backend permission checks authoritative and avoid broadening access through frontend-only role checks. |
| G12 · P1 | **The create form preserves mapped fields that its curated layout does not show.** `FinanceForm` renders only fields listed in `formLayouts`; `sanitizeSeed` deliberately preserves additional mapped fields for save. Therefore hidden source values can be carried without being visible for review. | Make inherited/source-derived data visible in labeled sections, including terms, schedule, tax/payment terms, ownership/provenance, and custom Opt-In links that matter to the action. Distinguish read-only inherited values from user-editable adjustments, and explain recalculated totals. Do not promise “review every field” unless every material field is actually represented. |
| G13 · P2 | **Print/document delivery exists, but verification is shallow; list “Print” is a different operation.** Single-record print/email correctly selects the native formats and letterhead. Current frontend tests verify format mapping and URL flags; the backend patch test verifies delegation to the bootstrap, not actual rendered output/email. Separately, `CrudSection.printAll` builds popup HTML by interpolating labels and record values and is not an ERPNext letterhead document print. | Preserve the four native formats and single-record email-copy action. Add site-backed rendering/email checks for all four formats with configured Letter Head. Rename list printing to “Print list” or remove it in favor of export; if retained, safely escape values or render through a safe DOM/template rather than injecting record values into `document.write`. |
| G14 · P0 | **Journey-level regression evidence is missing.** The searched frontend unit suite covers finance errors/inputs/print helpers, not the four section components or their end-to-end create/detail paths. Backend finance tests cover access and schedule parsing, but the searched tests do not exercise the invoice/payment APIs, workflow integration, or source-to-target UI behavior. Sprint notes also identify browser workflow and accessibility/UAT as remaining gates. | Add pure frontend tests for mapping/state/amount derivations; Frappe tests for roles, company/document permissions, workflow/no-workflow paths, schedule mapping, invoice duplicate/partial-billing rules, payment allocation, and pending/applied history; then authenticated browser tests for the complete Quote → Order → Invoice → Payment journeys on `cr-dev`, including narrow viewports, keyboard, and screen-reader checks. |
| G15 · P2 | **The current list-level Print action interpolates untrusted values into a same-origin popup.** `printAll` concatenates row fields into HTML and writes it with `document.write`; document names/customer data can contain markup. | Replace with safe DOM construction or an escaping utility and add a regression test with HTML-like values. Keep this separate from the professional native print formats. |

## CareVerse Affiliation patterns to adapt

The benchmark’s strengths are interaction structure, not its React/Ant Design implementation:

- A contextual module header with a clear primary action and supporting actions.
- A cohesive filter bar with active-filter count, visible clear behavior, and status meanings.
- Compact summary cues that answer operational questions; Finance summaries should use server-backed totals and avoid duplicate/ambiguous metrics.
- A framed desktop table with readable hierarchy, semantic status, and deliberate row actions.
- A purposeful mobile card with identity, status, key financial/date metadata, and actions. In-card actions must not trigger row navigation.
- Consistent loading skeletons, empty states, and retryable errors.
- Permission-aware actions and keyboard-accessible controls.

Implement these using CRM/Frappe Vue primitives and existing `ink-*`, `surface-*`, and `outline-*` tokens. Do not import CareVerse’s Ant Design components, CSS, or dependencies. Reference: [AffiliationsListView.tsx](../../../apps/careverse_hq/frontend/src/components/modules/affiliations/AffiliationsListView.tsx#L607), [MobileCardView.tsx](../../../apps/careverse_hq/frontend/src/components/shared/MobileCardView/MobileCardView.tsx#L1).

## Recommended target journeys

1. **Quotation → Sales Order:** open a quote with customer, commercial terms, items/taxes, native status, validity, CRM/Opt-In provenance, and existing downstream orders visible. “Make order” is available only when native permission/workflow permits. The review state shows all mapped fields and carries the Opt-In first-invoice date into `delivery_date` with its source visible.
2. **Sales Order → Sales Invoice:** show delivery/billing progress, source quote, schedule, and existing invoices. Prepare a native mapped invoice for review before saving; expose a clear “Create draft invoice” action, then land on the new invoice detail.
3. **Sales Invoice → Payment Entry:** lead with invoice total, amount paid, current outstanding balance, due/overdue state, and applied/pending payments. “Create payment” opens an invoice-seeded composer with an editable amount and allocation, and posts/submits through the applicable native workflow.
4. **Payment Entry → Invoice(s):** show every allocation as a cockpit link with the amount and native state. The invoice and payment details remain navigable in both directions.
5. **All journeys:** show native status and configured workflow actions, preserve company context and Frappe session, provide loading/empty/error/retry states, and keep browser back/refresh behavior predictable.

## Recommended delivery order

### Phase 0 — Resolve business and permission decisions

- Confirm whether the portal is Finance-only or shared with Sales roles.
- Confirm whether one Sales Order may produce multiple/partial invoices for the Opt-In schedule.
- Define how quote/order creation behaves when the first invoice date is missing or the schedule is unconfigured.
- Record native status, workflow, and action rules for each doctype; do not add custom accounting status values.

### Phase 1 — Define the transaction experience and data contract

- Map list → detail → create-from → review → saved detail for each of the four records.
- Define the canonical related-document graph and URL/navigation behavior.
- Define each source-to-target mapping, including fields that are inherited, editable, recalculated, hidden, or server-authoritative.
- Define workflow action discovery/application using current Frappe session and document permissions.

### Phase 2 — Build the shared design and list foundation

- Centralize Finance typography and list patterns in one shared style/token layer.
- Unify `FinanceTable` and `CrudSection` states and responsive behavior.
- Implement contextual list headers, meaningful summary cues, filter counts/clear, semantic statuses, and complete mobile cards.
- Migrate the four transaction sections, then validate all 18 FinanceTable consumers and other shared users.

### Phase 3 — Complete high-value transaction flows

- Add Quotation → Sales Order schedule-aware preparation and review.
- Add Sales Order → Sales Invoice preview/review before draft insertion.
- Unify invoice-originated and general payment creation on a seeded, editable allocation composer.
- Add complete, permission-aware related-record panels and workflow actions/history.

### Phase 4 — Verify and release

- Add unit and Frappe tests before browser coverage.
- Run authenticated Playwright journeys with Finance and (if approved) Sales personas on `cr-dev`.
- Validate configured and unconfigured native workflows, missing schedule, partial billing, multiple payments, partial allocation, denied permissions, and stale balances.
- Perform responsive, keyboard, screen-reader, light/dark, print/email/Letter Head checks; attach evidence to the implementation story/PR.

## Test and acceptance outline

- **Quotation → Order:** mapper preserves customer, item rows/quantities/rates, taxes, terms, payment terms, and relevant CRM fields; Opt-In first invoice date populates `delivery_date`; missing schedule follows the chosen rule; denied user cannot map/save.
- **Order → Invoice:** preview displays native mapped lines/taxes/totals and source; duplicate/partial billing behavior follows the confirmed policy; stale or concurrent requests cannot create unintended drafts.
- **Invoice → Payment:** invoice detail shows ERPNext outstanding amount and applied payment allocations; payment composer seeds invoice/customer/currency, allows valid partial allocation, rejects over-allocation server-side, and displays updated balance after success.
- **Configured workflow:** user sees only allowed native transitions; transition success, invalid action, self-approval denial, workflow task effects, and no-workflow fallback are tested.
- **Lists/details:** filters, pagination, permissions, statuses, empty/loading/error/retry, source relationships, mobile cards, row-action event handling, and browser back/refresh are tested.
- **Print/email:** each of the four formats renders with the configured native Letter Head; email copy uses the same format and letterhead; list printing safely handles HTML-like values.
- **Test commands after implementation:** frontend `cd frontend && yarn test:run`; backend targeted Frappe tests on the configured site (including `cr-dev`); authenticated browser regression suite for the transaction journeys.

## Open decisions for the product owner

1. **Audience:** Should Sales users create/manage quotations and orders in this portal, or does the portal remain Accounts-only with quote creation kept in CRM/Opt-In?
2. **Billing cardinality:** Is one invoice per Sales Order a deliberate business rule, or must the portal support partial/multiple invoices for a scheduled order?
3. **Schedule fallback:** If the Opt-In schedule is missing/unconfigured, should order creation be blocked, require an explicit manual delivery date, or use the existing fallback date with a warning?
4. **Workflow coverage:** Which of the four doctypes are expected to have site-configured workflows, and should the UX show workflow history/comments in the detail timeline wherever available?

These decisions do not block the audit; they must be resolved before final UX/API acceptance criteria and story breakdown are approved.
