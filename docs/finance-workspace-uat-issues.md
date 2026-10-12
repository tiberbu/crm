# Finance Workspace UAT Issues

Source: Finance Workspace issues log for Tiberbu HealthNet Limited, UAT.
Baseline: `f1eeff1` (PR #84 merge on `upstream/develop`). Branch: `fix/finance-workspace-uat-issues`.
UAT/test site provided by user: `cr-dev` (`cr-dev.tiberbu.app` in this bench).

| ID | Priority | UAT report | Finding on current source | Owner | Resolution / next proof |
|---|---|---|---|---|---|
| FIN-UAT-01 | Medium | Finance cannot submit draft quotations; screen says Sales-owned/read-only. | Cockpit already enables lifecycle actions and calls Frappe submit. UI eligibility is based on CRM role, while the server endpoint marks native submit permission per row; the table does not show that eligibility. The reported copy is absent from this source. | Site owner (not identified) | **Pending UAT permission/deploy evidence.** Capture deployed commit, user roles, Quotation Submit permission, and `finance_state` for an affected draft. Then decide whether eligibility needs clearer UI. |
| FIN-UAT-02 | High | Invoice “Create Payment” opens a Payment Entry with Mode and Paid Amount disabled. | **Confirmed UI defect; code change implemented on this branch.** The invoice detail's mapped Payment Entry now opens the editable payment composer; it retains company/customer/invoice/amount and restricts allocation to that invoice. Tolerated rounding drift is capped at the live outstanding balance. | CRM code owner for branch change; site owner (not identified) for UAT proof | **Code proof:** `frontend/tests/unit/financeMappedPaymentComposer.test.js` exercises the invoice detail → mapped composer path, editable amount/allocation controls, invoice restriction, and mapped bank references. `paymentAllocationSeed.test.js` covers context validation and allocation bounds. Frontend suite: 16 files / 171 tests passed. Backend suites: 9 payment-mode tests and 5 customer-allocation tests passed on `cr-dev.tiberbu.app`. **Pending UAT deployment proof:** capture deployed commit and verify the editable controls in the cockpit. |
| FIN-UAT-03 | High | Cash payment requires Bank Reference No/Date. | Current code derives reference requirements from the resolved account type and rejects a Cash mode mapped to a Bank account. ERPNext docs say Mode of Payment company defaults must map to an account with the matching type; a Bank account uses bank reference details. | Site owner (not identified) | **Pending UAT config/deploy evidence.** Record Mode of Payment type, company default account, account type, selected `paid_to`, and deployed commit. Preserve native Bank reference validation. Backend payment-mode tests passed: Cash optional refs, Bank required refs, and Cash-mode/Bank mismatch. |
| FIN-UAT-04 | Medium | Email Copy fails because no email account is configured. | Endpoint uses `frappe.sendmail`; the SES override supplies a synthetic sender account only when CRM SES is enabled. Otherwise Frappe needs a default outgoing Email Account. | Site owner (not identified) | **Pending UAT configuration action.** Configure a default outgoing Email Account or configure CRM SES, then prove a queued copy reaches its recipient. No code defect established. |
| FIN-UAT-05 | High | Generate Invoice from submitted Sales Order appears not to create an invoice. | Current endpoint checks role/doctype permissions, matching company, submitted order, and existing invoice links, then maps and inserts a draft invoice. The issue log lacks the toast/API error. The mapper is local-site only, so cross-site ERPNext setup is a possible incompatibility. | Site owner (not identified) | **Pending reproduction evidence.** Capture order/site mode, deployed commit, user permissions, and the exact toast/API response; verify whether a draft invoice exists. Decide code change after this evidence. |
| FIN-UAT-06 | Low | Edit is visible for a submitted Payment Entry. | Cockpit detail currently suppresses Edit for Payment Entry regardless of status. The report may be from the native ERPNext form or a stale frontend bundle. | Site owner (not identified) | **Pending screen/deploy evidence.** Capture URL, deployed commit, and status. Confirm the submitted record is read-only in the cockpit. |

## Source trace

- `frontend/src/pages/FinanceCockpit/components/crud/FinanceDetail.vue` -- quotation lifecycle action, invoice payment mapping, invoice generation action, and Payment Entry detail edit visibility.
- `frontend/src/pages/FinanceCockpit/components/crud/CrudSection.vue` -- routes explicitly configured mapped target doctypes to their custom composer.
- `frontend/src/pages/FinanceCockpit/components/crud/FinanceForm.vue` and `formLayouts.js` -- generic Payment Entry form uses read-only fields.
- `frontend/src/pages/FinanceCockpit/components/crud/PaymentAllocationForm.vue` -- editable customer payment composer and account-derived references.
- `frontend/src/pages/FinanceCockpit/components/crud/paymentAllocationSeed.js`, `frontend/tests/unit/paymentAllocationSeed.test.js`, and `frontend/tests/unit/financeMappedPaymentComposer.test.js` -- mapped-context validation and end-to-end component routing coverage for FIN-UAT-02.
- `crm/finance/api.py` -- quotation submit eligibility, invoice mapping, payment account checks, and Sales Order invoice creation.
- `crm/finance/email.py` and `crm/email/queue_patch.py` -- email-copy queue path and SES sender override.

## Context7 references

- [ERPNext Payment Entry](https://docs.frappe.io/erpnext/payment-entry) -- payment modes, accounts, invoice links, and bank references.
- [ERPNext Mode of Payment](https://docs.frappe.io/erpnext/mode-of-payment) -- company account defaults and account type/currency matching.
- [ERPNext Bank Accounts and Modes of Payment](https://docs.frappe.io/erpnext/bank-accounts-and-modes-of-payment) -- account selection for payments.

## Completion proof

Close each row only with an attached code/test result or UAT evidence. Frontend and backend unit suites passed; the site's runtime behavior and deployment commit have not been verified for FIN-UAT-01 through FIN-UAT-06. The responsible site owner is still unidentified for FIN-UAT-01 and FIN-UAT-03 through FIN-UAT-06. Do not mark these fixed from source inspection alone.

## PR 85 — Finance remediation status

**Status: In progress; owner review and cr-dev walkthrough are still required.**

| Work item | Code state | Proof / remaining action |
|---|---|---|
| Canonical Opt-In links | Conservative backfill and conflict inventory implemented; populated conflicting links are left unchanged. | 3 link-conflict unit tests pass. Read-only cr-dev inventory found 0 conflicting references; no repair was run. |
| Payment-based rebates and commissions | Received invoice allocations accrue configured rates; facility Supplier takes precedence over the Network fallback; commission uses the Deal User's unique active Employee. | 13 focused finance unit tests pass. Confirm configuration and example results in cr-dev. |
| Finance Settings and accounting Setup | Rate screens and CRM Setup forms are implemented for the listed accounting records. | 173 frontend tests and production build pass. Walk through create/edit permissions and saved records in cr-dev. |
| Finance list and Opt-In Supplier capture | Payment result details and filters were updated; Opt-In facility cards accept an optional Supplier and carry attribution into billing lines. | 7 Opt-In Supplier tests pass. Run the Opt-In flow and inspect quote/order/invoice attribution in cr-dev. |
| Remaining Desk destinations | Setup destinations now open CRM screens. Other finance record/report actions still include native accounting destinations and need a complete path audit. | Keep this remediation in progress until each in-scope action opens a CRM screen. |
