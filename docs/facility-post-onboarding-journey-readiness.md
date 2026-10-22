# Facility Post-Onboarding Journey — Gap Analysis & Stakeholder Questions

**Status:** For stakeholder review. No implementation is approved.
**Date:** 2026-10-22
**Baseline:** `develop` @ `39657cdc`, plus open PR #105 (self-onboarding portal-user permission fix)
**Purpose:** Get the decisions needed to write the implementation artifacts (revised PRD, architecture, UX spec, epics and stories) that connect Facility Self-Onboarding to a live HMIS facility from start to finish.

> **How to respond:** each question has an ID (for example `Q-PROV-1`). Reply in a PR review comment that starts with the ID, or fill in the **Answer** block under the question. If an answer depends on someone else, name them in the block. A question is closed when it has an answer, a name and a date.

---

## 1. The journey being completed

The target journey for a facility owner after a successful Self-Onboarding submission:

| Step | Journey | Owner sees |
|---|---|---|
| J1 | **Request → approved and paid**: the onboarding request becomes a won, paid commercial record | "My request was received / approved / paid" |
| J2 | **Automatic provisioning**: CRM submits the facility to the HMIS setup tool and tracks it until the site is deployed | "My facility is being set up" |
| J3 | **Sign in**: (a) sign in to the CX Portal; (b) once deployed, sign in to the newly provisioned HMIS instance | "I can get in" |
| J4 | **Open a facility and top up tokens**, before and after go-live | "I can buy tokens and see where they went" |
| J5 | **Onboarding status**: one view of where the facility is across J1–J4 | "I know where I am and what's next" |

## 2. Status at a glance

| Step | Spec | Code | Verdict |
|---|---|---|---|
| J1 | Partly: user guide `user-guides/facility-self-onboarding.md` | Submission, deal, quote and portal user are created. **Nothing marks a self-onboarded deal Won.** | **Gap that breaks the chain** |
| J2 | `facility-auto-provisioning-prd.md` (Draft 0.2, 6 open questions), `cx-portal-provisioning-gateway-api.md` (Proposed) | Pull-on-view auto-submit exists, but **every draft is blocked by two fields CRM never supplies** | **Built, never produces a draft** |
| J3a | `user-guides/cx-portal.md`, backlog E2-S1..S4 (in `review`) | Built | **Built, not verified on crm-dev** |
| J3b | None | None | **Not defined** |
| J4 | `cx-portal-health-facility-registry-and-portfolio-prd.md` (Under review), `cx-portal-ux-design-pattern.md`, `cx-portal-professional-admin-ui-audit-and-plan.md` | Built for pre-go-live purchases. No token ledger, no top-up path to a live HMIS | **Built in part** |
| J5 | Fragments (PRD FR-6, user guide) | Separate cards: Self-Onboarding requests, invoices, HMIS status | **Not defined as one journey** |

No BMAD planning artifacts (epics, stories, sprint status) exist for any of J1–J5. `tiberbu-crm-backlog.md` (2026-07-29) predates this work.

---

## 3. Findings by journey

Evidence references point at `develop` @ `39657cdc`. I found these by reading the code, not by running the flow end to end, except where a section says otherwise.

### J1 — From request to won and paid

**What exists**
- Self-Onboarding submit creates a `CRM Opt-In Submission` (`onboarding_source = token_self_onboarding`, created `Pending`, then processed to `Processed` during submit), a deal, an initial quote and a portal Website User (`crm/api/facility_onboarding.py`, `_create_submission` and `_submit_selected_facilities`).
- For Network Opt-In, the deal becomes Won when the facility contract is signed (`crm/automation/optin_billing.py:299` `handoff_facility_signed` → `:244` `_mark_deal_won`).

**Gaps**
- **G1.1 Self-onboarded deals never become Won.** `_mark_deal_won` is reached only from contract signing, and Self-Onboarding has no signature by design. Provisioning requires a Won deal (see G2.1), so a self-onboarded facility cannot reach provisioning without a manual status change.
- **G1.2 No approval step is defined.** Nothing says whether a Self-Onboarding request needs human review (KYC, network acceptance, credit) before it becomes Won, or whether payment alone is enough.
- **G1.3 The owner can't see the approval step.** Even if a review exists, nothing tells the owner it is pending.

### J2 — Automatic provisioning

**What exists**
- `crm/api/hfr.py:322` `get_provisioning_status`, called from the Single Facility View. It refuses guests and checks the facility against the caller's portfolio.
- When the external setup credentials in `CRM HFR Settings` are set and upstream reports `not_submitted`, CRM builds the payload (`hfr.py:639`, `:721`). It then submits once, behind a per-FID file lock, a status re-check and encrypted retry state (`hfr.py:794` onward). The tests are in `crm/tests/test_hfr_provisioning_status.py` (15 tests).
- The HIE gateway fallback reads status only.

**Gaps**
- **G2.1 Every draft is blocked today.** The payload builder requires `billing_model` and `token_expiry_date`. `_get_external_provisioning_source` never sets either, deliberately, because PRD §12 Q3 is unresolved. Every facility therefore stops at "blocked — missing fields" and no draft is created. It also needs a Won deal (G1.1) and a fully paid `Sales Invoice` tagged with the facility MFL and package.
- **G2.2 Provisioning is only checked when the owner opens the page.** The PRD specifies deal Won → background job → scheduler poll (FR-3, FR-5). The code provisions only when the owner opens the Single Facility View. A facility whose owner never opens that page is never provisioned or tracked.
- **G2.3 No audit record or milestones.** There is no `CRM Provisioning Request` DocType (PRD FR-7), no status poll in `scheduler_events`, no `provisioning_enabled` switch and no milestone emails (FR-6).
- **G2.4 The PRD contradicts itself.** Invariant 7 and §11 describe the built pull model, while §5, FR-3, FR-5, FR-7 and the delivery slices describe the push model.
- **G2.5 A status read can create a draft.** `get_provisioning_status` accepts `GET` and can cause an upstream POST that creates a draft. It has no `@rate_limit`. Frappe 15 supports both `@frappe.whitelist(methods=["POST"])` and `frappe.rate_limiter.rate_limit`; I checked both in frappe 15.107.5 on this bench and against the Frappe docs via Context7.
- **G2.6 The FID field rules aren't enforced.** PRD slice A (FID uniqueness, locking after submission, the "FID unresolved" flag) is not built. The FID is validated only when the payload is built.
- **G2.7 The upstream contract has open differences.** Status for an unknown FID returns HTTP 417 (documented: 400). POST has never been probed, because there's no upstream dedupe. The gateway `/v1/hmis/...` routes are "Proposed".
- **G2.8 Environment.** crm-dev has no provisioning or external setup credentials configured.

### J3 — Sign in

**J3a — CX Portal (exists)**
- During Self-Onboarding submit, the portal Website User is created and a password-setup email is sent. Login is branded and the user is redirected to `/cx-portal` (`crm/api/website_redirect.py`, backlog E2). PR #105 fixes a failure for first-time owners.
- **G3.1 Not verified.** Nobody has run the flow end to end on crm-dev. Outgoing email (SES or the default account) is not yet configured there, and a known `client_registry` patch can break `frappe.sendmail` on this shared bench (see the PR #105 follow-ups).

**J3b — Newly provisioned HMIS instance (not defined)**
- The setup contract creates an HMIS administrator from `admin_email`. Nothing defines how the owner learns the instance URL, how they first sign in (invite, temporary password, SSO), or what the CX Portal shows once the site is Live.
- **G3.2** No spec, no email, no portal element, and no upstream field for the instance URL (the v1.2 status response returns only `status`, `progress`, `log`, `error` and `last_attempt`).
- **G3.3** The administrator source is the Opt-In signatory. For Self-Onboarding this is the verified owner (`facility_signatory_email = person.email`). Nobody has confirmed that this person should be the HMIS administrator.

### J4 — Open a facility and top up tokens

**What exists**
- Single Facility View (`frontend/src/pages/FacilityPortal/FacilitySingleView.vue`) with **Top up tokens**, free and paid package options, invoices and payment history.
- APIs (`crm/api/customer_experience.py`): `get_purchase_context` (:153), `create_token_order` (:180), `start_token_payment` (:522), and `report_mpesa_payment` (:1078). The last one records an M-Pesa reference for Finance to reconcile; it does not verify the payment automatically.

**Gaps**
- **G4.1 No token balance.** The portal shows package quantities, not a remaining balance (the user guide says so). Nothing records tokens bought, awarded and used.
- **G4.2 Top-ups after go-live don't reach the HMIS.** Tokens reach the HMIS only once, as `tokens_awarded` in the provisioning draft. No API or process is defined for crediting tokens to a live instance.
- **G4.3 Payment verification is manual and its timing is undefined.** M-Pesa references wait for Finance. There's no defined SLA, no owner notification and no automatic matching.
- **G4.4 Environment.** On crm-dev, ordering depends on the VAT template, pricing, Selling Settings and email, all still open in the configuration checklist.

### J5 — Onboarding status

**What exists:** a Self-Onboarding requests card (`OptInRequests.vue`), invoice and payment rows, and the HMIS implementation card. Each is accurate on its own.

**Gaps**
- **G5.1** No single onboarding timeline is defined. The proposed stages are: request received → under review → approved → payment pending → paid → setup submitted → deploying → live → HMIS access sent.
- **G5.2** No list of stages, no owner-facing wording, no rules for what moves the owner to the next stage, and no matching email or SMS.
- **G5.3** No internal view of all facilities and where each one is stuck.

---

## 4. Questions for stakeholders

Owners are proposed. Change the owner if someone else should answer.

### 4.1 Product / Commercial — proposed owner: Product lead

**Q-COM-1. What makes a Self-Onboarding deal Won?** *(unblocks G1.1, G2.1)*
Options: (a) full payment of the initial package invoice; (b) internal approval; (c) approval, then payment; (d) a free package counts as paid once accepted.
Proposed default: (c) for paid packages, approval only for free packages.
> **Answer:** _pending_ · **By:** · **Date:**

**Q-COM-2. Is there an internal review of Self-Onboarding requests before go-live?** Who performs it, what do they check, and what is the SLA? *(G1.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-COM-3. Billing model per package: `Token` or `License`?** Where should it live: the `CRM Token Package`, the price list, or the deal? *(G2.1, PRD §12 Q3)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-COM-4. How are `token_expiry_date` and `license_expiry_date` derived?** Options: invoice paid date + package `billing_period`; contract end date; a fixed term. *(G2.1)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-COM-5. Can a facility be provisioned before payment** (for example, a free trial package), or only after the invoice is fully paid? *(G2.1)*
> **Answer:** _pending_ · **By:** · **Date:**

### 4.2 HMIS deployment / setup tool team — proposed owner: Deployment lead

**Q-DEP-1. Push or pull?** Should CRM submit the draft automatically when the deal is Won or paid, with background status polling (the PRD's push model)? Or should it stay with the pull model already built, where it submits when the owner opens the page? *(G2.2, G2.4)*
Proposed default: push model, keeping the pull read as a manual refresh.
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-2. Will the status response include the instance URL** (and a site health indicator) once `Deployed`? If not, where does CRM get the URL? *(G3.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-3. How does the HMIS administrator first sign in?** Options: an invite email from the HMIS, a temporary password, SSO through Identity Auth, or a CRM-sent handover email. Who sends it? *(J3b)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-4. Is there (or will there be) an API to credit tokens to a live instance** after go-live? If not, what is the manual process and its SLA? *(G4.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-5. Status code and dedupe.** Will "no Facility Setup found" return 400 (as documented) or 417 (as observed)? Can the upstream reject duplicate drafts for the same FID (409), so CRM no longer has to be the only guard? *(G2.7)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-6. Is there a safe target for testing POST** (a staging setup instance or sandbox FID) so CRM can test draft creation without creating a real draft? *(G2.7)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-7. How long should it take from Draft to Deployed?** CRM will use this to tell owners when to expect go-live and to flag stalled setups. *(J5)*
> **Answer:** _pending_ · **By:** · **Date:**

### 4.3 HIE / Integration — proposed owner: Integration lead

**Q-HIE-1. Will the `/v1/hmis/provisioning/...` APISIX routes be published,** or should CRM use the direct setup service permanently? *(G2.7)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-HIE-2. Confirm the FID format.** Does the registry's `facility_fid` always match `FID-XX-…`? Who resolves facilities with no FID or several FIDs? *(G2.6, PRD §12 Q6)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-HIE-3. Who issues and rotates the dedicated setup-service API key,** for crm-dev and for production? *(G2.8)*
> **Answer:** _pending_ · **By:** · **Date:**

### 4.4 Finance — proposed owner: Finance lead

**Q-FIN-1. What is the SLA for reconciling M-Pesa references, and how is the owner told the result?** Is automatic matching (for example M-Pesa C2B or STK push) in scope? *(G4.3)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-FIN-2. Is the system of record for a facility's token balance CRM, the HMIS, or both** (each tracking its own figures)? *(G4.1)*
> **Answer:** _pending_ · **By:** · **Date:**

### 4.5 Customer experience / Support — proposed owner: CX lead

**Q-CX-1. Approve the onboarding stages and owner-facing wording** proposed in G5.1. Add, remove or rename stages. *(G5.1, G5.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-CX-2. Which stages notify the owner, and by which channel** (email, SMS, both)? Covers PRD §12 Q4. *(G2.3, G5.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-CX-3. Who handles a blocked provisioning, and what do they do?** Includes cleaning up a stray draft in the setup app. *(G2.3)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-CX-4. Does the internal team need a dashboard of facilities by stage** (G5.3)? If yes, should it be in Desk, CRM or the Finance Cockpit?
> **Answer:** _pending_ · **By:** · **Date:**

### 4.6 Security / Engineering — proposed owner: Tech lead

**Q-SEC-1. Should the portal status read be POST-only and rate-limited** (G2.5)? Or should the draft submission move entirely to a background job, so that reading status never creates a draft?
> **Answer:** _pending_ · **By:** · **Date:**

**Q-SEC-2. Should the verified Self-Onboarding owner become the HMIS administrator,** or can the owner nominate someone else, and if so how is that person verified? *(G3.3)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-SEC-3. Should multiple facilities on one deal each get their own provisioning request?** *(PRD §12 Q5)* Should an FID field be added to `CRM Pre-Qualified Facility`? *(PRD §12 Q2)*
> **Answer:** _pending_ · **By:** · **Date:**

---

## 5. Which answers unlock which artifacts

| Artifact to write after answers | Needs answers to |
|---|---|
| Revised `facility-auto-provisioning-prd.md` v0.3 (one model, §12 closed) | Q-COM-1, 3, 4, 5 · Q-DEP-1, 5, 7 · Q-HIE-1, 2 · Q-CX-2, 3 · Q-SEC-1, 3 |
| New spec: **HMIS access handover** (J3b) | Q-DEP-2, 3 · Q-SEC-2 · Q-CX-2 |
| New spec: **Onboarding journey status** (J5) | Q-COM-1, 2 · Q-CX-1, 2, 4 · Q-DEP-7 |
| PRD-CX-PORTFOLIO-002 addendum: **token balance and top-ups after go-live** (J4) | Q-DEP-4 · Q-FIN-1, 2 |
| Architecture update (trigger, audit DocType, scheduler, security of the status read) | Q-DEP-1 · Q-SEC-1 · the revised PRD |
| UX spec for the timeline, HMIS access card and balance | J3b and J5 specs |
| Epics, stories and sprint plan | All of the above |
| crm-dev readiness (credentials, email, pricing) | Q-HIE-3 · the configuration checklist |

## 6. Work that needs no answers (can start when approved)

These don't depend on the questions above, but implementation is **not** approved by this document.
- Make PRD §5, FR-3, FR-5, FR-7 and §10 consistent with each other, marking the push/pull decision as open.
- Finish configuring crm-dev (email, VAT template, Selling Settings, pricing) and run J3a and J4 end to end. Record the results in this document.
- Merge PR #105, and fix the `client_registry` email patch (it affects OTP and password emails on the shared bench).

## 7. Proposed sequence after feedback

1. Collect answers in this PR. Close it once every blocking question has an answer, a name and a date.
2. Revise the PRD (BMAD `bmad-prd`, update intent) and write the J3b and J5 specs.
3. Update the architecture (`bmad-architecture`) and UX (`bmad-ux`).
4. Write epics and stories (`bmad-create-epics-and-stories`), then sprint planning (`bmad-sprint-planning`).
5. Implement one vertical slice at a time, starting with whatever the J1 → J2 chain needs first (Won rule, billing model and expiry), since those block every draft.
