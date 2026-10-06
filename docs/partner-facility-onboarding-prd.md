# PRD — Facility Self-Onboarding and Customer Experience

**Product:** tiberbu Express
**Implementation system:** CRM (`crm`) with CareVerse HQ integration

> **Scope decision:** Partner Portal and partner workspace delivery are
> descoped. Customer Experience is the only external authenticated surface.
> The Partner ID is a public identifier owned by `CRM Opt-In Network`; it is
> not a Partner Portal account or authorization token.

**Status:** Draft for product, UX, CRM, Careverse HQ, and Customer Experience handoff
**Version:** 0.1
**Date:** 2026-09-28
**System boundary:** `crm` + `careverse_hq` + public facility onboarding + Customer Experience

## 1. Product decision

Build a facility self-onboarding journey and one authenticated Customer
Experience surface that share the CRM design language and end in one canonical
commercial transaction: the existing Opt-In flow.

There are two supported entry contexts:

1. An admin sends a facility owner an invitation or a link with a
   preconfigured Network context.
2. A facility owner reads the public onboarding guide, starts the wizard,
   verifies their identity and HFR ownership, and enters the six-digit Partner
   ID belonging to the intended Opt-In Network.

The routes must converge before pricing and Opt-In. The facility is not added
to a Network by a free-form public write, and the portal does not create a
second quote, contract, or membership engine.

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

Success means:

- A facility owner can understand the process without support intervention.
- A verified owner can select only facilities returned by HFR for their
  identity.
- A six-digit Partner ID resolves to exactly one enabled Opt-In Network.
- Every facility request has an auditable Network, HFR identity,
  correlation ID, and onboarding status.
- The facility reaches the existing Opt-In pricing, terms, signature, and
  asynchronous submission flow without re-entering known information.
- The facility can later view read-only onboarding and implementation progress,
  receive email updates, and use a bounded chat capability.

## 3. Non-negotiable invariants

1. **Opt-In is the terminal action.** All successful facility onboarding paths
   terminate in the canonical CRM Opt-In submission. A case
   can be pending, rejected, or abandoned before Opt-In, but there is no
   alternate completion state.
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
| Facility owner | Join the correct Network with confidence | Read guide; verify identity/ownership; enter Partner ID; complete Opt-In; read progress; chat | Choose a facility they do not own, alter HFR facts, or access another facility |
| Support/Implementation | Resolve exceptions and help the customer | Read case timeline; respond in chat; retry safe steps | Impersonate a facility owner or disclose internal notes |

## 5. Canonical customer journey

### 5.1 Facility self-onboarding

```text
Public guide
  → identity details
  → Client Registry identity verification
  → HFR ownership verification
  → select eligible facility/facilities
  → Partner ID lookup
  → confirm Network
  → contact confirmation and OTP
  → facility onboarding case / CRM invitation
  → existing Opt-In wizard
  → five-year pricing + terms + signature
  → async submission
  → Network membership + Network menu visibility
  → email + read-only Customer Experience progress
```

The current Careverse implementation maps to:

- `careverse_hq.api.public_facility_login_onboarding.verify_onboarding_identity`
  — identity lookup through the Client Registry/HIE.
- `verify_onboarding_ownership` — HFR owner lookup via
  `facility_admin_registration._check_hfr_facility_ownership`.
- `send_onboarding_otp` and `verify_public_onboarding_otp` — contact proof.
- `submit_public_onboarding` — idempotent queued facility onboarding and user
  provisioning path.

The Network Partner ID binding and CRM Opt-In handoff are the missing product
steps. The public UI should preserve the existing independently auditable stage
model rather than collapsing it into one opaque request.

### 5.2 Admin-issued invitation

```text
CRM admin Network configuration
  → select Network and its Partner ID
  → create/send invitation for facility owner
  → secure expiring link / email
  → facility owner completes identity + HFR verification
  → invitation-bound Network is confirmed
  → existing Opt-In wizard
  → Network membership + Customer Experience access
```

The invitation may preconfigure the Network and Partner ID, but the server
must resolve and revalidate both. A facility owner must not be able to edit an
invitation into a different Network without restarting through the public
Partner ID route.

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

### FR-4 — Opt-In handoff

- The facility onboarding case passes verified identity, selected facility,
  Network, contact, and source metadata into the existing Opt-In
  wizard.
- The wizard uses the Network’s configured Year 1–Year 5 price lists and the
  same pricing, terms, witness/signatory, and submit pipeline as current CRM
  Opt-In.
- Facility and Network cannot be changed after pricing is loaded without
  invalidating the preview and restarting the handoff.
- A successful submission creates the normal CRM Opt-In Submission and downstream
  records, then marks the facility membership `Opted In` / ready for the
  existing implementation rules.

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
3. A verified facility case reaches the existing Opt-In wizard with facility,
   Network, contact, and five-year pricing context intact.
4. Opt-In submission is idempotent and produces normal CRM submission/membership
   records; the facility appears in the Network menu only at the defined
   post-submit state.
5. Email and the authenticated Customer Experience view expose the current
   case and implementation progress with no cross-Network leakage.
6. The Customer Experience team can build against the API, state machine, component map,
   and error semantics without reading internal Frappe documents.

## 11. Delivery slices

| Slice | Outcome |
|---|---|
| A | Network creation, six-digit Partner ID generation/override, and public lookup |
| B | Public wizard shell and HFR/identity session integration |
| C | Facility onboarding case and CRM/Careverse handoff |
| D | Opt-In prefill and five-year pricing preflight |
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
  menu: recommended default is after successful Opt-In submission, with
  `Opted In` visible to CRM before implementation is complete.
- Confirm whether one owner may select multiple HFR facilities in one Opt-In
  submission or whether each facility gets its own case/submission.
- Confirm Customer Experience authentication policy: passwordless email link is the
  recommended MVP; OTP-only login is an acceptable fallback.
- Confirm chat retention, support ownership, and escalation SLA.
