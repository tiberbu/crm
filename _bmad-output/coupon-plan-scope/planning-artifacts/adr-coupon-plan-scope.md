# ADR: Plan-scoped coupons (Flex tokens, Fixed discount), Flex-only bonus tokens, subscription on the customer side

- **Status:** Accepted (2026-11-09, party: `../implementation-artifacts/party-2026-11-09-coupon-plan-scope.md`)
- **Decisions:** P-107 to P-115
- **Closes:** openmeter_mediator `subscription-open-decisions.md` **D-6** (decided) and **D-4 option A** (decided; Renew button still open)
- **Builds on:** coupon management design (`_bmad-output/handoff/coupon-management/DESIGN-coupon-management.md`), welcome bonus P-76, ADR-007 (subscriptions)

## Owner brief (2026-11-09)

> Free tokens or bonus tokens should only be rewarded if a customer has purchased a flex token
> package. A Partner Network can create a coupon that slashes an amount off by a percentage (e.g. 5%).
> When creating a coupon, confirm whether it is for Fixed, Flex or both; for both, set the tokens
> for Flex and the discount for Fixed. Redemption validates that a Flex coupon is used only on Flex
> package invoices. A Fixed subscription's details should be available on the customer side too.

## Before

| Area | Behaviour |
|---|---|
| Coupon value | Tokens only: `flat_tokens` or `percentage_of_purchase` (of purchased tokens), optional cap |
| Which orders get a coupon | Only Flex orders get bonus lines (`token_bonus._earns_bonus`). There was no plan on the coupon itself, so nothing stated or enforced "Flex only" at claim or grant time |
| Fixed orders | No coupon benefit at all |
| Welcome bonus | Bonus lines on Flex orders only, and auto-assign only on Flex selection. **But** the Deal › Metering **Dispense** button granted it to any facility, including Fixed-only facilities with no purchase |
| Customer view of a Fixed subscription | The CX Portal showed the plan name and next invoice, but no activation or expiry |

## Decisions

**P-107: Bonus tokens need a Flex purchase.** Welcome-bonus and coupon tokens are only ever
given to a facility that has **bought a Flex token package**. Bought means a Flex package Sales
Order for that facility that is not cancelled (selected or confirmed). That is the moment
auto-assign already uses (P-76, owner-approved), and tokens are still released only by the
existing paths (dispense, or a fully paid invoice). The manual **Dispense** button and its API
refuse otherwise, with the reason shown on the card. Custom amounts and Fixed fees stay
excluded, as before.
*Stricter alternatives, if the owner wants them: "confirmed" (submitted orders only) or "paid"
(a fully paid Flex invoice). Each is a one-line change in `token_bonus.has_flex_purchase`; with
"paid", auto-assign on selection (P-76) would stop working.*

**P-108: Every coupon states the plans it applies to.** New field `applies_to`: **Flex**,
**Fixed** or **Both**. Existing coupons become **Flex** (their value is tokens).
- **Flex benefit:** complimentary tokens, using the existing `value_type`, `value` and `max_tokens`.
- **Fixed benefit:** `fixed_discount_percent` (greater than 0, at most 100) off the Fixed package price.
- **Both:** each plan gets its own benefit, and both are required.

`applies_to` and `fixed_discount_percent` become immutable once the coupon has a redemption (like the value fields).

**P-109: Resolution and claim are plan-scoped.** A Flex order considers only Flex and Both
coupons. A Fixed order considers only Fixed and Both coupons. At order confirmation
(`claim_on_submit`), a coupon that does not apply to the order's plan is refused with a clear
message. At grant time the metering app refuses a coupon token line whose coupon does not apply
to Flex. This is the "Flex coupon only on Flex invoices" check, enforced in three places.

**P-110: A Fixed discount is a price discount on the package line.** It is set as ERPNext
`discount_percentage` on the Fixed package line, stamped with `crm_coupon`, and copied to the
invoice. There is no zero-rated line, and no tokens. The redemption records `plan = Fixed`,
`discount_percent` and `discount_amount`, with `tokens_awarded = 0`. It is **Reserved** at
confirmation and **Granted** when the invoice is fully paid (the metering app's subscription
activation reports it; a daily reconcile backs it up).

**P-111: One coupon use per facility, whichever plan.** The existing guard stays (`facility_guard`
unique per MFL, plus the metering ledger for tokens). A facility that used a Both coupon's Fixed
discount does not later also get its Flex tokens. The owner can revisit this.

**P-112: A discount already confirmed is honoured.** If a coupon is revoked or expires after a
Fixed order is confirmed, the confirmed price stands (the customer agreed to it). Draft orders lose
the discount at the daily reconcile, as Flex coupon lines already do. Flex token lines keep the
existing rule: they lapse if the coupon was revoked or expired before payment.

**P-113: Partner networks see and offer both benefits.** Network coordinators create coupons
through the same dialog (their own network only). The onboarding offer and labels read like
"500 tokens on Flex · 5% off Fixed". The rule of one live coupon per network window is unchanged.

**P-114: The customer sees the subscription.** In the CX Portal, a Fixed (time-bound) facility
shows a **Subscription** card: status, **Active since**, and **Expires** (or Expired / Ended). It
reads `crm_get_facility_plan` through the same hook path as the live token balance. The Renew
button stays an open decision (D-4 option B, D-2).

**P-115: Order review shows the discount.** The CX Portal order review lists the discount on the
Fixed line (e.g. "5% coupon discount: −KES 500"), so the customer sees what they get before
confirming.

## Data and migration

- `CRM Coupon`: `applies_to` (Select Flex/Fixed/Both, default Flex), `fixed_discount_percent` (Percent).
- `CRM Coupon Redemption`: `plan` (Select Flex/Fixed), `discount_percent` (Percent), `discount_amount` (Currency).
- Patch `set_coupon_applies_to`: existing coupons → Flex; existing redemptions → plan Flex.
- No ERPNext field changes: `discount_percentage` and `crm_coupon` already exist on order and invoice lines.
