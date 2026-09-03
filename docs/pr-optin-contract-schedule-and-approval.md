# PR: Opt-In signatory handoff, yearly contract schedules, and approver review

## Summary

This change makes the Opt-In journey safer for support/ICT submitters, makes
multi-year commercial commitments easier to review, and puts CRM approvers on
the Quote tab where the commercial decision is made.

- A submitter can confirm **I am authorised to sign** (the clear default) or
  nominate another authorised signatory. The nominated person receives the
  Opt-In summary and their secure signing link; the submitter receives an
  acknowledgement without a link.
- CRM records both the submitter and the facility signatory, with notification
  and signing status visible in the review flow.
- User-facing wording now uses **contract schedule**, replacing the ERPNext
  term “price list”.
- Network-owned yearly contract schedules can be inherited or overridden per
  facility for only the configured years. The facility editor uses the same
  year-by-year hierarchy as the network editor.
- The Prequalified Contacts sample quote shows every applicable yearly schedule
  and the total contract commitment. A facility override applies only to its
  matching year.
- Quote bundles, CRM quote summaries, contract terms, and Quote PDFs retain
  the actual facility/year schedule rather than collapsing mixed schedules to
  one misleading value.
- Sales Managers and System Managers opening a Deal without an explicit tab
  URL land on **Quote**. Quote is also the first desktop tab; explicit links
  such as `#activity` remain unchanged.

## Data and migration impact

- Adds the Opt-In signatory mode and nominated-signatory fields to the Opt-In
  Submission model and related contract data.
- Includes patches to backfill existing submissions to the safe self-signing
  mode and to refresh network/facility terms data.
- Keeps legacy single-schedule fields compatible while persisting yearly
  facility overrides as a year-to-schedule map.
- Existing opted-in facility pricing remains locked; changes must continue
  through the quotation workflow before signature.

## Configuration requirements

- Network yearly contract schedules must be configured and enabled.
- A nominated signatory needs a name and work email; phone is optional for SMS
  delivery where configured.
- CRM approver landing behavior applies to **Sales Manager** and **System
  Manager** roles.

## Verification

- `bench --site crm.io run-tests --module crm.tests.test_optin` — 63 passed
- `bench --site crm.io run-tests --module crm.tests.test_optin_admin` — 30 passed
- `bench --site crm.io run-tests --module crm.tests.test_optin_bundles` — 3 passed
- `yarn test:run` — 135 passed
- `yarn build` — completed successfully

The production build retains its existing warnings for the unavailable Lucide
GitHub icon, dynamic/static NotPermitted import, and large non-precached
bundles; none are introduced by this change.

## Reviewer focus

- Verify the submitter-versus-signatory language and notification routing.
- Verify all configured contract years appear in the facility editor and sample
  quote, including a mixed override case.
- Verify a Sales or System Manager opens a Deal on Quote, while an explicit
  Activity deep link still opens Activity.

## Product specification

The supporting UX decisions and acceptance matrix are in
[optin-executive-ux-prd.md](./optin-executive-ux-prd.md).
