# Implementation stories — network-optin-polish

Status: all done on `fix/network-page-and-optin-polish`.

## S1 — Finance Workbook label (CAP-1) ✅
Files: `frontend/src/components/Layouts/AppSidebar.vue`, `frontend/src/pages/Deal/QuotingTab.vue`, `frontend/src/pages/FinanceCockpit/index.vue`, `frontend/finance-cockpit.html`, `crm/fcrm/page/finance_cockpit/finance_cockpit.json` (title + modified bump → synced on migrate), `crm/finance/access.py`.
Verify: `bench migrate` → Page title "Finance Workbook".

## S2 — Partner Coupon full link, Opt-In row removed (CAP-2) ✅
Files: `frontend/src/pages/Networks/NetworkDetail.vue`, `frontend/src/utils/coupons.js` (`partnerCouponLink`), `frontend/tests/unit/coupons.test.js`, `e2e/journey-separation/journeys.spec.ts`.
Note: header "Open Opt-In" preview link kept (admin preview, not a shareable row) — maintainer to confirm.

## S3 — Network detail on short laptop viewports (CAP-3) ✅
Files: `NetworkDetail.vue` (block scroll container, 5-column table: Facility+KEPH · Status (opt-in + go-live) · Contact · Access (invitation + Tiberbu Express) · Actions wrapping in 13rem; sentence-case labels; h1 weight 600).
Tests: `e2e/journey-separation/journeys.spec.ts` — two viewport tests (1280×631, 1366×657).

## S4 — Opt-in quotation step layout (CAP-4) ✅
Files: `frontend/src/pages/OptIn/StepPricing.vue`, `StepReview.vue`, `frontend/src/utils/optionalServices.js` (+ unit tests).
Tests: `frontend/e2e/regression/optin-layout.spec.ts` (added to `playwright.portal-ui.config.ts`).

## S5 — Access email after facility signatory + witness (CAP-5) ✅
Cherry-picked PR #162 commits (S1–S5 of `optin-post-signature-link`), then:
- `crm/api/contracts.py`: `_facility_side_signed(contract)`; `_transition` calls `_send_facility_access_invitation` only when it is true.
- `crm/api/website_redirect.py`: trigger `facility_side_signed`; button colour via `valid_brand_colour(network.primary_colour)`.
- Patch `crm.patches.v1_0.add_cx_portal_awaiting_signature_status` (Select option) — needs `bench migrate`.
Tests: `crm/tests/test_optin.py`, `crm/tests/test_website_redirect.py`, `crm/tests/test_cx_portal_status_patch.py`.

## Verification log (2026-11-12)
- `yarn test:run`: 39 files, 374 tests passed.
- Portal UI Playwright suite (4 viewports): 174 passed, 0 failed (126 skips = brand-asset checks that run on laptop only).
- Journey e2e on the dev site: 7/7 tests passed; afterAll leftover assertion fails on records from 2026-11-03 runs (this run's data fully removed).
- Python scratch run (rollback-only, crm-dev): test_website_redirect + test_cx_portal_status_patch + test_optin + test_finance_access → 184 run, 4 failures, all 4 identical on plain develop (pre-existing).
- Live rolled-back check on the dev DB: no email at processing or after the facility signatory alone; one branded email (brand red button, set-password link) after the witness signs; none after later signatures.
