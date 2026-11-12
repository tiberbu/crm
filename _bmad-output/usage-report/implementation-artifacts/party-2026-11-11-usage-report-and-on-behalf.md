# Party roundtable — 2026-11-11: facility usage report (P-135) and on-behalf prominence (P-136)

**Input:** business review feedback, 2026-11-10.
**Room:** 📊 Mary (analyst), 📋 John (PM), 🏗️ Winston (architect), 🎨 Sally (UX), 💻 Amelia (dev), 🧪 Quinn (QA).
**Evidence checked before the room met:** OpenMeter `v1.0.0-beta.236` on the local quickstart and the
metering gateway source (`to_billing_cloudevent`).

## Ask 1 — usage report on the CX Portal facility page

> As a customer, on a Flex facility with ongoing token use, I pick a date range, see a usage report and
> download it, so I can reconcile tokens purchased, tokens consumed, the per-billing-event breakdown, the
> number of patients attended, and confirm that each billing event was charged at its set price.

📊 **Mary:** Five reconciliations in one sentence. Purchased vs consumed, breakdown, patients, price audit, download. The audit is the one they'll actually use when a number looks wrong, so it has to be per event, not a vibe.

🏗️ **Winston:** Good news first. Every billing event the gateway sends carries `billing_event`, `quantity`, `unit_tokens`, `catalog_version` and `tokens`. So the audit is real: charged = quantity × unit price, and the unit price can be checked against the published list. Bad news: OpenMeter's raw event listing refuses `from` older than about 30 days, and pages are capped at 100. The meter aggregates have no such limit, but the meter only sums tokens by `module` — no quantities.

💻 **Amelia:** Verified locally: `/api/v1/events?subject=&from=&to=&limit=100`, newest first, `to` exclusive. `/api/v2/events` ignores the time filter on this version, so v1 with a moving `to` is the paging path. Dedupe by id for same-second ties.

📋 **John:** Then we split it honestly. Totals and the breakdown in tokens come from the meter for any range. Event-level detail — counts, quantities, the price check — covers the last 30 days and the page *says so*. No silent estimates dressed up as facts.

📊 **Mary:** Hold on. "Patients attended" beyond 30 days is the thing finance asks for at month end. If we print nothing they'll export to Excel and divide tokens by price themselves, badly.

📋 **John:** Then we divide for them and call it an estimate, in words, on screen and in the file. And we file the follow-up: a quantity meter so counts never expire.

🎨 **Sally:** And "patients attended" is not a number we own. HMIS knows patients. We know *patient registrations charged*. Label it that way, with consultations beside it, so nobody reconciles against the wrong thing.

🧪 **Quinn:** Ledger-export events (`/events`, pre-priced, no `quantity`) also land on this meter. They can't be price-checked. They need their own status, not a fake "OK".

🏗️ **Winston:** Architecture: same seam as balances. CRM never imports the metering app; the mediator answers a new `crm_get_facility_usage_report` hook. CRM owns authorisation — the facility must be one the signed-in owner's portal shows, with an FID. Range limit 366 days. Detail capped at 5,000 events with a truncated flag.

💻 **Amelia:** Download is server-side CSV from the same payload, so the file and the screen can't disagree. Sections: summary, breakdown, daily, events.

🎨 **Sally:** Placement: a **Usage** tab on the facility page, only when the facility uses tokens. Presets first — Last 7 days, Last 30 days, This month, Last month — then a custom From/To. Four stat cards in one style (per the readable-type rule), the breakdown table, a daily table, then the event audit. Brand red only for the primary action. Mismatch rows use the warning colour because they *are* warnings.

🧪 **Quinn:** Tests: mediator unit tests with a fake client (paging, ties, truncation, 30-day clamp, audit statuses, grants in range); CRM tests for authorisation and CSV; vitest for presets and range validation; Playwright brand check on the new tab.

📊 **Mary:** Tokens purchased: grants with status Granted whose effective date falls in the range, split by source — paid package, welcome bonus, coupon — plus the all-time total. Bonus tokens aren't "purchased"; the split stops that argument.

### Decisions (P-135)

| # | Decision |
|---|---|
| D1 | New **Usage** tab on the CX Portal facility page for token plans (Flex/token, metered) with an FID. |
| D2 | Range presets + custom From/To; maximum 366 days; dates in the site's time zone. |
| D3 | Totals and token breakdown per billing event from the OpenMeter meter (any range). |
| D4 | Event-level detail (counts, quantities, price audit) for the part of the range within OpenMeter's 30-day listing window, capped at 5,000 events; the page states the covered dates. |
| D5 | Price audit per event: **Matches**, **Price differs from current list**, **Charge differs from quantity × price**, **Pre-priced (ledger export)**. |
| D6 | "Patient registrations" and "Consultations" counts; estimated (tokens ÷ current price) only where detail is not available, labelled *estimate*. |
| D7 | Tokens added in range by source (paid, bonus, coupon, other) and all-time; available balance now. |
| D8 | CSV download, generated server-side from the same report. |
| D9 | Mediator answers `crm_get_facility_usage_report`; CRM authorises via the owner's portal facilities. |
| F1 (follow-up) | A quantity meter (`SUM $.quantity` by `module`) so counts and the audit do not expire after 30 days. |

## Ask 2 — "on behalf of the owner" path on Express onboarding

🎨 **Sally:** Today, after the OTP, a user with no facilities gets one grey sentence: "We couldn't find eligible facilities…". The on-behalf path is a text link on the *previous* screen. Wrong screen, wrong weight.

📋 **John:** The ask is "every user who gets here can tell this is an important journey". So it's a decision, not a footnote: two clearly labelled choices — "I'm setting up for the facility owner" (primary) and "Check my ID again" (secondary) — plus assistance.

📊 **Mary:** Say *why* they see nothing: facilities are linked to the registered owner's ID. Staff and administrators are the common case here.

🧪 **Quinn:** And the identity screen link becomes a visible option card, not a link. Same `data-testid`s so the journeys keep working.

🎨 **Sally:** Express landing tokens only — no CX glass, no new colours. Brand red for the primary button.

### Decisions (P-136)

| # | Decision |
|---|---|
| D10 | Empty facilities result becomes a decision panel: reason, a primary "Set up on behalf of the owner" action (opens the admin path), a secondary "Use a different ID", and onboarding assistance. |
| D11 | The identity-stage text link becomes an option card with a heading, one-line explanation and button; existing test ids kept. |
| D12 | Express landing styles only; Playwright brand spec extended for both states. |
