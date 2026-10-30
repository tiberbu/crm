# CX Portal: low-token email alerts and UI conformance review

**Status:** Implemented, 2026-10-30. Branch `feat/token-alerts-and-portal-ui-review`, PR against `develop`.
**Sources:** system-review recommendations from another team; [CX Portal UX Design Pattern](cx-portal-ux-design-pattern.md); [HMIS token / OpenMeter alignment](hmis-token-openmeter-alignment.md).

Two asks:

1. A facility owner sets a token threshold per facility, switches the alert on or off, and gets an email when the facility's live balance reaches the threshold.
2. A full review of the CX Portal views for layout, text alignment, responsiveness and design-pattern conformance. The reported example: on the dashboard's "Your facilities" cards, long facility names run behind the status pill ("Implementation in progress").

## Review method

- **Harness:** the built CX Portal bundle served locally, with Frappe's JSON API mocked by stress data: three facilities with long names, both go-live states, a live low balance, a live high balance, no balance, no FID, an overdue invoice, a pending M-Pesa report and a draft order (`frontend/e2e/regression/portalFixture.ts`).
- **Viewports:** phone 390×844, tablet 768×1024, laptop 1280×800, desktop 1536×900.
- **Automated audit** (`frontend/e2e/regression/portal-layout.spec.ts`): no horizontal page scroll; no text box drawn over another element's text (clipped to overflow containers, so ellipsis truncation is not reported); no control clipped or pushed off-screen. It runs on Dashboard, Facilities, Plans & Pricing, Billing, Profile and the Facility page.
- **Visual review:** full-page screenshots for each view and viewport, reviewed against the design pattern by UX, architecture, development and product (BMAD party mode).

Baseline result: 6 of 24 view/viewport checks failed, plus the content defects below that the audit cannot see.

## Findings and fixes

| ID | Screen | Finding | Fix |
|---|---|---|---|
| UI-1 | Dashboard › Your facilities | Name button is `block truncate` but a button shrinks to its content, so it never truncates. The name/ID column collapses to about 90px and the status pill sits over the name (laptop, desktop). At 768px the name runs past the card. At 390px the cards are wider than the screen and the action buttons are cut off. | Name on its own row (`w-full`, two-line clamp, `title` tooltip); status pill moves to the meta row; grid uses `auto-fill, minmax(18rem, 1fr)` so the column count follows the space left by the sidebar. |
| UI-2 | Facilities › cards | Same header pattern as UI-1: the pill squeezes the name into one word per line. | Same header layout as UI-1. |
| UI-3 | Facilities › table | At 1280px the seven-column table has no minimum widths: names wrap one word per line and "Pay M-Pesa" sits over the token count. | Table gets a minimum width inside a horizontal scroll container; settlement actions stack right-aligned and do not wrap; the list defaults to cards below 1024px. |
| UI-4 | Billing › invoices | At 768px each invoice row is one line: the facility chip and "Choose payment method" are pushed off the card. | Row wraps: details on the first line, amount and action on the second below `lg`. |
| UI-5 | Billing › payment activity | The table clips its Status column with no scroll. | Horizontal scroll container. |
| UI-6 | Billing › M-Pesa Paybill | "Business No: Not available" still shows a Copy button. | Copy appears only when a number is configured. |
| UI-7 | Profile › connected facilities | The KEPH badge squeezes beside the name into a vertical word stack. | Badge moves under the name. |
| UI-8 | Facility page › go-live token allocation | A long package name overlaps the price in the selected-package box. | `min-w-0` and wrapping on the package name. |
| UX-1 | Dashboard cards, Facilities table/cards, Profile strip | "Token Runway: 0 tokens" is shown when there is no live balance, which reads as "out of tokens". The pattern allows a token count only for a live `status: ok` balance. | Show the live number, or "Not metered yet"; label it "Available tokens". |
| UX-2 | Dashboard KPI | "Registry status · Clinics Live · completed the registry checks" presents `go_live` as HFR verification. | Relabelled "Go-live readiness · ready for go-live". |
| UX-3 | Profile › KYC | "This verified identity is authorized…" appears in success styling even when the National ID is "Not on file". | Shown only when an ID is on file, and worded "on file" rather than "verified". |

Found during implementation: the Profile's connected-facility cards called an undefined `openFacilityDetail` and threw on click; they now open the facility page. Missing FIDs there read "Facility ID not linked yet" instead of being hidden.

## Self-onboarding feedback (`/facility-onboarding`)

A second round of feedback on the Facility, Package and Review steps, checked against the current `develop` build.

| ID | Step | Feedback | Outcome |
|---|---|---|---|
| OB-1 | Facility | "Level not on record" has no helper text. | A selectable facility without a level now says the team confirms the level before go-live. A facility blocked for a missing level explains that Value Express is priced by level and links to contact the team, not the Advanced & Enterprise enquiry. |
| OB-2 | Package | No way back to the Facility step; the stepper is not clickable. | **Back** button in the summary bar. Completed Facility and Package steps in the stepper are buttons that reopen the step; selections are kept. Identity is not reopened, so the verified session is not lost. |
| OB-3 | Package | "Suits —" on every card. | Root cause: the onboarding catalog API sent `coverage_metrics` but never the `audience` the landing page reads. `get_catalog` now returns `audience`; the row is hidden on both pages when a package has none. |
| OB-4 | Package | Custom KES 7,000 shows "You pay KES 6,996.00". | The charge is correct: Custom buys whole tokens and is invoiced per token. The card now says why: "1,166 whole tokens at KES 6.00 each. That is KES 4.00 less than the KES 7,000 you entered…". |
| OB-5 | Package | Fixed appears in onboarding but not on the landing page. | Not changed. The current landing page renders Value Express Fixed (two tiers) from the same catalog source as onboarding. Needs confirmation of which build was reviewed. |
| OB-6 | Package | Fixed shows nothing on what's included. | The inclusions list now has a "What's included" heading so it reads as the plan's contents. |
| OB-7 | Package | Partner Coupon popup covers the facility tabs; "Done" and "Close" both shown. | The panel opens in the page flow, above the tabs, with one button ("Done" once a coupon is typed, otherwise "Close"). Escape still closes it. |
| OB-8 | Package | Badge "POPULAR" here, "RECOMMENDED" on the landing page. | Already fixed by PR #132: both now say "Popular" from the same `badge` metric. Verified on the dev landing page. |
| OB-9 | Package | Heading in Title Case with a hyphen. | "Value Express Flex: pay as you use". |
| OB-10 | Review | Terms show "KES To be confirmed" while the review shows KES 34,800. | The Terms are requested with the chosen facilities and packages. The server prices them and fills the Terms' pricing table and totals, so the selected-term totals equal the review total. Flex-only orders say there is no monthly subscription. The Terms hash is bound to that selection: submitting different choices asks the customer to review the Terms again. |
| OB-11 | Review | Three names for the Terms. | The section title, link and dialog all use the configured document's own title. The heading inside the document ("… CareverseHIMS Subscription Agreement") is site content in the Terms and Conditions record and should be renamed there to match. |

**Deferred (logged, not in this change):** portal eyebrow labels use uppercase tracking, whereas the centralized theme spec asks for sentence case on the public www pages. The portal's own pattern does not forbid it, and changing about 80 labels is a restyle rather than a fix.

## Low-token email alerts

### Behaviour

- On the Facility page, beside "Available tokens", the owner sees a **Low-token email alert** card: an on/off switch, a threshold in tokens, and the facility's current live balance.
- **Save** stores the setting and checks the live balance straight away. If the balance is already at or below the threshold, the email goes now and the card says so.
- After that, a scheduled check runs every 15 minutes. It emails **once** when the balance reaches the threshold, and re-arms when a top-up lifts the balance above it. Changing the threshold or turning the alert back on also re-arms it.
- A facility with no HFR Facility ID cannot be metered, so its switch is disabled with an explanation.
- When metering does not report a live balance (metering off, service unavailable, facility not yet metered), nothing is sent: an outage is never reported to the owner as "0 tokens".
- Dashboard facility cards show a bell with the threshold when an alert is on.

The email goes to the signed-in owner's address (their portal login). It names the facility, Facility ID and MFL code, the live balance and the threshold, and links to the portal to top up.

### Data: `CRM Facility Token Alert`

| Field | Type | Notes |
|---|---|---|
| `user` | Link User | Owner who receives the email |
| `mfl_code` | Data | Facility MFL code |
| `hfr_facility_id` | Data | FID used for the balance lookup, refreshed on every save |
| `facility_name` | Data | For the email and the desk list |
| `enabled` | Check | |
| `threshold` | Int | Tokens, 1 to 100,000,000 |
| `below_threshold` | Check | Set once the alert email has been sent; cleared when the balance rises above the threshold |
| `last_balance` | Float | Last live balance seen |
| `last_checked_at` / `alert_sent_at` | Datetime | |

One record per user and facility (validated). Desk access: System Manager. Portal access is only through the whitelisted API, which checks that the facility belongs to the signed-in user.

### API (`crm/api/token_alerts.py`)

- `get_token_alerts()` → `{alerts: {<mfl_code>: alert}}` for the signed-in user.
- `save_token_alert(mfl_code, enabled, threshold)` → the saved alert plus `{balance_status, balance, alert_sent}` from the immediate check. Rejects facilities not in the user's portal and facilities with no FID.
- Scheduler: `crm.api.token_alerts.check_token_alerts`, cron `*/15 * * * *`. It reads all enabled alerts and fetches every FID's balance in one `crm_get_facility_token_balances` call.

### Migration and configuration

- New DocType, created by `bench migrate`. No patch or backfill.
- Needs outgoing email (an Email Account with "Enable Outgoing") and the metering app's `crm_get_facility_token_balances` hook. Without the hook, alerts can be saved but never fire.

## Verification

- `frontend`: `npx playwright test -c playwright.portal-ui.config.ts` runs on four viewports, against the built bundle with the API mocked:
  - the layout audit on six portal views;
  - the token-alert journey;
  - the onboarding Facility, Package and Review steps.
- `frontend`: `yarn test:run`, unit tests.
- Backend: `crm/tests/test_token_alerts.py` covers ownership, validation, crossing and re-arming, an unavailable meter, and re-arming after a threshold change. `crm/tests/test_facility_onboarding.py` covers the priced Terms and rejects a submission whose choices differ from the reviewed Terms.
