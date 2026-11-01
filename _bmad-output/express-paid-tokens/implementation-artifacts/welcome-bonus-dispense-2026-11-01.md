# P-76 Welcome bonus: auto-assign, one-time Dispense button, payment dedupe, full payment only

Status: Implemented (awaiting maintainer review) · 2026-11-01 · builds on
`../planning-artifacts/token-bonus-and-partner-coupon-2026-10-27.md`
Party review: Mary (analyst), John (PM), Winston (architect), Amelia (dev), Sally (UX)

## Brief (from the maintainer)

1. Facilities get no free tokens until they pay for a package. Add an Admin UI setting that
   **auto-assigns the free/bonus tokens as soon as a package is selected**.
2. Add a **button** that dispenses the free tokens to the facility. It works **once only**, while the
   first-time tokens have not been added, and is **greyed out/disabled** afterwards.
3. When the first package is paid: if neither auto-assign nor the button dispensed the bonus, grant
   package + bonus; otherwise grant **only the package**. No double token assignment.
4. Review and enforce that the payment-triggered grant fires on **full payment only**, never on part payment.

## Party review (condensed)

- **Mary:** "Free tokens" here means the existing **Welcome Bonus** (`welcome_bonus_tokens`), not the
  Partner Coupon. The coupon is out of scope.
- **Winston:** The mediator already keys the bonus `welcome:<FID>` under a Redis lock and in the
  `OpenMeter Grant` ledger. Make that key the **only** once-per-facility record, with no second flag
  that could drift. Every path goes through it.
- **Amelia:** Two new mediator hooks (`crm_welcome_bonus_status`, `crm_dispense_welcome_bonus`), so CRM
  still never imports the app. `grant_invoice` already skips a settled bonus key, so dispense-then-pay
  gives the package only. Pin it with tests.
- **Winston:** An order must not show a "+N free" line the ledger will not honour.
- **John:** A credit note zeroes the outstanding amount, and today that would release tokens. Require
  status `Paid` and not a return, on both the event path and the backstop scan.
- **Sally:** The button goes on Deal › Metering › facility card: "Dispense N bonus tokens", with a confirm.
  Afterwards it is disabled, with "N tokens dispensed on <date> by <user> / automatically when package
  <SO> was selected / with paid invoice <SI>". It is disabled while running.
- **John:** A failed attempt must stay retryable. Only Granted/Skipped count as dispensed.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | The ledger entry `OpenMeter Grant` `welcome:<FID>` is the single source of truth for "dispensed". | One record for button, auto-assign and payment, so they cannot disagree. The existing lock and remote-lookup make it race-safe and lost-response safe. |
| D2 | `dispense_welcome_bonus(fid, tokens, source_doctype, source_name)` in the mediator; the source records how it went out (User / Sales Order / Sales Invoice). | The card can say who or what dispensed it, with no schema change. |
| D3 | CRM owns the quantity (`welcome_bonus_tokens`) and the role check (OpenMeter Admin via `crm_metering_admin_access`). | CRM owns commercial settings; the mediator hook is reused by the system-run auto job. |
| D4 | Auto-assign is a CRM Opt-In switch, **off by default**, fired on Sales Order `after_insert` and `on_submit` and enqueued after commit. It applies to **Flex packages only**. | It matches the existing bonus eligibility (`_earns_bonus`). Off by default changes nothing until the maintainer opts in. |
| D5 | Once dispensed, `eligible_bonuses` stops adding the welcome line, and the dispense drops the line from the facility's **draft** orders. Confirmed orders keep theirs. | The client's review and invoice never promise a bonus the meter will not grant. Submitted orders are immutable, and the mediator skips their line. |
| D6 | Full payment = `docstatus 1`, `is_return 0`, status `Paid`, outstanding ≤ 0.005 (`is_fully_paid`), in `grant_invoice` and in `scan_token_purchases`. | It closes the credit-note gap (status `Credit Note Issued`, outstanding 0). Part payment was already refused; it is now pinned by unit and Playwright tests. |
| D7 | A failed or interrupted dispense leaves the button enabled; auto-assign failures go to the Error Log. | Retry is safe (D1), and the first paid invoice still carries the bonus as a fallback. |
| D8 | A dispensed bonus is not reclaimed when an order is cancelled. | It is a per-facility welcome, not tied to one order. Flagged for review. |

## Files

openmeter_mediator (branch `feat/welcome-bonus-dispense`)
- `openmeter_mediator/services/grants.py`: `is_fully_paid`, `_ready_site`, `welcome_bonus_key`,
  `welcome_bonus_status`, `dispense_welcome_bonus`; the scan SQL requires `Paid` and not a return.
- `openmeter_mediator/hooks.py`: `crm_welcome_bonus_status`, `crm_dispense_welcome_bonus`.
- `openmeter_mediator/tests/test_mediator.py`: `TestWelcomeBonusDispense`, `TestFullPaymentOnly`.

crm (branch `feat/welcome-bonus-dispense`)
- `crm/utils/token_bonus.py`: status/dispense wrappers, the auto-assign hook and job, draft-line cleanup,
  and `eligible_bonuses` skipping a dispensed bonus.
- `crm/api/metering_admin.py`: `get_welcome_bonus`, `dispense_welcome_bonus` (OpenMeter Admin only).
- `crm/api/optin_admin.py`, `frontend/src/components/Settings/OptInSettings.vue`: the auto-assign switch.
- `crm/patches/v1_0/add_welcome_bonus_auto_dispense.py`, `crm/patches.txt`.
- `crm/hooks.py`: Sales Order `after_insert` / `on_submit`.
- `frontend/src/pages/Deal/FacilityMeteringCard.vue`, `MeteringTab.vue`: the Welcome bonus block and button.
- Tests: `crm/tests/test_welcome_bonus_dispense.py`, `crm/tests/test_express_draft_order.py`.
- E2E: `e2e/metering/welcome_bonus_dispense.spec.ts`, `welcome_bonus_auto_assign.spec.ts`,
  `journey.ts` (part payment), `crm/tests/e2e_express_fixture.py` (admin user and Deal).
- Docs: `docs/welcome-bonus-dispense.md`, `docs/deal-metering-tab.md`, `e2e/metering/README.md`.

## Verification (2026-11-01)

| Check | Result |
|---|---|
| Mediator unit tests (`test_mediator`, test site) | 97 / 97 pass (10 new) |
| CRM new + bonus tests (`test_welcome_bonus_dispense`, `test_express_draft_order`) | 38 / 38 pass |
| CRM full Python suite | 739 run; the 55 failures are identical to a `develop` baseline run (environmental: KES→USD exchange rate, VAT template, Frappe 15/16 test imports) |
| Frontend unit (`yarn test:run`) | 241 / 241 pass |
| Playwright `welcome_bonus_dispense` on the dev site | pass: button → disabled → repeat no-op → no bonus line → part payment 0 → full payment = bonus + package |
| Playwright `welcome_bonus_auto_assign` on the dev site | pass |
| Playwright `express_draft_order` (no dispense: package + bonus + coupon) | pass |
| Playwright `openmeter_token_topup` | pass |
| Playwright portal-ui regression | 68 / 68 pass |
| Playwright facility regression | 5 pass, 8 fail, the same 8 as on a `develop` build (pre-existing: duplicate-FID strict-mode locator, onboarding network screens) |

The first Playwright run found a real gap: a draft order built before the dispense still showed the bonus
line until it was confirmed. D5's draft cleanup fixes it, and the rerun passed.

## Follow-ups

- The Partner Coupon has no button or auto-assign (out of scope).
- Fix the 8 pre-existing facility regression failures separately.
