# Spec: Opt-In billing ledger, paying ahead, and accounting visibility

- **Status:** Accepted (2026-11-10, party: `../implementation-artifacts/party-2026-11-10-optin-billing-ledger.md`)
- **Decisions:** P-124 to P-133
- **Builds on:** `docs/optin-multi-year-billing.md` (quarterly schedule), `docs/cx-facility-page-tabs-and-registry-notice-fixes.md` (facility tabs)

## 1. Before

| Area | Behaviour |
|---|---|
| Opt-In Requests card | Network shows `[object Object]`; "Orders & Invoices" = counts of open records; quotes joined as text |
| Facility page (Opt-In) | Quote rows not clickable; only outstanding invoices; no payments; schedule hidden behind "Upcoming invoices" with duplicate "Quarter 1" labels |
| Paying ahead | Impossible. Invoices exist only when the hourly worker reaches each row's `invoice_date` |
| Failed rows | Never retried, error invisible |
| Admin | Deal Quoting tab shows yearly quotes only; no schedule, orders, invoices or payments |

## 2. Data model

No schema change. `CRM Opt-In Submission.billing_schedule_json` rows gain optional keys when issued by hand:

| Key | Meaning |
|---|---|
| `scheduled_invoice_date` | The contract date of the period (copied from `invoice_date` before it is overwritten) |
| `issued_early` | `true` when issued before `scheduled_invoice_date` |
| `issued_on` | ISO datetime of issue |
| `issued_by` | `customer` or `staff`, plus `issued_by_user` (the user id) |

The worker (`process_due_optin_billing`) is unchanged: it skips rows with `sales_invoice`.

## 3. Pure helpers — `crm/utils/optin_ledger.py` (no frappe import, unit-tested)

- `period_label(row)` → `"Year N · QM"`.
- `period_state(row, invoice, today)` → `scheduled | order_ready | due | overdue | paid | paid_ahead | needs_attention`.
  `invoice` is `{outstanding, grand_total, due_date, docstatus}` or `None`.
  Paid ahead = outstanding ≤ 0 and `today < scheduled_invoice_date`.
- `issuable_rows(rows)` → rows without `sales_invoice`, in schedule order (year, quarter).
- `select_next_periods(rows, count)` → first `count` issuable rows; raises `ValueError` for count outside 1–`MAX_ADVANCE_PERIODS`.
- `early_due_date(today, scheduled_due)` → later of the two.
- `ledger_summary(periods, today)` → `contract_total, invoiced_total, paid_total, outstanding_total, overdue_total, paid_ahead_total, next_payment {label, date, amount, state}`.
- `advance_policy(ois_status, contract_status, rows, unpaid_count)` → `{allowed, reason, max_periods, remaining}`.

Constants: `MAX_ADVANCE_PERIODS = 4`, `MAX_UNPAID_INVOICES = 4`.

## 4. API — `crm/api/optin_ledger.py`

| Method | Who | Does |
|---|---|---|
| `get_optin_ledger(ois_number)` GET | Portal user with the OIS User Permission | Ledger for one submission (§5) |
| `issue_optin_periods(ois_number, count)` POST | Same | Issues the next `count` periods now; returns `{issued: [{billing_key, sales_order, sales_invoice, amount}], ledger}` |
| `get_optin_ledger_for_deal(deal)` GET | Deal read + Sales Order read | Same ledger + Desk extras (`error`, `issued_by_user`) |
| `issue_optin_periods_for_deal(deal, count)` POST | Sales Manager / Accounts Manager / System Manager | Same issue path, `issued_by = staff` |
| `quotation_pdf(quotation, ois_number=None, customer=None)` GET | Portal user: quote in one of their OIS `quote_names_json`, or `party_name` is a customer they can see | Streams "Careverse Quote Standard" PDF |

Issue path (shared): lock the OIS row `for_update`, re-read the schedule, check `advance_policy`, then for each selected row call `optin_billing._create_order_and_invoice(row, quotation, submission, today, due_date=early_due_date(...))` inside a savepoint. On failure the row is marked `Failed` with the error and the call raises after saving the earlier successes.

## 5. Ledger shape

```json
{
  "ois": "OIS-…", "network": "…", "contract": "CONT-…", "contract_status": "Fully Executed",
  "currency": "KES", "today": "2026-11-10",
  "summary": {"contract_total": 0, "invoiced_total": 0, "paid_total": 0, "outstanding_total": 0,
              "overdue_total": 0, "paid_ahead_total": 0,
              "next_payment": {"label": "Year 1 · Q1", "date": "2027-01-30", "amount": 0, "state": "scheduled"}},
  "advance": {"allowed": true, "reason": "", "max_periods": 4, "remaining": 20,
              "next": [{"billing_key": "…", "label": "Year 1 · Q1", "amount": 0}]},
  "years": [{"year": 1, "quotation": {"name": "SAL-QTN-…", "status_label": "Accepted", "amount": 0},
             "periods": [{"billing_key": "…", "label": "Year 1 · Q1", "year": 1, "quarter": 1,
                          "scheduled_date": "…", "due_date": "…", "amount": 0, "state": "scheduled",
                          "state_label": "Scheduled", "sales_order": "", "sales_invoice": "",
                          "outstanding": 0, "payments": [{"name": "…", "date": "…", "amount": 0, "mode": "…"}],
                          "issued_early": false}]}],
  "quotes": [{"name": "…", "year": 1, "status_label": "Accepted", "amount": 0}]
}
```

## 6. UI

**Opt-In Requests (`OptInRequests.vue`)** — per request: header (network display name, journey chip, status, contract, signatory, facility count); `OptInLedger` component (summary tiles → pay-ahead card → schedule by year → quotes); facilities list. Ledger loads per request on mount, refresh button with "Updated hh:mm".

**`components/OptInLedger.vue`** — props `oisNumber`, `compact`. Emits `pay(invoice)` with `{name, amount, currency, ois_name}` so the portal's existing payment modal opens. Pay-ahead card: 3-step instructions, quarter stepper (1–min(4, remaining)), exact total, button "Create N invoice(s) · KES X". Blocked state shows the reason.

**Facility page** — `facilityTabs` adds `schedule` ("Payment schedule") after Overview when the journey is Network Opt-In; panel renders `OptInLedger` for the facility's OIS. Quote rows are links to the PDF (both journeys). `BillingJourney` shows a Billed / Paid / Outstanding strip from `get_facility_document_counts.totals` (Express) when the facility is customer-linked.

**Deal Quoting tab (OIS)** — `OptInBillingSchedule.vue` (Desk styling, frappe-ui): summary, per-period rows with `/app/sales-order/…`, `/app/sales-invoice/…`, `/app/payment-entry/…` links, error text, "Issue next period" for managers.

## 7. Brand / type rules

CX tokens only on the CX Portal; frappe-ui tokens on Desk. Weights ≤ 600, no uppercase eyebrows, sentence case. Status colours only for Due / Overdue / Paid / Paid ahead / Needs attention. Labels `ink-3`, sentences `ink-2`, values `ink`; sibling tiles share classes.

## 8. Verification

- `frontend`: `yarn test:run` (new `optinLedger.test.js`, updated `facilityTabs`, `OptInRequests`).
- Python: `crm/tests/test_optin_ledger.py` (pure helpers) on the scratch runner.
- Playwright: new `optin-ledger.spec.ts` in the portal UI suite at 4 viewports (overflow, brand weights, pay-ahead flow with the API mocked), plus the full `playwright.portal-ui.config.ts` run.
- Live: on crm-dev, issue Y1-Q1 early for a dev OIS via the API, confirm Sales Invoice + schedule row, then cancel nothing (dev data only).

## P-134 — Customers never invoice before the date (owner feedback, 2026-11-10)

Supersedes the customer half of P-125/P-126. The customer keeps the full breakdown (quotes, every period's invoice
and due dates) but cannot generate an invoice for a period whose contract invoice date has not arrived, on the
Opt-In journey or on Express fixed packages. Portal issuing is `due_only`: it only catches up a period that is
already due (worker lag or a failed row). The pay-ahead card becomes "How your payments work" with a Next invoice
panel. Staff early issue on the Deal stays. Express: future-dated orders cannot be invoiced (`is_future_dated`).
