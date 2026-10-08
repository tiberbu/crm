# Finance Cockpit and Accounting Handoff — Implementation Stories

**Status:** Ready for implementation planning
**Scope:** CRM → Opt-In / signed facility → Quotation → Sales Order → Sales Invoice → Payment Entry
**Primary app:** `apps/crm`
**Accounting authority:** ERPNext Selling and Accounting doctypes/workflows

## Outcome

Finance users with `Accounts User` or `Accounts Manager` can open Finance Cockpit from CRM, review and operate the CRM-to-cash pipeline, and post customer payments through native ERPNext flows. Users without either Accounts role cannot access the cockpit, its APIs, or its accounting actions.

All historical Year 1 Opt-In quotations for eligible signed facilities are reconciled safely, and future handoff is idempotent, auditable, and governed by Network billing-period configuration. The implementation must use existing native ERPNext and CRM lifecycle values only; it must not add custom status fields or invent new status options.

## Access policy

The authoritative access rule is:

```text
Administrator OR Accounts User OR Accounts Manager
```

`System Manager`, `Finance Manager`, `AR Accountant`, `AP Accountant`, `Sales Manager`, and `Partner RM` do not receive Finance Cockpit access unless they also have `Accounts User` or `Accounts Manager`.

Administrator is retained as the recovery and migration escape hatch. This exception must be documented in the security test cases.

## Story FC-ACCESS-01 — Centralize Finance Cockpit authorization

**Priority:** P0
**Owner:** Backend / Security

Create one shared access policy used by the standalone page, Desk route guard, Finance APIs, and frontend boot state. Do not maintain separate role lists in each surface.

**Acceptance criteria**

- `Accounts User` can open `/finance-cockpit`.
- `Accounts Manager` can open `/finance-cockpit`.
- Administrator can open `/finance-cockpit`.
- Every other role receives the branded access-restricted response.
- Direct calls to `crm.finance.api.*` fail closed with `PermissionError` for unauthorized users.
- Mixed-role users are evaluated by the full role set, not only their primary role.
- Error text tells the user which role is required without exposing implementation details.
- Role lookup failure denies access rather than failing open.

**Implementation anchors**

- `crm/finance/access.py`
- `crm/api/route_guard.py`
- `crm/www/finance_cockpit.py`
- `crm/finance/api.py`

## Story FC-ACCESS-02 — Add the accounting permission migration patch

**Priority:** P0
**Owner:** Backend / Migration

Add and register a post-model-sync patch that normalizes Finance Cockpit access and related CRM accounting DocType permissions.

The patch must:

- Restrict the `finance-cockpit` Page role list to `Accounts User` and `Accounts Manager`.
- Preserve Administrator access.
- Ensure Accounts roles have the required read/create/write/submit permissions for the CRM accounting DocTypes used by the cockpit, including rebate vouchers and sales commissions.
- Never grant permissions to unrelated CRM roles merely because they can view CRM deals.
- Be idempotent and safe to run on CRM-only sites where ERPNext doctypes are absent.
- Avoid deleting administrator-created permission customizations unless explicitly required.
- Log or report missing ERPNext doctypes instead of failing migration.

**Required verification**

- `bench --site <site> migrate` succeeds on an ERPNext-enabled site.
- `bench --site <site> migrate` succeeds on a CRM-only site.
- Re-running the patch produces no duplicate permission rows.
- Page and DocType permissions match the shared access policy after migration.

**Implementation anchors**

- `crm/patches.txt`
- `crm/patches/v1_0/restrict_finance_cockpit_to_accounts.py`
- `crm/fcrm/page/finance_cockpit/finance_cockpit.json`
- Relevant CRM accounting DocType JSON permission blocks

## Story FC-NAV-01 — Add Finance Cockpit to the CRM sidebar

**Priority:** P0
**Owner:** Frontend

Add a CRM navigation item labelled **Finance Cockpit** that opens `/finance-cockpit`.

**Acceptance criteria**

- Visible to Accounts User, Accounts Manager, and Administrator.
- Hidden or disabled for users without those roles, according to the CRM sidebar convention.
- Works on desktop and mobile navigation.
- Opens the standalone Finance Cockpit page without exposing a native Desk page.
- Role evaluation uses the full boot role list.
- The link is not treated as a CRM Vue Router route.
- Browser back, refresh, and logout preserve the expected CRM/Finance route behavior.

**Implementation anchors**

- `frontend/src/components/Layouts/AppSidebar.vue`
- `crm/www/crm.py` boot payload

## Story FC-HANDOFF-01 — Reconcile historical signed Year 1 quotations

**Priority:** P0
**Owner:** CRM / Accounting Backend

Create a retry-safe reconciliation command or patch for all eligible Year 1 Opt-In quotations where the facility signing condition is satisfied.

**Eligibility rules**

- Quotation belongs to an Opt-In submission.
- Quotation is Year 1.
- Facility signatory status is explicitly `Signed`.
- Network, company, customer, CRM Deal, and quotation links are resolvable.
- Quotation is not cancelled, rejected, expired in a way that prevents acceptance, or already converted incompatibly.

**Behavior**

- Run in dry-run mode first and return eligible, skipped, failed, and already-complete counts.
- Submit only eligible draft quotations.
- Submit the quotation through the native ERPNext workflow. A submitted quotation must retain ERPNext's native `Open` status unless native ERPNext transitions it to `Replied`, `Partially Ordered`, or `Ordered` through normal downstream activity. Do not write `Accepted` into the native Quotation status because `Accepted` is not an available ERPNext option.
- Mark the linked CRM Deal Won exactly once.
- Detect existing Sales Orders and Sales Invoices before creating anything.
- Preserve existing quotation totals, taxes, terms, company, customer, and CRM links.
- Write an audit event containing quotation, submission, deal, facility, actor, timestamp, and result.
- Continue processing independent records after an individual failure.
- Persist a human-readable failure reason for manual correction.

**Native-state interpretation**

The business phrase “quotation accepted” is represented operationally by the native sequence `Quotation.docstatus = 1` and native quotation status (`Open` initially), followed by native Sales Order creation. The CRM Deal uses its existing native `CRM Deal Status` value `Won`; no new status is introduced.

## Story FC-HANDOFF-02 — Start future handoff at facility signature

**Priority:** P0
**Owner:** CRM / Accounting Backend

When the facility signatory completes the required signature step, create an idempotent Finance handoff event/state for the related Opt-In submission and Year 1 quotation.

**Confirmed trigger rule**

- As soon as the facility signatory reaches native `Signed`, submit the Year 1 ERPNext Quotation if it is still a draft.
- Immediately generate and submit the Year 1 / Quarter 1 native Sales Order.
- Generate a Sales Invoice at that same handoff only when the Network has a valid billing schedule configured for invoice issuance at that point in time.
- If the Network has no configured billing schedule, leave the Sales Order submitted and leave the invoice uncreated; show the exact configuration gap to Finance.
- Remaining signatures may continue independently. They must not block the Year 1 Quotation submission or Q1 Sales Order creation.
- The existing native contract lifecycle remains authoritative for legal execution; no custom status is introduced.

The handoff must:

- Be emitted once for a signature, regardless of retries or duplicate callbacks.
- Carry submission, contract, deal, quotation, network, company, facility, year, and signature timestamp.
- Not trust browser state as proof of signature.
- Not create duplicate orders or invoices.
- Preserve a pending/blocked state when remaining legal signatures or accounting conditions are incomplete.
- Be visible to Finance Cockpit users with a clear reason when billing is not yet eligible, using the existing schedule row state/error fields rather than a new document status.
- Retry failed downstream processing through a queue or scheduled reconciliation.

The facility signature starts the commercial handoff. Invoice creation is separately gated by the Network billing schedule, while the native contract signature lifecycle remains authoritative for legal execution.

## Story FC-HANDOFF-03 — Bind billing to Network period configuration

**Priority:** P0
**Owner:** CRM / Accounting Backend

Use the Network configuration as the sole source for period scheduling.

The schedule must honor:

- Enabled contract years and yearly price lists.
- Billing frequency: monthly, quarterly, annual, or the configured supported mode.
- First invoice offset.
- Signature-based versus scheduled issue timing.
- Signature/contract start anchor.
- Period start and end dates.
- Due-date rule.
- Company fiscal-period status and closed-period restrictions.
- Currency, tax template, payment terms, and customer account configuration.

Each generated period row must retain its existing schedule metadata, stable idempotency key, and error details where applicable. Do not add a new ERPNext or CRM document status.

## Story FC-HANDOFF-04 — Generate native Sales Orders and Sales Invoices

**Priority:** P0
**Owner:** ERPNext Integration

For each due schedule period, generate native ERPNext documents using supported ERPNext mappers and validated document data.

**Acceptance criteria**

- Sales Order links back to submission, quotation, deal, network, year, period, and billing key.
- Sales Invoice links back to Sales Order, quotation, submission, deal, network, year, period, and billing key.
- Customer, company, currency, price list, item, UOM, tax, accounts, cost center, warehouse, payment terms, posting date, and due date validate successfully.
- Annual quotations remain annual commitments; period documents use calculated period amounts.
- Duplicate workers cannot create duplicate documents.
- Failed order/invoice creation rolls back only the current schedule row and leaves a retryable failure state.
- Submitted documents are never silently modified to repair a failed process.
- Posting into a closed accounting period is blocked with an actionable error.
- Q1 Sales Order is created immediately after the facility signature even when invoice scheduling is absent.
- Sales Invoice is created immediately only when the Network billing schedule explicitly permits it; otherwise the order remains the only downstream accounting document.

## Story FC-COCKPIT-01 — Finance Cockpit accounting workspace

**Priority:** P1
**Owner:** Finance UX / Frontend

Provide a clear workflow across Quotes, Orders, Invoices, Payments, Partner/Commission, and Reports.

The cockpit must show:

- Current company and currency context.
- Handoff state and downstream document links.
- Draft, submitted, cancelled, overdue, paid, and failed states.
- Related CRM Deal, quotation, Opt-In submission, order, invoice, and payment references.
- Pending actions and retryable failures.

CRUD must follow native Frappe permissions and lifecycle rules. Generic Save/Submit must not be presented as a substitute for domain actions such as Accept, Win Deal, Generate Order, Generate Invoice, Cancel, Amend, Allocate Payment, or Retry Handoff.

## Story FC-PAY-01 — Receive and allocate customer payments

**Priority:** P0
**Owner:** Finance UX / Accounting Backend

Allow an Accounts user to open the cockpit, select an outstanding Sales Invoice, and create a native Receive Payment Entry.

**Acceptance criteria**

- Customer search matches both customer code and customer name.
- Outstanding invoices are fetched server-side for the selected company/customer.
- Amount Received can be entered before allocation.
- Auto-allocation uses oldest due date first.
- Manual allocation remains possible.
- Partial payments are supported.
- Overpayments are clearly shown as unallocated credit.
- Allocations cannot exceed live outstanding balances.
- Payment mode, reference number, reference date, posting date, company, account, currency, and party fields satisfy ERPNext validation.
- Backend revalidates all invoices and amounts before insert/submit.
- Duplicate submission cannot post a duplicate receipt.
- Payment hook side effects remain idempotent.
- Success shows the Payment Entry number and linked invoice state.

## Story FC-ERROR-01 — Standardize backend accounting errors

**Priority:** P0
**Owner:** Backend

Create a safe error contract for Finance APIs and handoff jobs.

Every error should provide:

- Stable error category/code.
- User-safe message.
- Actionable next step.
- Related document and schedule identifiers where safe.
- Correlation/request identifier for support.
- Server logs containing traceback and context, without credentials or sensitive payment data.

Error categories should include permission, missing mandatory field, invalid company, invalid customer, closed period, duplicate/idempotency conflict, ERPNext validation failure, missing configuration, network mismatch, and transient integration failure.

Never expose raw Python tracebacks, SQL, internal file paths, or secrets in the UI.

## Story FC-ERROR-02 — Improve Cockpit loading and recovery states

**Priority:** P1
**Owner:** Frontend

Replace generic “Failed to load data” messages with consistent error panels that show the normalized server message, affected operation, and recovery action.

Required states:

- Initial load.
- Refresh failure while stale data remains visible.
- Empty result.
- Permission denied.
- Company context unavailable.
- Network timeout.
- Mapping failure.
- Save/submit/cancel/delete failure.
- Payment posting failure.
- Handoff blocked or failed.

Recovery actions should include Retry, Change Company, Back, Review Fields, Open Source Document, or Contact Finance Support as appropriate.

Errors must remain visible until dismissed or resolved; they must not rely only on auto-dismissing toasts.

## Story FC-ERROR-03 — Improve form and payment validation UX

**Priority:** P1
**Owner:** Frontend / Finance UX

- Show field-level validation beside mandatory fields.
- Preserve entered values after a failed save or payment submission.
- Focus the first invalid field.
- Distinguish client validation from ERPNext server validation.
- Show the exact document and operation that failed.
- Disable duplicate-submit actions while a request is in flight.
- Provide a review step before posting payments.
- Show allocation mismatch, unallocated amount, and overpayment warnings before confirmation.
- Keep errors accessible to keyboard and screen-reader users.
- Use design-system tokens and support light/dark themes without raw gray utility drift.

## Story FC-TEST-01 — Authorization and permission test matrix

**Priority:** P0
**Owner:** QA / Security

Test at minimum:

| User | CRM | Cockpit page | Finance APIs | Accounting actions |
|---|---:|---:|---:|---:|
| Administrator | Yes | Yes | Yes | Yes |
| Accounts Manager | Yes | Yes | Yes | Manager actions |
| Accounts User | Yes | Yes | Yes | User actions |
| Finance Manager only | Existing policy | No | No | No |
| AR Accountant only | Existing policy | No | No | No |
| AP Accountant only | Existing policy | No | No | No |
| Sales Manager only | Yes | No | No | No |
| Partner RM only | Yes | No | No | No |
| Guest / Website User | No or portal-only | No | No | No |

Verify both browser navigation and direct HTTP/RPC calls.

## Story FC-TEST-02 — End-to-end accounting workflow tests

**Priority:** P0
**Owner:** QA / Automation

Cover:

1. Signed facility → eligible Year 1 quotation → accepted state → Won Deal.
2. Network schedule → due Sales Order → due Sales Invoice.
3. Repeated signature callback → one handoff only.
4. Repeated scheduler run → no duplicate order/invoice.
5. Missing customer/account/tax/item configuration → actionable blocked state.
6. Closed fiscal period → no invalid posting.
7. Invoice → partial payment → second payment → fully paid.
8. Overpayment → unallocated amount shown and preserved.
9. Payment submission retry → one Payment Entry only.
10. Payment Entry hook → one rebate/commission record per valid allocation.
11. Unauthorized user → access denied at navigation, page, API, and native action layers.
12. Light/dark mode, responsive layout, keyboard navigation, and screen-reader error announcement.

## Story FC-ROLLOUT-01 — Migration, observability, and support runbook

**Priority:** P1
**Owner:** Release / Operations

- Register all patches in the correct migration section.
- Run migration on staging first.
- Capture dry-run reconciliation output before mutating historical records.
- Back up affected quotation, deal, schedule, order, invoice, and payment data.
- Record patch version and execution timestamp.
- Monitor failed handoff rows and scheduled-job failures.
- Provide a Finance support view for blocked/failed rows.
- Document how to retry a failed row safely.
- Document how to reverse or cancel an incorrectly posted document using native ERPNext procedures.
- Run frontend build, backend tests, migration, and browser tests before release.

## Definition of Done

- No non-accounting role can access Finance Cockpit through any route or API.
- Accounts users can complete the supported quotation-to-payment workflow without entering Desk.
- Historical reconciliation is dry-run reviewed, idempotent, auditable, and rerunnable.
- Network configuration determines billing periods and timing.
- Native ERPNext validations pass without silent data loss.
- Error states identify what failed, why it failed, and what the user can do next.
- All acceptance tests pass on supported Frappe/ERPNext versions.
- Migration, rollback/recovery, and Finance support procedures are documented.
