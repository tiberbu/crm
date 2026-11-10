# ADR: Coupon rewards by facility level

- **Status:** Accepted (2026-11-10, party: `../implementation-artifacts/party-2026-11-10-coupon-level-rewards.md`)
- **Decisions:** P-116 to P-123
- **Builds on:** plan-scoped coupons P-107 to P-115 (`../../coupon-plan-scope/planning-artifacts/adr-coupon-plan-scope.md`)

## Owner brief (2026-11-10)

> 1,000 free or bonus tokens given to a Level 2 facility serve a certain number of patients. Given to a
> Level 4 facility, they serve far fewer (60% or more fewer than at Level 2). When a coupon is
> created, it must be possible to set the tokens per facility level, for Flex and Fixed plans alike:
> add a facility level and give its token amount, or its percentage discount for the Fixed plan.
> The same coupon can then be used by two clients at different facility levels, and each gets the
> reward set for their facility's level.

## Before

| Area | Behaviour |
|---|---|
| Coupon value | One value for every facility: `value_type`/`value`/`max_tokens` (Flex) and `fixed_discount_percent` (Fixed) |
| Facility level | Used only to decide *who* gets a CRM coupon (`targeting = Facility Level`), never *how much* |
| Grant check | The metering app caps a coupon token line at `coupon_tokens(coupon.value_type, coupon.value, …)`, so a larger per-level amount would be cut down |

## Decisions

**P-116: A coupon can set its reward per facility level.** New check **Reward by facility level**
(`reward_by_level`) and a table **Level rewards** (`level_rewards`, child doctype
`CRM Coupon Level Reward`). Each row: `facility_level`, `flex_value` (Flex reward, read in the
coupon's value type: tokens for flat coupons, % of purchased tokens for percentage coupons) and
`fixed_discount_percent` (Fixed reward). Works for Flex, Fixed and Both coupons, and for partner
network coupons and CRM coupons alike.

**P-117: The facility's registry level picks the row.** The level is the facility's
`CRM Pre-Qualified Facility.keph_level` (what onboarding and the Fixed pricing already use). Matching
uses `value_express.level_key` (Unicode-normalised, spacing and case ignored: "level  3b" = "Level 3B").
No fuzzy matching: "Level 3" does not match "Level 3B".

**P-118: The coupon's own values are the reward for every other level.** When levels are on, the
normal value fields are relabelled **All other levels** and may be 0. A facility whose level is
not listed (or is not on record) gets those values; 0 means the coupon gives that plan nothing at
those levels, and the coupon is not picked for them.

**P-119: Row rules.** At least one row. Each level appears once (by `level_key`). Each row gives
at least one benefit the coupon's plan uses. A Flex value is a whole number of tokens from 1 to
1,000,000 (flat) or more than 0% and at most 100% (percentage); a Fixed discount is more than 0%
and at most 100%. 0 means "nothing for this plan at this level". Fields for a plan the coupon does
not apply to are cleared. The coupon's token cap (`max_tokens`) still applies to every level.

**P-120: Everything else is unchanged.** One coupon use per facility (P-111), one live coupon per
network window, validity, max redemptions, plan checks (P-109), the Flex-purchase rule (P-107) and
confirmed-price rule (P-112) work exactly as before. `targeting = Facility Level` still decides who
may get a CRM coupon; level rewards decide how much. When a CRM facility qualifies for several
coupons, the existing "assigned first, then largest benefit" choice compares each coupon's reward
*for that facility's level*.

**P-121: The level is recorded and re-checked at grant time.** At confirmation the server recomputes
the reward from the coupon and the facility's level (server value wins over anything stamped on the
draft), and the redemption stores `facility_level`. The metering app's grant check
(`grants._coupon_line`) calls the new `crm.utils.coupons.token_ceiling(coupon, purchased, level)` with
the redemption's level, so a per-level amount is neither cut down nor exceeded. A mediator without the
call keeps the old base-value check.

**P-122: Level rewards are fixed once used.** `reward_by_level` and the rows join the immutable
fields: once a coupon has a redemption, changing them is refused (revoke and create a new coupon).

**P-123: Everyone sees the level rewards.** Settings › Coupons shows "By facility level" on the card
with one line per level and "All other levels". The dialog offers a level list drawn from the
self-onboarding allowed levels, the Fixed package levels and the levels on record. The guest onboarding
offer lists the rewards per level. Order lines and the CX order review show the facility's own amount
(they already read the resolved value).

## Data and migration

- New child doctype `CRM Coupon Level Reward`: `facility_level` (Data, required), `flex_value` (Float),
  `fixed_discount_percent` (Percent).
- `CRM Coupon`: `reward_by_level` (Check, default 0), `level_rewards` (Table).
- `CRM Coupon Redemption`: `facility_level` (Data, read only).
- No data patch: every existing coupon has `reward_by_level = 0` and behaves as before.
- New API: `crm.api.coupons.coupon_level_options()`; `get_coupon`, `list_coupons` and `save_coupon`
  carry `reward_by_level` and `level_rewards`; `public_offer` adds them to the guest offer.

## Stories

| # | Story | Done when |
|---|---|---|
| S1 | Doctype fields, child table, validation and immutability | Controller tests pass for every rule in P-116/P-118/P-119/P-122 |
| S2 | Level-aware resolution, claim and redemption level | Two facilities (Level 2, Level 4) on one coupon get their own tokens and discount |
| S3 | Metering grant re-check uses the level | `token_ceiling` tests; mediator `_coupon_line` honours a per-level amount |
| S4 | Admin UI: dialog rows, level options, card lines; guest offer label | Unit tests for label helpers; Playwright journey |
| S5 | Docs and Playwright journey | `coupon-admin-lifecycle.md` section; `e2e/metering/coupon_level_rewards.spec.ts` passes; existing coupon journey still passes |
