# Party Mode: coupons by plan, bonus tokens for Flex only, the customer's subscription (2026-11-09)

**Led by:** 🏗️ Winston (Solutions Architect), with 📋 John (Product Manager)
**Also in the room:** 📊 Mary (Business Analyst), 💻 Amelia (Developer), 🎨 Sally (UX Designer), walk-ons 😤 Grumbal (The Adversary) and 🌶️ Boundary (Edge-Case Hunter)
**Mode:** code review, then implementation and Playwright review
**Brief (owner):** Free or bonus tokens only for a facility that has purchased a Flex token package. A Partner Network can create a coupon that takes a percentage off (e.g. 5%). When creating a coupon, say whether it is for Fixed, Flex or both; for both, tokens for Flex and a discount for Fixed. Redemption must check that a Flex coupon is used only on Flex package invoices. A purchased Fixed subscription must be visible on the customer side.

## Evidence on the table

| # | Observation | Source |
|---|---|---|
| E1 | Coupons carry only a token value (`flat_tokens` / `percentage_of_purchase`). Nothing on the coupon says which plan it is for. | `crm_coupon.json`, `coupon_math.py` |
| E2 | Bonus lines are added to Flex orders only (`_earns_bonus`), but that rule lives in one function. The claim and the metering grant never check the plan. | `token_bonus.py`, `coupons.claim_on_submit`, mediator `_coupon_line` |
| E3 | The Deal › Metering **Dispense** button grants the welcome bonus to any facility, even one with only a Fixed order or no order at all. | `metering_admin.dispense_welcome_bonus` |
| E4 | Fixed orders come from self-onboarding through `_order_package`. A coupon gives them nothing. | `facility_onboarding.py`, `customer_experience.py` |
| E5 | The CX Portal already routes Fixed facilities to a time-bound view (Plan, Next invoice), but has no activation or expiry dates. | `FacilitySingleView.vue`, `portal_commercial.py` |
| E6 | ADR-007 exposes the term via `crm_get_facility_plan`. | openmeter_mediator ADR-007 |

## The session

📋 **John:** The owner was clear: tokens are a Flex thing. A clinic on a Fixed fee doesn't get free tokens, full stop. And E3 says right now an admin can hand them out anyway.

💻 **Amelia:** The order path already does the right thing. It's the button and its API that don't. One function, `has_flex_purchase`, called at dispense time and shown on the card.

😤 **Grumbal:** "Purchased" meaning paid? Because auto-assign fires when the order is *created*. If you say paid, you just broke P-76, which the owner signed off.

🏗️ **Winston:** So "purchased" means a Flex order that isn't cancelled. That's the same moment auto-assign uses. We write the stricter options down, with the one line to change, so the owner can tighten it without another design round.

📊 **Mary:** Coupons. One field: **Applies to**, Flex, Fixed or Both. Flex keeps today's token value; Fixed gets a percentage off. Old coupons are all token coupons, so they migrate to Flex.

🌶️ **Boundary:** Where does the discount live? If it's another zero-rated line, the metering app will try to grant it.

💻 **Amelia:** It's ERPNext's own `discount_percentage` on the Fixed package line, stamped with `crm_coupon`. No bonus type, so the metering app ignores it. It travels to the invoice by itself.

🌶️ **Boundary:** And "Flex coupon only on Flex invoices": checked where?

🏗️ **Winston:** Three places. Resolution only offers a coupon that fits the order's plan. Confirmation refuses a mismatch with a sentence a human can read. And the metering app refuses a token line whose coupon isn't Flex or Both, in case someone edits a line by hand.

😤 **Grumbal:** A coupon is revoked after the clinic confirmed a discounted Fixed order. Do you claw the 5% back?

📋 **John:** No. They agreed a price. Drafts lose the discount at the nightly reconcile, same as token lines. Confirmed orders keep it.

📊 **Mary:** And one coupon per facility, whichever plan, like today. If the owner wants a Both coupon to pay out twice, that's a decision, not a default.

🎨 **Sally:** The dialog: three radios, labelled with what each gives. Only the fields for the chosen plan show. Native radios take the brand red, never the forms blue. That's the brand rule we broke on the opt-in last week. The card says "500 tokens on Flex · 5% off Fixed".

🎨 **Sally:** Customer side: in the Fixed view, a **Subscription** card between Plan and Next invoice. "Active until 9 Dec 2026", note "Active since 9 Nov 2026 · Value Express Fixed - Level 2". Same card style as its siblings. And the order review shows the discount before they confirm.

## Decisions

P-107 to P-115: [adr-coupon-plan-scope.md](../planning-artifacts/adr-coupon-plan-scope.md). This closes openmeter_mediator `subscription-open-decisions.md` D-6, and D-4 option A.

## Verification

- CRM unit tests: 89 coupon, bonus and portal tests (21 new in `test_coupon_plan_scope.py`). Mediator: 166 (3 new). Frontend: 326 (7 new).
- Dev CRM, real orders built the way self-onboarding builds them: the Fixed order is 15,000 → 14,250 (5% off, no token lines); the Flex order gets 400 welcome + 500 coupon tokens and no discount. Paying the Fixed invoice activates the subscription and marks the discount redemption Granted.
- Playwright `e2e/metering/coupon_plan_scope.spec.ts` passes end to end: coupon card and dialog (brand-red radio asserted), both order reviews, payment, the customer's Subscription card, and bonus gating on the Deal card.
