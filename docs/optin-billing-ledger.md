# Opt-In billing ledger and paying ahead

**Status:** Implemented 2026-11-10 (decisions P-124 to P-133)
**Spec:** `_bmad-output/optin-billing-ledger/planning-artifacts/spec-optin-billing-ledger.md`
**Roundtable:** `_bmad-output/optin-billing-ledger/implementation-artifacts/party-2026-11-10-optin-billing-ledger.md`
**Builds on:** [optin-multi-year-billing.md](./optin-multi-year-billing.md)

## What the customer sees (CX Portal)

**Opt-In Requests** — one card per request:

1. The partner network's name (this used to show `[object Object]`), journey, status, contract and signatory.
2. Four money tiles: contract value, invoiced, paid (and how much was paid ahead), outstanding (and how much is overdue).
3. **Next payment** — the next period, its date and amount, with a refresh button ("Updated hh:mm").
4. **Pay ahead of your schedule** — three plain steps, a stepper for 1–4 quarters, the exact total, and
   "Create N invoices · KES X". If paying ahead is not open yet, the card says why (for example, the contract is not
   fully signed).
5. **Payment schedule** — grouped by contract year, one row per quarter labelled "Year N · QM": invoice date, due
   date, amount, state, and the document trail `Order → Invoice → Paid <date> · <mode>`. Issued, unpaid rows have a
   **Pay** button that opens the portal's usual payment choices (card, M-Pesa, bank transfer).
6. **Other invoices on this request** — any invoice on the submission that is not a schedule period, still payable.
7. **Yearly quotations** — one per year, *Accepted* once the contract is fully executed (*Awaiting signatures*
   before). Each opens its PDF.

**Facility page (Network Opt-In facility)** — a **Payment schedule** tab after Overview shows the same ledger. Quote
rows in the Quotes tab open the PDF, for Network and Express facilities alike.

**Express facilities** — a Billed / Paid / Outstanding strip above the facility tabs (from
`get_facility_document_counts.totals`).

### States

| State | Meaning |
|---|---|
| Scheduled | No order or invoice yet; the invoice is issued on the date shown |
| Order ready | The Sales Order exists (Year 1 Q1 is created at signature); no invoice yet |
| Due | Invoice issued, not paid, not past due |
| Overdue | Invoice past its due date with a balance |
| Paid | Paid, period already started |
| Paid ahead | Paid before the period's contract date |
| Needs attention | Issuing failed; staff see the error on the Deal |

## Rules for paying ahead

- Only the **next** unissued periods, in order — never a later quarter before an earlier one.
- 1–4 periods per action (`MAX_ADVANCE_PERIODS`), and no new invoice while 4 Opt-In invoices on the submission are
  unpaid (`MAX_UNPAID_INVOICES`). Both are constants in `crm/utils/optin_ledger.py`.
- The OIS must be *Processed* and the contract *Fully Executed*.
- An early invoice posts today and is due on the **later** of today and its contract due date. Paying ahead never
  makes anything due sooner.
- Documents are the same native Sales Order → Sales Invoice the hourly worker creates (`_create_order_and_invoice`).
  The worker is unchanged and skips periods that already have an invoice.
- Each issued row records `scheduled_invoice_date`, `scheduled_due_date`, `issued_early`, `issued_on`, `issued_by`
  (`customer` / `staff`) and `issued_by_user`, and the submission gets an "issued early" comment.
- A *Failed* row is issuable again, which is how staff retry a period the worker could not invoice.
- No discount for paying ahead.

## What staff see (CRM Desk)

Deal → **Quoting** tab (Opt-In deals) → **Quarterly billing schedule**: the same totals, every period with Desk links
to its Sales Order, Sales Invoice and Payment Entries, who issued it early, the error on failed rows, and **Issue
now** (1–4 periods) for Sales Manager, Accounts Manager and System Manager.

## API

| Method | Caller | Purpose |
|---|---|---|
| `crm.api.optin_ledger.get_optin_ledger(ois_number)` | Portal user with the OIS User Permission | Ledger |
| `crm.api.optin_ledger.issue_optin_periods(ois_number, count)` | Same | Issue the next periods now |
| `crm.api.optin_ledger.get_optin_ledger_for_deal(deal)` | Deal read | Ledger with staff detail and `can_issue` |
| `crm.api.optin_ledger.issue_optin_periods_for_deal(deal, count)` | Sales / Accounts / System Manager | Issue as staff |
| `crm.api.optin_ledger.quotation_pdf(quotation, ois_number | customer)` | Portal user who owns the quote | "Careverse Quote Standard" PDF |

`quotation_pdf` checks that the quote is in one of the user's submissions (`quote_names_json`) or belongs to a
customer the user can see, then renders the PDF without needing Quotation print permission.

## Data

No schema change or migration. Everything is read from `billing_schedule_json` and the native ERPNext documents.
`portal_commercial` now labels schedule rows "Year N · Quarter M" (stored `period_label` repeats "Quarter N" every
year) and exposes `plan.ois` so the facility page knows which ledger to load.

## Tests

- `crm/tests/test_optin_ledger.py`, `crm/tests/test_facility_documents_pure.py`, `crm/tests/test_portal_commercial_pure.py` (pure, `pytest`).
- `frontend/tests/unit/optinLedger.test.js`, `OptInRequests.test.js`.
- `frontend/e2e/regression/optin-ledger.spec.ts` in `playwright.portal-ui.config.ts` (4 viewports: network name,
  first-view schedule, pay ahead → Pay, facility Payment schedule tab and quote links, layout and type gates).
