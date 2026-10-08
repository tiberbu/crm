# Facility Onboarding and Customer Experience — Implementation Brief

**Customer-facing product:** Tiberbu Customer Experience (also: Tiberbu HMIS Customer Experience Portal)
**Implementation system:** Frappe app in `apps/crm`; the repository/app name is an implementation detail and must not appear in customer-facing copy
**Reference only:** `careverse_hq` request and response shapes; no CRM import, cross-app call, or runtime dependency
**Status:** Public Customer Experience entry, facility onboarding welcome/wizard, sign-in routing, and authenticated portal foundation stabilized; token purchase order-to-invoice flow remains the next story
**Date:** 2026-10-08

## 0. Stabilization pass — 2026-10-08

This pass records the implemented customer-facing entry points and the verification
performed before the focused PR. It does not claim that the downstream token
purchase, invoice, or payment stories are complete.

### Customer-facing language

- Use **Tiberbu Customer Experience** or **Tiberbu HMIS Customer Experience Portal**.
- The primary audience is facility owners and facility administrators.
- Do not use the repository/app name, internal workspace terminology, or sales,
  pipeline, telephony, or staff-operations language in the facility-owner journey.
- Any internal link on the public page is secondary and labelled **Staff access**.

### Implemented route map

| Route | Audience | Current behavior | Source of truth |
|---|---|---|---|
| `/` | Public facility owner | Explains Customer Experience, the value to an owner, the onboarding journey, requirements, security, and next steps. | `crm/www/index.html`, `crm/www/index.py` |
| `/facility-onboarding` | Public facility owner | Opens directly on the welcome screen, then continues through identity, OTP, facility selection, package/network selection, review, and submission. | `crm/www/facility-onboarding.html`, `crm/www/facility_onboarding.py`, `frontend/src/pages/FacilityOnboarding/FacilityOnboardingLanding.vue` |
| `/login?redirect-to=/cx-portal` | Existing facility owner | Branded sign-in path for Customer Experience access. | `crm/www/login.html`, `crm/www/login.py` |
| `/cx-portal` | Authenticated facility owner | Redirects guests to the Customer Experience sign-in path; authenticated users receive the facility-scoped portal shell. | `crm/www/cx-portal.html`, `crm/www/cx_portal.py`, `frontend/src/pages/FacilityPortal/FacilityPortal.vue` |

### Build and asset publication

The frontend is a Vite multi-entry build. `frontend/facility-onboarding.html`
must include `facility-onboarding-main.js`; otherwise Vite emits a 200 HTML
entry with no application bundle and the Frappe route appears blank.

The Frappe `www` wrappers remain thin. `facility_onboarding.py` and
`cx_portal.py` lift the hashed module, modulepreload, and stylesheet tags from
`crm/public/frontend/{facility-onboarding,cx-portal}.html` and omit PWA
manifest/service-worker tags for these authenticated or guest flows. The build
must not overwrite those wrappers with generated HTML, because that duplicates
the injected tags.

Build command:

```text
cd apps/crm
yarn build
```

The production path is served through Nginx at `https://cr-dev.tiberbu.app`;
the raw Gunicorn port is not the static-asset verification path.

### Verification evidence

- `/`, `/facility-onboarding`, and `/login?redirect-to=/cx-portal` returned HTTP
  200 on `https://cr-dev.tiberbu.app`.
- `/cx-portal` returned the expected guest redirect to
  `/login?redirect-to=/cx-portal`.
- The landing-page links resolved successfully.
- The facility onboarding HTML entry, module bundle, modulepreload bundles, and
  stylesheet returned HTTP 200.
- Frontend unit tests: 8 files, 135 tests passed.
- Frappe unit tests: onboarding module 2 passed; Customer Experience redirect and
  progress module 9 passed.
- `git diff --check` passed.

The build still reports non-blocking existing warnings for Browserslist data,
the missing Lucide GitHub icon placeholder, and large chunks excluded from PWA
precaching.

## 1. Product goal

Enable a Facility Admin to verify ownership, choose an Opt-In Network using its six-digit Partner ID, select a token service package, submit an Opt-In Request, and complete the existing contract-signature process.

This onboarding workflow is for token users only.

The workflow does not use Year 1–Year 5 pricing or create a Year 1–Year 5 quotation.

The workflow creates a Quotation and a separate Sales Order for each facility for the next billing period.

The Sales Order has a configurable, generic validity period. It does not create an invoice during onboarding.

The workflow does not create purchases, invoices, or payments automatically.

After login, the facility user finds an open Sales Order and intentionally starts payment. CRM then creates the Sales Invoice with payment terms due within 30 days and opens the existing Paystack Checkout experience. Payment will usually happen immediately, but the invoice remains the accounting authority.

After the required signatures, CRM adds the facility to the Network, creates or reconciles a Website User, and sends a Customer Experience login invitation.

## 2. Business outcome

At completion:

1. The owner’s identity and facility ownership are verified through Client Registry and Health Facility Registry data.
2. The facility is linked to one Opt-In Network. The Network is the Agent for this workflow.
3. The owner selects a facility-friendly token service item from the configured catalogue Price List.
4. CRM creates a next-period quotation and Sales Order using native ERPNext records.
5. CRM creates the Opt-In Request.
6. The facility appears in the resolved Network list with a pending-signature status.
7. All required facility and Network signatories complete the applicable signature steps.
8. The membership becomes `Opted In` only after signature completion.
9. The owner receives a Website User invitation and can view progress.

Every Opt-In Request and Network contact created or linked by this journey must be identifiable as token-based self-onboarding.

Future token purchases are intentional user actions from the authenticated Customer Experience.

For each future purchase, Customer Experience creates or resumes a Quotation and Sales Order. The user starts payment from the open Sales Order; CRM then creates the Sales Invoice and sends the user to the existing Checkout page.

## 3. Scope

### In scope

- Public facility onboarding information.
- Token package search and selection.
- Token package workload descriptions.
- Owner identity verification.
- Client Registry contact triangulation and OTP.
- Health Facility Registry facility discovery.
- Facility selection.
- Six-digit Partner ID entry or an approved admin-preconfigured Network.
- Next-period Quotation and Sales Order.
- Existing Opt-In Request and contract-signature process.
- Applicable facility and Network signatories.
- Network membership creation and post-signature activation.
- Website User invitation.
- Authenticated Customer Experience with read-only progress and purchase/payment actions.
- Authenticated token purchases.
- Open invoice visibility and payment through the existing Checkout page.
- Guest endpoint security and portal authorization.

### Out of scope for this workflow

- KEPH-based pricing.
- Other classification-based pricing.
- Year 1–Year 5 quotations.
- Anonymous creation or editing of token packages.
- User-edited rates or Price Lists.
- Automatic token purchases, automatic renewals, and cron-driven invoice or payment flows.
- A second contract or signature engine.
- A CRM-only accounting ledger.

Existing classification-based and Year 1–Year 5 Opt-In behavior must remain available to existing workflows unless separately retired. It is not part of this token onboarding path.

Lago or another metering system may be evaluated later. Metering is out of scope for this release.

## 4. Network identity

The Opt-In Network is the Agent for this workflow. Partner ID is the public
six-digit identifier for that Network.

On Network insert, CRM generates a unique six-digit Partner ID when the admin
leaves the field blank. An admin may provide a six-digit value instead. The
value is unique and immutable after creation.

The required relationship is:

```text
Partner ID → one CRM Opt-In Network → one Agent identity
```

If the owner has no Partner ID, CRM may use only the admin-issued entry
context’s approved preconfigured Network. The owner cannot choose a second
Network through that invitation.

CRM must stop safely when no valid Network can be resolved.

The resolved Network is a strict foreign-key gate for the entire onboarding request.

CRM must reject an unknown, inactive, ambiguous, or mismatched Network. A blank Partner ID is accepted only when the CRM setting contains a valid six-digit Partner ID for an enabled Network.

The Opt-In Request must use the contacts and signatory configuration belonging
to the resolved Network, whether that Network came from the owner’s Partner ID
or the approved admin-preconfigured Network.

## 5. User journey

### 5.1 Information and entry

The landing page must explain:

- what the facility is joining;
- what tokens are;
- what each package can cover;
- the information required;
- the onboarding steps;
- the applicable price and VAT treatment;
- the signatories and approvals required;
- support and legal terms; and
- what happens after submission.

The page must not expose internal ERPNext or integration concepts.

### 5.2 Identity and facility verification

The owner enters an identity type and identity number.

CRM sends the request to the configured registry endpoints through its own server-side adapter.

The registry verifies the identity, retrieves the registered contact, and finds facilities linked to the owner in HFR.

CRM sends an OTP to the verified Client Registry contact.

The owner enters the OTP.

Only then may CRM return the eligible facility list.

The owner selects one or more eligible facilities.

### 5.3 Network Partner ID resolution

The owner chooses one of two paths:

1. Enter an enabled Network’s six-digit Partner ID.
2. Continue without a Partner ID and use the explicit CRM-configured default Partner ID.

CRM resolves the Network and Agent identity server-side.

The owner sees the resolved Network before continuing.

The owner cannot enter a Network slug, Agent ID, Price List, or internal record as a substitute.

### 5.4 Token package selection

The owner searches enabled service items in the configured catalogue Price List.

Search must be simple and safe. It may use service-item name, item code, facility-friendly description, or workload terms.

Each result must show:

- package name;
- short description;
- token quantity;
- ex-VAT price;
- currency;
- validity or billing period;
- workload coverage description; and
- key coverage examples.

Example coverage language:

- “Designed for daily traffic of approximately X claims.”
- “Covers up to 100 laboratory transactions.”
- “Designed for approximately X invoices per month.”

Coverage descriptions are estimates unless the package explicitly defines them as contractual entitlements.

The owner selects a package. The owner does not enter an arbitrary token quantity or price.

### 5.5 Quotation and Sales Order

CRM creates a quotation for the next billing period, normally the next month.

CRM creates a separate Sales Order for each selected facility from the accepted quotation or the same server-generated pricing context, according to ERPNext workflow rules.

The quotation and Sales Order must use the same token package, items, rates, currency, validity, and tax calculation.

There is no Year 1–Year 5 quotation for this workflow.

### 5.6 Opt-In and signatures

The wizard collects the existing Opt-In information, including:

- facility details;
- facility signatory details;
- witness details where required;
- applicable Network signatory details;
- optional services;
- implementation information; and
- terms and consent.

CRM creates the Opt-In Request.

CRM adds the selected facility to the resolved Network with a pending-signature status.

CRM attaches the applicable contacts and signatories from that resolved Network to the request and Contract. The browser cannot submit contacts from another Network.

CRM creates the existing Contract.

All required signatories must be applied according to the configured signing rules.

The signing sequence may include the facility signatory, witness, Network signatory, or multiple Network signatories as applicable.

No required signatory may be skipped because the onboarding started from a public or guest flow.

The existing signature OTP, signing tokens, witness rules, and status transitions remain authoritative.

### 5.7 Completion and portal access

After all required signatures:

- the membership becomes `Opted In`;
- the Opt-In Request is marked accordingly;
- CRM creates or reconciles a restricted Website User;
- CRM sends a password-setup or login invitation; and
- the owner can access the facility portal.

Account creation and email delivery must be retryable and must not create duplicate submissions.

### 5.8 Future token purchases

After login, the facility user can intentionally buy more tokens from the portal.

The purchase flow is:

1. Select a token package.
2. Review the package coverage and ex-VAT price.
3. Confirm the package and create or resume the Quotation and a facility-specific Sales Order.
4. Return to the portal and show the open Sales Order.
5. Start payment from the open Sales Order.
6. Create a Sales Invoice with payment terms due within 30 days.
7. Open the existing Checkout page.
8. Pay the open invoice.
9. Return to the portal and see the payment and token status.

There are no cron jobs for this flow.

There are no automatic token purchases or automatic renewals.

Each purchase request must be idempotent. Repeated clicks must not create duplicate Quotations, Sales Orders, Sales Invoices, or payment attempts.

The portal must show open invoices, payment status, payment date, amount due, and receipt or transaction reference when available.

## 6. Token pricing requirements

### 6.1 Global price rule

**All prices in this flow exclude VAT.**

The UI must label every package, quotation, and Sales Order amount as **excluding VAT** or **ex VAT**.

VAT must be shown separately.

The UI may also show the VAT-inclusive total for clarity, but it must never present the gross total as the base price.

The quotation, Sales Order, contract evidence, and portal summary must use the same treatment.

### 6.2 Token catalogue Price List

One configured ERPNext selling `Price List` contains several token service items.

The Price List is a global catalogue and does not belong to a Network. Each service item has facility-friendly CRM metadata describing its token quantity and workload coverage.

The onboarding flow searches the configured catalogue by service-item name, package code, description, or workload terms.

The selected catalogue service item is independent of the resolved Network’s existing Year 1–Year 5 pricing, `price_lists_json`, `price_list_override`, or default Price List.

A Network may have legacy or configured classification prices. Those prices must not change, block, or replace the token package price in this workflow.

The Network still matters for identity, branding, membership, contacts, signatories, and Opt-In ownership. It does not determine the token package rate.

CRM Settings must provide the catalog metadata required for display:

- one Price List link;
- service-item link;
- display name;
- short description;
- token quantity;
- ex-VAT package amount;
- currency;
- billing period;
- validity;
- coverage summary;
- coverage metrics;
- enabled/disabled status.

The package’s commercial rate must remain in ERPNext `Item Price` records.

CRM Settings must not become a second rate ledger.

The onboarding flow must not expose unrestricted Price Lists or service items. It may return only enabled, sellable, onboarding-approved packages from the configured catalogue Price List.

### 6.3 Workload coverage descriptions

Every published token package must explain the workload it is intended to cover.

Coverage can be described using configurable metrics such as:

- daily transaction volume;
- monthly laboratory volume;
- monthly invoice volume;
- monthly claims volume;
- number of active facilities; or
- another approved operational metric.

Coverage descriptions must distinguish estimates from contractual limits.

The selected package, description, metrics, and version must be copied into the quotation and Opt-In snapshot.

### 6.4 Package selection and pricing authority

The owner selects a configured package.

The owner cannot:

- create a package;
- change a package’s token quantity;
- change an Item Price;
- choose an internal Price List directly;
- add an unconfigured item; or
- submit a client-calculated total.

The server resolves the package, Price List, Item Price rows, validity, currency, taxes, and quotation totals.

### 6.5 Next-period quotation and Sales Order

The next-period quotation must include:

- package name and description;
- token quantity;
- coverage summary;
- ex-VAT amount;
- VAT amount;
- VAT-inclusive total;
- currency;
- billing period;
- validity dates;
- Price List reference; and
- applicable terms.

The Sales Order must be created from the same accepted commercial context and must have the configured generic validity period.

The quotation and Sales Order must reconcile line-by-line and total-by-total.

If the package contains multiple billable items, each item must come from ERPNext Item and Item Price records.

If the package is represented by one token item, that item must have the correct income, tax, and stock/service treatment in ERPNext.

### 6.6 Future purchase accounting flow

Future purchases are created only after an authenticated facility user confirms the purchase.

The server creates or resumes the following native ERPNext records in stages:

```text
Quotation → Sales Order → user starts payment → Sales Invoice → existing Checkout/payment flow
```

The invoice is the payment authority and is due within 30 days. The portal may create it immediately when payment starts.

The portal must not collect payment directly or create a second checkout experience.

No cron job, scheduled task, automatic renewal, or background purchase flow may create these records.

## 7. Network signatory requirements

Network signatories are part of the commercial approval process.

The system must support:

- zero Network signatories where the configuration explicitly allows it;
- one required Network signatory;
- multiple required Network signatories;
- ordered or parallel signing;
- role-specific signatories;
- substitute or delegated signatories where approved; and
- signatory reminders and expiry.

The configured Network signatory rules determine who must sign.

The onboarding UI must show the owner which approval steps apply without exposing internal workflow configuration.

The Contract must contain all applicable signatory roles.

The Opt-In Request cannot become fully opted in until every required signature is complete.

### 7.1 Contact attribution

For this PRD, a Network contact is any CRM Contact created or linked to the resolved Network during token self-onboarding.

This includes the Facility Admin, facility signatory, witness, and any Network signatory contact created or linked by the flow.

Each such Contact must be marked as `Token self-onboarding` and linked to the source Opt-In Request.

Existing contacts must be reconciled idempotently. Their original creation source must not be overwritten.

## 8. Product rules

1. This workflow is token-only.
2. There is no Year 1–Year 5 quotation in this workflow.
3. The commercial output is the next-period Quotation and Sales Order, followed by an Invoice and payment when the user purchases.
4. All prices exclude VAT.
5. VAT is calculated and displayed separately.
6. One configured ERPNext selling Price List contains several token service items.
7. Token service items do not need a Network link.
8. CRM Settings stores facility-facing package descriptions and coverage metadata.
9. ERPNext stores the commercial rates and accounting values.
10. Package search returns only enabled, onboarding-approved items from the configured catalogue.
11. The owner cannot submit arbitrary token quantities or prices.
12. All applicable Network signatories must complete the configured signature process.
13. Membership remains pending until all required signatures are complete.
14. Accepted or signed prices are immutable commercial snapshots.
15. Future purchases are initiated by the facility user from the portal.
16. An open Sales Order is the starting point for payment; the Sales Invoice is created when the user starts payment.
17. The existing Checkout page is the only payment experience.
18. There are no cron jobs, automatic renewals, or background purchases.
19. Website User access is restricted to verified facility membership.
20. Every self-onboarded Opt-In Request and Network contact carries an explicit token self-onboarding source.
21. Source attribution survives contact reconciliation, retries, signature completion, and future purchases.
22. Network resolution is a strict existence, activity, and relationship gate.
23. Network contacts and signatories come only from the resolved Network.
24. Network legacy Price Lists do not participate in token self-onboarding pricing.
25. One Network may contain normal KEPH/classification memberships and token-based memberships at the same time.
26. The membership’s pricing commitment and selected service catalogue determine the commercial path; Network identity and signatories remain shared.

## 9. Brownfield consistency review

The existing CRM and ERPNext integration provides the accounting foundation, but the portal must use a different commercial path from the existing Year 1–Year 5 flow.

| Existing capability | Decision for this token workflow |
|---|---|
| Network `price_lists_json` and legacy Price List override | Preserve for existing workflows. Do not use as the token catalog authority. |
| Network price configuration during token onboarding | Ignore for token pricing. Use the resolved Network for contacts, signatories, membership, and branding only. |
| KEPH-to-item mapping in `crm.api.optin` | Preserve for existing workflows. Do not invoke in token onboarding. |
| ERPNext `Item Price` lookup | Continue as the rate authority for items on the configured token catalogue Price List. |
| Native ERPNext `Quotation` | Use for the next billing period only. |
| Native ERPNext `Sales Order` | Create from the accepted token quotation/context. |
| Native ERPNext `Sales Invoice` | Create only when the authenticated facility user starts payment from an open Sales Order; use it as the payment authority with 30-day terms. |
| Existing Checkout page | Reuse for payment of open Sales Invoices. Do not create a second checkout. |
| Native VAT template and tax utilities | Use for every quotation and Sales Order. Store prices ex VAT and VAT separately. |
| Quote metadata and Price List history | Use for audit and accepted-price immutability. |
| Existing Opt-In contract/signature flow | Reuse without creating a second signature engine. |
| Existing Network signatory configuration | Apply every required signatory according to configured rules. |
| Registry/HFR response data | CRM uses the copied request shapes for identity, ownership, facility discovery, and eligibility. |
| Registry token pricing | None. Token catalogue metadata is new CRM configuration; future Lago evaluation is out of scope. |

The initial onboarding purchase must use this path:

```text
search enabled token service items in the configured Price List
  → resolve CRM package metadata
  → resolve ERPNext Item Price rows
  → create next-period Quotation per facility
  → create one Sales Order per facility
  → create Opt-In Request and Contract
```

Future portal purchases must use this path after an authenticated user confirms:

```text
select enabled token service item
  → resolve CRM package metadata
  → resolve ERPNext Item Price rows
  → create or resume Quotation
  → create or resume one facility Sales Order
  → user starts payment from the open Sales Order
  → create Sales Invoice with 30-day terms
  → open existing Checkout page
  → payment
```

The existing Year 1–Year 5 path must remain regression-tested separately.

### 9.1 Building-block audit

| Building block | Current brownfield position | Requirement for token self-onboarding |
|---|---|---|
| HFR search by facility ID | `crm.api.hfr.search_facility` and `get_facility_detail` support FID lookup for the existing authenticated CRM experience. | Add a separate guest-safe proxy flow. Bind every FID to the verified identity session and recheck ownership at finalization. |
| IDOR/BOLA prevention | Existing Opt-In endpoints protect invitation/signing-token contexts and the checkout protects invoices within an OIS session. | Add session-bound HFR ownership, facility selection, Partner resolution, token purchase, invoice, and portal authorization tests. |
| Enumeration prevention | Existing Opt-In and checkout flows use generic responses and rate limits in their own contexts. | Apply equivalent controls to identity, HFR, FID, Partner ID, package search, invoice, and purchase endpoints. |
| Opt-In process | Existing guest Opt-In, quotation, contract, OTP, and signatory workflows are reusable. | Add token self-onboarding provenance and pass the verified facility context into the existing process without forking signatures. |
| Token catalogue | ERPNext `Price List`, `Item`, and `Item Price` are available. CRM Settings currently has no complete token package catalogue. | Add one configured selling Price List with searchable service-item metadata and facility-friendly coverage descriptions. |
| Current checkout | The existing page and API support outstanding OIS invoices, Paystack, and bank-transfer reporting. | Reuse the existing Paystack integration and extend authorization for facility portal users. |
| Customer Experience portal | Public `/` now explains the facility-owner journey; `/facility-onboarding` is the welcome/wizard entry; `/cx-portal` is the authenticated facility-scoped shell. | Continue the downstream package purchase, open-invoice, payment, and support work. Keep `/portal` as a compatibility redirect only. |

The audit conclusion is that the accounting, Paystack, and signature foundations exist, while the identity-first HFR flow, token catalog, and portal purchase flow remain implementation work.

## 10. Technology and architecture

This section defines implementation choices separately from the product goal.

### 10.1 Frontend

Use the existing CRM Vue frontend for the public onboarding journey and authenticated facility portal.

The public information page is a standalone Frappe web page at `/`. The
onboarding and authenticated portal pages use thin Frappe wrappers around the
hashed Vite entries. The wrappers inject CSRF data and asset tags at request
time; they are not generated-file copies.

The authenticated customer-facing surface is named **Customer Experience** and is served at `/cx-portal`. The route name is implementation-facing; user-facing copy must say “Customer Experience”. Existing `/portal` links must redirect to `/cx-portal` during the transition.

The frontend displays package metadata and server-calculated values.

The frontend does not control identity, the catalogue Price List, Item Prices, VAT, signatory rules, or totals.

### 10.2 CRM backend

CRM owns the public API, onboarding session, package search, package eligibility, pricing context, Opt-In creation, future purchase orchestration, and portal authorization.

CRM exposes guest-whitelisted endpoints for unauthenticated steps.

CRM stores an opaque onboarding session reference.

CRM does not expose registry sessions, upstream tokens, or credentials.

### 10.3 CRM-owned registry adapter

`careverse_hq` is reference material only. CRM does not import it, call its Python
modules, or depend on its runtime. CRM owns the guest boundary, credentials,
session, OTP, response normalization, and OIS handoff.

The registry service account is configured once in the existing `CRM HFR
Settings` record used by CRM HFR search: HIE base URL, username, password, and
JWT expiry. Facility onboarding reuses those credentials. `CRM Opt-In Settings`
contains only onboarding-specific Client Registry and HFR owner/facility paths;
it does not maintain a second credential set.

The CRM adapter copies the approved upstream request shapes:

- Client Registry: `GET {base_url}/client-registry/fetch-client` with a JSON
  `payload` query parameter containing `identification_type` and
  `identification_number`.
- HFR owner lookup: `GET {base_url}{owner_path}` with
  `owner_id_number={identification_number}`.

The CRM adapter accepts the upstream `message.data.facilities`,
`message.facilities`, or top-level `facilities` variants and normalizes the
result to allow-listed facility fields. It retains raw upstream data only in
the encrypted server-side onboarding session.

CRM normalizes unknown identity, no-facility, upstream-error, and invalid
response cases to the same public failure response. Credentials, upstream
tokens, raw identity values, and registry sessions never reach the browser.

### 10.4 ERPNext accounting

Use native ERPNext records:

- `Price List`;
- `Item Price`;
- `Quotation`;
- `Sales Order`;
- `Sales Invoice`;
- `Sales Taxes and Charges Template`; and
- existing Checkout/payment records.

CRM owns workflow state, package metadata, package eligibility, identity binding, signatory orchestration, and pricing provenance.

CRM must not become a second accounting ledger.

The existing Checkout page remains the only payment interface.

### 10.5 Paystack payment integration

Paystack is the required payment provider for this customer journey.

The existing checkout page and Paystack API should be extended for authenticated facility portal purchases.

CRM must create a server-authorized Paystack payment session for one outstanding Sales Invoice.

The browser must never receive the Paystack secret key or decide the invoice amount.

Paystack webhook events must be signature-verified and idempotent.

Only verified Paystack payment events may update payment status or submit the related ERPNext Payment Entry.

The current Paystack implementation is the starting point. Its OIS-session authorization must be extended to support authenticated Website User and facility authorization.

### 10.6 Paystack dependency checklist

The existing integration depends on:

- `CRM Finance Settings.paystack_enabled`;
- `CRM Finance Settings.paystack_public_key`;
- `CRM Finance Settings.paystack_secret_key`;
- ERPNext `Mode of Payment = Paystack`;
- a configured ERPNext bank or clearing account for the Paystack mode of payment;
- Payment Entry fields for checkout provider, checkout reference, and Opt-In Submission;
- an outstanding submitted ERPNext Sales Invoice;
- the Paystack transaction initialize and verify API;
- the Paystack signed webhook endpoint; and
- the existing Vue `PaymentCheckout` page.

The current Python integration uses Frappe HTTP helpers. No separate Paystack Python or JavaScript SDK is currently required.

Deployment must configure the Paystack keys, enable the provider, confirm the KES currency behavior, expose the webhook over HTTPS, and register:

```text
https://<site>/api/method/crm.api.checkout.paystack_webhook
```

The webhook must receive the raw request body needed for HMAC-SHA512 signature verification.

The existing code verifies the Paystack transaction server-side, checks the invoice amount in minor units, creates an ERPNext Payment Entry, and prevents duplicate payment references. The portal extension must preserve these controls while replacing OIS-only authorization with facility-scoped Website User authorization.

## 11. Security requirements

All guest endpoints must be POST-only, rate-limited, and stateful.

Before OTP verification, responses must not reveal whether an identity, facility, Partner ID, or contact exists.

Facility details must be returned only after successful OTP verification.

Facility selection must be checked against the same verified onboarding session.

Network, Agent, Price List, package, Item Price, signatories, and totals must be re-resolved during finalization.

The browser must not submit authoritative rates, item codes, Price Lists, facility lists, Agent IDs, signatory identities, or VAT values.

The server must reject cross-Network contact, signatory, facility, and membership substitutions.

Guest sessions must have expiry, stage guards, OTP attempt limits, resend cooldowns, and replay protection.

Do not log raw identity numbers, OTPs, phone numbers, emails, or upstream payloads.

Portal endpoints must authorize by the logged-in Website User’s server-side facility membership.

A URL parameter such as `facility_id`, `submission_ref`, or `queue_id` is not authorization.

For Paystack, the server must verify invoice ownership, amount, currency, and status before creating a Checkout session. Webhook signatures, event IDs, invoice references, and payment references must be verified and deduplicated.

## 12. Data model requirements

### 12.1 Network and Partner ID

- `CRM Opt-In Network.partner_id`: unique six-digit public identifier.
- Blank on insert: CRM generates the identifier.
- Supplied on insert: CRM validates exact six-digit format and uniqueness.
- After insert: the identifier is immutable and cannot be reassigned.
- `CRM Opt-In Network.enabled`: strict gate for public onboarding resolution.
- The existing `CRM Partner` DocType remains outside this onboarding workflow.

### 12.2 Token package catalog

The CRM Settings catalog must support one global catalogue Price List and several service-item rows:

- one ERPNext selling Price List link;
- ERPNext service-item link;
- display name;
- description;
- token quantity;
- ex-VAT amount for display validation;
- currency;
- billing period;
- validity;
- coverage summary;
- coverage metrics;
- enabled status.

The catalogue is not tied to a Network. A Network can contain both normal KEPH/classification memberships and token memberships. The membership or Opt-In Request stores the pricing commitment and selected catalogue item; the Network identity, contacts, signatories, and facility relationships remain the same.

The ERPNext Price List and Item Price records remain the commercial authority.

The catalog must be searchable without requiring a Network link.

### 12.3 Opt-In submission snapshot

Store:

- onboarding source and channel;
- Network Partner ID and Network;
- derived Agent ID;
- Network source;
- catalogue Price List and selected service item;
- package code/item code and version;
- package description and coverage metadata;
- token quantity;
- quotation reference;
- Sales Order reference;
- Sales Invoice reference;
- invoice status;
- payment status;
- checkout reference where available;
- ex-VAT total;
- VAT total;
- gross total;
- billing period;
- signatory completion state;
- pricing configuration version;
- verified facility reference; and
- source onboarding session reference or hash.

The snapshot becomes immutable after acceptance or signature.

### 12.4 Self-onboarding provenance

The Opt-In Request must store:

- `onboarding_source = token_self_onboarding`;
- `onboarding_channel = public_portal`;
- Network Partner ID and Network;
- selected catalogue Price List, service item, and package version;
- verified facility reference;
- verified owner/contact reference;
- originating onboarding session reference or hash; and
- creation timestamp.

The Network contact created or linked by the journey must store or inherit:

- `contact_source = token_self_onboarding`;
- contact role;
- facility and Network relationship;
- Network Partner ID;
- source Opt-In Request;
- verified identity/contact binding reference; and
- creation or reconciliation timestamp.

Use the project’s final field names, but do not rely on free-text notes for provenance.

The source must be visible in CRM list views, filters, reports, API responses for authorized users, and audit history.

If an existing Contact is reconciled, preserve its original source and add a source relationship or provenance history. Do not overwrite unrelated contact origins.

Future token purchases must link to the existing self-onboarded facility and Opt-In Request. They must not create duplicate Opt-In Requests or Network contacts.

### 12.5 Portal purchase record

Future purchases require an idempotent purchase record linked to:

- Website User;
- facility and Network membership;
- token service item and package version;
- Quotation;
- Sales Order;
- Sales Invoice;
- invoice status;
- payment status; and
- existing Checkout reference.

The purchase record must prevent duplicate document creation when the user retries.

### 12.6 Customer Experience account

Store:

- Website User;
- verified identity hash;
- facility/network membership;
- account status; and
- invitation status.

Account and invitation status must be independent of Opt-In status.

### 12.7 Identification and reporting

CRM users must be able to identify token self-onboarding records without inspecting raw payloads.

Opt-In Request list views must support filters for:

- onboarding source;
- catalogue Price List/service item/package;
- Network Partner ID and Network;
- facility;
- request status;
- signatory status; and
- creation date.

Network contact list views must support filters for:

- contact source;
- contact role;
- facility;
- source Opt-In Request; and
- creation or reconciliation date.

The default display label should be `Token self-onboarding`.

This label is an attribution value, not a permission. Normal CRM permissions still apply.

## 13. Minimal API contract

Guest onboarding methods are CRM guest-whitelisted, POST-only, rate-limited, and return `{success, data, message}`. Portal purchase and invoice methods require an authenticated Website User and facility-scoped authorization.

| Method | Purpose |
|---|---|
| `crm.api.customer_experience.start` | Start identity verification, HFR discovery, and OTP delivery. |
| `crm.api.customer_experience.resend_otp` | Resend OTP after cooldown. |
| `crm.api.customer_experience.verify_otp` | Verify OTP and release safe facility results. |
| `crm.api.customer_experience.select_facilities` | Bind selected facilities to the verified session. |
| `crm.api.customer_experience.context` | Resolve the six-digit Partner ID or approved admin-preconfigured Network, strictly validate the Network, and return safe Network/contact/signatory context. |
| `crm.api.customer_experience.search_token_packages` | Return enabled, onboarding-approved service items from the configured catalogue Price List and CRM descriptions. |
| `crm.api.customer_experience.preview_token_purchase` | Resolve the selected service item, Item Price row, VAT, next-period totals, and pricing context. |
| `crm.api.customer_experience.finalize_optin` | Revalidate context, create the Quotation, Sales Order, Opt-In Request, pending Network membership, applicable Network contacts, and existing Contract. Persist `token_self_onboarding` provenance. |
| `crm.api.customer_experience.create_token_purchase` | For an authenticated user, create or resume a facility-specific Quotation and Sales Order for a confirmed package selection. |
| `crm.api.customer_experience.start_order_payment` | Confirm an authorized open Sales Order, create its Sales Invoice with 30-day terms, and return the existing Paystack Checkout route. |
| `crm.api.customer_experience.open_invoices` | Return open Sales Invoices scoped to the logged-in facility user. |
| `crm.api.customer_experience.checkout_reference` | Return the authorized route/reference for the existing Paystack Checkout page. |
| `crm.api.customer_experience.progress` | Return facility-scoped progress after Website User login. |
| `crm.api.customer_experience.chat` | Read or create facility-scoped support messages after login. |

The existing Checkout API must expose an equivalent authenticated Paystack operation:

| Checkout method | Purpose |
|---|---|
| `crm.api.checkout.initialize_paystack_payment` | Create an idempotent Paystack Checkout session for one authorized open Sales Invoice. |
| `crm.api.checkout.paystack_webhook` | Verify Paystack signatures and reconcile successful or failed payment events. |

### Token package search response

The response may include only enabled, onboarding-approved packages:

```json
{
  "success": true,
  "data": {
    "packages": [
      {
        "code": "TOK-100",
        "name": "100 Token Package",
        "description": "Designed for approximately 100 laboratory transactions.",
        "token_quantity": 100,
        "amount_ex_vat": 100000,
        "currency": "KES",
        "billing_period": "monthly",
        "coverage": [
          {"metric": "laboratory_transactions", "description": "Approximately 100 per month"}
        ]
      }
    ]
  }
}
```

### Purchase preview response

The response must include:

- selected package;
- package version;
- token quantity;
- coverage description;
- ex-VAT total;
- VAT total;
- gross total;
- currency;
- billing period;
- quotation validity; and
- an opaque pricing context reference.

The pricing context must be bound to the verified session, selected facilities, Network, package, Price List version, and configuration version.

Finalization must revalidate the context and fail closed when it is stale or changed.

### Network gate

Before `finalize_optin` creates any record, CRM must resolve and validate:

1. the supplied six-digit Partner ID, or the approved admin-preconfigured Network;
2. the linked Network’s existence and active status;
3. the Network’s configured contacts and signatory rules; and
4. the verified facility’s eligibility for that Network.

An unknown, inactive, missing, ambiguous, or mismatched Network must return a safe configuration error and create no Opt-In Request, contact, membership, Quotation, Sales Order, or Contract.

The final token rate must still come from the selected service item’s valid ERPNext Item Price row on the global token catalogue Price List. Network legacy pricing must not be consulted as a fallback.

Finalization must return safe provenance fields such as `onboarding_source`, `onboarding_channel`, and the Opt-In Request reference. Contact relationships remain server-side and are available through authorized CRM views. The response must not return raw identity values or upstream payloads.

### Portal purchase response requirements

`create_token_purchase` must return the native document references needed for the existing Checkout page, plus safe display fields:

- purchase reference;
- Quotation reference;
- Sales Order reference;
- Sales Invoice reference;
- amount ex VAT;
- VAT amount;
- gross amount;
- amount due;
- invoice status;
- payment status; and
- checkout route/reference.

`open_invoices` must return only invoices belonging to the logged-in user’s authorized facility membership.

The portal must allow the user to select an open invoice and continue to the existing Checkout page.

The Checkout page must use Paystack for this workflow. The Paystack session must be created server-side from the authorized invoice and must be single-invoice and idempotent.

## 14. Network signatory data and orchestration

The Network configuration must define:

- required signatories;
- signatory roles;
- signing order or parallel groups;
- approved delegation rules;
- reminder policy; and
- expiry behavior.

The finalization endpoint must resolve the applicable signatories from the Network configuration and existing Contract rules.

The client cannot submit or replace signatories.

The Contract must include every required facility and Network signatory.

The Opt-In Request and membership status must remain pending until all required signatures are complete.

## 15. Backfill requirement

Create an idempotent patch that:

1. Adds or backfills the canonical six-digit Partner ID on each Network.
2. Adds the approved preconfigured Network and membership/request status fields.
3. Adds token package catalog fields and submission snapshot fields.
4. Backfills existing relationships from an approved mapping.
5. Backfills submissions only where the Network relationship is unambiguous.
6. Derives Agent ID only from an approved rule or mapping.
7. Reports unresolved, duplicate, and conflicting records.
8. Never guesses a Partner ID or Agent ID from a slug.

Required input: `Partner ID → CRM Opt-In Network`.

## 16. Engineering stories

### E1 — Network identity model

Add Network-owned six-digit Partner ID generation, optional admin-supplied ID,
immutability validation, enabled-Network resolution, and an idempotent backfill
for existing Networks.

### E2 — Identity backfill

Implement the idempotent patch, dry-run report, approved mapping, and conflict handling.

### E3 — Secure CRM-owned registry adapter

Implement CRM guest endpoints and copy the approved Client Registry/HFR request
shapes into CRM. Do not import or call `careverse_hq`.

### E4 — Identity, HFR, and OTP orchestration

Implement stage guards, session expiry, OTP limits, facility binding, and safe responses.

### E5 — Network Partner ID resolution

Implement exact six-digit Partner ID lookup, admin-preconfigured Network
resolution, strict Network existence/activity checks, and resolved-Network
contact/signatory loading. Never fall back to a default Network or Network
Price List.

**Acceptance:** an invalid or mismatched Network creates no onboarding records, and a valid request uses only the resolved Network’s contacts and signatory configuration while pricing comes from the selected catalogue service item.

### E6 — Token catalogue configuration

Add the native Opt-In Settings section for one reusable token Price List, facility-friendly service-item descriptions, coverage metrics, Sales Order validity, and invoice terms. Do not create a second rate ledger or Network-specific token price configuration.

### E7 — Token service-item search

Implement safe search over enabled onboarding-approved service items from the configured Price List without exposing unrestricted ERPNext records.

### E8 — Token pricing preview

Resolve package metadata, Item Price rows, ex-VAT totals, VAT, gross totals, validity, and workload descriptions.

### E9 — Next-period quotation and Sales Order

Create a native ERPNext Quotation and Sales Order from one immutable pricing context.

### E10 — User-initiated invoice and Checkout

For an authenticated portal purchase, create the Sales Invoice, expose open-invoice status, and route the user to the existing Checkout page. Do not add cron jobs, automatic renewals, or a second payment experience.

### E11 — Signatory orchestration

Apply every required facility and Network signatory using the existing Contract rules and signature engine.

### E12 — Opt-In integration

Create the Opt-In Request, pending Network membership, existing Contract, and signature route.

### E13 — Website User and Customer Experience portal

Create or reconcile the Website User, create a `User Permission` with `allow = CRM Opt-In Submission` and `for_value = OIS number`, send the invitation, and build the facility-scoped Customer Experience portal at `/cx-portal` with package purchase, open invoices, payment status, and Checkout access.

All Website Users must be redirected to `/cx-portal` by default. The portal must resolve OIS records from the session-bound permission, never from a browser-supplied OIS query parameter. Users without an OIS permission see an unlinked account state. `/portal` is legacy compatibility only.

### E14 — Accounting and package governance

Define token item/account/tax treatment, package versioning, expiry, renewal, overage, and Price List governance.

### E15 — Security and regression tests

Test enumeration, replay, IDOR/BOLA, stale pricing, duplicate submissions, VAT, token package search, quotation/Sales Order/Invoice reconciliation, Checkout authorization, no-cron behavior, provenance, and all applicable signatories.

### E16 — Self-onboarding provenance and reporting

Add explicit source fields and relationships for token self-onboarded Opt-In Requests and Network contacts. Add CRM list filters, badges, reports, reconciliation history, and audit events.

**Acceptance:** CRM users can find every token self-onboarded request and contact by source, package, Network, facility, status, and date without inspecting free-text notes.

### E17 — Guest-safe HFR identity flow

Implement the CRM-owned identity verification, HFR ownership lookup by ID, OTP,
facility selection, and final ownership revalidation. Keep raw identity values,
upstream tokens, and credentials server-side; `careverse_hq` remains reference
only.

**Acceptance:** a FID returned in one verified session cannot be selected from another session, and invalid identities or FIDs do not create distinguishable enumeration responses.

### E18 — Token catalog in CRM Settings

Add searchable token package metadata linked to the one reusable ERPNext selling Price List. Validate enabled status, sellability, Item Price availability, VAT, currency, coverage description, and version before publication.

**Acceptance:** package search returns only onboarding-approved packages and never exposes unrestricted ERPNext pricing records.

### E19 — Authenticated portal purchase flow

Build the Website User flow for package selection, server-side pricing preview, Quotation, Sales Order, Sales Invoice, open-invoice display, and payment status.

**Acceptance:** one intentional purchase creates one document chain and can be resumed safely after refresh or retry.

### E20 — Paystack Checkout integration

Extend the existing Paystack checkout path for authenticated portal purchases. Create Paystack Checkout sessions from authorized open Sales Invoices and reconcile payment through a signed, idempotent webhook.

**Acceptance:** the user can pay only an invoice belonging to their facility, the client cannot alter the amount, and repeated Paystack events do not create duplicate Payment Entries.

### E21 — Paystack deployment and dependency validation

Validate Finance Settings, Paystack keys, Mode of Payment, clearing account, KES minor-unit handling, HTTPS webhook delivery, raw-body signature verification, and legacy OIS checkout compatibility.

**Acceptance:** a configured test transaction can be initialized, verified, reconciled to one ERPNext Payment Entry, and safely replayed without duplication.

## 17. Active sprint — onboarding invitation and Customer Experience progress

**Sprint objective:** complete the post-Opt-In handoff. Every completed OIS must
produce a least-privilege Website User invitation, a permission-bound
`/cx-portal` experience, and a customer-safe progress view for each facility.

The existing `CRM Facility Membership.go_live` field is the authoritative
GoLive field for a Network Contact. It must be projected into portal progress
as `network_contact.go_live` and as the final GoLive milestone. Do not add a
second GoLive field to the generic `CRM Contacts` table.

### Sprint dependency order

| Order | Story | Depends on | Sprint result |
|---|---|---|---|
| 1 | E11/E12 — contract and Opt-In completion | Existing signature engine, OIS, membership records | A canonical processed OIS and Network membership exist. |
| 2 | ONB-1 — Website User invitation | Processed OIS and facility signatory email | Website User and `User Permission(allow=CRM Opt-In Submission, for_value=OIS)` are created idempotently. |
| 3 | ONB-2 — progress projection | OIS permission, OIS snapshot, Contract Signatory rows, Facility Membership | Portal receives contract, signature, membership, Network Contact, and GoLive progress without raw document access. |
| 4 | ONB-3 — Customer Experience UI | ONB-2 response contract | `/cx-portal` renders next action, milestones, facilities, and GoLive state. |
| 5 | ONB-4 — regression and security QA | ONB-1 through ONB-3 | No OIS enumeration, permission bypass, cross-facility leakage, duplicate user, or duplicate permission. |

### Sprint story acceptance criteria

**ONB-1 — Website User invitation.** When an OIS reaches `Processed`, create or
reconcile one enabled Website User for the facility signatory email, create
one OIS User Permission, and send the native welcome invitation. Reprocessing
the OIS must not duplicate either record. Internal-user email collisions and
disabled Website Users are blocked and visible to CRM staff.

**ONB-2 — Progress projection.** Resolve only OIS records granted to the
session user. Return an allow-listed projection of contract/signature status,
facility membership, Network Contact source, and `network_contact.go_live`.
Never accept an OIS query parameter as an authorization input.

**ONB-3 — Customer Experience UI.** Render the authenticated user’s linked
OIS records at `/cx-portal`, show an unlinked state when there is no permission,
show one progress card per facility, and make the GoLive milestone explicit.
GoLive is read-only for the facility owner.

**ONB-4 — regression and security QA.** Prove OIS permission isolation,
stale-permission handling, multi-facility isolation, invitation idempotency,
generic login routing, and correct GoLive projection from the Network Contact
membership record.

### Explicit handoff rules

- Website Users always land on `/cx-portal`; `/portal` is only a compatibility
  alias.
- The browser never supplies an OIS number for authorization. The server reads
  OIS numbers only from the logged-in user’s User Permissions.
- A processed OIS can have multiple facilities. Each facility gets its own
  Network Contact projection and its own GoLive state.
- `CRM Facility Membership.status` describes Network membership. Its
  `go_live` flag describes implementation readiness and is not inferred from
  signature completion.
- The facility may see GoLive progress but cannot set or edit it. CRM
  implementation staff use the existing guarded `set_facility_go_live` action.
- The invitation is created after the OIS is processed. Account creation is
  idempotent; an existing Website User is linked rather than duplicated. An
  existing internal User with the same email is blocked and reported for
  manual reconciliation.

### Deferred dependencies

Token package purchase, quotation/order/invoice creation, Paystack checkout,
chat, and CareVerse auto-provisioning remain downstream stories. They consume
the same permission-bound portal context but do not block the invitation and
progress-tracking sprint.

## 18. Design stories

### D1 — Landing page

Implemented for the stabilization pass at `/`. The page now presents the
Customer Experience value proposition, facility-owner capabilities, six-step
onboarding journey, required information, post-onboarding expectations, trust
and security commitments, **Start facility onboarding**, **Already have access?
Sign in**, and secondary **Staff access**. Detailed package coverage and
calculated pricing remain in the onboarding and authenticated portal flows.

### D2 — Identity and facility verification

Design identity, OTP, loading, retry, generic error, facility selection, and session expiry states.

### D3 — Network Partner ID resolution

Design six-digit Partner ID entry, admin-preconfigured Network explanation,
resolved Network confirmation, and configuration errors.

### D4 — Token package search

Design search, package cards, descriptions, token quantity, coverage examples, ex-VAT price, VAT, validity, and selection.

### D5 — Quotation and Sales Order review

Design next-period ex-VAT amount, separate VAT, gross total, billing period, package coverage, confirmation, invoice creation, open-invoice state, and the handoff to the existing Checkout page.

### D6 — Signatory progress

Design facility and Network approval steps, pending signatures, reminders, completed signatures, and exception states.

### D7 — Customer Experience portal and support

Design the `/cx-portal` invitation handoff, login, progress timeline, implementation states, package purchase, open-invoice payment entry, and facility-scoped chat. Use “Customer Experience” in the interface; keep “portal” as an implementation term.

### D8 — Accessibility and responsive behavior

Define keyboard flow, focus states, screen-reader content, validation, mobile layouts, and plain-language copy.

### D9 — Provenance visibility

Design the `Token self-onboarding` badge, source details, package, Network, facility, contact role, request status, and signature status in CRM list and detail views.

### D10 — End-to-end customer experience

Design the complete progression from public trust and identity verification to package selection, quotation, Sales Order, invoice, Paystack Checkout, payment confirmation, Opt-In signatures, onboarding progress, token balance or entitlement status, open invoices, support chat, and repeat purchase.

The experience must preserve context between steps, explain what happens next, and provide recovery for expired sessions, failed payments, incomplete signatures, duplicate clicks, and support escalation.

## 19. Decisions required

1. Is the billing period always one month, or may packages use another next-period duration?
2. Is the package Price List itself the quote line, or does it select a configured token item or service-item set?
3. Which income, tax, deferred-revenue, and stock/service accounts apply to token sales?
4. Are tokens a monetary balance, a service entitlement, or both?
5. Do tokens expire, roll over, refund, renew, or support top-ups?
6. How are overages priced?
7. Are coverage descriptions estimates or contractual limits?
8. Which package metadata belongs in CRM Settings, and which belongs in ERPNext Item/Price List fields?
9. May a Network restrict the global token catalog, or are all enabled packages always available?
10. What is the authoritative Partner ID backfill mapping?
11. What separate Agent ID mapping is required by downstream systems?
12. Which Network signatory rules apply to each Contract type?
13. At which user action is the Sales Invoice created: purchase confirmation, order acceptance, or Checkout start?
14. What exact existing Checkout route and payment reference does CRM consume?
15. Which invoice statuses are visible to the facility user?
16. Are partial payments, failed payments, refunds, and credit notes supported in the portal?
17. Which registry identity and HFR paths are approved for the CRM-owned adapter, and what upstream response variants must be normalized?
18. What is the Paystack account, webhook endpoint, checkout mode, currency, clearing account, and refund policy for this workflow?
19. Does the existing Paystack checkout remain active for legacy OIS invoices while portal authorization is extended?
20. Which token entitlement or balance record is updated after a successful payment?

## 20. Definition of done

### 20.1 Stabilization increment acceptance

The public and authenticated entry-point increment is complete when:

- a new facility owner can understand Customer Experience and its value from `/`;
- `/facility-onboarding` opens directly on the welcome screen before requesting
  identity information;
- existing owners have a clearly labelled Customer Experience sign-in path;
- unauthenticated `/cx-portal` requests redirect to the correct sign-in target;
- no facility-owner-facing copy calls the product CRM or exposes internal
  workspace terminology;
- the hashed onboarding and portal entries are published by the frontend build;
- the route, asset, link, frontend-unit, and focused Frappe checks pass.

The feature is complete when an owner can verify identity, receive and verify an OTP, select an owned facility, resolve a Network by six-digit Partner ID or approved admin preconfiguration, search and select an enabled catalogue service item, review an ex-VAT next-period quotation with separate VAT and coverage information, accept it, and receive the corresponding facility-specific Sales Order.

The owner must then complete the Opt-In Request and every applicable facility and Network signature.

After signature, the facility must be fully `Opted In`, visible in the correct Network, invited as a Website User, and able to access Customer Experience with read-only progress and purchase/payment actions.

From the portal, the user must be able to intentionally select another token package, create or resume a facility-specific Quotation and Sales Order, start payment from the open Sales Order, create the Sales Invoice with 30-day terms, view the open invoice, and pay through the existing Checkout page. No cron job or automatic purchase may be required.

CRM users must be able to identify every Opt-In Request and Network Contact created or linked through token self-onboarding using an explicit source, package, Network, facility, status, and date.

The HFR flow must be guest-safe, session-bound, non-enumerating, and protected against IDOR/BOLA.

An unknown or mismatched Network ID must fail before any Opt-In, contact, membership, quotation, order, or contract record is created.

From the customer portal, the user must be able to select a package, find the facility-specific open Sales Order, start payment, receive the Sales Invoice with 30-day terms, view the open invoice, and pay through the existing Checkout page using Paystack.

Existing KEPH/year-plan workflows must remain regression-tested separately. Token quotation, Sales Order, invoice, VAT, Paystack, signatory, provenance, security, and portal behavior must be covered by automated tests.
