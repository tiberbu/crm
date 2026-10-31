# Network Opt-In and Partner Coupon: two journeys, one network

Status: separated and verified on the dev site, 2026-10-30.

A network has two ways in. It is easy to confuse them because both use the same network and
the same six-digit Partner ID, and both write `CRM Facility Membership` rows.

| | **Network Opt-In** | **Partner Coupon** (Value Express self-onboarding) |
|---|---|---|
| Started by | The partner: the Partner Portal (F360) `deal_won` / `configure_facility_pricing` APIs, or a network admin adding a contact on Network Detail | The facility owner, from a coupon link (`/facility-onboarding?partner_coupon=<Partner ID>`) or by typing the coupon |
| Route | `/opt-in?network=<slug>` (plus `&facility=` or `?deal_invitation=`) | `/facility-onboarding` |
| Who can enter | Only a pre-qualified network contact: an email on a membership row **without** a Customer | Anyone whose identity verifies with the Client Registry and who owns the facility in HFR |
| Identity check | OTP to the pre-qualified email (or SMS) | Client Registry lookup, then OTP, then HFR ownership |
| Pricing | Negotiated Year 1–5 price lists on the membership (`price_list_overrides_json`), otherwise the network schedule | Public Value Express token packages (Flex, Fixed, Custom) |
| Outcome | Opt-In Submission → quotation → contract signing → finance hand-off | Customer + portal user, Deal, draft token order, HMIS setup; coupon earns bonus tokens |
| Membership row | Network contact row, **no Customer**, may carry negotiated pricing | Customer-linked row, `partner_coupon = 1` when a coupon was entered |
| Invitation email | "You've been pre-qualified" with the `/opt-in` link | "Log in to Tiberbu Express" with the portal link |
| Admin view (Network Detail) | "Network Opt-In" badge, invitation status, "Resend Opt-In invitation" | "Self-Onboarding" badge, "Tiberbu Express access" |
| Shareable link (Network Detail) | **Opt-In invitation** link | **Partner Coupon link** |

## How it was set up before work began on this server

Before 2026-10-22, opt-in was invite-only: a network admin added a facility contact, the contact
got an invitation and signed through the Opt-In wizard. `/facility-onboarding` was the
self-onboarding page. It had a "Network ID" field, so the same six-digit number was already doing
two jobs. The rule that told the journeys apart was a single line: a membership row with a
Customer is self-onboarding, a row without one is opt-in.

Later additions made that overlap bigger:

| Date | Change | Effect on the overlap |
|---|---|---|
| 2026-10-26 | Partner Portal APIs (`deal_won`, `configure_facility_pricing`) | A second writer into the opt-in side, keyed on network only |
| 2026-10-27 | Partner Coupon bonus tokens | The coupon row now carries value (`partner_coupon`, bonus lookup by Customer) |
| 2026-10-28 | Opt-In fixes: price-override heuristic, `mem_rows[0]` fallback, "customer-linked contact can request OTP" | Readers guessed the journey; coupon buyers could reach `/opt-in` |
| 2026-10-30 | Coupon via URL, "Self-onboarding link" on Network Detail | The only shareable link on a network led to Value Express, not Opt-In |

## Where the journeys were mixed up

Writers changed rows that belonged to the other journey. Readers then guessed, and each fix
added another guess.

1. **Partner Coupon took over the opt-in row.** `_upsert_facility_membership` matched any row in
   the network with the same email and stamped the Customer on it. The network contact then
   counted as self-onboarding: no Opt-In invitation, and no `/opt-in` access.
2. **F360 `deal_won` rewrote the coupon row.** It updated the first row in the network,
   overwrote the buyer's contact email and cleared the Customer. The buyer lost the link to
   their account and their coupon bonus.
3. **`configure_facility_pricing` priced the coupon row.** It wrote negotiated pricing onto the
   first row in the network. This is how rows with both a Customer and pricing came about.
4. **Admin edit merged the rows.** `save_facility` deleted every row in the edited network,
   rebuilt one and copied the Customer across. It also sent pricing when a coupon contact was
   edited.
5. **The facility, not the row, chose the email.** A contact added by an admin to any facility
   that had ever self-onboarded got the Express login alert instead of the Opt-In invitation.
6. **Opt-In readers let coupon buyers in.** `_get_membership` fell back to any row
   (`mem_rows[0]`), so a coupon-only buyer could request an Opt-In OTP. `_get_all_memberships`
   and `_mark_opted_in_facilities` did the same.
7. **The screen hid the difference.** Network Detail labelled a row "Self-Onboarding" whenever
   the facility had self-onboarded, and offered only the coupon link.

## The separation contract

One row, one journey, permanently.

- **Discriminator:** a row with a Customer is Partner Coupon / Self-Onboarding. A row without one
  is Network Opt-In. No pricing heuristics, no fallbacks (`crm/utils/onboarding_source.py`).
- **Writers stay on their own side.** Self-Onboarding resumes only its own customer-linked row
  and otherwise appends one. `deal_won`, `configure_facility_pricing` and admin
  `save_facility` touch only the opt-in row and otherwise append one. Nothing sets or clears a
  Customer on the other journey's row.
- **Admin edits:** the form names the coupon row it edits (`membership_name`), and that edit
  changes only contact name, phone and status. Email and pricing are locked. Every other edit
  goes to the opt-in row.
- **Readers filter on the discriminator.** Opt-In OTP, facility listing and "Opted In" marking
  see only opt-in rows.
- **Emails follow the row.** An opt-in row gets the Opt-In invitation, a coupon row gets the
  Express alert. Only the explicit "Invite to Tiberbu Express" action sends the Express alert
  for an opt-in row (`express=True`).
- **Both links on Network Detail.** "Opt-In invitation" and "Partner Coupon link" are labelled.
  A facility in both journeys shows "Network Opt-In" plus "Also Partner Coupon".
- **Existing data:** patch `split_mixed_journey_memberships` splits any row that has both a
  Customer and pricing into an opt-in row (keeps pricing and invitation history) and a coupon
  row (keeps Customer and coupon flag). The dev site had none.

## Panel decisions (Party Mode)

Led by the Solutions Architect, Business Analyst, UI/UX Expert, QA Lead and Security Expert.

- Architect: go back to the single discriminator from before this server; fix the writers, not
  the readers.
- Analyst: the `mem_rows[0]` fallback is leakage, not parity. Opt-In must still work for a
  facility that has also self-onboarded.
- Security: an integration API must never re-point or detach a customer's record. Mixed rows
  are split, never silently re-labelled.
- UX: two labelled links side by side, and the row badge reflects the row.
- QA: tests must fail before the fix and pass after; both journeys run live on synthetic data
  that is removed afterwards.

## Verification

- `crm/tests/test_journey_separation.py` (integration, real records) covers: coupon never adopts
  the opt-in row, `deal_won` and pricing leave the coupon row alone, a coupon buyer can't open
  Opt-In, admin edit keeps both rows, and the patch splits a mixed row idempotently. The PQF
  routing tests cover the emails. 7 of these fail on the old code and pass now.
- Full backend suite on the test site: 726 tests. The failure set is identical to `develop`
  (55 failures caused by test-site configuration: VAT template, exchange rate, package pricing,
  customer group). No new failures.
- Frontend unit tests: 233 passed. Build OK.
- Live Playwright on the dev site, `e2e/journey-separation/` (5/5). Coupon link → Value Express
  submit; F360 `deal_won` on the same facility and email; network contact verifies on `/opt-in`;
  coupon-only buyer refused; admin view, labels and edit. Teardown left 0 synthetic records.
- Existing `e2e/value-express/` suite on the dev site: 38/38 (desktop and mobile).

```bash
# backend (scratch runner, see the bench environment notes)
python run_tests.py <test site> crm.tests.test_journey_separation \
  crm.fcrm.doctype.crm_pre_qualified_facility.test_crm_pre_qualified_facility
# live journeys (creates and removes its own synthetic data)
BASE_URL=<https site URL> SITE=<site> BENCH_DIR=<bench> \
  npx playwright test --config e2e/journey-separation/playwright.config.ts
```

## Follow-ups (not changed here)

- `deal_won` writes Year 1–5 pricing even when the network schedule has fewer years. An admin
  editing that contact is then refused ("can only be overridden for configured years"). Real
  partner networks configure five years, so this only shows up on networks without a schedule.
- A row adopted before this fix, from an opt-in contact *without* negotiated pricing, cannot be
  told apart from a genuine coupon row, so the patch cannot split it. If a network contact
  reports "not registered" on `/opt-in`, re-add them as a network contact on Network Detail.
- The Opt-In journey was validated live up to facility selection after OTP. Submission and
  contract signing were not run, because they email real approvers.
