# Subscription lifecycle: Fixed and Flex plans

**Status:** Built 2026-11-09. Decisions: openmeter_mediator ADR-007 (P-97 to P-106). Checklist and open items: openmeter_mediator `_bmad-output/planning-artifacts/subscription-lifecycle-checklist.md`.

## The two plans

| | Flex | Fixed |
|---|---|---|
| Buys | Prepaid tokens | Platform access for a billing period |
| Starts | First fully paid token invoice (grant in OpenMeter) | Fully paid Fixed-package invoice (a subscription term) |
| Renews | Another paid token invoice (top-up) | Another paid Fixed invoice; an early one starts when the current term ends, so no paid day is lost |
| Ends | Never: tokens don't expire. Only an empty balance stops work | At `expires_at`, or earlier if cancelled |
| Cancel | Not applicable; suspend the site instead | **Cancel subscription** (reason required): the term and paid renewals end now. A cancelled invoice or a credit note revokes its term automatically. Refunds are Finance's |
| Pause | **Suspend site** / **Reactivate site** (reason required) | Same |

## What happens when a Fixed invoice is paid

1. Finance records the payment (Payment Entry). Once the invoice is **fully paid** and something was
   actually collected, the metering app records one subscription term for the invoice's facility
   (FID): it starts when the invoice was paid (or when the live term ends) and runs for the
   package's billing period × the invoice quantity.
2. The facility's plan is written to its OpenMeter customer (`plan_type`, `subscription_*`).
3. Within 5 minutes, HMIS sees it at `GET /ingest/v1/plan`.

A 15-minute job is the backstop for missed payments, starts scheduled renewals, expires lapsed
terms and retries any projection that failed. An invoice found late starts from its payment date,
so it never gives a free period.

## The HMIS API

`GET https://<billing-host>/ingest/v1/plan` with the facility's `X-OpenMeter-Site-Key`:

```json
{"site": "FID-…", "as_of": "2026-11-09T10:08:55Z", "plan_type": "subscription", "has_access": true,
 "subscription": {"status": "active", "package": "Value Express Fixed - Level 2", "billing_period": "Monthly",
                  "activated_at": "2026-11-09T10:08:50Z", "expires_at": "2026-12-09T10:08:50Z", "cancelled_at": null},
 "tokens": null}
```

`plan_type` is `subscription`, `tokens` or `none`. The gateway computes the status from the dates on
every call, so access always ends at `expires_at`. Full contract: openmeter_mediator
`docs/hmis-ingest-contract.md` §3a.

## Where to manage it

Deal › **Metering** tab › the facility card's **Plan** section (OpenMeter Admins). See
[deal-metering-tab.md](deal-metering-tab.md).

## Open decisions (not built)

Renewal reminders, automatic renewal invoices, a grace period, the CX Portal view, Opt-In network
invoices, the welcome bonus on Fixed facilities and refunds on cancellation are open owner decisions.
Each has its context, options and constraints in openmeter_mediator
`_bmad-output/planning-artifacts/subscription-open-decisions.md` (D-1 to D-7). Read it before working
on any of these, and record the decision there first.

## Deployment

1. Metering app (openmeter_mediator): deploy and migrate (new doctype `OpenMeter Subscription`).
2. Metering gateway 1.1.0, and the APISIX route for `GET /ingest/v1/plan`.
3. CRM frontend build.
4. HMIS: pull `/plan` (story HMIS-H6).
