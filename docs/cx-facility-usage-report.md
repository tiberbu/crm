# CX Portal facility usage report (P-135)

**Status:** built 2026-11-11 · **Roundtable:** `_bmad-output/usage-report/implementation-artifacts/party-2026-11-11-usage-report-and-on-behalf.md`
**Repos:** crm (portal, API, CSV) and openmeter_mediator (report service, hook)

## What the customer gets

A **Usage** tab on a facility's page in the CX Portal. It appears next to Overview when the facility is on a token plan (Flex or metered) and has an HFR Facility ID.

| Part | What it shows | Source |
|---|---|---|
| Date range | Last 7 days, Last 30 days, This month, Last month, or From/To. At most 366 days. Dates are in the site's time zone. | — |
| Tokens added | Tokens added in the range, split into paid tokens, initial package, welcome bonus, coupon and other, plus the total since onboarding | Mediator `OpenMeter Grant` (status Granted, by `effective_at`) |
| Tokens consumed | Total for the range | OpenMeter meter query |
| Available now | Live balance | `crm_get_facility_token_balances` |
| Patient registrations | Quantity of `patient_registration` events charged, with consultations beside it | Event detail; otherwise tokens ÷ current price, labelled *estimate* |
| Consumption by billing event | Quantity, current price, tokens and share for each billing event | Meter query grouped by `module`; quantities from event detail |
| Price check | Each event: tokens charged = quantity × unit price, and the unit price compared with the current price list | OpenMeter raw events (`billing_event`, `quantity`, `unit_tokens`, `catalog_version`) |
| Daily consumption | Tokens per day | Meter query, `windowSize=DAY` |
| Download | One CSV: summary, tokens added, breakdown, daily, every event and its check | Built on the server from the same report |

Price check outcomes:

| Outcome | Meaning |
|---|---|
| Matches the price | Charge = quantity × unit price, and the unit price equals today's list price |
| Price differs from current list | The arithmetic is right, but the unit price charged is not today's list price (for example, the price changed after the event) |
| Charge differs from quantity × price | The tokens charged do not equal quantity × unit price |
| Pre-priced (ledger export) | Sent through the ledger export (`/ingest/v1/events`) with a token amount and no quantity, so there's no price to check |

"Patient registrations" counts registrations the HMIS was charged for. HMIS owns the patient register; the page and the file both tell the customer to compare against it.

## Limits

- **Event detail covers about the last 30 days.** OpenMeter `v1.0.0-beta.236` refuses a raw-event `from` older than about 32 days and returns at most 100 events per page. `/api/v2/events` ignores its time filter on this version. Totals, the token breakdown and the daily series come from the meter and cover the whole range. Counts and the price check cover the detail window, and the page says which dates that is.
- Event detail is capped at 5,000 events per report. Above that, the report is marked as partial.
- Follow-up **F1**: add a quantity meter (`SUM $.quantity` grouped by `module`) so counts no longer expire after 30 days and never need estimating.

## Contracts

### CRM (whitelisted, portal login)

| Method | Arguments | Returns |
|---|---|---|
| `crm.api.usage_report.get_facility_usage_report` | `mfl_code`, `from_date`, `to_date` (YYYY-MM-DD) | The report, plus `facility {mfl_code, facility_name, fid}` |
| `crm.api.usage_report.download_facility_usage_report` (GET) | the same | A `token-usage-<FID>-<from>-to-<to>.csv` attachment (UTF-8 with BOM) |

Who may see a report: the facility must be one the signed-in owner's portal shows (`token_alerts._portal_facilities`), and it must have an FID. A text cell that starts with `= + - @` is prefixed with `'` so spreadsheets don't run it as a formula.

`status` is `ok`, `disabled` (no metering app, or metering is switched off), `not_metered` (OpenMeter doesn't know the FID) or `unavailable`. A bad range, such as a reversed, future or longer-than-366-day range, raises a validation error with a message the customer can read.

### Mediator hook

`crm_get_facility_usage_report(fid, from_date, to_date) -> dict` maps to `openmeter_mediator.services.usage_report.facility_usage_report`. It reads OpenMeter through the gateway credential (`OpenMeterClient`) and doesn't change anything.

OpenMeter calls:
- `GET /api/v1/meters/{meter_slug}/query?subject=<FID>&groupBy=module&from&to&windowTimeZone[&windowSize=DAY]`
- `GET /api/v1/events?subject=<FID>&from&to&limit=100`, newest first with `to` exclusive. To page, move `to` back to the oldest event seen (+1 s for same-second ties, de-duplicated by id).
- `GET /api/v1/features?meterSlug=…` gives the current price list; without it, the catalog file is used.

## Configuration and deployment

There are no new settings, doctypes or migrations. Both apps need deploying and the frontend rebuilding. The gateway credential needs to read meters, events and features, which the existing balance and catalog reads already do.

## Verification

- Mediator: `openmeter_mediator.tests.test_usage_report` (11 tests): range rules, paging with same-second ties, the one-second full-page edge case, truncation, the four audit outcomes, reconciliation, estimates, outage, not-metered and disabled.
- CRM: `crm.tests.test_usage_report` (8 tests): owner-only access, FID required, the hook seam, unavailable and validation errors, CSV sections and formula neutralising, and the download headers.
- Frontend: `tests/unit/usageReport.test.js`, plus `e2e/regression/usage-report.spec.ts` in the portal UI suite at four viewports, with the layout, weight, size and contrast gates and the brand-red download button.
- Live smoke against the local OpenMeter quickstart for a synthetic FID: 10 registrations matched their price and 1 ledger-export event was flagged pre-priced. The paid/bonus grants split correctly.
