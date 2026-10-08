# Finance Cockpit Frontend Overhaul — UX/Frontend Sprint Plan

**Status:** Code implementation complete for the current Finance Cockpit scope; release/UAT gates remain
**Owners:** Senior UX Engineer, Senior Frontend Engineer
**Supporting owners:** Finance/AR lead, ERPNext integration engineer, QA engineer
**Scope:** `apps/crm/frontend/src/pages/FinanceCockpit`
**Principle:** Native Frappe/ERPNext documents, permissions, workflows, and statuses remain authoritative.

## Sprint 1 progress

The implementation is complete locally across the following slices:

- Shared table, KPI, chart, and inbox error states now expose normalized server messages, accessible alert semantics, and retry actions.
- Touched surfaces use the Finance Cockpit/Frappe token language for surfaces, borders, text hierarchy, and interactive states.
- The AR dashboard now includes a due-invoice queue and a read-only signed-facility handoff timeline.
- The handoff timeline resolves native Year 1 Quotation, Q1 Sales Order, Sales Invoice, and Payment Entry records, shows signature/modified/creator timestamps, and derives the next action from native state and Network schedule metadata.
- Quotation and Sales Order field editing remains read-only for Finance. Native Sales Order submit/cancel and duplicate-safe draft invoice generation remain available where permitted.
- Remaining finance API gates and frontend report/KPI metadata use native Accounts User/Accounts Manager roles; deprecated Finance Manager/AR Accountant/AP Accountant gates are no longer used by the cockpit.
- The production build and frontend unit suite pass; existing bundle-size, Browserslist, and Lucide brand-icon warnings remain unchanged.

The remaining release work is environment-dependent: browser-level workflow coverage, keyboard/screen-reader audit, and Finance UAT against representative configured and unconfigured Network schedules.

The current workspace refinement also establishes the invoice-workbench contract:

- Finance sees outstanding invoices by due date, with overdue age, relative and absolute timestamps, last modifier, creator, and explicit sort guidance.
- Clear filters resets status, due-date windows, and pagination together.
- Quotations are read-only in Finance; Sales Orders are read-only for field edits but retain native Submit and guarded invoice generation actions.
- Invoice generation from an order uses the native ERPNext mapper only after a server-side duplicate check; existing draft or submitted invoices block the action.

## Product outcome

An Accounts Receivable or Finance User opens Finance Cockpit and immediately knows:

1. What needs attention today.
2. Which customer invoice or handoff is blocking collection.
3. What native action is valid next: review, submit, cancel, allocate payment, or open the linked ERPNext record.
4. Why an operation failed and exactly how to recover it.

The cockpit must feel like one coherent finance workspace rather than a collection of section pages and Desk links.

## Audit findings

### Strengths retained

- Standalone Frappe UI shell with company context, section navigation, breadcrumbs, theme support, and responsive layout.
- Native `frappe.client` CRUD for document loading, insert, save, submit, cancel, and delete.
- Dedicated payment allocation form with customer selection, invoice allocation, review, and native Payment Entry creation.
- Shared Finance API for AR/AP lists, KPIs, pending actions, reports, and payments.
- Native lifecycle interpretation: `docstatus`, ERPNext `status`, `outstanding_amount`, `billing_status`, and CRM Deal `Won`.
- Accounts-only authorization is now enforced at page, route, API, and CRM navigation boundaries.

### Gaps to address

| Area | Finding | User impact | Priority |
|---|---|---|---|
| Information architecture | Dashboard, invoices, payments, reports, and partner operations are separate areas without a clear AR work queue | Dashboard now leads with due invoices and handoffs; validate with Finance UAT | P0 — UAT |
| Handoff visibility | CRM quotation → Q1 order → invoice → payment relationships are not presented as a single traceable chain | Timeline now resolves the chain and next action from native data | Complete in code |
| Invoice workbench | Invoice rows expose basic fields but lack a focused overdue/collection action model | Due-date ordering, age, filters, read-only source docs, and payment flow are implemented | Complete in code |
| Payment capture | Payment form is materially better, but amount-first allocation, smart mode selection, balance context, and review ergonomics need completion | Receipt posting is slower and error-prone | P0 |
| Native workflow actions | Some actions still open `/app/...` Desk URLs or rely on generic CRUD controls | Context is lost and actions may be unavailable to the current role | P1 |
| Error handling | Several sections still show generic “Failed to load” messages | Core Finance surfaces now provide normalized messages and retry paths; classify remaining sections during UAT | P0 — UAT |
| Design language | Legacy `gray-*` classes and mixed card/table treatments remain | Core cockpit surfaces use Frappe tokens; full visual audit remains | P1 — audit |
| Responsive behavior | Tables and deep links are not consistently designed for small screens | Mobile card fallbacks exist; validate all payment/detail paths | P1 — audit |
| Accessibility | Keyboard focus, semantic table actions, status announcements, and contrast need a dedicated pass | Core alerts/buttons have semantics; dedicated keyboard/screen-reader pass remains | P1 — audit |
| Test coverage | Production build exists, but browser-level Finance Cockpit workflow coverage is incomplete | Unit/build/ERPNext focused tests pass; browser suite remains a release gate | P0 — release gate |
| Role metadata | Some report/KPI configuration still contains legacy Finance Manager/AR Accountant labels | Runtime metadata is normalized to native Accounts roles | Complete in code |

## Native status and workflow contract

No custom statuses or invented lifecycle values may be added.

Use:

- Quotation: `docstatus` plus native ERPNext status (`Open`, `Replied`, `Partially Ordered`, `Ordered`, etc.).
- Sales Order: native `docstatus`, `status`, and `billing_status`.
- Sales Invoice: native `docstatus`, `status`, `outstanding_amount`, and due-date calculations.
- Payment Entry: native `docstatus`, references, allocated amount, and outstanding amount.
- CRM Deal: native status value `Won`.
- Opt-In handoff: existing schedule metadata, document links, and error fields; never a new document status.

UI labels may explain a business action, but the saved value must always be the native ERPNext/CRM value.

## Sprint structure

### Sprint 0 — Discovery and design contract

**Duration:** 2–3 days

- Senior UX Engineer maps AR journeys and produces annotated wireframes for dashboard, invoice workbench, payment review, and handoff detail.
- Senior Frontend Engineer inventories existing Frappe UI components, tokens, composables, and API contracts.
- Finance lead validates action priority, terminology, and exception paths.
- QA defines fixtures and browser scenarios before implementation starts.

**Exit criteria:** approved information architecture, component inventory, API dependency map, and acceptance-test matrix.

### Sprint 1 — AR workbench and payment completion

**Duration:** 5 working days

- FCO-01 through FCO-05 are implemented in the current branch.
- Focus remaining validation on practical daily use: prioritization, invoice review, amount-first receipt capture, allocation review, and clear recovery.

### Sprint 2 — Handoff traceability and workflow surfaces

**Duration:** 5 working days

- FCO-06 through FCO-08 are implemented in the current branch.
- Bring Finance UAT evidence into the release record and reduce any remaining unnecessary Desk context switches.

### Sprint 3 — Responsive quality, accessibility, and regression hardening

**Duration:** 4–5 working days

- FCO-09 and FCO-10 remain release hardening work.
- Complete visual regression, keyboard testing, permission testing, and native ERPNext validation testing.

## Implementation stories

### FCO-01 — Establish the Finance Cockpit design system

**Priority:** P0 · **Estimate:** 3 points · **Owner:** Senior UX + Senior Frontend

Create a compact finance visual language using existing Frappe UI components and design tokens.

**Acceptance criteria**

- Define reusable tokens for surfaces, borders, text hierarchy, positive/attention/error states, spacing, focus rings, and density.
- Replace legacy raw gray classes in touched Finance Cockpit surfaces with Frappe design tokens.
- Standardize page headers, section cards, tables, empty states, status badges, action bars, and inline alerts.
- Support light and dark themes without loss of contrast.
- Document component usage and prohibited one-off visual patterns.

### FCO-02 — Build the AR action-center dashboard

**Priority:** P0 · **Estimate:** 5 points · **Owner:** Senior UX + Senior Frontend

Turn the dashboard into a daily queue for receivables work.

**Acceptance criteria**

- Show company and currency context prominently.
- Present overdue invoices, due soon, unapplied/allocated payments, signed-facility handoffs, and failed accounting actions as actionable groups.
- Every item has a native document link, customer, amount, age/due date, and next valid action.
- Empty, loading, partial, and error states are designed separately.
- Filters preserve company and period context and are reflected in the URL/hash state.
- No chart is used where a prioritized work queue is more useful.

### FCO-03 — Deliver the receivables invoice workbench

**Priority:** P0 · **Estimate:** 5 points · **Owner:** Senior Frontend

Make Invoices the primary AR operating surface.

**Acceptance criteria**

- Default views include overdue, due soon, unpaid, partly paid, and paid using native ERPNext fields.
- Columns support amount, outstanding, due date, days overdue, customer, native status, and handoff references.
- Sorting, pagination, company filtering, and refresh preserve server truth.
- Row actions expose only valid native actions for the current document state and role.
- Selecting an invoice opens a detail view with related quotation, deal, sales order, payment entries, and handoff metadata where present.
- The UI never implies that an invoice exists when the Network billing schedule has not produced one.

### FCO-04 — Complete amount-first payment capture

**Priority:** P0 · **Estimate:** 5 points · **Owner:** Senior Frontend

Optimize receipt posting for the real AR workflow: receive an amount, then allocate it.

**Acceptance criteria**

- Amount Received is the first primary input after customer selection.
- Customer search matches code and display name and shows outstanding context.
- Mode of Payment uses searchable Frappe UI controls and preserves the user’s recent choice.
- Auto-allocation uses oldest due date first and remains manually editable.
- Overpayments and unallocated balances are explicit before posting.
- Review step shows customer, amount, mode, date, reference, allocations, and unallocated amount.
- Backend validation errors remain visible in the review surface with clear correction steps.
- Success displays the native Payment Entry number and a safe link to the record.

### FCO-05 — Make payment allocation safe and auditable

**Priority:** P0 · **Estimate:** 3 points · **Owner:** Senior Frontend + QA

Prevent accidental misallocation and make the final posting decision reversible before submission.

**Acceptance criteria**

- Invoice rows show outstanding balance, allocated amount, remaining amount, and overdue indicator.
- Select-all and clear-all actions are available and keyboard accessible.
- Allocation cannot exceed server-provided outstanding balance without an explanatory error.
- Changes to customer or company clear stale invoice data and show a loading state.
- Double-submit is prevented while the native Payment Entry is being inserted/submitted.
- On failure, the form retains entered data and provides retry/correction guidance.

### FCO-06 — Add a signed-facility handoff timeline

**Priority:** P0 · **Estimate:** 5 points · **Owner:** Senior UX + Senior Frontend

Present the CRM-to-cash chain in one view.

**Acceptance criteria**

- Show facility, Network, CRM Deal, Year 1 Quotation, Q1 Sales Order, Sales Invoice if generated, and Payment Entries.
- Show native state for each document and the timestamp of the facility signature.
- Clearly distinguish “invoice not configured,” “invoice deferred by schedule,” “failed,” and “posted” using existing metadata/error fields, not custom statuses.
- Provide direct links to native records while preserving cockpit context.
- Show an actionable next step for every incomplete link.

### FCO-07 — Replace generic CRUD with native action surfaces

**Priority:** P1 · **Estimate:** 5 points · **Owner:** Senior Frontend

Use domain actions while retaining native Frappe validation and permissions.

**Acceptance criteria**

- Draft, submit, cancel, amend, allocate, and retry actions appear only when valid for the native document state.
- Generic Save/Submit is not presented as a business action where a domain-specific flow exists.
- Native validation messages are mapped into field, section, or page-level errors.
- Desk links are fallback actions, not the primary workflow for supported cockpit operations.
- Unauthorized actions are disabled with an explanation of the required Accounts role.

### FCO-08 — Create an actionable error and recovery system

**Priority:** P0 · **Estimate:** 3 points · **Owner:** Senior UX + Senior Frontend

Create one error vocabulary and recovery pattern.

**Acceptance criteria**

- Errors classify as permission, missing configuration, validation, duplicate/idempotency, closed accounting period, network/API, or unknown.
- Each error provides: what happened, why, next step, and retry availability.
- Preserve form state after recoverable errors.
- Include a correlation/reference identifier when the server provides one.
- Do not expose tracebacks, secrets, or raw SQL/database errors.
- Screen-reader users receive live announcements for failed and successful actions.

### FCO-09 — Responsive and accessible finance operations

**Priority:** P1 · **Estimate:** 5 points · **Owner:** Senior UX + Senior Frontend + QA

Make the cockpit reliable at laptop, tablet, and mobile widths.

**Acceptance criteria**

- Key invoice and payment actions remain available without horizontal table scrolling on mobile.
- Keyboard navigation covers sidebar, filters, comboboxes, tables, dialogs/drawers, and review flow.
- Focus is restored after drawers, errors, and successful submissions.
- Status and overdue meaning is not conveyed by color alone.
- Contrast meets the project accessibility target in light and dark themes.
- Touch targets meet the project minimum and do not conflict with row navigation.

### FCO-10 — Browser regression suite and release gate

**Priority:** P0 · **Estimate:** 5 points · **Owner:** Senior Frontend + QA

Automate the high-risk journeys before declaring the overhaul complete.

**Acceptance criteria**

- Accounts User can open cockpit, find an invoice, create a payment, review allocation, and post it.
- Accounts Manager can perform manager-only actions permitted by native permissions.
- Non-Accounts users are redirected/denied and cannot call Finance APIs.
- Signed facility with configured Network billing shows quotation → Q1 order → invoice chain.
- Signed facility without billing configuration shows Q1 order and actionable no-invoice explanation.
- Duplicate refresh/retry does not create duplicate native documents.
- Tests cover loading, empty, permission, validation, server failure, and success states.
- Build, focused unit tests, and browser tests are required checks for the PR.

## Definition of Done

- UX flows reviewed by a Finance/AR user and a senior UX engineer.
- Frontend implementation reviewed by a senior frontend engineer.
- Native status/permission behavior verified against ERPNext on an enabled test site.
- No custom lifecycle statuses introduced.
- Responsive, keyboard, dark-mode, and error-state checks completed.
- Unit and browser tests pass.
- PR includes screenshots or a short screen recording for changed flows, test evidence, known limitations, and rollout notes.

## Out of scope for this sprint

- Replacing ERPNext accounting logic or document validation.
- Introducing a second finance ledger or custom invoice/payment lifecycle.
- Re-designing the CRM sales pipeline outside Finance Cockpit entrypoints.
- Changing Network billing policy or fiscal-period rules.
