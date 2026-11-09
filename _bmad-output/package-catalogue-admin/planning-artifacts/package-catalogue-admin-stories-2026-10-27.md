# Package Catalogue admin — stories

Spec: `package-catalogue-admin-spec-2026-10-27.md`. Rules: `_bmad-output/STORY-RULES.md`.
One branch, `feat/package-catalogue-admin`, one PR into `develop`.

## Dependency graph

```
PC-1 schema+patch ──► PC-2 rules ──► PC-3 API ──► PC-5 admin page ──► PC-7 e2e
                          │             └──► PC-4 opt-in save guard ─────┘
                          └──► PC-6 periods + grids (landing, onboarding) ┘
```

---

## PC-1 — Package status fields and backfill (S) ✅

- **Primary file:** `crm/fcrm/doctype/crm_token_package/crm_token_package.json`
- **Also:** `crm/patches/v1_0/backfill_token_package_status.py` (create), `crm/patches.txt`
- **Change:** add `status` (Select `Active\nDisabled\nDiscontinued`, default Active, in list
  view), `discontinued_on` (Date, read only); `billing_period` gains `Semi-annual`.
  Patch sets `status` from `enabled`.
- **Depends on:** None. **Blocks:** PC-2, PC-3.
- **AC:** after `bench migrate`, every row has a status and `enabled == (status == "Active")`.

## PC-2 — Catalogue rules (M) ✅

- **Primary file:** `crm/utils/value_express.py`
- **Also:** `crm/tests/test_value_express.py`, `frontend/src/utils/valueExpress.js`,
  `frontend/tests/unit/valueExpress.test.js`
- **Change:** `PERIOD_MONTHS`, `period_months`, `period_label`, `monthly_equivalent`,
  `grid_columns(n, max)`, `validate_catalogue(rows)` (D9); JS `gridColumns`, `periodLabel`.
- **Depends on:** PC-1. **Blocks:** PC-3, PC-6.
- **AC:** unit tests cover each D9 rule, 1–9 cards for `grid_columns`, all four periods.

## PC-3 — Package catalogue API (L) ✅

- **Primary file:** `crm/api/package_catalogue.py` (create)
- **Also:** `crm/tests/test_package_catalogue.py` (create)
- **Change:** `get_package_catalogue`, `save_package` (create Item + Item Price for a new
  package, update price, sold lock D6, metrics D10), `set_package_status` (D5),
  `move_package`; version check (D2); audit comment (D12); `_period_key` handles Semi-annual.
- **Depends on:** PC-1, PC-2. **Blocks:** PC-5.
- **AC:** API tests: create/edit/disable/enable/discontinue/move; sold package refuses a token
  change; stale version refused; Sales User refused.

## PC-4 — Opt-In save leaves packages alone (S) ✅

- **Primary file:** `crm/api/optin_admin.py`
- **Also:** `frontend/src/components/Settings/OptInSettings.vue`
- **Change:** `update_optin_settings` touches `token_packages` only when sent; the Opt-In page
  drops the package table and links to Settings › Packages.
- **Depends on:** PC-3. **Blocks:** PC-7.
- **AC:** saving Opt-In settings without `token_packages` leaves the rows as they were.

## PC-5 — Packages settings page (L) ✅

- **Primary file:** `frontend/src/components/Settings/PackageCatalogue.vue` (create)
- **Also:** `frontend/src/components/Settings/PackageEditDialog.vue` (create),
  `frontend/src/components/Settings/Settings.vue`
- **Change:** page and dialog per spec §4; visible to managers (`isManager()`).
- **Depends on:** PC-3. **Blocks:** PC-7.
- **AC:** a Sales Manager can do every action in spec §1 without Desk.

## PC-6 — Periods and responsive grids on landing and onboarding (M) ✅

- **Primary file:** `crm/www/index.html`
- **Also:** `crm/api/landing.py`, `crm/public/css/value-express-landing.css`,
  `frontend/src/pages/FacilityOnboarding/FacilityOnboardingLanding.vue`,
  `frontend/src/pages/FacilityOnboarding/valueExpressOnboarding.css`
- **Change:** Fixed price "per <period>", calculator uses the monthly equivalent, `--cols`
  from `grid_columns` for Flex+Custom (max 4) and Fixed tiers (max 3); cards follow the
  admin's order (Most popular still marked).
- **Depends on:** PC-2. **Blocks:** PC-7.
- **AC:** 7 cards render 4+3 at 1440 px, 2 per row at 900 px, 1 at 360 px with no
  horizontal scroll; a Quarterly Fixed reads "per quarter".

## PC-7 — Playwright journey (M) ✅

- **Primary file:** `e2e/package-catalogue/catalogue.spec.ts` (create)
- **Also:** `e2e/package-catalogue/playwright.config.ts`, `e2e/package-catalogue/helpers.ts`
- **Depends on:** PC-4, PC-5, PC-6. **Blocks:** release.
- **AC:** spec §6 journey passes on desktop and mobile; the existing `e2e/value-express`
  suite still passes.

## Build notes

- `enabled` stays the field every catalogue reader uses; CRM Opt-In Settings keeps it equal
  to `status == Active`. Whichever of the two a save changed wins, so Desk edits and older
  code that tick Enabled still work.
- Move earlier/later passes the packages the user cannot see under the current filter, so a
  card always moves one place on screen (found by the Playwright journey).
- Fixed tiers on the landing page hold at most two a row (they sit inside the half-width plan
  card); onboarding allows three.
- The landing stylesheets now carry a content-hash `?v=`: the CDN caches `/assets` for a year,
  so CSS changes did not reach visitors without it.
- The calculator overflowed a 360 px screen by 20 px (grid `1fr` with a wide child); the
  mobile grid is now `minmax(0,1fr)`.
- The Opt-In Process page no longer embeds the package table; it links to Settings › Packages.
- Playwright users and cleanup: two synthetic users (Sales Manager, Sales User) whose
  passwords live outside the repo; `crm.demo.package_catalogue_e2e.remove_e2e_packages`
  removes the "E2E …" packages a run leaves behind.
