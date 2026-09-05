# OIS invoice checkout

The public `/payment-checkout` page accepts an OIS reference, sends a one-time
code to the facility signatory stored on that OIS, and only then lists submitted
Sales Invoices with an outstanding balance. The page supports hosted Paystack
checkout and manual bank transfer.

Paystack is server-authoritative: the browser is redirected to Paystack and the
transaction is verified (and also accepted through the signed webhook) before a
Payment Entry is submitted. The amount is sent in the currency's minor unit and
re-checked against the current invoice balance. Configure Paystack's webhook to
`https://<site>/api/method/crm.api.checkout.paystack_webhook`.

Manual transfer reports create a draft Payment Entry with provider/reference
metadata. Finance confirms the bank statement and submits it through
`crm.api.checkout.confirm_bank_transfer`; the public page never marks a manual
transfer as paid.

The `seed_checkout_payment_settings` patch adds Paystack configuration fields and
seeds ERPNext's native accounting records where installed:

- TIBERBU HEALTHNET LIMITED
- Gulf African Bank
- account `0300163301`
- branch `UpperHill`
- KES bank account and Bank Transfer/Paystack modes of payment

Paystack keys are intentionally blank and must be configured by a System
Manager. The Network Detail → Prequalified Contacts table can send the same
protected link to the stored opted-in contact, and completed OIS submissions
automatically send it to the facility signatory.

The same seeded destination is available to Terms & Conditions and contract
renderers as `{{ bank_account_name }}`, `{{ bank_name }}`,
`{{ bank_account_number }}`, `{{ bank_branch }}`, and `{{ bank_gl_account }}`.
The grouped form is `payment_bank_details.account_name` (with corresponding
`bank`, `account_number`, and `branch` keys).
