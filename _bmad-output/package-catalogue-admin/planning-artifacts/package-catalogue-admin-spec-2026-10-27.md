# Package Catalogue admin

**Date:** 2026-10-27
**Status:** Built (see the stories file for build notes)
**Panel (Party Mode review):** Business Analyst (Mary), PM (John), UX (Sally), Architect (Winston),
Dev (Amelia), QA (Quinn)
**Builds on:** Value Express redesign (merged into `develop`).

## 1. Outcome

A senior Sales Agent (role **Sales Manager**) opens CRM Settings › **Packages** and runs the
whole Value Express catalogue without a developer or Desk: add a Flex token package, a Fixed
package for one or more facility levels on a Monthly, Quarterly, Semi-annual or Annual
period, or the Custom offer; edit names, wording, tokens and the price; reorder; disable
(pause) and discontinue (retire). The landing page and self-onboarding show the change on the
next page load, and their card grids lay out cleanly for any number of cards.

## 2. Findings (review of what exists)

| # | Finding | Consequence |
|---|---|---|
| F1 | Packages are rows of the `token_packages` table on the single CRM Opt-In Settings, edited at the bottom of Settings › Opt-In Process. | Hard to find; mixed with agreement and signatory settings. |
| F2 | That page and its API are System Manager only. | A Sales Manager cannot manage packages. |
| F3 | The editor picks an existing Item and has no price; the price is an Item Price on the token Price List, set in Desk. | A new package needs Desk work. |
| F4 | `update_optin_settings` replaces the whole package table on every save. | Saving an unrelated Opt-In setting from a stale tab overwrites package edits. |
| F5 | `_order_tokens` and the bonus rule read each item's tokens from the **live** table when an order is paid. | Changing the tokens of a sold package changes what open orders grant. |
| F6 | "per month" is hard-coded for Fixed in the landing page, the compare table and onboarding; the calculator compares the Fixed fee to a monthly Flex cost. | Any non-monthly Fixed package is shown and compared wrongly. |
| F7 | `fixed_package_for_level` takes the first Fixed row whose levels match. | Two active Fixed packages for one level are ambiguous. |
| F8 | "Most popular" and the journeys figure live in the `coverage_metrics` JSON. | Not editable by a Sales Agent. |
| F9 | Grids use `repeat(var(--cards),1fr)`: 7 cards make 7 narrow columns. | Cards squeeze as the catalogue grows. |

## 3. Decisions

| Ref | Decision |
|---|---|
| D1 | New Settings page **Packages** (System Configuration group), shown to Sales Managers and admins. Opt-In Process keeps the token Price List, bonuses and order/invoice days, and links to Packages instead of embedding the table. |
| D2 | New API module `crm.api.package_catalogue` with per-package calls: `get_package_catalogue`, `save_package`, `set_package_status`, `move_package`. Guard: System Manager, Sales Manager or Administrator. Every write carries the `version` it was read at (the settings' `modified`), and a stale version is refused with "reload". |
| D3 | `update_optin_settings` changes `token_packages` only when the payload contains the key (F4). |
| D4 | `CRM Token Package` gains `status` (Active / Disabled / Discontinued, default Active) and `discontinued_on`. `enabled` stays and is kept equal to `status == Active`, so existing readers are unchanged. A patch backfills `status` from `enabled`. |
| D5 | **Disable** hides a package and can be undone. **Discontinue** is final, needs confirmation, keeps the row for history and order lookups, and hides it from the default view. To sell it again, **Duplicate** creates a new package from it. |
| D6 | **Sold lock** (F5): once the package item appears on a submitted or draft Sales Order or Quotation, its item, plan and tokens are read-only. Price, wording, levels, period, order and status stay editable. The UI says why fields are locked. |
| D7 | A new package can **create its Item** (non-stock sales item, item group and UOM copied from an existing package item, else defaults) and its **Item Price** on the token Price List. Editing the price updates that Item Price; orders already raised keep their own rate. |
| D8 | Periods: Monthly (1), Quarterly (3), Semi-annual (6), Annual (12) months, in `value_express.PERIOD_MONTHS`. Fixed prices are shown "per month", "per quarter", "per half-year" or "per year"; the calculator compares the monthly equivalent (price ÷ months). The renewal period key handles Semi-annual. |
| D9 | Validation (pure, in `value_express.validate_catalogue`): Flex needs ≥ 1 token and a price > 0; Fixed needs ≥ 1 level and a price > 0, and no level may belong to two active Fixed packages (F7); Custom has 1 token, needs no price, at most one is active and it cannot be active with no active Flex package; item codes are unique. |
| D10 | "Most popular" toggle and an optional "Patient journeys" figure write `badge` and `journeys` into `coverage_metrics`, keeping any other keys. |
| D11 | Grid columns: `grid_columns(n, max)` = ceil(n ÷ ceil(n ÷ max)) — rows as even as possible with at most `max` per row (Flex+Custom max 4: 5 → 3+2, 7 → 4+3; Fixed tiers max 2 inside the landing plan card, 3 in onboarding). Landing and onboarding set `--cols`; ≤ 1000 px two columns, ≤ 560 px one. Pure in Python and JS, unit-tested. |
| D12 | Audit: each change adds an Info comment on CRM Opt-In Settings naming the package and the action. |

## 4. Admin page (UX, Sally)

- Header: title, the token Price List and currency (or a warning linking to Opt-In Process
  when none is set), **New package**.
- Filter: Active · Disabled · Discontinued · All, with counts.
- Sections by plan (Flex, Fixed, Custom), each a responsive card grid
  (`repeat(auto-fill, minmax(260px, 1fr))`). A card shows the name, status, price and period,
  tokens and per-token rate (Flex), levels (Fixed), and "Most popular".
- Card actions: Edit, Duplicate, Move up/down (within its plan), Disable/Enable, Discontinue
  (confirm dialog).
- Edit dialog: plan, name, item (new from name or existing), tokens, price (ex VAT), period,
  levels (Fixed), description, coverage summary, journeys, Most popular. Locked fields show
  "Sold on N orders: duplicate to change tokens".

## 5. Out of scope

- Fixed metering exemption and the unpaid-month rule (VE-F1, VE-F2): unchanged.
- Choosing between several periods for one level in onboarding (D9 keeps one active Fixed per level).
- Changing the token Price List or VAT from the Packages page.

## 6. Quality gate (Quinn)

- Python: unit tests for `validate_catalogue`, `grid_columns`, period helpers; API tests for
  save/status/move, sold lock, stale version, permission.
- Frontend: `yarn test:run` green with tests for `gridColumns` and period labels.
- Playwright (`e2e/package-catalogue/`), on the dev site as a Sales Manager: create a Flex
  package with a new item and price; it appears on `/` and in onboarding; edit the price; move
  it; disable (gone) and enable; create a Quarterly Fixed package ("per quarter"); discontinue;
  7 Flex+Custom cards lay out 4+3 at 1440 px; no horizontal scroll at 360 px; a Sales User is
  refused. The test restores the catalogue it started with.
