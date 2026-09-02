# CareverseHIMS network/facility agreement template

The `seed_network_facility_terms_v1` migration creates **CareverseHIMS Network
Facility Agreement v1 (Facility Template)** as a new `Terms and Conditions`
document. It does not change `CRM Opt-In Settings.active_tc_document`; an
administrator can review the rendered agreement and select it manually.

## Template behaviour

- Network identity is supplied at render time through `network.display_name`,
  `network.legal_name` and `network.contact_email`.
- Facility identity is supplied through `facility.name`, `facility.mfl_code`,
  `facility.keph_level` and `customer.email`.
- Schedule B contains only the accepted submission pricing in `pricing_table`.
  It is generated from the server-side KEPH/Item Price result and includes the
  configured VAT calculation. No fixed Level 2–6 or “other levels” price table is
  embedded in the document.
- The same context is used for the opt-in terms screen, contract generation and
  later contract/quotation PDF rendering, so the accepted facility pricing stays
  consistent.

## Safety and compatibility

The HTML is a static app asset. No user data is interpolated into the template
source. Scalar network, facility, contact and pricing values are escaped before
they are exposed to Jinja; the only HTML-valued variable is the server-built
`pricing_table`, whose cells are escaped individually. The template uses Jinja
expressions only (no `{% for %}` or `{% if %}` blocks), because Frappe's Terms and
Conditions Text Editor sanitiser removes block tags on save.

The patch is idempotent, skips CRM-only sites where the ERPNext Terms and
Conditions DocType is unavailable, and leaves an existing document with the same
title untouched.

## Deployment

Run the normal site migration. After reviewing the new document in **Terms and
Conditions**, set it as the active document in **CRM Opt-In Settings** when ready.
