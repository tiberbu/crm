# Metering Token Traceability & Onboarding Terms Copy

Status: implemented (2026-11-03)
Decided in: Party Mode round table — Sally (UI/UX, chair), Mary (Business Analyst), Winston
(Solutions Architect), Rita (QA), Vex (Security)

## Problems reported

1. **Onboarding Review step** — the acceptance sentence printed the backend *Terms and
   Conditions document name* (e.g. "CareverseHIMS Opt-In Terms and Conditions") instead of a
   stable generic label. The sentence is a contractual statement and must not change when an
   admin renames the T&C document or points `self_onboarding_tc_document` elsewhere.
2. **Deal → Metering tab** — the welcome-bonus banner mixed "tokens granted as bonus" with the
   related invoice in one line, and showed no line at all for tokens bought on the paid invoice
   or for Partner Coupon tokens. Identifiers (invoice number, partner ID) were plain text.
3. **Metering tab affordances** — no explanation of what the header buttons (Test Connection,
   Import sites from CRM, Scan paid token purchases) do, and the Grants table's Status/Source
   values (e.g. "Skipped", "Initial Package") carried no explanation or trace link.

## Decisions

### D1 — Onboarding terms sentence (issue 1)

- Sentence: `I have read and accept the [Terms and Conditions](opens dialog) and the
  [token rules](/#flex-rules).` — the link text is the generic label `__('Terms and
  Conditions')`, not `termsTitle`.
- The section heading (`#review-terms-title`) and the full-terms dialog title **keep** the
  document's own name — they name the document being read; the sentence accepts "the Terms and
  Conditions" generically.
- `get_self_onboarding_terms`, the content-hash binding, `termsDownload.js` (filename from the
  document slug) and the backend resolution chain are unchanged.
- Files: `frontend/src/pages/FacilityOnboarding/FacilityOnboardingLanding.vue` (line ~533).
- Tests flipped: `frontend/tests/unit/FacilityOnboardingLanding.test.js`
  (terms-open link text), `frontend/e2e/regression/onboarding-layout.spec.ts` (terms-open
  expectation keeps `#review-terms-title` = mock document title, link = generic label).

### D2 — Token grant lines in the facility card (issue 2a)

The `OpenMeter Grant` ledger is the single source of truth. The facility card renders up to
three **separate** lines in a "Token grants" panel, each with its own tokens, date and
identifiers; a line is hidden when no grant of that type exists:

| Line | Data source | Test ID |
|---|---|---|
| Welcome bonus | `get_welcome_bonus` state (button + narrative) — same ledger row | `welcome-bonus` (kept) |
| Token purchase | `probe_site.grants` where `grant_source == 'Token Purchase'` — one line per invoice | `token-purchase` |
| Partner coupon | `probe_site.grants` where `grant_source == 'Partner Coupon'` | `partner-coupon` |

- Identifiers are links via `cockpitRecordHref(doctype, name)` (Finance Cockpit record view —
  the convention from the Customer 360 commit): invoice number → `Sales Invoice` record;
  partner → `CRM Opt-In Network` record. Anchor: `target="_blank" rel="noopener noreferrer"`,
  class `text-ink-blue-6 hover:underline`.
- Partner resolution (mediator, best-effort, wrapped so a failure never breaks the probe):
  facility → `CRM Pre-Qualified Facility` (by FID, then MFL) → membership with
  `partner_coupon = 1` → `network` → `CRM Opt-In Network` (`name` = partner ID,
  `display_name`). Exposed as `probe.partner`.
- Non-Granted purchase/coupon grants show their status + `last_error` reason instead of
  implying the tokens exist. Multiple invoices → multiple lines (no collapsing). Reissue/Manual
  grants stay table-only.
- Backend: `probe_site` gains `source_doctype` per grant and `partner`.

### D3 — Grants table tooltips (issue 2b)

frappe-ui `Tooltip` (`#content` slot for links):

- **Status cell** — explains the state and carries `last_error`:
  - `Skipped` — "No tokens were granted from this source: {reason}".
  - `Granted` — tokens are active in OpenMeter.
  - `Failed` — last attempt failed + reason.
  - `Pending` — not confirmed yet.
- **Source cell** — explains the source and carries the trace link:
  - `Initial Package` → link to the parent **CRM Deal** (server rewrites the child-table
    `CRM Deal Facility` source to its parent deal, since child rows have no URL).
  - `Token Purchase` / `Welcome Bonus` / `Partner Coupon` → link to the invoice/order.

### D4 — Button tooltips (issue 3)

Every metering button gets a one-to-two-line tooltip verified against the actual handlers
(`Button.tooltip` for buttons, `description` for Dropdown items):

- **Test connection** — read-only credential/connectivity check; persists last status; changes
  nothing.
- **Import sites from CRM** — creates/updates one `OpenMeter Site` (Draft) per facility on the
  deal; idempotent; new sites must be set Active to start metering.
- **Scan paid token purchases** — backstop for the 15-minute scheduler; only grants for fully
  paid token invoices; safe to repeat.
- **Site keys for existing facilities** (dropdown) — lists facilities with no delivered key and
  offers the signed delivery job.
- Per-card: Sync to OpenMeter, Send probe event, Retry failed events, Re-issue expiring grants,
  Issue site key, Reveal full key, Refresh — each with its real effect.

Security constraint (Vex): links use relative hrefs only; tab stays gated by
`get_access` (OpenMeter Admin / System Manager); key reveal stays Administrator + password;
`last_error` stays capped at 1000 chars.

## Verification results (2026-11-03, crm-dev.tiberbu.app)

1. `frontend`: `yarn test:run` → 265/265 pass (incl. flipped onboarding assertions and new
   `welcomeBonusVia`/`tokenLines` unit tests); `yarn build` clean.
2. `openmeter_mediator`: `py_compile` clean; `probe_site` verified live — grants carry
   `source_doctype`, child-table `CRM Deal Facility` sources are rewritten to the parent
   `CRM Deal`, and the partner resolves (e.g. FID-00-E2EX-10270907 → partner_id `909091`).
3. Playwright:
   - `frontend` portal-ui regression `onboarding-layout` → 4/4 viewports pass (sentence reads
     "I have read and accept the **Terms and Conditions** and the token rules"; heading and
     dialog still name the configured document).
   - new live spec `e2e/metering/metering_traceability.spec.ts` → pass (6 steps): header
     button tooltips; bonus / purchase / coupon lines separate with clickable identifiers
     (invoice, order, partner — Finance Cockpit record hrefs, `{ absolute: true }`); clicking
     the invoice link opens the record; grants-table status tooltips (Skipped explains why,
     incl. `last_error`) and source tooltips (Initial Package traces to the parent CRM Deal);
     order-assigned bonus links the Sales Order; coupon line absent when no coupon grant.
   - Fixture data: temporary deal `16511` (coupon facility) was created for the live pass and
     deleted afterwards.
4. Note: reka-ui renders `role="tooltip"` on an off-screen a11y copy; e2e targets the visible
   bubble (`div.bg-surface-gray-10`) and settles the pointer (reka ignores "in transit"
   pointer moves).
5. `welcome_bonus_auto_assign.spec.ts` wording updated (`automatically when order … was
   selected` — the identifier in that sentence is the order number, which it now names).
