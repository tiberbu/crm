# Opt-In Executive Journey and Signatory Handoff

**Status:** Draft for implementation

**Date:** 2026-09-03

**Scope:** The public Opt-In wizard, Opt-In Submission (OIS) notifications,
contract signing, and the internal CRM review view.

**Companion documents:**

- [Multi-year Opt-In quoting and quarterly billing](./optin-multi-year-billing.md)
- [Opt-In signatory defaults](./tiberbu-crm-optin-signatories.md)

---

## 1. Product outcome

A hospital executive must be able to understand a multi-facility commitment in
seconds. An ICT or support colleague must be able to complete an Opt-In without
being incorrectly represented as the person who can legally sign the agreement.

The experience has two equally important outcomes:

1. make the commercial decision clear: scope, term, total commitment, Year 1
   cashflow, then facility detail; and
2. make the authority hand-off explicit, secure, and visible to both the
   submitter and the CRM team.

This is a clarification of the existing one-contract Opt-In flow. It does not
decide whether multi-facility agreements should be one master agreement or
separate facility agreements; that legal-product decision remains a release
gate for the five-facility contract presentation.

## 2. Design principles

### Simplicity and hierarchy

Every executive-facing page must present information in this order:

1. **Scope** — number of facilities and KEPH mix.
2. **Decision** — selected contract term and total contract commitment,
   inclusive of VAT.
3. **Near-term cashflow** — Year 1 amount and quarterly billing cadence.
4. **Detail on demand** — each facility's contract schedule, optional services,
   and full legal text.
5. **Next action** — who must act next and when.

There must be one dominant total per screen: the total for the selected term.
Monthly, annual, and individual facility figures are supporting information and
must not compete visually with it.

### Authority belongs to the right person

The verified wizard user is the **submitter**. They are a **signatory** only
when they explicitly confirm that they are authorised to sign. A nominated
signatory accepts the agreement in the secure signing portal; the submitter
does not accept it on that person's behalf.

### One consistent communication per person

The submitter receives an OIS acknowledgement. The signatory receives a
signing package containing the same commercial summary and their unique signing
link. When the submitter and signatory are the same person, they receive one
combined message rather than two overlapping emails.

## 3. UX audit issues to resolve

| ID | Finding | Impact | Priority |
| --- | --- | --- | --- |
| UX-01 | The contract identifies the first facility as an individual facility while its schedule can contain several facilities. | The agreement scope is legally and commercially unclear. | P0 |
| UX-02 | Term selection is global and accepts non-contiguous years; independent facility terms of 3, 4, and 5 years are not modelled. | The displayed term can misrepresent the selected commercial commitment. | P0 |
| UX-03 | Pricing, review, confirmation, and success screens foreground a primary-year monthly amount rather than the selected-term commitment. | A health executive must reconcile figures across screens. | P0 |
| UX-04 | The wizard always makes the submitter the Facility Signatory. | ICT/support users are incorrectly assigned legal authority. | P0 |
| UX-05 | The OIS receipt goes to the submitter and the signing invitation is a separate, summary-free message. | The nominated signatory lacks decision context; a self-signing user receives noisy duplicate communication. | P0 |
| UX-06 | The public completion state says “You’re in!” while signing and provisioning remain outstanding. | It overstates progress and creates avoidable follow-up. | P1 |
| UX-07 | CRM review exposes the first facility plus “+N more” instead of the full scope, commercial summary, and notification state. | Internal teams cannot confidently support or chase a multi-facility decision. | P1 |
| UX-08 | Facility-level yearly terms are visually subordinate to one legacy selector and can appear inconsistent with the network schedule. | Operators may apply an override to the wrong year or mistake inherited terms for negotiated terms. | P1 |
| UX-09 | A CRM approver opening a Deal lands on the general Activity tab before the commercial decision surface. | Approval takes an unnecessary navigation step and risks delaying review of the actual quote. | P1 |

### 3.1 Contract schedule inheritance

The network owns the contract years and their default schedules. A prequalified
facility may replace the schedule for a configured year, but may not add a new
contract year or override a year that the network has not configured. This keeps
term length and commercial ownership clear.

The facility editor must present the same year-by-year structure as the network
editor: Year, network contract schedule, and facility contract schedule. An
empty facility value explicitly means **Inherit network schedule**. After
Opt-In, the full yearly set is read-only and changes continue through the
quotation workflow before signature.

### 3.2 CRM approver landing

For Sales Managers and System Managers, opening a Deal without an explicit tab
link must open the **Quote** tab. Quote is the first desktop tab and is the
primary surface for reviewing commercial terms, approval readiness, and the
generated document. An explicit URL tab, such as an activity notification,
continues to open the requested tab.

## 4. Required user journey

### 4.1 Review step: choose the signatory

Place a **Who will sign the agreement?** section immediately before the witness
section. It is a visible two-choice control, not a hidden link or a secondary
dialog.

Use two full-width, selectable radio cards:

| Choice | Default and copy | Behaviour |
| --- | --- | --- |
| **I am authorised to sign** | **Selected by default.** “Choose this if you are authorised to bind your organisation to this agreement.” | The verified submitter's contact details are used as the Facility Signatory. |
| **Someone else is authorised to sign** | Always visible. “Choose this if you are completing the Opt-In for an authorised colleague.” | Reveal the signatory fields directly below the choice. |

The selected card needs an obvious visual state: brand-colour border, check
indicator, and a short explanatory line. The unselected option must retain a
border, title, and explanatory copy so it remains discoverable. The whole card
and its label are selectable by mouse, keyboard, and touch; colour is not the
sole state indicator.

The default is intentional: it preserves the fastest path for an authorised
executive, while the equally prominent alternate card makes delegation
understandable for an ICT/support user.

### 4.2 Nominated signatory fields

When **Someone else is authorised to sign** is selected, show a compact
**Authorised signatory** block using the same visual treatment and field order
as the Facility Witness block:

- Signatory name — required; full legal name.
- Signatory email — required; valid work email.
- Signatory phone — optional; recommended for SMS delivery where configured.

The block states: “We will email this person the Opt-In summary and a secure
link to review and sign the agreement.” The submitter must be able to return
to the self-signing choice without losing their own contact details. Changing
the choice must never copy a signing token, link, or OTP between people.

The Facility Witness remains a distinct person and follows the existing
sequential witnessing step. The form should prevent a nominated signatory from
also being entered as the witness without a clear, deliberate exception approved
by legal/commercial policy.

### 4.3 Terms acknowledgement

The terms screen remains visible to the submitter so they can review the
proposed agreement and schedule. The confirmation wording changes by choice:

| Signatory choice | Required acknowledgement |
| --- | --- |
| Self | “I confirm I am authorised to submit and sign this agreement for my organisation, and I accept these terms.” |
| Someone else | “I confirm the submitted information is accurate, I am authorised to nominate this signatory, and I have permission to provide their contact details. The nominated signatory will review and accept the agreement.” |

The second statement is an OIS acknowledgement, not contractual acceptance by
the submitter. Contractual acceptance remains attributable to the named
signatory's authenticated signature.

### 4.4 Submission and notification hand-off

After canonical server validation succeeds, the system creates the OIS, Deal,
quotation bundle, and contract according to the normal Opt-In transaction.
The Facility Signatory row must use the selected signatory identity, not an
assumption derived from the submitter.

Notification behaviour is deterministic:

| Scenario | Submitter receives | Signatory receives |
| --- | --- | --- |
| Submitter signs | One combined **OIS confirmed — review and sign** message: OIS summary plus their unique secure signing link. | Same person; no duplicate email. |
| Another person signs | **OIS submitted** acknowledgement: reference, commercial summary, nominated signatory, and next step. No signing link. | One **Review and sign** package: the same OIS summary plus their unique secure signing link. |

The OIS summary must include the hierarchy from §2: facility scope/KEPH mix,
selected term, total selected-term commitment inclusive of VAT, Year 1 amount,
quarterly timing, optional services excluded from subscription totals, and OIS
reference. It must use **Contract schedule**, not “Price list”.

The invitation link is unique to the signatory, expires under the existing
invitation policy, and is never included in the submitter-only acknowledgement.
Existing OTP verification and signing-token rules remain in force.

### 4.5 Completion and CRM visibility

The public completion page says **Opt-In submitted**. It names the next actor:

- “Your signing invitation has been sent to you”; or
- “A signing invitation has been sent to [signatory name].”

It does not say “You’re in” before the required signatures and activation are
complete.

The CRM OIS/Deal view displays, before detailed schedules:

1. commercial decision summary;
2. **Submitted by** identity;
3. **Facility signatory** identity;
4. witness identity;
5. invitation status: not applicable, queued, sent, failed, expired, signed,
   or re-sent; and
6. a manager-only retry/resend action when a notification needs attention.

The full facility list and contract schedule remain expandable beneath the
summary. CRM must never claim email **delivery** based only on a successful
queue request; it may say **queued** or **sent** according to the recorded
provider/queue state.

## 5. Data and integration requirements

Additive fields preserve existing records and clients:

| Record | Required addition or rule |
| --- | --- |
| OIS payload | `signatory_mode`: `self` or `delegate`; `signatory` identity when delegated. |
| CRM Opt-In Submission | Persist submitter identity separately from the selected Facility Signatory; retain the witness fields and record acknowledgement wording/version. |
| CRM Contract / signatory row | Use the selected identity for the Facility Signatory row. Existing contract signing tokens remain row-specific. |
| Notification audit | Store invitation recipient, purpose, email-queue/provider reference, issued time, current state, and last failure reason suitable for an operator. Do not persist a plaintext signing URL. |
| Existing submissions | Treat them as `signatory_mode=self` only where the historical submitter and Facility Signatory are the same; do not mutate signed contracts. |

The server remains authoritative. It validates the selected mode, email format,
required delegated fields, canonical facility/pricing data, and conditional
acknowledgement before creating a contract or invitation.

An email-provider failure must not be presented as a successfully sent signing
invitation. The OIS may remain commercially processed, but its invitation state
must become **Needs attention** and expose a safe retry to authorised CRM users.

## 6. Stories for execution

### OIS-UX-01 — Clear signatory choice

**As** an authorised facility executive, **I want** the fastest path to remain
selected by default, **so that** I can complete my Opt-In without unnecessary
data entry.

**As** an ICT/support colleague, **I want** to clearly nominate the authorised
signatory, **so that** I do not misrepresent my authority.

**Acceptance criteria:**

1. “I am authorised to sign” is selected on first render.
2. Both choices are visible without expansion, are keyboard accessible, and
   have text labels and non-colour selection cues.
3. Selecting delegation reveals name, email, and phone fields in the existing
   witness-style treatment.
4. Delegation cannot continue without a name and valid email.
5. Switching between choices preserves the verified submitter and does not
   expose or reuse any signing credential.

### OIS-UX-02 — Correct acknowledgement and data persistence

**As** the business, **I want** the OIS to distinguish submitter, signatory,
and witness, **so that** the contract and audit trail identify the correct
people.

**Acceptance criteria:**

1. The submission payload and server validation support `self` and `delegate`
   modes.
2. The Facility Signatory is the submitter only in self mode; otherwise it is
   the nominated identity.
3. The terms acknowledgement is stored with the correct conditional wording.
4. The signer, witness, and submitter appear separately in CRM.
5. Existing unsigned and signed contracts remain readable and unchanged.

### OIS-UX-03 — Summary-and-link notification package

**As** a nominated signatory, **I want** the commercial summary with my secure
link, **so that** I know what I am being asked to approve before I open the
signing portal.

**Acceptance criteria:**

1. A delegated signatory receives one signing package after a successfully
   processed OIS and generated contract.
2. The package contains the canonical OIS summary and only that signatory's
   unique signing link.
3. The submitter receives an acknowledgement without the delegated person's
   link.
4. If submitter and signatory are the same email, one combined notification is
   sent instead of two duplicate messages.
5. The contract invitation remains subject to the current expiry and OTP
   controls.

### OIS-UX-04 — Observable delivery and recovery

**As** a CRM operations user, **I want** to see whether the signatory package
was queued or needs attention, **so that** I can intervene without asking the
facility to start again.

**Acceptance criteria:**

1. CRM shows recipient, timestamp, and notification state without exposing
   invitation tokens or the full signing URL.
2. A queue/provider failure is labelled **Needs attention**, not **sent**.
3. An authorised user can issue a fresh invitation; it invalidates the earlier
   token using the existing resend semantics and records the event.
4. A retry never changes the OIS commercial snapshot, selected signatory, or
   signed evidence.

### OIS-UX-05 — Executive commercial hierarchy

**As** a hospital executive or signatory, **I want** the same concise decision
summary at review, signing, and CRM, **so that** I do not have to reconcile
multiple figures.

**Acceptance criteria:**

1. The selected-term commitment is visually dominant on Pricing, Review,
   Terms, the signing portal, and CRM.
2. Year 1 amount and quarterly timing are secondary but visible without opening
   the legal contract.
3. Facility schedules and optional services are detail-on-demand.
4. The completion page accurately says whether the submitter or a nominated
   signatory must act next.

## 7. Verification matrix

| Scenario | Required evidence |
| --- | --- |
| Self-signing, one facility | One combined summary-and-link email; correct signer; no duplicate acknowledgement. |
| Delegated signing, one facility | Submitter acknowledgement has no link; signatory package has summary and unique link; CRM identifies both people. |
| Delegated signing, five facilities, five years | Summary shows five-facility scope, selected-term total, Year 1, quarterly cadence, and expandable contract schedule. |
| Facility Year 2 override | Contact editor shows the inherited Year 1 and Year 3 schedules plus the explicit Year 2 override; sample quote, portal pricing, quotation bundle, CRM quote tile, contract terms, and Quote PDF all retain the Year 2 schedule. |
| Email queue failure | CRM shows Needs attention; no success claim; manager resend creates a fresh link and audit event. |
| Signatory signs then witness signs | Existing sequential signing and OTP protections still work. |
| Existing contract | No modification to historic signer, signature, or contract content. |

Test the API validation and notification composition as backend tests; test the
choice, conditional form, and completion copy as frontend tests; manually test
the email outputs in a non-production mail environment. All relevant frontend
and backend suites must pass before release.

## 8. Release gates and non-goals

### Release gates

1. Product/legal decision: a single multi-facility master agreement versus one
   agreement per facility.
2. Product decision for mixed 3/4/5-year terms: one common contiguous term or

   3. Approved email copy and identity/privacy wording for nominated signatories.

### Non-goals for this increment

- Changing the existing network/Tiberbu co-signatory policy.
- Replacing OTP, signature-pad, or token security.
- Making email delivery guarantees that the provider cannot prove; the product
  records queue/send state and provides recovery instead.
- Retrospectively changing a signed agreement or historic notification.
