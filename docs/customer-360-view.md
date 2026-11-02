# Customer 360 — one-screen customer trace for inquiry calls

Status: implemented · Reviewed in BMAD Party Mode (2026-11-02, room: John, Mary, Winston,
Amelia, Sally). Planning artifact: `_bmad-output/customer-360/planning-artifacts/`
(gitignored, local only).

## Problem

An inquiry call ("hello, this is Mercy West — when does our site go live?") makes an admin
reconstruct a customer's whole journey by hand: deal → quote → sales order → onboarding
request → facility list → invoices. Five hops across five modules, mid-call.

## What was built

One org-centric API, two entry points (decision D1):

| Entry | Where | Who |
|---|---|---|
| **Customer 360 tab** on the Deal page | `Deal.vue` tab array + `Activities.vue` panel branch; component `Deal/Customer360Tab.vue` | admin + sales manager (`isManager()`) |
| **Customer 360 nav item** (sidebar) → `/customer-360` | `AppSidebar.vue` links + `router.js`; page `Customer360.vue` | admin only |

The nav page has a debounced search (600 ms, min 3 chars — same contract as
`HfrSearchPanel`) over organizations, deals and facilities; clicking a result opens the
same 360 view for that customer.

### What the view shows (all read-only, permission-scoped)

- **KPI row**: package paid (yes/no + amount), pending orders (count + open value),
  site provisioning ("x of y live"), outstanding balance.
- **Partner Details** — whichever attribution exists: the Value Express partner
  *network* (`deal.optin_network` → display name, partner id, contact email) and/or the
  legacy `CRM Partner` reached via `deal.lead.partner` (D2).
- **Customer + deal** — org profile (industry, territory, website, employees, revenue)
  and the deal's status/value/contacts.
- **Orders** — customer-wide sales orders for the customer's deals (open = `per_billed < 100`).
- **Billing** — customer invoices (total, outstanding, due, days overdue, Paid/Draft/
  Overdue/Unpaid) + payments received.
- **Facilities & Provisioning** — each pre-qualified facility for the customer with its
  network memberships (`Opted In` / `Active` / `Declined`, go-live state, self-onboarding
  flag) plus onboarding requests (status, approvals, Careverse provisioned date).
- **Deals** — the customer's deal list with partner attribution, linked to the deal page.

Document links: order, invoice, payment and facility rows link to their source documents,
opening the Finance Cockpit record view in a new tab (`cockpitRecordHref` — the same deep
links the cockpit sidebar generates, e.g. `/finance-cockpit#/invoices?doctype=Sales
Invoice&name=…`). Deals use the CRM deal page.

Customer-wide aggregation (D3): a customer can hold several deals, so payment state,
orders and invoices aggregate across all of the customer's deals, not just one.

## Data contract

`crm/api/customer_360.py`:

- `get_customer_360(organization=None, deal=None)` — deal-scoped calls are gated by
  `frappe.has_permission("CRM Deal", "read", deal)` (same contract as
  `crm.api.lifecycle.get_deal_lifecycle`); org-only calls and search require a manager
  role. Every sub-read stays permission-scoped (`_can_read` guard per doctype); a missing
  link resolves to `None`/`[]`, never an exception. Custom fields are only selected when
  `frappe.db.has_column()` confirms them.
- `search_customer_360(query, limit=10)` — manager-gated; org by name like, deal by
  name like + deals of matching orgs, facility by name or MFL code.

Join paths (all `frappe.get_list`, no raw SQL): org ← `deal.organization` · deals ←
`CRM Deal.organization` · partner ← `deal.optin_network` / `deal.lead → lead.partner` ·
orders ← `Sales Order.crm_optin_submission ∈ OIS(org deals)` ∪
`crm_optin_quotation ∈ quotations(org deals)` · invoices ← `crm_optin_submission` ∪
`crm_quotation` ∪ `customer ∈ {deal.cx_customer}` · payments ← `Payment Entry
(payment_type=Receive, customer ∈ …)` · facilities ← `CRM Pre-Qualified Facility.organization`
with memberships read off the parent doc (pattern: `lifecycle._resolve_signatories`).

## UI decisions (D7/D8)

- Full-width tab, not right panel — four dense sections don't fit a scratchpad
  (Sally's first instinct was the side panel; she conceded on the density argument).
- frappe-ui `Badge` themes for status (no hardcoded hex; dark-mode parity), app
  `formatCurrency`/`formatDate`, debounced search with grouped results.
- Pure state helpers live in `frontend/src/utils/customer360.js` and are unit-tested.

## Verification (2026-11-02, dev site)

- Backend: `crm/tests/test_customer_360.py` — 13 new tests (summary math, gating,
  partner resolution, search); local harness 22/22 (9 opt-in + 13 new).
- Frontend: `yarn test:run` 259/259 (18 new in `tests/unit/customer360.test.js`);
  `yarn build` clean.
- Live API: deal `50048` (CORE CLINIC) returns partner network LIFEMED LTD, facility
  membership Opted-In, onboarding request Submitted/Pending, 1 paid + 1 draft invoice,
  1 open order, summary `package_paid: true`.
- Playwright: `e2e/tests/customer360.spec.ts` (4 tests) — nav page + seeded-org search,
  seeded-deal-from-search, short-query guard, deal tab with real partner/provisioning
  data — **6/6 passed** incl. auth setups.

## Known site quirk (not fixed — flagged for decision)

This site's ERPNext doctypes (Sales Order, Sales Invoice, Quotation, Payment Entry,
Customer, …) carry **no System Manager permission rows** — access is via the
Sales/Accounts role rows (intentional RBAC on this site). Consequences:

- A plain System Manager user sees 360 *partner/facility/onboarding* data but an empty
  billing section. The site's Administrator (which bypasses role perms) sees everything.
- For E2E coverage the synthetic QA user was granted `Sales User` + `Accounts User` so
  its billing assertions exercise real data.
- If you want System Manager to see the billing section without extra roles, the missing
  standard System Manager DocPerm rows would need to be restored on the site (a
  permission-data change, deliberately not made here).

## E2E note

`e2e/tests/customer360.spec.ts` captures its CSRF token from the session it actually
uses (embedded in the `/crm` HTML) because `quote_auth.setup.ts` overwrites the shared
`e2e/.auth/csrf.json` with its own session's token — a latent race in the shared e2e
infra that breaks any suite relying on the shared `createDoc`/`deleteDoc` helpers when
both setup projects run. The shared helpers were left untouched.
