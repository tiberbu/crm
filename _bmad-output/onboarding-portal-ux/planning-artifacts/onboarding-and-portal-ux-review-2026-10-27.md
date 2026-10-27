---
epic: onboarding-portal-ux
date: 2026-10-27
status: review
session: Party Mode (UX lead, Business Analyst, Solutions Architect, Quality Analyst, Security Analyst)
follows: express-paid-tokens/planning-artifacts/token-bonus-and-partner-coupon-2026-10-27.md
---

# Onboarding and facility portal UX review

Review feedback after the Partner Coupon release, walked through on the dev site with a
synthetic facility owner and confirmed with Playwright before any change (baseline below).

## Baseline (confirmed with Playwright before changes)

| # | Screen | Observed |
|---|--------|----------|
| B1 | Onboarding · Facilities | Every eligible facility is one card in one list; 25 facilities make the page ~3,300 px tall and push Continue off screen. No search. |
| B2 | Onboarding · Facilities | Email mask shows only the first character of the local part, while the phone mask shows both ends. |
| B3 | Onboarding · Review | Row labelled "Network" with value "No Network"; note says "You can submit without a Network…" with an "Add a Network ID" link, although step 3 asks for a Partner Coupon. |
| B4 | Onboarding · Review | Terms can be read in a dialog but not saved. |
| B5 | Portal · Plans & Pricing | Card rows misalign (summary length moves the price), dead space above the button, "Ksh" prices beside "KES" summaries, token quantity is a small pill under the price. |
| B6 | Portal · Facilities | Facilities onboarded without a coupon show "No Network" as their partner. The value is the onboarding sentinel network record (`no-network`), shown as if it were a partner. Elsewhere the portal falls back to "CareVerse Partner Network" when a facility has no partner. |
| B7 | Portal · Facility | "Available tokens" is a small box squeezed in with the header buttons, not aligned with the page's cards. |
| B8 | Portal · Facility | Token orders list draft orders with no action; review and invoice actions exist only under Billing & Invoices. |
| B9 | Portal · Facility | No billing information (billed-to customer, KRA PIN, billing address). |

## Decisions

- **D1 Pagination is client-side.** The verified session already returns every facility in one
  response. Pages of 10 with a name/MFL search, selection kept across pages and searches, a
  "n selected" count on the Continue button.
- **D2 Email mask** keeps the first and last characters of the local part (`a***z@domain`). Local
  parts of one or two characters keep only the first, so nothing is fully revealed. Server-side
  only (`_mask_email`); no masked or real values in code, tests, docs or PR text.
- **D3 One name, Partner Coupon.** Review row "Partner Coupon" shows the six digits applied and
  the partner's name, or "Not applied". The no-coupon note and its link use Partner Coupon wording.
- **D4 Terms download is client-side** from the snapshot the session hashed and the user accepts:
  a standalone HTML file with the document name, date, content hash, and a CSP meta tag
  (`default-src 'none'`) so nothing in it runs when opened. No new guest endpoint: a server-side
  PDF would need wkhtmltopdf to fetch the URLs in admin-authored HTML (SSRF, CPU cost per
  session) and would be a second rendering, not the accepted one. Users can print the file to PDF.
- **D5 Pricing cards** use one card layout: title and badge, token quantity as the headline,
  price excl. VAT with VAT and total, price per token calculated from the catalogue, a summary
  limited to three lines, and the button pinned to the bottom. Money is formatted as "KES" to
  match the catalogue and onboarding.
- **D6 No partner is not a partner.** The portal API treats the `no-network` sentinel as no
  network (`_portal_network` returns `{}`, network names resolve to empty). The client shows a
  partner chip only when there is one, drops the "CareVerse Partner Network" fallback for facility
  rows, and groups facilities without a partner under "Without a partner". The Network Support
  view keeps its default CareVerse contact.
- **D7 Facility page** gets a summary row of equal-height cards: Available tokens, Current
  package, Amount to pay, and Partner (only when there is one). Token orders get the same Review
  order / Generate invoice actions as Billing & Invoices, wired to the same handlers.
- **D8 Billing information** on the facility page reads a new `get_billing_profile(customer)`,
  allowed only when the customer is one of the user's own (`get_user_customer_names()`), the same
  rule as `get_draft_order`. It returns the customer name, KRA PIN and saved addresses (billing
  first), and is read-only; edits happen in the order review.

## Stories and acceptance criteria

### S1 Paginate and search the facility list (B1)
- Given more than 10 facilities, the list shows 10 per page with "Showing a–b of n" and
  Previous/Next.
- Search by facility name or MFL narrows the list and returns to page 1.
- Selections persist across pages and searches; the Continue button shows the count selected.
- With 10 or fewer facilities, no pager or search is shown.

### S2 Email mask shows first and last characters (B2)
- `_mask_email` returns first + `***` + last of the local part when it has three or more
  characters, first + `***` otherwise, then `@domain`. Unit tested.

### S3 Partner Coupon wording on review (B3)
- Review row label "Partner Coupon"; value is the coupon digits and partner name, or "Not applied".
- No-coupon note: "No Partner Coupon applied…", link "Add a Partner Coupon" returns to packages.
- No "Network ID" or "No Network" text on the review step.

### S4 Download the complete Terms (B4)
- "Download Terms" saves an `.html` file named after the document; it contains the accepted HTML,
  the content hash and a CSP meta tag that blocks scripts.

### S5 Consistent pricing cards (B5)
- Cards in a row align the price, tokens and button; money is shown as "KES"; each paid card
  shows the price per token.

### S6 Hide "No Network" (B6)
- Facilities without a partner show no partner chip and are not listed as "No Network" anywhere
  in the facility list, grid, filter or grouping.

### S7 Facility summary cards (B7)
- Available tokens, Current package, Amount to pay and Partner (when present) render as cards of
  equal height in one row.

### S8 Pay from the facility page (B8)
- A draft order shows "Review order" (opens the order review); an order ready for an invoice
  shows "Generate invoice". Outstanding invoices keep "Choose payment".

### S9 Billing information (B9)
- The facility page shows billed-to, KRA PIN (or "Added when you review your first order") and
  the billing address, with a link to Billing & Invoices.
- `get_billing_profile` refuses customers the user is not linked to.

## Security review notes
- No new guest endpoints. `get_billing_profile` is portal-user only and ownership-checked.
- Terms file: CSP meta tag blocks scripts and remote loads; content is the session's own snapshot.
- Mask change reveals one more character only for local parts of three or more characters.

## Verification
- `crm/tests/test_facility_onboarding.py`: mask cases, including the decoy shown for unknown IDs,
  which now has the same `a***z@` shape so it cannot be told apart from a real address.
- `crm/tests/test_express_draft_order.py`: billing profile for the owner; refused for another
  customer and for an empty customer.
- `crm/tests/test_customer_experience.py`: the `no-network` record gives no partner label or
  partner details.
- Vitest `tests/unit/onboardingPortalUx.test.js`: pager, search, `partnerName`, `pricePerToken`,
  Terms file (CSP, escaping, file name).
- Playwright `e2e/onboarding-ux/`: onboarding steps with synthetic API answers (no registry
  identity or SMS) and the portal as the synthetic facility owner. `crm.tests.e2e_express_fixture`
  with `partner_coupon` false now records the `no-network` record, as self-onboarding does.

### Results (2026-10-27, dev site)
| Check | Result |
|---|---|
| Python: new and changed tests (9) | pass |
| Python: affected modules | 29 failures before and after, identical set (test-site pricing/Terms configuration); none new |
| Vitest | 219 passed |
| Vite build | pass |
| Playwright `e2e/onboarding-ux` | 4 passed |
| Playwright `frontend/e2e/regression` | 13 passed (after updating the two review-step assertions and a selector made stale by the Partner Coupon release) |

Additional fix from the post-implementation walkthrough: the facility page's Amount to pay
counts draft orders (they have no invoice until reviewed), and Current package shows the package
on order until one is paid for.

B6 was confirmed by code trace rather than screenshot: none of the existing synthetic facilities
had the `no-network` record at baseline. The post-implementation check uses a synthetic facility
onboarded without a coupon.

## Addendum: Facility ID beside every MFL code (2026-10-27)

Request: rename the portal Facilities table's "MFL Code" column to "Facility ID", and make sure
no screen shows an MFL code without the Facility ID (the Health Facility Registry FID).

- **D9 Facility ID is the registry FID**, read by `facilityId()` from `hfr_facility_id`,
  `facility_fid`, `fid` or `facility_id`, and only when the value looks like an FID. An MFL code is
  never shown in its place. A facility not yet in the registry shows "Not linked yet".
- **D10 MFL stays visible beneath the Facility ID.** Owners and staff still quote MFL codes, so
  each screen shows both, with the Facility ID first. Search boxes match either one.

### Screen audit

| Screen | Before | After |
|---|---|---|
| Portal · Facilities table (list and grouped) | "MFL Code" column | "Facility ID" column (copyable FID, MFL beneath) |
| Portal · Facilities grid, Dashboard cards, Profile list, Network Support drawer, top-up picker, link-facility notice | MFL only | Facility ID and MFL |
| Portal · Find and link facility (registry search) | FID on some results only | Facility ID on all results that have one; search option renamed "Facility ID" |
| Portal · Facility page | FID in profile panel only | Facility ID in the header, the profile panel and the identifiers line |
| Portal · facility search | Name only | Name, Facility ID or MFL |
| Onboarding · Choose facilities, Packages | MFL only | Facility ID and MFL; search by either |
| Desk · Organization, Lead, Deal facility rows; HFR search panel | MFL only | Facility ID chip beside MFL |
| Desk · Pre-qualified facilities table, Network detail facility rows | MFL only | Facility ID (API now returns `hfr_facility_id`; search matches it) |

Left MFL-only on purpose, because these screens don't have a Facility ID to show:
- **Desk, input-only:** Network detail "add facility" form and CSV import preview. The MFL code
  is what is typed in or uploaded, before any registry match.
- **Opt-in invite screens:** facility selection and review. They work from the network's
  invite records, which don't carry a FID.
- **Desk · Deal quoting tab:** facility rows come from the quote, which doesn't carry a FID.
- **Desk · Opt-in submissions:** the facility MFL column and its "Duplicate MFL" badge.
- **Finance cockpit setup form:** the `mfl_code` field.

Adding the Facility ID to these needs backend data changes, so they are left as a follow-up.
`FacilityDrawer.vue` was not changed because nothing renders it.

### Results
- Python `crm.tests.test_optin_admin`: 37 passed. Vitest: 220 passed. Build passes.
- Playwright `e2e/onboarding-ux`: 4 passed (adds Facility ID checks: table header, row FID, page
  header, onboarding cards and search). `frontend/e2e/regression`: 13 passed.
