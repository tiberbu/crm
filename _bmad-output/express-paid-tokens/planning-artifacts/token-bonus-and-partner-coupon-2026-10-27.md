# First-purchase bonus and Partner Coupon (no more Free Trial)

Status: Implemented (awaiting maintainer review) · 2026-10-27 · builds on express-draft-order-to-paid-tokens-2026-10-27.md
Party review: Mary (analyst), John (PM), Winston (architect), Amelia (dev), Sally (UX), Murat (test architect)

## Brief

- The Free Trial package goes away. Starter is preselected in the Express package step so Continue is active.
- Paying for any package grants the bought tokens **plus**, the first time, complimentary tokens.
  Example: Starter (1,000) paid → 1,400 tokens; the invoice shows only the 1,000 were paid for.
- Entering a Partner ID at onboarding earns extra complimentary tokens: the **Partner Coupon**.
  Copy changes from "Were you referred by a Network?" to "Enter Partner Coupon"; the popover must close (✕, Esc, outside click).
- Both quantities are controlled in CRM settings.
- Selection controls in the journey (checkboxes, select) must be clearly visible.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Two CRM Opt-In Settings: **First-purchase bonus tokens** (default 400, seeded from the retired Free Trial quantity) and **Partner Coupon tokens** (default 0). | 1,000 + 400 = the brief's 1,400. No commercial number is invented for the coupon: the maintainer sets it. |
| D2 | Complimentary tokens are **zero-rated lines** on the token Sales Order and invoice (item `CV-TOKEN-BONUS`), marked `crm_bonus_type` (Welcome Bonus / Partner Coupon) and `crm_bonus_tokens`. | The invoice shows what was paid for and what was free; eTIMS gets a zero-value line; finance can report promotional tokens apart from revenue. |
| D3 | "First time" is **per facility**: the welcome bonus goes on a facility's first confirmed token order; the coupon on the first confirmed order after onboarding with a coupon. | Tokens are metered per facility (FID). |
| D4 | Eligibility is decided when an order is raised **and again when a draft is confirmed**. | Two open drafts cannot both carry the bonus to an invoice. |
| D5 | openmeter_mediator grants each bonus type separately, keyed `welcome:<FID>` / `coupon:<FID>`, with grant sources "Welcome Bonus" / "Partner Coupon". | Once-per-facility enforced at the meter too; balances and reports can split paid and complimentary tokens. |
| D6 | Only a Partner Coupon **typed by the client** earns tokens, recorded as `partner_coupon` on the facility's CRM Facility Membership. The default Network (blank coupon) earns nothing. | Partner attribution and fairness; the default Network is a fallback, not a referral. |
| D7 | One global Partner Coupon amount. Per-partner amounts are a follow-up. | Keeps configuration in one place until commercial asks for more. |
| D8 | Free Trial package row is disabled by the patch (not deleted). | Reversible; historical orders keep their item. |

## Tracking (answer to "do we need to track these differently?")

Yes, and this change does it:

1. **Invoice lines**: complimentary tokens are separate zero-rated lines with a type and a token count, so the
   invoice and accounting distinguish paid from free tokens.
2. **Metering grants**: each type is its own OpenMeter grant with its own source and key, so the ledger shows how
   many tokens each facility got for free, and the same bonus can never be granted twice.
3. **Partner attribution**: the membership flag records which facilities joined with a Partner Coupon.

Not done here (follow-ups): a report of complimentary tokens by type/partner/month, and an accounting treatment
(promotional liability account) if finance wants one beyond the zero-value line.

## Changes

| Area | File |
|---|---|
| Patch: settings, line fields, membership flag, bonus item, retire Free Trial | `crm/patches/v1_0/add_token_bonus_and_partner_coupon.py` |
| Eligibility and bonus lines | `crm/utils/token_bonus.py` |
| Orders (raise, confirm, review payload) and portal add-facility coupon | `crm/api/customer_experience.py` |
| Coupon recorded at Express submit; catalog returns bonus amounts | `crm/api/facility_onboarding.py` |
| Settings API | `crm/api/optin_admin.py` |
| Settings UI | `frontend/src/components/Settings/OptInSettings.vue` |
| Wizard: coupon popover, copy, Starter preselect, bonus on cards, visible controls | `frontend/src/pages/FacilityOnboarding/FacilityOnboardingLanding.vue` |
| Portal review dialog breakdown | `frontend/src/pages/FacilityPortal/FacilityPortal.vue` |
| Separate bonus grants | `openmeter_mediator/services/grants.py`, OpenMeter Grant sources |

## Verification

- `crm.tests.test_express_draft_order.TestTokenBonuses`: zero-rated welcome line, coupon + welcome on a coupon facility
  and on its invoice, bonus only on the first confirmed order (draft re-checked at confirm), nothing when set to 0.
- `openmeter_mediator` `test_bonus_lines_are_separate_grants_once_per_facility`.
- Playwright: Express journey with a coupon facility pays Starter and ends at 1,000 + 400 + coupon tokens in the portal
  and gateway; wizard check for Starter preselected, coupon copy, Esc/✕ closing the popover, visible checkboxes.
