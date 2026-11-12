# SPEC — Network page and opt-in polish (Finance Workbook, coupon link, responsiveness, access email)

Branch `fix/network-page-and-optin-polish` → `develop`. Date 2026-11-12.

## Capabilities

| ID | Capability | Acceptance |
|---|---|---|
| CAP-1 | "Finance Cockpit" is shown as **Finance Workbook** | CRM sidebar, browser title, Desk page title, Quoting-tab link text, preferences copy and the access error read "Finance Workbook". Route `/finance-cockpit`, page name, code identifiers unchanged. |
| CAP-2 | Network detail shows only the Partner Coupon link, as a full URL | No `optin-invitation-link` row. `partner-coupon-url` text equals `<window.location.origin>/facility-onboarding?partner_coupon=<id>`; Copy copies the same string. |
| CAP-3 | Network detail is usable on short laptop viewports | At 1280×631 and 1366×657: contacts table not squeezed (scrollHeight ≤ clientHeight+1), no horizontal scroll, every row action reachable by page scroll; sentence-case labels, weights ≤ 600. |
| CAP-4 | Opt-in quotation step never spills text on desktop/laptop Chrome | With 5 years × 4 facilities × eight-figure KES amounts and long service names, no text box exceeds its card at phone/tablet/laptop/desktop and at 1280×631 / 1366×657. Optional service names/descriptions render as plain text (no `&amp;`, no tags); a description equal to the name is not repeated. |
| CAP-5 | Facility gets a branded Tiberbu Express access email once the facility side has signed | Contract journeys: Website User + OIS permission at processing, no email (`Awaiting signature`). Email sent once when Facility Signatory **and** every Facility Witness row are `Signed` (signatory alone when no witness row). Idempotent per OIS; best-effort (never rolls back a signature). Button colour = network `primary_colour` if strict hex, else `#bc1823`. |
| CAP-6 | Answer: optional services are configurable | Documented in PR body (see "Configuration"). |

## Constraints
- Brand guide binding (no new colours/weights; sentence case). No PII in artefacts.
- Partner Coupon / Opt-In journey separation unchanged (link only).
- Self-onboarding journeys and admin "Invite to Tiberbu Express" unchanged.

## Root causes
- CAP-3: page wrapper `flex flex-col h-full overflow-y-auto`; the `overflow-x-auto` table child has min-height 0 and was flex-shrunk to the leftover viewport height (inner scroll box). Plus 8 columns + 6 inline buttons wider than the ~960px content area at 1280.
- CAP-4: `OptInWizard` card is fixed at `max-w-2xl` (~640px content) while `StepPricing` used viewport breakpoints (`lg:grid-cols-5`, `lg:grid-cols-4`, `sm:grid-cols-2`), so desktop widths packed 5/4/2 columns into 640px.
- CAP-5: no code ever sent an access email at signature. PR #162 implemented it (first facility signature) but was closed unmerged on 2026-11-05; develop only sends Frappe's generic welcome at OIS processing (nothing when the email already has a Website User).

## Non-goals
- Renaming the `/finance-cockpit` route or Python/JS identifiers.
- Changing what the optional-services price list contains (configuration, not code).
- Retro-sending access emails to OIS rows already marked `Sent` under the old processing-time welcome.
