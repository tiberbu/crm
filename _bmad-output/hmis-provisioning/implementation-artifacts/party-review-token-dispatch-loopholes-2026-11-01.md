# Party review: unpaid token dispatch from "Sync to OpenMeter" (2026-11-01)

Roster: Winston (architect), Amelia (dev), Mary (analyst), John (PM).

## Incident

Deals › Metering › **Sync to OpenMeter** granted a facility's whole paid package
("Initial Package" grant) with no payment. The welcome-bonus button stayed active
because the bonus ledger was untouched. That was correct behaviour, but it hid the problem.

## Root cause

`sync_site()` defaults to `grant=True` and calls `ensure_initial_grant()`, which
granted `site.token_quantity` unconditionally. "Initial Package" was assumed to be a
free plan. The only thing that settled a *paid* package as Skipped was CRM's
`defer_package_grant` flag on `on_provisioning_submitted`. Every other caller bypassed it:

| Path | Trigger |
|---|---|
| Sync to OpenMeter (manual) | `api/admin.sync_site` → `sync_site(grant=True)` |
| Auto-sync on activation | `OpenMeter Site.on_update` → `sync_site_job` |
| Provisioning backstop | `retry_incomplete_provisioning_job`, every 15 min, every Active site with a package and no settled initial grant. **It needed no click.** |
| Bonus / invoice site bootstrap | `_ready_site` → `ensure_site_for_fid` made the site Active, and the backstop then granted it |

Evidence on the dev site: 5 paid-package facilities had Initial Package grants with
no payment. 2 of them later paid and were granted again (double dispatch).

## Fixes (openmeter_mediator + crm)

1. **One invariant, in one place:** `ensure_initial_grant` grants only a package the
   CRM catalog lists at price 0, capped at the catalog token quantity. A package that
   is paid, has no list price or is unknown is settled as Skipped ("granted only when
   the token invoice is paid in full"). This covers every caller above.
2. **Sync only registers:** the Sync action calls `sync_site(grant=False)`.
3. **Provisioning passes `package_item`** so the mediator checks the price itself
   instead of trusting the `defer_package_grant` flag.
4. **Zero-charge invoices wait:** a priced package on an invoice whose grand total
   minus write-off is 0 (a 100% discount or full write-off) returns Pending instead of
   granting, even though ERPNext marks it Paid.
5. **Bonus lines are capped** at the Opt-In Settings welcome/coupon sizes. The invoice
   line is editable through the API.
6. **Welcome bonus button** refuses an FID that no CRM facility carries. The mediator
   would otherwise create an Active site for any string.

## Confirmed sound (no change)

- `is_fully_paid`: submitted, not a return, status Paid, nothing outstanding. A credit note never releases tokens.
- Invoice tokens come from the catalog × qty, not from invoice amounts.
- Per-key Redis lock + ledger + remote idempotency-key lookup: no double grant from concurrent or lost-response retries.
- Welcome bonus: one `welcome:<FID>` key shared by the button, auto-assign and the first paid invoice.

## Open (product decision, not changed)

- **No revocation:** a Payment Entry cancelled, or a credit note issued after the
  grant, leaves the tokens granted. Decide whether to void, claw back, or flag for finance.
- **Wrongly granted dev rows:** existing Initial Package grants on paid packages are
  left as they are. Void them in OpenMeter only after finance confirms.
- A paid package skipped at Sync is final for `initial:<FID>`. If a facility later
  moves to the free trial, its free grant needs an admin to clear the Skipped row.

## Verification

- openmeter_mediator: 108 tests OK, 12 new in `TestNoUnpaidDispatch`. With only the
  Sync change reverted, both Sync tests fail, so each layer is tested on its own.
- crm: `test_hmis_token_source`, `test_hmis_provisioning_api_v2_0`,
  `test_welcome_bonus_dispense`, `test_metering_admin`, `test_hmis_provisioning_journey`: 90 tests OK.
- Dev site after restart: the catalog guard reads paid vs free packages correctly. The UI click was not re-run.
