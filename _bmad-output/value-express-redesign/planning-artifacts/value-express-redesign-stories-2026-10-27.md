# Value Express redesign — stories

Spec: `value-express-redesign-spec-2026-10-27.md`. Rules: `_bmad-output/STORY-RULES.md`.
One branch, `feat/value-express-redesign`, one PR into `develop`.

## Dependency graph

```
VE-0 snapshot ──────────────────────────────────────────────┐
VE-1 schema ──► VE-2 pricing rules ──► VE-3 catalogue+submit ──► VE-7 onboarding UI ──► VE-9 e2e
                        │                    │                         ▲
                        │                    └──► VE-6 landing page ───┤
                        └──► VE-4 bonus rule      ▲                    │
VE-5 contact email ───────────────────────────────┘                    │
VE-8 fonts, logo, tokens CSS ──► VE-6, VE-7                            │
VE-10 demo catalogue seed (needs VE-1) ─────────────────────────────────┘
```

---

## VE-0 — Snapshot the v1 UI (S) ✅

- **Primary file:** `docs/ui-versions/README.md` (create)
- **Also:** annotated tag `ui/value-express/v1-legacy` on `0e5901b7`, pushed with the branch.
- **Depends on:** None. **Blocks:** nothing (must land before VE-6/VE-7 merge).
- **AC:** `git show ui/value-express/v1-legacy:crm/www/index.html` prints the v1 landing page.

## VE-1 — Plan and level fields on token packages (S)

- **Primary file:** `crm/fcrm/doctype/crm_token_package/crm_token_package.json`
- **Change:** add `plan` (Select `Flex\nFixed\nCustom`, default `Flex`, in list view) and
  `facility_levels` (Small Text, `depends_on: eval:doc.plan=='Fixed'`, one level per line,
  matched like `self_onboarding_allowed_facility_levels`).
- **Depends on:** None. **Blocks:** VE-2, VE-3, VE-10.
- **Steps:** `bench --site <site> migrate`.
- **AC:** `frappe.get_meta("CRM Token Package").get_field("plan").options == "Flex\nFixed\nCustom"`.

## VE-2 — Pricing rules module (M)

- **Primary file:** `crm/utils/value_express.py` (create)
- **Also:** `crm/tests/test_value_express_pricing.py` (create)
- **Interface:**
  ```python
  def flex_tiers(packages: list[dict]) -> list[dict]          # [{name, item_code, from_amount, rate}] by price
  def custom_quote(amount, packages: list[dict], min_tokens: int = 1000) -> dict
      # {ok, amount, tokens, rate, tier, charge, error}; rate = round(price/tokens, 2)
  def fixed_package_for_level(level, fixed_packages: list[dict]) -> dict | None
  ```
- **Depends on:** VE-1. **Blocks:** VE-3, VE-4.
- **AC:** `custom_quote(7000, flex) → tokens 1166, rate 6.0, charge 6996.0`;
  `custom_quote(20000, flex) → tier Growth, rate 5.36, tokens 3731`; below the minimum → `ok False`.

## VE-3 — Catalogue and submit accept Fixed and Custom (L)

- **Primary file:** `crm/api/facility_onboarding.py`
- **Also:** `crm/api/customer_experience.py` (order line qty/rate for Custom), `crm/api/landing.py`
  (`get_pricing_preview` → Flex only; new `get_value_express_offer()` for the landing page).
- **Change:**
  - `_token_packages()` returns `plan` and `facility_levels`.
  - `get_catalog` → `packages` (Flex), `fixed_packages`, `custom_offer`.
  - `_packages_for_facilities` accepts `{"custom_amount": n}`; Fixed must match the facility level
    (server-side `_facility_level_key`), otherwise `ValidationError`.
  - Quote and draft order lines use `qty`/`rate` from the resolved package when present.
- **Depends on:** VE-2. **Blocks:** VE-6, VE-7.
- **AC:** Python test: submit with `{"custom_amount": 7000}` produces a quote line `qty 1166, rate 6.0`;
  Fixed Level 2 package for a Level 3B facility raises `ValidationError`.

## VE-4 — No first-purchase bonus on Custom or Fixed (S)

- **Primary file:** `crm/utils/token_bonus.py`
- **Change:** `apply_bonus_lines` adds no lines when the order's package plan is Custom or Fixed.
- **Depends on:** VE-2. **Blocks:** None.
- **AC:** Python test: a Custom draft order gets no `crm_bonus_type` lines.

## VE-5 — Contact form emails the Value Express team (S)

- **Primary file:** `crm/api/landing.py`
- **Change:** after creating the Lead and note, `frappe.sendmail` to `landing_contact_email`
  (queued, reference = the Lead). No address in code; skipped when the setting is empty.
- **Depends on:** None. **Blocks:** VE-6.
- **AC:** Python test with the setting filled: one Email Queue row referencing the new Lead.

## VE-8 — Fonts, logo and design tokens (M)

- **Primary file:** `crm/public/css/value-express.css` (create)
- **Also:** `crm/public/fonts/value-express/*.woff2` (create), `crm/public/images/careverse-wordmark.svg` (create)
- **Change:** tokens from the prototype (`--bg … --sel`, light and dark), `@font-face` for the
  three families, the `.btn`, `.secno`, `.pin`-free component classes both pages share.
- **Depends on:** None. **Blocks:** VE-6, VE-7.
- **AC:** `curl -sI <site>/assets/crm/fonts/value-express/bricolage-grotesque-latin.woff2` → 200.

## VE-6 — Landing page (L)

- **Primary file:** `crm/www/index.html`
- **Also:** `crm/www/index.py`
- **Interface (context keys):** `landing`, `flex_packages`, `fixed_packages`, `custom_offer`,
  `calculator` (JSON: service points, presets, access tokens, bill value per token),
  `onboarding_url` (`/facility-onboarding`).
- **Sections:** 01 hero (illustration), 02 how it works, 03 benefits, 04 is it for me,
  05 plans + compare + choose, 06 Flex (why, getting tokens, usage + ledger, packages + Custom,
  zero-balance callout, 12 rules), 07 calculator (presets, fine-tune, verdict, carried CTA),
  08 support (settings rows + form), commercial notes, footer.
- **Depends on:** VE-3, VE-5, VE-8. **Blocks:** VE-9.
- **AC:** `curl -s <site>/ | grep -c 'class="secno"'` → 8; "Get started" links resolve to
  `/facility-onboarding` with `plan=` where a choice is carried.

## VE-7a — Onboarding pricing helpers (S)

- **Primary file:** `frontend/src/utils/valueExpress.js` (create)
- **Also:** `frontend/tests/unit/valueExpress.test.js` (create)
- **Interface:**
  ```js
  export function customQuote(amount, tiers, minTokens = 1000) // mirrors the server rule
  export function fixedForLevel(level, fixedPackages)          // package or null
  export function parseCarriedChoice(search)                   // {plan, package, amount} | null
  export function journeys(tokens)                              // Math.floor(tokens / 40)
  ```
- **Depends on:** VE-2 (same rule). **Blocks:** VE-7b.
- **AC:** `cd frontend && yarn test:run` passes, including the new file.

## VE-7b — Onboarding page (L)

- **Primary file:** `frontend/src/pages/FacilityOnboarding/FacilityOnboardingLanding.vue`
- **Change:** prototype layout: header lockup, stepper aligned with the card, Verify (one-line
  intro, resend countdown), Facility (lock for not eligible, level-unknown helper), Package
  (carried-choice note, Flex/Fixed picker with the facility's own Fixed price, calculator link
  above the cards, Starter/Growth/Scale/Custom cards, aligned buttons, next-facility prompt,
  sticky summary with hint), Review (Change links, Terms dialog and token-rules link, confirm
  hint, "Total to pay"), success page unchanged in substance. Partner Coupon kept.
- **Depends on:** VE-3, VE-7a, VE-8. **Blocks:** VE-9.
- **AC:** `cd frontend && yarn build` succeeds; VE-9 onboarding specs pass.

## VE-10 — Demo catalogue seed (S)

- **Primary file:** `crm/demo/seed_token_package_catalog.py`
- **Change:** add Fixed Level 2, Fixed Level 3 and Custom rows (items and prices), idempotent,
  dev sites only.
- **Depends on:** VE-1. **Blocks:** VE-9.
- **AC:** after running it, `get_catalog()` returns two `fixed_packages` and a `custom_offer`.

## VE-9 — Playwright review (M)

- **Primary file:** `e2e/value-express/landing.spec.ts` (create)
- **Also:** `e2e/value-express/onboarding.spec.ts`, `e2e/value-express/playwright.config.ts`
- **Depends on:** VE-6, VE-7b, VE-10. **Blocks:** release.
- **AC:** `npx playwright test --config e2e/value-express/playwright.config.ts` passes on
  desktop and mobile projects; existing `e2e/landing` and `e2e/onboarding-ux` suites reviewed
  and updated where the redesign changed what they assert.

## Follow-up epic (not in this PR): Fixed in production

- **VE-F1** Metering exemption for active Fixed subscriptions (openmeter mediator / gateway).
- **VE-F2** Monthly renewal invoices and the unpaid-month rule (needs a business decision).
