# Welcome bonus: dispense once, by button, auto-assign or first payment

The welcome bonus (Settings › Opt-In › **First-purchase bonus tokens**) is a facility's one-time
complimentary Care Tokens. A facility can now receive it in one of three ways. Whichever comes first
grants it, and the other two then add nothing.

| Path | When | Who |
|---|---|---|
| **Dispense button** | Any time before the bonus is out | An OpenMeter Admin, on Deal › Metering › the facility's card |
| **Auto-assign** | When the facility selects a Flex package (its token Sales Order is created or submitted), before payment | Settings › Opt-In › **Auto-assign the bonus when a package is selected** (off by default) |
| **First paid package** | When the first token invoice is paid in full | Automatic, as before |

## Rules

- **Once per facility, ever.** All three paths write the same metering ledger entry,
  `OpenMeter Grant` `welcome:<FID>`. The grant runs under a Redis lock, and before posting it looks
  for a grant OpenMeter already holds under that key. Two clicks, a click racing a payment, or a
  worker that died mid-grant therefore cannot grant the bonus twice.
- **After a dispense, payment grants the package only.** The paid invoice's welcome line (if it
  has one) finds the ledger entry settled and is skipped. Open draft orders lose their welcome line
  as soon as the bonus is dispensed, so the client's review shows only the package. Orders confirmed
  after that never get the line.
- **No dispense, then payment grants package + bonus**, exactly as before.
- **The button** reads *Dispense N bonus tokens*. It asks for confirmation, then turns grey
  (*Bonus dispensed*) and stays disabled once the ledger entry is Granted, whichever path granted
  it. The card says when the bonus went out and how. A failed attempt leaves the button enabled and
  shows the error, so the admin can retry without risking a double grant.
- **Auto-assign** follows the existing bonus rule: Flex packages only (not Custom amounts or Fixed
  fees). If the facility has no Facility ID or metering site yet, or OpenMeter is down, the attempt
  is logged in the Error Log. The first paid invoice still carries the bonus, and the button still works.
- A bonus dispensed before payment is **not reclaimed** if the order is later cancelled.

## Full payment only

Tokens are released only by an invoice that is **paid in full**: submitted, not a return,
ERPNext status `Paid`, and nothing outstanding (`openmeter_mediator.services.grants.is_fully_paid`).

- A **part payment** (status `Partly Paid`) grants nothing. When the rest is paid, the package (and the
  bonus, if it is still due) is granted once.
- A **credit note** that brings the outstanding amount to 0 (status `Credit Note Issued`) is a
  refund, not a payment, and grants nothing. Before this change it released the tokens.
- The Payment Entry hook and the 15-minute backstop scan apply the same rule.

## Configuration

- Settings › Opt-In: **First-purchase bonus tokens** (0 turns the bonus off and disables the button)
  and **Auto-assign the bonus when a package is selected**.
- Needs `openmeter_mediator` with the `crm_welcome_bonus_status` and `crm_dispense_welcome_bonus` hooks.
  Without it, the card says no metering app is installed and auto-assign does nothing.
- Migration: patch `crm.patches.v1_0.add_welcome_bonus_auto_dispense` adds the switch (default off).

## Tests

- Unit: `crm/tests/test_welcome_bonus_dispense.py`, `crm/tests/test_express_draft_order.py`
  (`TestTokenBonuses`), `openmeter_mediator/tests/test_mediator.py` (`TestWelcomeBonusDispense`,
  `TestFullPaymentOnly`).
- Playwright: `e2e/metering/welcome_bonus_dispense.spec.ts` (button → part payment → full payment) and
  `e2e/metering/welcome_bonus_auto_assign.spec.ts`. The fixture is `crm.tests.e2e_express_fixture.setup`
  with `admin_password`, `partner_coupon: false` and `auto_dispense`. See `e2e/metering/README.md`.
