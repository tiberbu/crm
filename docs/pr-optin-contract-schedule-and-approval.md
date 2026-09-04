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
- The wizard and CRM quoting panel use one VAT-aware commitment hierarchy:
  selected-term total first, Year 1 second, then yearly detail. Quote and
  contract PDFs state that source rates are exclusive of VAT and show net, VAT,
  and inclusive commitment totals without mixing yearly and full-term figures.
- A completed OIS is reconciled to one CRM Contract and one tracked Facility
  Signatory invitation. Direct OIS inserts are queued after commit; the public
  submission path remains synchronous so the user receives a definitive status.
  Once a Deal has a contract, CRM shows **Download PDF** only.
- **CRM Contract Standard** is maintained from a shared template, borrows the
  active/default Terms & Conditions document, and is selected as the DocType
  default by migration. The Download PDF endpoint explicitly uses this format,
  with a network-owned name, logo, contact, footer, and delivery-partner identity.

## Contract template placeholders

Use the namespaced display aliases below in editable Terms and Conditions
templates. They are preformatted in KES and are safe to place directly in HTML:

- `{{ contract_totals.monthly_exclusive_vat_display }}`
- `{{ contract_totals.monthly_vat_display }}`
- `{{ contract_totals.monthly_inclusive_vat_display }}`
- `{{ contract_totals.selected_term_exclusive_vat_display }}`
- `{{ contract_totals.selected_term_vat_display }}`
- `{{ contract_totals.selected_term_inclusive_vat_display }}`

The earlier flat aliases remain supported for existing templates. Pending
contract/PDF renders repair only these fixed numeric aliases when an older
stored body still contains them; arbitrary Jinja is never evaluated a second
time.

## Data and migration impact

- Adds the Opt-In signatory mode and nominated-signatory fields to the Opt-In
  Submission model and related contract data.
- Includes patches to backfill existing submissions to the safe self-signing
  mode, refresh network/facility terms data, and update system-owned contract
  templates with the canonical totals aliases. The migration also repairs the
  optional-services bootstrap for the Single Opt-In Settings record.
- Keeps legacy single-schedule fields compatible while persisting yearly
  facility overrides as a year-to-schedule map.
- Existing opted-in facility pricing remains locked; changes must continue
  through the quotation workflow before signature.
- Quote list and Deal lifecycle responses now expose normalized net, VAT, and
  inclusive totals. Legacy net-only quotation totals are repaired for display
  without changing the stored quotation or signed contract.

## Configuration requirements

- Network yearly contract schedules must be configured and enabled.
- Network records may provide a Technology Delivery Partner name and short name;
  legacy rows fall back to the network's legal/display name. The CHAK-affiliated
  network is seeded with **CHAK BUSINESS SERVICES LIMITED (CBSL)** explicitly.
- A nominated signatory needs a name and work email; phone is optional for SMS
  delivery where configured.
- CRM approver landing behavior applies to **Sales Manager** and **System
  Manager** roles.

## Verification

- `bench --site crm.io run-tests --module crm.tests.test_optin` — 70 passed
- `bench --site crm.io run-tests --module crm.tests.test_contract_print_format_patch` — passed
- `bench --site crm.io run-tests --module crm.tests.test_optin_admin` — 30 passed
- `bench --site crm.io run-tests --module crm.tests.test_optin_bundles` — 3 passed
- `yarn test:run` — 135 passed
- `yarn build` — completed successfully
- Quote and contract print formats were checked for selected-term commitment,
  Year 1 payable amount, and explicit exclusive/inclusive VAT labels.

The production build retains its existing warnings for the unavailable Lucide
GitHub icon, dynamic/static NotPermitted import, and large non-precached
bundles; none are introduced by this change.

## Reviewer focus

- Verify the submitter-versus-signatory language and notification routing.
- Verify all configured contract years appear in the facility editor and sample
  quote, including a mixed override case.
- Verify a Sales or System Manager opens a Deal on Quote, while an explicit
  Activity deep link still opens Activity.
- Verify the CRM commitment card equals the sum of the current yearly quote
  totals and matches the selected-term amount in the wizard and both PDFs.

## Product specification

The supporting UX decisions and acceptance matrix are in
[optin-executive-ux-prd.md](./optin-executive-ux-prd.md).
