# CareverseHIMS network/facility agreement template

The `seed_network_facility_terms_v1` migration creates **CareverseHIMS Network
Facility Agreement v1 (Facility Template)** as a new `Terms and Conditions`
document. It does not change `CRM Opt-In Settings.active_tc_document`; an
administrator can review the rendered agreement and select it manually.

## Template behaviour

- The rendered agreement opens with a document cover, a compact facility/network
  summary, and a prominent commercial summary so the parties and accepted amounts
  are immediately scannable in both the portal and the PDF print format.
- Network identity is supplied at render time through `network.display_name`,
  `network.legal_name` and `network.contact_email`.
- Facility identity is supplied through `facility.name`, `facility.mfl_code`,
  `facility.keph_level` and `customer.email`.
- The complete body of the reviewed CHAK/Tiberbu agreement is included, including
  the execution page and Schedules/Appendices A–G. Source tables are rendered as
  readable print tables rather than being summarised or truncated.
- Schedule B opens with the accepted submission pricing in `pricing_table`.
  It is generated from the server-side KEPH/Item Price result and includes the
  configured VAT calculation. The complete source framework pricing references
  are retained below it for auditability and are clearly labelled as reference
  pricing; they do not replace the facility-specific negotiated rates above.
- Appendix B retains the complete **Optional Services, Hardware and Software**
  table from the source agreement. It covers implementation/training/support
  add-ons, endpoint hardware and endpoint/office software, with reference rates
  shown as exclusive of VAT. These items remain excluded unless selected and
  itemised in the facility’s accepted quotation or signed order.
- The same context is used for the opt-in terms screen, contract generation and
  later contract/quotation PDF rendering, so the accepted facility pricing stays
  consistent.
- Print-friendly page breaks separate the service schedules and execution block;
  the signature section remains together and records that electronic verification
  details are retained with the contract record.

## Safety and compatibility

The HTML is a static app asset. No user data is interpolated into the template
source. Scalar network, facility, contact and pricing values are escaped before
they are exposed to Jinja; the only HTML-valued variable is the server-built
`pricing_table`, whose cells are escaped individually. The template uses Jinja
expressions only (no `{% for %}` or `{% if %}` blocks), because Frappe's Terms and
Conditions Text Editor sanitiser removes block tags on save.

The patch skips CRM-only sites where the ERPNext Terms and Conditions DocType is
unavailable. On each migration it creates the seeded document when absent, or
refreshes the document with the exact seeded title from the reviewed repository
asset when it already exists. It does not change `CRM Opt-In Settings` or any
other Terms and Conditions document. This keeps deployments convergent while
ensuring the full reviewed agreement (including all pricing and optional-offerings
tables) is not left truncated on a site that received an earlier version of the
patch.

## Deployment

Run the normal site migration. Review the seeded document in **Terms and
Conditions** (the exact-title document is refreshed on migration), then set it as
the active document in **CRM Opt-In Settings** when ready.
