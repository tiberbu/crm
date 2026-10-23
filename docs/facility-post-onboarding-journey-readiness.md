# Facility Post-Onboarding Journey — Gap Analysis & Stakeholder Questions

**Status:** For stakeholder review. No implementation is approved.
**Date:** 2026-10-22 · **Revised:** 2026-10-23 after PR #103
**Baseline:** `develop` @ `ce591ff9` (includes PR #103), plus open PR #105 (self-onboarding portal-user permission fix)
**Response page:** [Facility Go-Live Decisions](https://claude.ai/artifact/KMmq6PQeRE8n5GAA339BsF). Stakeholders answer there, under their own names.
**Purpose:** Get the decisions needed to write the implementation artifacts (PRD updates, architecture, UX spec, epics and stories) that connect Facility Self-Onboarding to a live HMIS facility from start to finish.

> **How to respond:** use the response page, or reply in a PR review comment that starts with the question ID (for example `Q-COM-1`). A question closes when it is marked Decided with a note.

## What changed in revision 2 (PR #103)

PR #103 (merged 2026-10-22) replaced `facility-auto-provisioning-prd.md` with **`docs/hmis-implementation-prd.md`** (Implementation baseline 1.0, stories HIMS-01..08) and rewrote `cx-portal-provisioning-gateway-api.md`. In the code (`crm/api/hfr.py`):

- **Reading and creating are now separate.** `get_provisioning_status` is GET-only and read-only. The new `ensure_provisioning_draft` (POST) creates the draft. The Single Facility View calls it on load and on Retry.
- **No commercial check.** A Won deal and a paid invoice are no longer required. A draft is created as soon as an authorized facility has a verified FID and the setup tool reports no draft.
- **Payload rules decided.** `billing_model` = `Token`. `token_expiry_date` = CRM onboarding date (the facility row's creation date) + 30 days. `tokens_awarded` = the selected package quantity, or `0`.
- **Responses and errors.** The setup tool's 400 and 417 "no setup found" responses are both handled. Every request carries a correlation ID, and System Managers can see the setup tool's error details.
- **FID lookup.** CRM resolves the FID across Pre-Qualified, Deal and Lead facility records and the registry. It won't choose between conflicting registry FIDs, and reports `not_linked` when there is none.

Effect on this document:
- The two blockers in revision 1 are gone: drafts no longer wait for a Won deal, and `billing_model` and the token expiry are now filled in.
- 7 questions now ask stakeholders to **confirm** a decision PR #103 made.
- 3 questions are **closed**.
- 1 question is **new** (Q-DEP-8).
- The questions to answer first changed (§4).

---

## 1. The journey being completed

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
| J1 | Partly: `user-guides/facility-self-onboarding.md` | Submission, deal, quote and portal user are created. Nothing marks a self-onboarded deal Won, but since PR #103 that no longer blocks provisioning | **No longer blocks setup.** Approval and payment stages are undefined |
| J2 | `hmis-implementation-prd.md` (baseline 1.0), `cx-portal-provisioning-gateway-api.md` (implemented contract) | Draft created when the facility page opens. Read and create are separate. Payload is complete | **Built. Not yet tested against the real setup tool** (HIMS-08 in progress; no credentials on crm-dev) |
| J3a | `user-guides/cx-portal.md`, backlog E2-S1..S4 | Built | **Built, not verified on crm-dev** |
| J3b | None | None | **Not defined** |
| J4 | `cx-portal-health-facility-registry-and-portfolio-prd.md` (Under review), UX pattern, admin UI plan | Built for purchases. No token balance, no path for tokens bought after the draft | **Built in part.** More urgent now that drafts often go out with 0 tokens |
| J5 | Fragments | Separate cards | **Not defined as one journey** |

No BMAD epics or sprint tracking exist for J1, J3b, J4 or J5. J2 has stories HIMS-01..08 in the HIMS PRD.

---

## 3. Findings by journey

Evidence references are against `develop` @ `ce591ff9`. I found these by reading the code; the journeys were not run end to end.

### J1 — From request to won and paid

- Self-Onboarding submit creates a `CRM Opt-In Submission` (`onboarding_source = token_self_onboarding`, processed to `Processed`), a deal, a quote and a portal Website User (`crm/api/facility_onboarding.py`).
- A deal becomes Won only when a Network Opt-In contract is signed (`crm/automation/optin_billing.py` `handoff_facility_signed` → `_mark_deal_won`).
- **G1.1 (changed)** A self-onboarded deal still never becomes Won. Since PR #103 that no longer blocks provisioning, but the commercial record and the owner's status never show approved or paid.
- **G1.2** No approval step is defined.
- **G1.3 (new)** Drafts can now be created before approval or payment, with 0 tokens. Deployment is a manual step in the setup tool, and that's the only remaining point where an unpaid facility can be stopped. The setup tool has no payment information.

### J2 — Automatic provisioning

**What exists (PR #103):** `ensure_provisioning_draft` (POST) and `get_provisioning_status` (GET, read-only) in `crm/api/hfr.py`. The ensure flow: check portfolio access → resolve one FID → check status in the setup tool → submit only on an exact "no setup found" → reload status. It's serialized by a per-FID lock. A retry after a timeout or 5xx checks status first. Missing payload data is reported by field name. Stories HIMS-01..07 are implemented baseline; HIMS-08 (regression coverage and environment verification) is in progress.

**Gaps that remain**
- **G2.1 (resolved by PR #103)** `billing_model` and `token_expiry_date` are now set. Both are decisions for stakeholders to confirm (Q-COM-3, Q-COM-4).
- **G2.2 (changed)** Drafts are created only when someone opens the facility page. A facility nobody opens never gets a draft, and status refreshes only when someone looks (Q-DEP-1).
- **G2.3** No milestone emails or SMS, and no internal list of all setup requests. The CRM Error Log with correlation IDs is the only record.
- **G2.4 (resolved by PR #103)** The contradictory PRD was replaced by one canonical HIMS PRD.
- **G2.5 (mostly resolved)** Reading status is now GET-only and read-only. The new POST command runs on every page load with no `@rate_limit` (Q-SEC-1).
- **G2.6 (changed)** FID lookup is now deterministic. Nobody owns fixing facilities that have no usable FID (Q-HIE-2).
- **G2.7** The setup tool still can't reject duplicate drafts. The HIMS PRD names duplicate-rejection by FID in the setup tool as the follow-up (Q-DEP-5). Draft creation has never been tested against a real target (Q-DEP-6).
- **G2.8** crm-dev has no setup-service credentials, so none of this can be verified there (Q-HIE-3).

### J3 — Sign in

- **J3a (exists):** the portal user and password-setup email are created at Self-Onboarding submit, followed by a branded login and the `/cx-portal` redirect. **G3.1** Not verified on crm-dev: email is not configured there, and the `client_registry` sendmail patch affects this shared bench.
- **J3b (not defined):** the setup tool creates an HMIS administrator from `admin_email`. **G3.2** No spec, email, portal element or status field gives the owner the instance URL or a first sign-in route (Q-DEP-2, Q-DEP-3). **G3.3** PR #103 confirms the administrator comes only from the one processed Opt-In signatory matching the facility, which is the verified owner for Self-Onboarding. Nobody has signed off on this (Q-SEC-2).

### J4 — Open a facility and top up tokens

- Built: `FacilitySingleView.vue` (Top up tokens), `crm/api/customer_experience.py` `create_token_order`, `start_token_payment`, `report_mpesa_payment` (an M-Pesa reference recorded for Finance to reconcile by hand).
- **G4.1** No token balance (Q-FIN-2).
- **G4.2 (more urgent)** Tokens reach the HMIS only in the draft. Drafts are now created at first page view, often with 0 tokens. Every later purchase, including top-ups after go-live, has no defined path to the HMIS (Q-DEP-4).
- **G4.3** Payment verification is manual, with no SLA and no owner notification (Q-FIN-1).
- **G4.4** crm-dev pricing, VAT and email configuration are still open.

### J5 — Onboarding status

- **G5.1–G5.3** There's still no single timeline, no list of stages, no matching notifications and no internal stage view (Q-CX-1, Q-CX-2, Q-CX-4).

---

## 4. Questions for stakeholders

Legend:
- **[Answer first]**: blocks the next set of artifacts or verification.
- **[Confirm]**: PR #103 already built this; sign it off or change it.
- **[New]**: added in revision 2.

### Answer first

| ID | Why first |
|---|---|
| Q-COM-1 | Decides whether drafts may go out before approval or payment |
| Q-COM-4 | Decides whether a 30-day token expiry is acceptable for go-live |
| Q-DEP-3 | Without it, a deployed facility has no way to start using its HMIS |
| Q-DEP-4 | Tokens bought after the draft have no way to reach the HMIS |
| Q-DEP-8 | The last place an unpaid facility can be stopped |
| Q-HIE-3 | Nothing built can be tested against the real setup tool until these credentials exist |

### 4.1 Commercial — proposed owner: Product lead

**Q-COM-1 [Answer first] [Confirm]. Is it acceptable that a setup draft is created before approval or payment?**
PR #103 removed the Won-deal and paid-invoice requirement. A draft is created as soon as the facility has a verified FID, carrying 0 tokens if no package was chosen.
Options: (a) keep it; (b) require full payment first; (c) require internal approval first; (d) require approval, then payment.
> **Answer:** _pending_ · **By:** · **Date:**

**Q-COM-2. Is there an internal review of Self-Onboarding requests before go-live?** Who performs it, what do they check, and what is the SLA? *(G1.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-COM-3 [Confirm]. Should every CRM token package bill as Token, or is License billing ever needed?** PR #103 sends `Token` for every package. License billing would need its own expiry date and a place in CRM to record it.
> **Answer:** _pending_ · **By:** · **Date:**

**Q-COM-4 [Answer first] [Confirm]. Should tokens expire 30 days after onboarding?** PR #103 counts expiry from the facility record's creation date. Tokens bought later don't change it.
Options: (a) 30 days is correct; (b) a different period; (c) follow the purchased package's billing period.
> **Answer:** _pending_ · **By:** · **Date:**

**Q-COM-5 — Closed by PR #103.** Drafts are now created before payment. Whether that should stay is asked in Q-COM-1.

### 4.2 HMIS deployment — proposed owner: Deployment lead

**Q-DEP-1 [Confirm]. Is it enough to create drafts only when someone opens the facility page?** That's what PR #103 built. A facility nobody opens never gets a draft, and status refreshes only on view.
Options: (a) on view is enough; (b) also create drafts and refresh status in the background.
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-2. Will the status response include the HMIS instance URL once deployed?** If not, where does CRM get it? *(G3.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-3 [Answer first]. How does the facility's HMIS administrator first sign in?** Options: an invite email from the HMIS, a temporary password, SSO through Identity Auth, or a CRM handover email. Who sends it? *(J3b)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-4 [Answer first]. How do tokens reach the HMIS after the draft is created?** Drafts now often carry 0 tokens. Options: an API to credit tokens exists or is planned, or a manual process (describe it and its SLA). *(G4.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-5 [Confirm]. Will the setup tool reject a second draft for the same FID?** PR #103 handles both 400 and 417. The HIMS PRD names duplicate-rejection by FID in the setup tool as the follow-up for safe retries. If yes, when?
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-6. Is there a safe place to test draft creation?** Options: a staging setup instance, a named test facility on production, or neither yet. *(G2.7, HIMS-08)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-7. How long should it take from draft to deployed?** Give the typical and worst-case time. *(J5)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-DEP-8 [Answer first] [New]. Before deploying a draft, will the deployment team check approval and payment?** Drafts can now exist before payment, and the setup tool shows nothing about it.
Options: (a) they check CRM before deploying (say how); (b) CRM sends the payment and approval state with the draft; (c) no check is needed. *(G1.3)*
> **Answer:** _pending_ · **By:** · **Date:**

### 4.3 HIE / Integration — proposed owner: Integration lead

**Q-HIE-1 — Closed by PR #103.** The direct setup service is now the standard path, and the HIE fallback only reads status. Reopen this if the gateway must stay in the path.

**Q-HIE-2. Who fixes facilities that have no usable FID?** PR #103 reports `not_linked` and won't choose between conflicting FIDs. Name the team, how they fix it, and how the owner is told. *(G2.6)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-HIE-3 [Answer first]. Who issues and rotates the setup-service API key for crm-dev and production?** *(G2.8)*
> **Answer:** _pending_ · **By:** · **Date:**

### 4.4 Finance — proposed owner: Finance lead

**Q-FIN-1. How fast are M-Pesa payments reconciled, and how is the owner told?** Is automatic matching (C2B or STK push) in scope? *(G4.3)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-FIN-2. Which system holds the facility's token balance:** CRM, the HMIS, or both? *(G4.1)*
> **Answer:** _pending_ · **By:** · **Date:**

### 4.5 Customer experience / Support — proposed owner: CX lead

**Q-CX-1. Do these onboarding stages and labels work for owners?** Request received → Under review → Approved → Payment pending → Paid → Setup submitted → Deploying → Live → HMIS access sent. Add, remove or rename. *(G5.1)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-CX-2. Which stages should notify the owner, and by which channel** (email, SMS, both)? *(G2.3, G5.2)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-CX-3. Who handles a facility whose setup is blocked, and what do they do?** PR #103 gives System Managers the setup tool's error details and a correlation ID, but nobody is named to act on them. *(G2.3)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-CX-4. Does the internal team need a view of every facility by stage?** If yes, should it be in Desk, the CRM app or the Finance Cockpit? *(G5.3)*
> **Answer:** _pending_ · **By:** · **Date:**

### 4.6 Security / Engineering — proposed owner: Tech lead

**Q-SEC-1 [Confirm]. Should the draft-creation command be rate-limited?** PR #103 made reading status side-effect free. `ensure_provisioning_draft` runs on every page load and Retry with no `@rate_limit`; the per-FID lock already serializes requests for the same facility. *(G2.5)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-SEC-2 [Confirm]. Should the verified owner become the HMIS administrator,** or may the owner nominate someone else, and if so how is that person verified? *(G3.3)*
> **Answer:** _pending_ · **By:** · **Date:**

**Q-SEC-3 — Closed by PR #103.** One draft per FID by design, with the FID resolved across Pre-Qualified, Deal and Lead facility records.

---

## 5. Which answers unlock which artifacts

| Artifact to write after answers | Needs answers to |
|---|---|
| `hmis-implementation-prd.md` update (commercial check, expiry, background creation, duplicates, notifications) | Q-COM-1, 3, 4 · Q-DEP-1, 5, 8 · Q-CX-2, 3 · Q-SEC-1 |
| HMIS PRD verification (HIMS-08) on crm-dev | Q-HIE-3 · Q-DEP-6 |
| New spec: **HMIS access handover** (J3b) | Q-DEP-2, 3 · Q-SEC-2 · Q-CX-2 |
| New spec: **Onboarding journey status** (J5) | Q-COM-1, 2 · Q-CX-1, 2, 4 · Q-DEP-7, 8 |
| PRD-CX-PORTFOLIO-002 addendum: **token balance and tokens after the draft** (J4) | Q-DEP-4 · Q-FIN-1, 2 · Q-COM-4 |
| Architecture update | Q-DEP-1 · Q-SEC-1 · the updated HIMS PRD |
| UX spec for the timeline, HMIS access card and balance | J3b and J5 specs |
| Epics, stories and sprint plan for J1, J3b, J4, J5 | All of the above |

## 6. Work that needs no answers (can start when approved)

Implementation is not approved by this document.
- Finish configuring crm-dev (email, VAT template, Selling Settings, pricing) and run J3a and J4 end to end.
- Merge PR #105, and fix the `client_registry` email patch on the shared bench.

## 7. Proposed sequence after feedback

1. Collect answers on the response page. Start with the [Answer first] questions.
2. Update the HIMS PRD, and write the J3b and J5 specs and the J4 addendum.
3. Update the architecture (`bmad-architecture`) and UX (`bmad-ux`).
4. Write epics and stories (`bmad-create-epics-and-stories`), then sprint planning (`bmad-sprint-planning`).
5. Implement one vertical slice at a time, starting with tokens after the draft (Q-DEP-4) and the deployment check (Q-DEP-8). Since PR #103 these are the gaps that most directly affect real facilities.
