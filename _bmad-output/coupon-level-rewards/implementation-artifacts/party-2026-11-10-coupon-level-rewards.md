# Party Mode: one coupon, a reward per facility level (2026-11-10)

**Led by:** 📋 John (Product Manager), with 🏗️ Winston (Solutions Architect)
**Also in the room:** 📊 Mary (Business Analyst), 💻 Amelia (Developer), 🎨 Sally (UX Designer), walk-ons 😤 Grumbal (The Adversary) and 🌶️ Boundary (Edge-Case Hunter)
**Mode:** design, then implementation and Playwright review
**Brief (owner):** 1,000 bonus tokens go much further at a Level 2 facility than at a Level 4 (60% or more fewer patients served at Level 4). At coupon creation, set the tokens per facility level, for Flex and Fixed: add a level and give its token amount, or its discount % for Fixed. One coupon, two clients at different levels, each gets their level's reward.

## Evidence on the table

| # | Observation | Source |
|---|---|---|
| E1 | A coupon has one Flex value (`value_type`/`value`/`max_tokens`) and one Fixed discount. | `crm_coupon.json` |
| E2 | Facility level only decides *who* gets a CRM coupon (`targeting = Facility Level`). Network coupons ignore it. | `coupons._crm_coupon_candidates` |
| E3 | The level on record is `CRM Pre-Qualified Facility.keph_level`; onboarding writes it from the registry. Values seen: "Level 2", "Level 3B", "3". | `facility_onboarding.py`, dev data |
| E4 | Level names are already compared with `value_express.level_key` for Fixed pricing. | `value_express.py` |
| E5 | The metering app caps a coupon line at `coupon_tokens(coupon.value, …)`. A larger Level 2 amount would be cut back to the base value. | mediator `grants._coupon_line` |

## The session

📋 **John:** The owner's point is about fairness, not generosity. A thousand tokens at a dispensary is a month of patients. At a Level 4 it's a long weekend. So the partner wants Level 2 at 1,000 and Level 4 at, say, 2,500, on the *same* coupon, the same six digits.

📊 **Mary:** Same for Fixed. A 10% discount on a Level 2 fee and 4% on a Level 4 fee. The level table needs both columns, and Flex-only coupons just hide the discount column.

🏗️ **Winston:** One child table on the coupon. Level, Flex value, Fixed discount. The coupon's own values stay, and they mean "every other level". That way an old coupon is just a coupon with no rows, so there's nothing to migrate.

😤 **Grumbal:** "Every other level" sounds generous until a Level 5 hospital walks in and gets the Level 2 amount because nobody listed Level 5.

📋 **John:** Then the partner puts 0 in "All other levels". Zero means that level gets nothing and the coupon isn't picked for it. Explicit, visible on the card.

🌶️ **Boundary:** Levels are free text. "Level 3" and "Level 3B" are different levels. "level  3b" with two spaces is the same one. And a facility with no level on record?

💻 **Amelia:** We match with `level_key`, the same function Fixed pricing uses, so no fuzzy matching and spacing and case don't matter. No level on record means "All other levels". And the dialog suggests real levels: the self-onboarding allowed list, the Fixed packages' levels and the levels in the registry table. You can still type a new one.

🌶️ **Boundary:** Two rows for "Level 2" and "level 2"?

💻 **Amelia:** Refused. One row per level by `level_key`.

😤 **Grumbal:** Now the bit that bites. E5. The metering app re-checks the line against `coupon.value`. Your Level 4 gets 2,500 on the order, the invoice is paid, and the grant hands out 1,000. Support ticket by lunch.

🏗️ **Winston:** Right. The redemption records the facility's level at confirmation, and CRM gets one function, `token_ceiling(coupon, purchased, level)`. The mediator calls it with the redemption's level. If the mediator is older and doesn't call it, it falls back to the base value. That under-grants, but never over-grants.

😤 **Grumbal:** And a facility upgraded from Level 2 to Level 3 between draft and confirm?

💻 **Amelia:** Confirmation recomputes from the level on record at that moment. Server value wins, like it already does for tokens and the discount. The redemption keeps that level, so grant time agrees with confirmation.

📊 **Mary:** Picking between CRM coupons, "largest benefit" has to be the benefit *for this facility's level*. Otherwise a coupon that's big at Level 4 but zero at Level 2 beats a real Level 2 coupon.

💻 **Amelia:** `_benefit` gets the level. It already returns None for zero.

🌶️ **Boundary:** Can you edit the table after the coupon's been used?

📋 **John:** No. Same rule as the value: revoke and make a new one.

🎨 **Sally:** The dialog gets a checkbox, **Set the reward per facility level**, in brand red like the plan radios (we're not repeating the forms-blue mistake). Below it, one row per level: Level, Tokens (or % of purchase), Fixed discount, and a remove button. **Add level** under the rows. The normal value fields get the heading **All other levels**. The card says "By facility level" with one line per level: "Level 2: 1,000 tokens · 10% off Fixed". Sentence case, ink-gray-7 labels, no new colours.

🎨 **Sally:** The client never sees the table. Their order already shows their own number, because the order line is built from the resolved reward. The onboarding offer lists the levels, because a partner sharing six digits wants the clinic to know what *its* level gets.

## Decisions

P-116 to P-123: [adr-coupon-level-rewards.md](../planning-artifacts/adr-coupon-level-rewards.md).

## Verification

- CRM unit tests (crm-dev, scratch runner, commits stubbed, rolled back, data snapshot unchanged): 22 new in
  `test_coupon_level_rewards.py`; 228 coupon, bonus and portal tests run, 226 pass. The 2 failures
  (`test_partner_portal` idempotency) fail the same way on unchanged `develop`. `test_portal_commercial`
  errors in its own setup on crm-dev data (a group Customer Group), also on `develop`.
- Mediator: 144 run, 143 pass (1 new). `TestSetupChecklist.test_empty_openmeter_…` fails the same way without this change.
- Frontend unit tests: 346 pass (6 new).
- Dev CRM, real draft orders built the way self-onboarding builds them, one Both coupon: Level 2 Flex gets
  1,000 coupon tokens, Level 4 Flex 2,500, Level 2 Fixed 10% off, Level 3B Fixed 4% off.
- Playwright `e2e/metering/coupon_level_rewards.spec.ts` passes: card lines, dialog with level rows (brand-red
  checkbox asserted, suggested levels), the four order reviews, and confirmation recording the level with the
  metering grant check letting 2,500 through. Regression: `coupon_plan_scope.spec.ts` passes; the portal UI
  brand suite passes at all four viewports (126 passed, 126 skipped by design).
