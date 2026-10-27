# CareverseHIMS Value Express — landing and onboarding redesign

**Date:** 2026-10-27
**Status:** Approved for build (prototypes signed off after four review rounds)
**Panel:** Business Analyst (Mary), PM (John), UX (Sally), Architect (Winston), Dev (Amelia), QA (Quinn)
**Sources:** business enhancement brief (landing Sections 1–7, onboarding Steps 1–3, new logo),
the Value Express product datasheet, reviewer feedback rounds 3 and 4.
**Approved prototypes:** two private review pages shared with the business (landing v7,
onboarding v5). They are the visual and behavioural reference for this build.

## 1. Outcome

A Level 2 or Level 3 outpatient facility owner lands on `/`, understands Value Express,
picks how to pay (Fixed, Flex package or a Custom amount), and finishes self-onboarding at
`/facility-onboarding` with that choice already selected for each facility.

## 2. Previous version

The v1 UI is preserved as the annotated tag `ui/value-express/v1-legacy`. See
`docs/ui-versions/README.md` for the files it covers and how to restore it.

## 3. Product rules (settled in review)

| Ref | Rule |
|---|---|
| R1 | Flex packages are Starter, Growth, Scale and Custom. |
| R2/O3 | Package cards show tokens, approx. patient journeys (tokens ÷ 40, business figure), price per token and, in onboarding, tokens left for services in month 1 (tokens + bonus − 500). |
| R3 | The calculator recommends the cheaper plan and warns when Flex is within 15% of the Fixed fee. |
| R6/O4 | Fixed: KES 15,000/month (Level 2), KES 18,000/month (Level 3), excl. VAT. |
| O5 | The Fixed tier matching the facility's level is preselected and the other is disabled; with no level on record both are selectable and the team confirms the level before invoicing. |
| O6 | The +400 first-purchase bonus applies to Flex Starter, Growth and Scale only (not Custom, not Fixed). |
| R7 | Custom: any amount from the price of 1,000 tokens. It is priced at the published per-token rate of the highest Flex package the amount reaches (Starter KES 6.00, Growth KES 5.36, Scale KES 4.80). Tokens are rounded down; the invoice is tokens × rate, never more than the amount entered. |
| R8/R14 | Contact phones, email and hours come from CRM Opt-In Settings › Landing Page. The contact form also emails Contact Email. Empty rows are hidden. |
| R5 | "DHA HIE Compliant" links to the DHA certificate in the same settings section when set. |
| R10 | Logo: the tibERbu wordmark from the training site, with "CareverseHIMS / Value Express". |
| R12 | Token benefits are said once (Flex grid, six tiles). |
| R13 | Hero uses the drawn product illustration until marketing supplies a screenshot. |
| R15 | Every primary button reads "Get started" and opens onboarding; on a plan, package or calculator result it carries that choice. |
| O8 | "Value Express terms" opens the self-onboarding Terms already used by the flow; "token rules" links to the landing page rules. |
| O9 | A carried choice is preselected for every selected facility and marked "Recommended for you"; Fixed always uses each facility's own level. |

## 4. Architecture

- **Landing** stays a server-rendered Jinja page (`crm/www/index.html`). No bundle; its own
  inline script for the calculator, Custom quote, section nav and contact form. Data comes
  from `index.py`: landing settings, Flex packages, Fixed packages, the Custom offer and the
  calculator configuration (service points, presets) — the same server sources onboarding uses.
- **Onboarding** stays the Vue page `FacilityOnboardingLanding.vue`. The existing state
  machine, API calls, conflict handling, Partner Coupon, terms snapshot and success page are
  kept; the template and styles are replaced to match the prototype. Pricing rules live in a
  pure module, `frontend/src/utils/valueExpress.js`, with unit tests.
- **Shared look**: `crm/public/css/value-express.css` holds the design tokens (light and dark),
  and the self-hosted fonts (Bricolage Grotesque, Source Sans 3, JetBrains Mono; OFL) live in
  `crm/public/fonts/value-express/`. No external font or script requests.
- **Catalogue**: one table, CRM Token Package, gains `plan` (Flex / Fixed / Custom) and
  `facility_levels`. Fixed and Custom are offered only when an enabled row of that plan exists,
  so a site without them keeps the v1 offer.
- **Custom invoicing** reuses token grants unchanged: the Custom row has `token_quantity = 1`,
  and the quote/order line is `qty = tokens`, `rate = per-token rate`. OpenMeter grants
  `token_quantity × qty`, so the paid invoice grants exactly the tokens bought.
- **Fixed invoicing** uses the Fixed row's item and price; it carries no tokens.

### API contract changes (additive)

`get_catalog` keeps `packages` (now Flex only, so older clients see what they saw before) and adds:

```json
{
  "fixed_packages": [{"item_code": "...", "display_name": "...", "facility_levels": ["Level 2"], "price_ex_vat": 15000, "...": "..."}],
  "custom_offer": {"item_code": "...", "min_tokens": 1000, "min_amount": 6000,
                   "tiers": [{"name": "Starter", "from_amount": 6000, "rate": 6.0}, "..."]}
}
```

`submit_onboarding.facility_package_items` values may be an item code (as before) or
`{"custom_amount": 7000}`. The server recomputes Custom tokens and checks a Fixed choice
against the facility's level; the browser's numbers are never trusted.

## 5. Out of scope here, needed before Fixed goes live in production

1. **Metering exemption for Fixed facilities.** HMIS sites are metered on token balance; a
   Fixed facility has no tokens and would be limited at zero. The metering gateway / OpenMeter
   mediator must treat an active Fixed subscription as unmetered.
2. **Monthly renewal and missed payments.** The first month is invoiced through onboarding.
   Renewals (the existing Recurring order frequency is the likely route) and the rule for an
   unpaid month need a business decision and their own story.

Until both are done, keep Fixed rows disabled on production. The UI hides Fixed when no
Fixed row is enabled.

## 6. Quality gate (Quinn)

- Python: unit tests for the pricing rules and the catalogue/submit changes.
- Frontend: `yarn test:run` green, with new tests for `valueExpress.js`.
- Playwright (`e2e/value-express/`): landing sections and nav, calculator presets and the
  carried choice, Custom quote, contact rows from settings, no horizontal scroll at 360px;
  onboarding stepper alignment, not-eligible lock, Fixed level preselection, Custom card,
  next-facility prompt, Change links, confirm hint. Desktop and mobile.
- Screenshots of both pages reviewed against the approved prototypes.
