# Opt-in journey: brand guide restored

**Date:** 2026-11-09 · **Scope:** the network opt-in journey, from the
"You've been pre-qualified: …" email through the `/opt-in` wizard (and the payment
checkout fallback colour).

## What was wrong

Commit `9e1966bb` (2026-10-20, CX Portal facility detail / HFR work) put the CX Portal
"glass" material on the opt-in wizard through `.cx-enrollment` and `.cx-enrollment-glass`:

- a slate `#f4f6f8` page with a **teal** (`rgba(16,185,129)`) and a pink radial gradient
- a translucent, blurred card instead of the white card
- a white band at the top of the page (card margin collapsing through the wrapper)

The same journey also had three different reds: `#C0101A` (wizard fallback),
`#b91c1c` (both invite emails, the deal invitation email, the OTP email default and the
checkout fallback) and `#bc1823` (the brand guide). Headings used `font-bold`,
`font-extrabold` and `font-black`, but the typography spec caps weight at 600.

## What changed

| Area | Change |
|---|---|
| `OptInWizard.vue` | CX glass classes removed, so the page is plain `bg-gray-50` with a white card again. `flow-root` stops the top band. Fallback colour is `#bc1823`, and a partner `primary_colour` is used only when it is a strict hex literal |
| `index.css` | `.cx-enrollment*` rules deleted (only the wizard used them) |
| `OptIn/*.vue` | Weights above 600 changed to `font-semibold`. Terms CSS changed from 700 to 600 |
| Emails | Pre-qualified invite, demo invite and deal opt-in invite buttons now use `#bc1823` (the deal invite uses the network colour, validated) |
| `crm/api/_email.py` | Single source for the brand colour. `valid_brand_colour` accepts only `#rgb`/`#rrggbb`, and the fallback RGB matches `#bc1823`. `crm/api/optin.py` imports these instead of keeping its own copies |
| `PaymentCheckout.vue` | Fallback colour is `#bc1823` |

Kept: the native, keyboard-accessible facility checkbox from `9e1966bb` (UX PRD
requires keyboard and touch selection). Semantic status colours (error/amber/green)
are unchanged.

Follow-up (not in this change): Pricing and Review use uppercase `tracking-wider`
eyebrows. The typography spec prefers sentence case.

## Verification

- `frontend/e2e/regression/optin-brand.spec.ts` (new, mocked API) walks landing →
  contact → OTP → facilities → pricing → review → terms → commit → progress at phone,
  tablet, laptop and desktop widths. It asserts no gradients, glass or off-brand
  tints, InterVar only, weights ≤ 600 and sizes ≥ 11px. It also asserts the brand red
  on the CTA, the fallback for a non-hex partner colour, and that a valid partner hex
  is still honoured.
- Full UI suite: `npx playwright test -c playwright.portal-ui.config.ts` gives **84 passed**
  (opt-in brand, CX Portal layout and typography, onboarding layout, token alerts).
- Unit tests: `yarn test:run` gives **307 passed**.
- Python: `valid_brand_colour` was checked on the dev site with `#bc1823`, `#abc`,
  `#1a73e8` (kept) and an injection string, `url(x)` and empty (all fell back to
  `#bc1823`). `_invite_html` renders `background:#bc1823`.
