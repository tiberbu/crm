# Express Journey: draft order → invoice → payment → tokens

Status: Implemented (awaiting maintainer review) · 2026-10-27
Party review: Mary (analyst), John (PM), Winston (architect), Amelia (dev), Sally (UX), Murat (test architect)

## Problem

Submitting a Tiberbu Express request credits the facility's token package before anything is paid:

1. `submit_onboarding` creates the Customer, Deal and a draft Quotation, then queues HMIS provisioning.
2. When the setup service accepts provisioning, CRM runs `crm_on_hmis_provisioning_submitted`.
   openmeter_mediator's `on_provisioning_submitted` syncs the site **and grants the Initial Package**.
3. The CX portal facility card falls back to the package size when OpenMeter has no balance, so it
   shows the package's tokens even when nothing was granted.

## Target flow

1. Submit request → provisioning starts in the background, as before.
2. A **draft Sales Order** is created from the preselected package for each facility (docstatus 0).
3. The portal facility card shows **0 tokens** until OpenMeter reports a balance.
4. Billing → **Draft orders**: the client reviews the order, then:
   - picks a saved billing address or adds one (reusable: ERPNext Address of type Billing linked to the Customer);
   - enters the KRA PIN (mandatory; stored on `Customer.tax_id`, which eTIMS reads);
   - chooses **One-time** or **Recurring** (Monthly / Quarterly / Yearly).
5. **Confirm order & generate invoice** submits the Sales Order and creates and submits its Sales Invoice.
6. The client pays (Paystack, M-Pesa report or bank transfer, as today). The Payment Entry `on_submit` hook in
   openmeter_mediator grants the package's tokens (existing `grant_for_payment_entry`).
7. The portal reads the facility's available tokens from OpenMeter.

Pricing cards no longer say "/ monthly": the price buys the stated tokens.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | CRM puts `defer_package_grant: true` in the provisioning context for **paid** packages; the metering app then settles `initial:<FID>` as **Skipped**. | The backstop job grants any Initial Package that is not Granted/Skipped. Leaving it unsettled would grant it later. |
| D2 | ~~Zero-priced packages (Free Trial) keep the grant at provisioning.~~ **Reversed 2026-10-27:** no tokens before payment; nothing is granted at provisioning (setup service contract v2, D5). | Nothing to pay; waiting on a KES 0 invoice adds a step with no value. **Flagged for maintainer review.** |
| D3 | Draft Sales Order, not draft Quotation. The onboarding Quotation is submitted and the order made from it. | The brief asks for an order; the CRM Deal keeps its quote link. |
| D4 | KRA PIN on `Customer.tax_id`, validated `^[A-Z]\d{9}[A-Z]$`. | eTIMS reads the customer's tax id; one PIN per customer, reused across orders. |
| D5 | Recurring = ERPNext **Auto Repeat** on the submitted Sales Order, `submit_on_creation = 0`. | Each period's order arrives as a draft for the client to review again. No silent charges. |
| D6 | Confirming an order stamps a purchase key when missing (auto-repeated orders copy none: the field is `no_copy`). | Invoice idempotency looks the key up; an empty key would match unrelated invoices. |
| D7 | Facility card fallback is 0, not the package size. | The dashboard shows what OpenMeter reports. |

## Data

New Sales Order custom fields (patch `crm.patches.v1_0.add_token_order_frequency_fields`):

- `crm_order_frequency`: Select `One-time` / `Recurring`, default `One-time`
- `crm_recurrence_period`: Select `Monthly` / `Quarterly` / `Yearly`, shown when Recurring

No new DocTypes. Address and Customer use standard ERPNext fields.

## API (crm.api.customer_experience)

| Method | Purpose |
|---|---|
| `create_express_draft_order(customer, facility_mfl, package, quotation=None)` | Internal. Called by `submit_onboarding`; idempotent per customer/facility/package/period. |
| `get_draft_order(sales_order)` | Portal: order lines, totals, saved billing addresses, current KRA PIN, frequency. |
| `confirm_draft_order(sales_order, billing_address=None, new_address=None, kra_pin, frequency, recurrence_period=None)` | Portal: validate, save address/PIN, set frequency, submit the order, create and submit the invoice; set up Auto Repeat when Recurring. |

The portal `open_orders` list now includes drafts (`is_draft: true`).

## openmeter_mediator

`on_provisioning_submitted(fid, context)`: when `context.defer_package_grant`, sync the site with
`grant=False` and settle `initial:<FID>` as Skipped ("Tokens are granted when the token invoice is paid").

## Stories

1. **Defer paid package grant** — `openmeter_mediator/services/provisioning.py` (primary), `crm/api/hfr.py`.
2. **Draft order on Express submit** — `crm/api/customer_experience.py` (primary), `crm/api/facility_onboarding.py`.
3. **Review and confirm draft order** — `crm/api/customer_experience.py`, patch, `crm/api/website_redirect.py`.
4. **Portal draft-order review UI and 0-token card** — `frontend/src/pages/FacilityPortal/FacilityPortal.vue`.
5. **Remove monthly wording from pricing** — `FacilityPortal.vue`, `FacilityOnboardingLanding.vue`.
6. **Tests** — CRM pytest, mediator pytest, Playwright `e2e/metering/express_draft_order.spec.ts`.

## Verification

- `crm/tests/test_express_draft_order.py`: draft order created as docstatus 0; confirm requires KRA PIN and address;
  confirm submits order and invoice; Recurring creates a draft-producing Auto Repeat; repeated orders get a key.
- `openmeter_mediator/tests/test_provisioning_hooks.py`: deferral settles the initial grant as Skipped and grants nothing.
- Playwright `e2e/metering/express_draft_order.spec.ts` (fixture `crm.tests.e2e_express_fixture.setup`): card shows 0 and
  the gateway 0 → no "/ monthly" on pricing → review → address (new, then reused on the next run) + KRA PIN → confirm →
  still 0 → cash payment approved → portal and gateway show the package tokens from OpenMeter.

## Follow-ups (not in this change)

- Facilities submitted before this change that are not yet provisioned have no draft order, and a paid package is no
  longer granted at provisioning: they buy tokens from the portal top-up action (unchanged: it raises a submitted order).
- Portal top-ups do not yet ask for the billing address / KRA PIN; bring them through the same review step if eTIMS needs it.
- Free Trial (KES 0) packages are still granted at provisioning (D2): **decided 2026-10-27, no grant before payment** (CRM-P3 and X2 in `docs/hmis-provisioning-status-api-requirements.md`).
- KRA PIN check against KRA iTax is not done here; eTIMS invoice submission validates it.
