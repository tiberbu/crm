# PRD — Facility Self-Onboarding and Customer Experience

**Customer-facing product:** Tiberbu Customer Experience (also: Tiberbu HMIS Customer Experience Portal)
**Implementation system:** Frappe app in `apps/crm` with CareVerse HQ integration; `crm` is an implementation name, not customer-facing product language

> **Scope decision:** Partner Portal and partner workspace delivery are
> descoped. Customer Experience is the only external authenticated surface.
> The Partner ID is a public identifier owned by `CRM Opt-In Network`; it is
> not a Partner Portal account or authorization token.

**Status:** Workflow decision updated; remaining delivery details are historical proposal
**Version:** 0.1
**Date:** 2026-10-22
**System boundary:** `crm` + `careverse_hq` + public facility onboarding + Customer Experience

## 1. Product decision

Customer Experience supports two separate facility journeys. Self-Onboarding
is the primary public route and requires no invitation. Network Opt-In is an
invitation-only route for a facility that has already been added to a Network.
The homepage gives Self-Onboarding the primary action and keeps an Opt-In link
as a secondary way to find the invitation journey.

**Self-Onboarding has no signatures.** The owner verifies identity and contact,
chooses eligible facilities and token packages, reviews the quote and Terms,
accepts the Terms, and submits a request. There are no signatory or witness
fields, contract-signing actions, or signature progress in this route. Terms
acceptance is not a signature.

The secure Network email link is the preferred entry to Network Opt-In because
it carries invitation context. That separate journey retains its quotation,
agreement, signatory, witness, and signature steps. The routes do not converge
into a single wizard.

## 2. Problem and outcomes

Today, the pieces exist in separate products:

- CRM has `CRM Opt-In Network`, `CRM Facility Membership`, the
  Opt-In wizard, and multi-year pricing configuration.
- `careverse_hq` has public identity verification, Client Registry lookup,
  HFR facility-owner lookup, OTP, and queued facility onboarding.
- The Network-owned six-digit Partner ID and safe cross-app binding from a
  verified facility owner to an Opt-In Network are being completed.
- The current public Careverse account path provisions a facility-facing user,
  but it is not yet the requested minimalist, read-only journey portal.

Self-Onboarding succeeds when:

- A facility owner can understand the process without support intervention.
- A verified owner can select only facilities returned by HFR for their
  identity.
- A six-digit Partner ID resolves to exactly one enabled Opt-In Network.
- Every facility request has an auditable Network, HFR identity,
  correlation ID, and onboarding status.
- The owner can review configured packages, VAT, totals, and Terms before
  submitting without a signing step.
- The owner can later use Customer Experience to review the available quote
  and next action for each facility.

Network Opt-In succeeds when an eligible invited facility can review its
quotation and agreement and complete the existing signatory and signature
process independently of Self-Onboarding.

## 3. Non-negotiable invariants

1. **The routes stay distinct.** A public Self-Onboarding request does not
   become a Network Opt-In or enter its signing flow. Network Opt-In requires
   Network eligibility and an invitation.
2. **HFR is authoritative for ownership eligibility.** The public UI may only
   select facilities returned by the Careverse HFR ownership check for the
   verified identity.
3. **Partner ID is a Network-owned public lookup key, not an authorization
   token.** It resolves to exactly one enabled Network; authorization is still
   enforced server-side on the onboarding case and membership.
4. **Network is the tenancy boundary.** Membership, pricing, Opt-In,
   portal visibility, and future events are Network-scoped.
5. **Pricing is configuration, not client input.** Price lists are resolved
   from the Network configuration. The browser can show
   a preview but cannot choose a price list or rate.
6. **Portal access is least privilege.** The facility portal is read-only for
   CRM and Careverse records, except for chat messages and explicitly scoped
   document requests in a later phase.
7. **No raw PII in public responses or logs.** ID numbers, OTPs, unmasked
   contact data, and HFR payloads remain server-side or encrypted at rest.

## 4. Users and responsibilities

| Actor | Needs | Can do | Cannot do |
|---|---|---|---|
| CRM Sales/Manager | Configure Networks, invitations, pricing, and review queues | Create a Network; accept or provide its six-digit Partner ID; invite facility owners; review exceptions; manage pricing | Bypass audit or silently alter a submitted Opt-In |
| Facility owner | Choose the right route and understand each next step | Verify identity/ownership; choose facilities/packages; accept Self-Onboarding Terms and submit, or use an eligible Network invitation; read progress | Choose a facility they do not own, alter HFR facts, or access another facility |
| Support/Implementation | Resolve exceptions and help the customer | Read case timeline; respond in chat; retry safe steps | Impersonate a facility owner or disclose internal notes |

## 5. Canonical customer journey

### 5.1 Facility self-onboarding

```text
Public home: primary “Start Self-Onboarding” action
  → identity details and registered-contact OTP
  → eligible facilities returned for the verified identity
  → Network selection and configured token package(s)
  → review prices, VAT, totals, and Terms
  → accept Terms and submit request (no signature step)
  → Customer Experience quote and next action when available
```

The current CRM implementation maps to:

- `crm.api.facility_onboarding.start_identity`, `verify_otp`, and facility
  lookup — identity, contact, and registry checks.
- `get_catalog` — configured Network and package catalogue.
- `get_self_onboarding_terms` and `submit_onboarding` — Terms snapshot,
  acceptance, and request submission.
- Submission creates facility/customer enrollment records and an initial quote
  when the required commercial configuration is available.

The current public route submits a Self-Onboarding request directly after the
owner accepts the Terms. It does not hand off to Network Opt-In. The invitation
route remains a separate CRM Opt-In journey.

### 5.2 Invitation-only Network Opt-In

```text
Facility is added to a Network and invited
  → secure Opt-In link in the invitation email
  → verify invitation/contact eligibility
  → review Network quotation and agreement
  → provide requested signatory/witness details
  → complete applicable signature steps
  → Opt-In progress in Customer Experience
```

The Opt-In entry on the website helps invited facilities find the journey. The
server must still confirm eligibility for that Network. The invitation email
link remains the preferred route and preserves its secure context.

## 6. Functional requirements

### FR-1 — Network Partner ID generation and administration

CRM must provide a manager-only Network form and list for the public Partner
ID.

Required behavior:

- `partner_id` is exactly six digits, unique, safe to share publicly, and
  generated on Network insert when the admin leaves it blank.
- An admin may provide the six-digit value on Network creation.
- The value is immutable after creation and is never reassigned.
- Public lookup returns only an enabled Network.
- Public lookup returns Network display name, logo/brand, onboarding copy, and safe
  contact details; it does not return CRM document names, internal owners,
  rates, or credentials.
- CRUD changes are audited and invalidate any cached public lookup.

### FR-2 — Identity and HFR verification

- The wizard accepts the configured identification type and number.
- Identity is checked through the existing Careverse Client Registry/HIE
  adapter.
- HFR ownership is checked only after identity verification and returns the
  facility rows associated with the owner ID.
- The user can select eligible facilities returned by HFR; already onboarded,
  public/ineligible, ambiguous, or failed matches are explained separately.
- Upstream errors distinguish “not found,” “temporarily unavailable,” and
  “needs support” without exposing technical payloads.
- The session is short-lived, stage-guarded, rate-limited, and resumable only
  through a secure server-issued reference.

### FR-3 — Network binding by Partner ID

- A facility owner enters or follows a Partner ID.
- CRM validates the Partner ID and returns a branded Network confirmation card:
  Network name, logo, and safe contact/support copy.
- The owner must explicitly confirm before the case is created.
- The server stores the resolved Network, source (`public` or
  `invitation`), and correlation ID.
- The facility owner can report an incorrect Partner ID; this creates an
  exception, not a membership.

### FR-4 — Keep invitation-only Network Opt-In separate

- A facility already added to a Network may enter Network Opt-In through its
  secure invitation email link. The public Opt-In entry may help the recipient
  find that route, but eligibility remains server-checked.
- The existing Network Opt-In process retains its quotation, agreement,
  signatory, witness, and signature requirements.
- Public Self-Onboarding submits its own request after Terms acceptance. It
  does not hand off into, create, or wait for a Network Opt-In signature.
- Changing the Network or facility in either journey invalidates that journey's
  current review state and requires a fresh server-side validation.

### FR-5 — Authenticated Customer Experience

- After a verified case reaches the agreed provisioning point, create or link
  a guest facility owner account using the verified contact email.
- Login is passwordless or invite-based in MVP; email remains the canonical
  delivery channel.
- Customer Experience shows only the owner’s facility/case(s) and their Network.
- The dashboard exposes progress, next action, last update, expected owner,
  documents/email history, and a chat thread.
- The dashboard never exposes internal CRM comments, other facilities, raw
  HFR responses, pricing-edit controls, or payment administration.
- If the owner never logs in, the same milestones are sent by email.

### FR-6 — Five-year pricing

- Every Opt-In Network has configured Year 1, Year 2, Year 3, Year 4, and
  Year 5 price-list assignments before it can be published.
- Pricing preview shows year, plan/service, currency, effective date, and
  estimated total with the same semantics as the CRM Opt-In wizard.
- The effective configuration is resolved server-side and versioned in the
  Opt-In submission payload.
- Missing or incomplete year configuration blocks publication or gives CRM a
  clear preflight error; it must not silently fall back to a different Network.

## 7. Proposed data model changes

### CRM — extend `CRM Opt-In Network`

| Field | Type | Rule |
|---|---|---|
| `partner_id` | Data | Exactly six digits; generated on insert when blank; unique and immutable |
| `enabled` | Check | Controls whether the Network may receive new onboarding requests |
| `display_name` | Data | Safe public Network label |
| `custom_header_copy` | Text | Public onboarding copy |
| `contact_email` | Data/Email | Safe Network support contact |
| `logo_url` | Attach Image | Optional Network logo |

The existing `CRM Partner` DocType remains available for unrelated CRM and
finance workflows. It is not part of facility self-onboarding, does not own
the Partner ID, and does not receive a portal account.

### New CRM DocType — `CRM Facility Onboarding Case`

This is the cross-app handoff aggregate, not a second membership model.

| Field group | Contents |
|---|---|
| Identity | case ID, source, correlation ID, verified identity hash, masked identity metadata |
| Network binding | Partner ID snapshot, Network, invitation reference |
| Facility | HFR facility ID/code, facility name snapshot, selected facility, CRM facility/membership links |
| Contact | verified email/phone references, owner display name |
| State | initiated, identity_verified, facilities_found, partner_confirmed, otp_verified, optin_pending, opted_in, implementation, live, rejected, expired |
| Commercial | price configuration version, Opt-In Submission, primary quote/contract links |
| Portal | user, last login, notification preference, chat thread reference |
| Audit | created/submitted/updated timestamps, actor, reason codes, safe event log |

The case owns orchestration state. `CRM Facility Membership` remains the
Network relationship, and `CRM Opt-In Submission` remains the commercial
acceptance record.

### Careverse — reuse and extend

Reuse the Redis-backed public onboarding session and the existing
`Facility Onboarding Queue` for Careverse facility creation. Add a safe
outbound handoff/adaptor that sends the verified case context to CRM after
Network confirmation. Do not make Careverse the source of Network,
price, or Opt-In truth.

## 8. UX requirements

- Lead with a calm explanation: “We’ll verify who you are, confirm the
  facilities you manage, then connect you to the right Network.”
- Show one primary action per step and a persistent “What you’ll need” panel.
- Preserve entered values and show a resumable reference after every remote
  call.
- Use plain-language statuses; keep technical reason codes in support details.
- Make HFR data feel trustworthy: show “Verified from the Health Facility
  Registry” beside the facility facts, and allow the owner to report a mismatch.
- Require explicit confirmation before Partner binding and before Opt-In commit.
- Do not surprise the user with an account. Explain that a read-only Customer
  Experience account
  will be created and that email updates are always available.
- Mobile-first layout, keyboard navigation, visible focus, labelled inputs,
  44px minimum targets, and WCAG AA contrast.
- The component map defines the visual grammar and responsive states.

## 9. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | Guest endpoints rate-limited; short-lived sessions; OTP attempt limits; no client-trusted Network/facility IDs |
| Privacy | Encrypt persisted PII; mask identity/contact data; retention and deletion policy required before production |
| Reliability | HFR and CRM handoffs idempotent; async jobs retry safely; duplicate submit returns existing case/result |
| Performance | Initial public guide fast and cacheable; partner lookup < 500ms at CRM edge when warm; remote HFR states shown honestly |
| Observability | Correlation ID across browser, CRM, Careverse, HFR, email, and queue; redacted structured events |
| Accessibility | WCAG 2.2 AA target; screen-reader step/status announcements; no color-only status |
| Localization | All customer copy translatable; dates/currency formatted by locale with KES default |

## 10. MVP acceptance criteria

1. CRM manager can create an Opt-In Network; the system generates a unique
   six-digit Partner ID unless the manager supplies one.
2. Public guide can verify identity, validate HFR ownership, accept a Partner
   ID, and display the correct Network confirmation.
3. A verified public Self-Onboarding case shows its configured package and
   Terms; after Terms acceptance, request submission succeeds without creating
   an Opt-In Submission, Contract, or signature task.
4. An eligible facility already added to a Network can independently follow
   its secure invitation email link into the existing Network Opt-In journey
   and complete that journey's quotation, agreement, and required signatures.
5. Email and the authenticated Customer Experience view expose each route's
   own current progress with no cross-Network leakage or signature status on
   Self-Onboarding requests.
6. The Customer Experience team can build against the API, state machine, component map,
   and error semantics without reading internal Frappe documents.

## 11. Delivery slices

| Slice | Outcome |
|---|---|
| A | Network creation, six-digit Partner ID generation/override, and public lookup |
| B | Public wizard shell and HFR/identity session integration |
| C | Facility onboarding case and CRM/Careverse handoff |
| D | Invitation-only Opt-In entry and eligibility; public Self-Onboarding remains separate |
| E | Membership/Network menu reconciliation and Customer Experience read model |
| F | Customer Experience chat, email journeys, analytics, and hardening |

### Active sprint dependency slice

The first implementation sprint is narrower than the full commercial roadmap:

```text
Existing Opt-In + Contract
        ↓
Website User + OIS User Permission + invitation
        ↓
OIS-scoped progress projection
        ↓
Vue Customer Experience
        ↓
GoLive milestone from CRM Facility Membership
```

Customer Experience must not expose progress until the session resolves at least one
OIS through User Permission. A user can be authenticated and still see an
unlinked state while CRM reconciles the account. Package purchase, Paystack,
chat, and deployment-tool progress are follow-on capabilities on this same
Customer Experience context.

## 12. Decisions required before implementation

- Confirm whether Partner ID is printed/published as a human code, QR code,
  or both. QR can carry the same immutable code; it must not become a second
  identity system.
- Confirm the exact CRM status that makes a facility appear in the Network
  menu for invitation-only Network Opt-In. Keep it separate from public
  Self-Onboarding request progress.
- Confirm whether one owner may select multiple HFR facilities in one
  Self-Onboarding request or whether each facility gets its own case/request.
- Confirm Customer Experience authentication policy: passwordless email link is the
  recommended MVP; OTP-only login is an acceptable fallback.
- Confirm chat retention, support ownership, and escalation SLA.
