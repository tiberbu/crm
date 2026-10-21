# PRD — Facility Auto-Provisioning via the HIE Deployment Tool

**Customer-facing product:** Tiberbu Customer Experience (cx-portal) + CRM facility deals
**Implementation system:** `crm` app (`apps/crm`) reading the External Facility Provisioning API of the `hmis_setup` deployment tool directly when dedicated service API credentials are configured, with the **HIE gateway** as fallback
> `crm` / `hmis_setup` / "setup app" are implementation names, not customer-facing language.

> **Upstream contract:** "External Facility Provisioning API — Contract v1.2" (attachment,
> implemented in `hmis_setup/api/external_provisioning.py` on the setup instance). All
> statements marked *(TA)* come from that document; statements marked *(repo)* are
> verified in this codebase; everything else is a **proposal** in this draft or an
> **assumption** in §12.

**Status:** Draft 0.2 — decisions D1–D3 resolved 2026-10-16; remaining questions in §12
**Version:** 0.2
**Date:** 2026-10-16
**System boundary:** `crm` (CRM + cx-portal) ⇄ HIE gateway (existing HIE integration) ⇄ `hmis_setup` (setup app, draft-only provisioning)

## 0. Resolved decisions (2026-10-16)

| # | Decision | Resolution |
|---|---|---|
| D1 | FID source | **MFL → FID lookup.** The existing HIE/HFR integration already returns the HIE facility ID (`facility_fid`) alongside the MFL code and stores it as `hfr_facility_id` on facility rows *(repo: `crm/api/hfr.py` → `_map_facility_to_org_fields`, `search_facility(search_by="mfl_code")`)*. The new FID field is auto-populated from that lookup; manual entry is a fallback. |
| D2 | Trigger | **Deal Won + valid FID + purchased package present** for the facility — reuses the existing E7 deal-Won automation pattern *(repo: `crm.automation.support_journey.on_deal_update`)*. |
| D3 | Status auth | **Use the external setup service when its dedicated API credentials are configured; otherwise use HIE APISIX.** Direct calls use Frappe Basic API-key authentication with a dedicated service user's API key/secret stored server-side in `CRM HFR Settings`. Never use an Administrator login password. HIE Bearer JWT remains the fallback. The live host returned 403 (`get_provision_status` is not whitelisted) on 2026-10-21; direct status remains unavailable until the method is published. |

---

## 1. Product decision

When a facility's commercial deal reaches its provisioning point (deal Won, facility
has a valid FID, package purchased — D2), the CRM **automatically registers the
facility with the deployment tool** by calling the External Facility Provisioning API
(POST `provision_facility`, *(TA §4)*) through the HIE gateway, then **tracks deployment
progress automatically** (GET `get_provision_status`, *(TA §5)*) and shows that progress
to the facility owner inside the Customer Experience portal (cx-portal) as read-only,
plain-language status.

The CRM never deploys anything. The upstream API creates a **Draft Facility Setup**
document and stops; a human in the Setup app reviews and presses Deploy *(TA §1, §7)*.
This PRD automates only the hand-off, tracking, and customer visibility around that
manual step.

The workflow is the "deployment-tool progress" follow-on capability already named in
`partner-facility-onboarding-prd.md` §11.

## 2. Problem and outcomes

Today:

- A sold facility's registration with the deployment tool is manual (or absent). The
  deployment team assembles the Facility Setup payload by hand from CRM/quote data.
- The facility owner has no visibility between Opt-In and go-live beyond generic CRM
  status; questions go to support.
- CRM facility rows already carry both an HFR **MFL code** (`mfl_code`) and the HIE
  facility ID (`hfr_facility_id` ← registry `facility_fid`, *(repo: `CRM Deal Facility`
  fields + HFR sync)*) — but the value is not surfaced as the deployment tool's
  tracking key, is not validated against the TA format, and nothing consumes it.

Success means:

- A deal with a resolvable FID provisions itself: no human assembles the payload.
- Exactly one draft exists per facility: retries never create duplicate drafts upstream
  (the API has no dedupe — duplicates make status lookup ambiguous, *(TA §4.5)*).
- The facility owner sees honest, plain-language deployment status in cx-portal without
  calling support; email mirrors the milestones.
- Every upstream call is auditable in CRM with a correlation ID and redacted logs.

## 3. Non-negotiable invariants

1. **CRM never deploys.** The API stops at Draft by design *(TA §1, §7)*; no CRM code
   path may trigger deployment, and the portal must show "awaiting deployment" as a
   real, expected state — not a stall.
2. **FID is the join key.** No provisioning is attempted without an FID that passes the
   TA regex `^FID-\d{2}-[\w-]+$` (case-insensitive, *(TA §4.1)*). No FID ⇒ no call; the
   record stays `Not Provisioned` with a clear reason.
3. **No duplicate drafts upstream.** The API does not dedupe *(TA §4.5)*; the CRM is the
   system of record for "which facility_setup document was created" and guards every
   re-post client-side.
4. **Credentials stay server-side.** HIE JWT material comes from `CRM HFR Settings`
   *(repo)*; the setup-side API key/secret (TA Basic auth) live on the gateway/setup
   site only *(D3)*. The portal and all customer-facing responses never expose
   credentials or raw upstream payloads.
5. **Least privilege upstream.** The setup-site calling user is a dedicated system user
   with create/read on `Facility Setup` only *(TA §7)*; not Administrator.
6. **Honest remote states.** Failures distinguish *not configured* (silent no-op),
   *transient network* (auto-retry, capped), *validation/business 400* (needs support,
   no blind retry), and *auth 401/403* (config incident, alert) *(TA §4.4 semantics)*.
7. **Portal is read-only and OIS-scoped.** The owner sees only their own facilities'
   provisioning state, consistent with the existing portal access model
   *(repo: `crm.api.customer_experience` gating)*.
8. **Registry-first data.** Facility facts come from the HIE/HFR registry via the
   existing integration; manual overrides only before submission and only for the FID.

## 4. Users and responsibilities

| Actor | Needs | Can do | Cannot do |
|---|---|---|---|
| Sales / implementation (CRM) | Get a sold facility provisioned without assembling data by hand | See the auto-populated FID; confirm/correct it pre-submission; retry a blocked submission; read provisioning history | Force a deploy; alter the billing snapshot sent upstream |
| Facility owner (cx-portal) | Know where their deployment stands | Read status/progress/next action per facility; request support via existing channels | Trigger, cancel, or retry provisioning; see other facilities or internal notes |
| Deployment tool operator (Setup app) | Receive clean, complete drafts | Review the Draft Facility Setup; deploy from the Setup app UI | — (out of CRM scope) |
| Support (CRM) | Resolve 400s and ambiguous states | Read redacted request log, correct FID/payload source, re-run | Expose credentials or raw registry payloads to the customer |

## 5. Canonical workflow

```text
Facility row synced from HFR  →  mfl_code + facility_fid (= FID) captured (existing sync)
  → FID field auto-populated, regex-validated (FR-1)
  → deal Won + FID valid + package purchased   (D2 trigger)
  → CRM builds payload from CRM data (FR-4 mapping)
  → async job POST provision_facility (HIE gateway, Bearer JWT — D3)
  → 200: store facility_setup doc name + status Draft → "Submitted"
      400: record reason → "Blocked (needs support)", no retry storm
      401/403/5xx/network: retry with backoff (capped) → then "Blocked"
  → scheduler polls get_provision_status?fid=… every N minutes (non-terminal only)
  → portal + email mirror state transitions
  → Setup app human deploys (manual, outside CRM)
  → next poll returns Deployed → "Live"; final email
```

State machine (CRM-owned, per facility):

```text
Not Provisioned → Submitted → Awaiting Deployment → In Progress → Live
                    │  (upstream Draft created)          (progress 0→100)
                    ├────────────► Blocked (retryable) ◄──┘
                    └────────────► Blocked (needs support)   [terminal; human re-run]
```

## 6. Functional requirements

### FR-1 — FID field in CRM (auto-populated MFL → FID lookup; D1)

- `CRM Deal Facility` gains `fid` (Data, "Facility ID (HIE)").
- **Auto-population:** when a facility row is created or resynced from HFR, `fid` is
  filled from the registry response — the same value the existing sync already writes to
  `hfr_facility_id` (`facility_fid`/`hie_id`, *(repo: `_map_facility_to_org_fields`)*).
  Where `hfr_facility_id` is absent but `mfl_code` exists, the job calls the existing
  `search_facility(mfl_code, search_by="mfl_code")` *(repo: `crm/api/hfr.py`)*, takes
  the row whose MFL matches exactly, and uses its `fid`. Zero matches or multiple exact
  matches → FID left blank + row flagged `FID unresolved (support)`; the lookup is
  retried automatically on resync and at trigger time.
- **Fallback:** manual entry allowed before submission (sales may receive the FID from
  the customer or the deployment team).
- **Validation:** TA regex `^FID-\d{2}-[\w-]+$`, case-insensitive *(TA §4.1)*; stored
  upper-cased, trimmed. Invalid values are rejected with the TA-style message.
- **Uniqueness:** FID is unique per site across deal facility rows — the same FID must
  never be posted twice (invariant 3).
- **Locking:** editable until the provisioning request reaches `Submitted`; afterwards
  changing the join key is a support action, not a form edit.
- `CRM Pre-Qualified Facility` gets the same field if §12 Q2 confirms earlier capture;
  default MVP = Deal Facility only.

### FR-2 — Provisioning settings and credentials (D3: reuse existing HIE integration)

Extend `CRM HFR Settings` (existing HIE home: `hfr_url` "HIE Base URL", `hfr_username`,
`hfr_password`, `hfr_jwt_expiry`, *(repo)*) with:

| Field | Type | Rule |
|---|---|---|
| `provisioning_enabled` | Check | Master switch; off ⇒ silent no-op, records stay `Not Provisioned` |
| `provision_facility_path` | Data | Gateway path, default `/api/method/hmis_setup.api.external_provisioning.provision_facility` *(TA §1)*; final gateway path to confirm (§12 Q1) |
| `status_path` | Data | Default `/api/method/hmis_setup.api.external_provisioning.get_provision_status` *(TA §1)* |
| `status_poll_minutes` | Int | Scheduler cadence, default 10 |
| `max_submit_retries` | Int | Capped transient retries, default 5 |

- Auth: same HIE JWT as HFR search — HS256 token `{key: hfr_username, exp}` signed with
  `hfr_password`, `Authorization: Bearer <jwt>` *(repo: `_generate_jwt`)*. **No new
  credentials in CRM.** The TA's Basic-auth API key/secret pair is a gateway/setup-site
  concern (D3).
- "Test connection" (admin): GET status on a known FID via the gateway; 200 or a 400
  `No Facility Setup found for FID '…'` proves routing + auth; 401/403 flags a
  credential/role problem.

### FR-3 — Trigger and idempotent submission (D2)

- Trigger: **deal Won** for a facility with a valid FID and a purchased package, via
  the established E7 pattern *(repo: `CRM Deal` `on_update` →
  `crm.automation.support_journey.on_deal_update` enqueues a background job)*.
- The async job, per facility:
  1. Re-check FID validity/uniqueness; if invalid → resolve via MFL lookup (FR-1);
     still invalid → `Blocked (needs support)`, no call.
  2. Idempotency guard: an existing request in any of `Submitted / Awaiting / In
     Progress / Blocked (retryable)` for the same FID ⇒ return the existing record,
     **do not post again** (invariant 3; duplicates make `get_provision_status`
     ambiguous — *(TA §4.5)*).
  3. Build payload (FR-4) → `POST {hfr_url}{provision_facility_path}` with Bearer JWT,
     60 s timeout.
  4. Record outcome: 200 → `Submitted`, store returned `facility_setup` document name
     (resolves future ambiguous-upstream states — *(TA §4.4, §4.5)*); 400 →
     `Blocked (needs support)` with the upstream message (validated-field names are
     safe to store); 401/403 → `Blocked (needs support)` + Error Log entry
     `CRMProv Auth`; network/5xx → backoff-retry up to `max_submit_retries`, then
     `Blocked (retryable)`.
- A support action **Re-run provisioning** on `Blocked` records goes through the same
  guard (if a draft already exists, the re-run refuses and tells support to clean the
  stray draft in the Setup app — *(TA §4.5)*).

### FR-4 — Payload construction (CRM → API mapping)

| API field *(TA §4.1)* | Source in CRM | Notes |
|---|---|---|
| `fid` | `CRM Deal Facility.fid` (new, auto-populated) | Tracking key; regex-validated |
| `licence` | Contract/quote licence number | Exact field open — §12 Q3 |
| `tokens_awarded` | Purchased `CRM Token Package.token_quantity` for the facility | From the Opt-In/quote line *(repo: field exists)* |
| `token_expiry_date` | Package/contract end date | ISO `YYYY-MM-DD`; derivation §12 Q4 |
| `admin_email` | `CRM Opt-In Submission.facility_signatory_email` | Verified owner only (invariant 8) |
| `admin_name` | `facility_signatory_name` | Server splits first/middle/last (TA expects the split) |
| `admin_mobile` | `facility_signatory_phone` | |
| `billing_model` | Product/package: `License` or `Token` | Source §12 Q4 |
| `license_expiry_date` | Contract end date | Required iff `billing_model == License` *(TA §4.1)* |
| `facility_name` | `facility_name` | Overrides registry `officialName` |
| `facility_level` | `facility_level` | Drives the upstream template *(TA §4.1)* |
| `county` / `sub_county` | `hfr_county` / `hfr_sub_county` | |
| `hmis_instance` | — | Not sent in MVP; upstream auto-resolves; add later if resolution proves unreliable |

Registry behaviour (upstream looks the facility up by FID; transient registry failure
degrades to caller-supplied data; genuine "not found" is a hard 400) is upstream
behaviour — CRM only surfaces the 400 reason *(TA §4.2, §7)*.

### FR-5 — Status tracking

- Scheduler (cron, `status_poll_minutes`) calls `get_provision_status?fid=…` for every
  non-terminal request *(TA §5)*.
- Map upstream → CRM: `Draft`/no progress → `Awaiting Deployment`; `progress > 0` →
  `In Progress` (store `progress` 0–100, `log`, `error`, `last_attempt`); `Deployed` →
  `Live`; upstream `Error` → `Blocked (needs support)` with the upstream `error` text.
- Ambiguity handling *(TA §4.5, §5)*: "Multiple Facility Setup documents found…" 400 →
  `Blocked (needs support)` with the message verbatim; support resolves in the Setup
  app, then re-runs.
- Polling is idempotent and rate-safe (one call per interval per facility; no polling
  for `Not Provisioned` or `Live`).

### FR-6 — Customer Experience portal (cx-portal)

New read-only section in `FacilityPortal.vue` *(repo: existing sections "Your facility
journey", "Facility Accounts", "Opt-In Requests", "Available Token Packages")* —
proposal: **"Your deployment status"**, one card per facility the session resolves
through OIS User Permissions (same scoping as `get_purchase_context`,
*(repo: `customer_experience.py`)*):

- Status badge with plain-language label + one-sentence next action:
  - `Not Provisioned` → "We're preparing your facility setup." (pre-trigger) / "Action
    needed — our team will contact you." (post-trigger, still not submitted).
  - `Submitted` → "Received. Our setup team is preparing your deployment."
  - `Awaiting Deployment` → "Prepared. Deployment is scheduled — nothing you need to do."
  - `In Progress` → progress bar (`progress`%) + last updated time.
  - `Live` → "Your system is deployed."
  - `Blocked` → "We're resolving an issue. Our team will contact you." (never the raw
    upstream error or 400 detail — invariants 4, 6).
- Data via one new whitelisted read API (e.g. `get_provisioning_status`) returning
  per-facility: status label, progress, last updated, next-action copy. No
  retry/submit actions in the portal (invariants 1, 7).
- Email milestones at: `Submitted`, `In Progress` (first time), `Live`; `Blocked` goes
  to support, customer gets a neutral "we'll be in touch" note — reusing the existing
  branded email pattern *(repo: `crm.api._email`)*. Scope §12 Q5.

### FR-7 — Audit, logging, observability

- New CRM DocType **`CRM Provisioning Request`** (one per facility per deal) is the
  audit record: deal + facility links, `fid`, `status`, upstream `facility_setup`
  document name, `progress`, `last_attempt`, `last_status_check`, redacted request/
  error text, correlation ID, timestamps.
- Every upstream call logs a redacted structured event (no credentials, no raw
  registry PII beyond what the owner already sees) to Error Log under a stable tag
  (`CRMProv`) — consistent with the upstream's own `ExtProv RoleSeed` convention
  *(TA §7)*.

## 7. Proposed data model summary

| Surface | Change |
|---|---|
| `CRM Deal Facility` | + `fid` (Data, site-unique, regex-validated, HFR auto-populated, locked post-submission) |
| `CRM Pre-Qualified Facility` | + `fid` (same rules) — if §12 Q2 confirms |
| `CRM HFR Settings` (single) | + provisioning section (FR-2 fields); no new credentials (D3) |
| `CRM Provisioning Request` (new) | FR-7 audit + state record |
| `hooks.py` | + scheduler entry for the status poll; trigger reuses the E7 Won-handler path (no new doc_events) |
| cx-portal | + `FacilityPortal.vue` section + one whitelisted read API |

No changes to `CRM Opt-In Submission`, `CRM Onboarding Request`, or the payment flow.

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| Security | JWT material from existing settings only; portal responses contain status/progress/copy only; rate-limit the new portal read like other portal APIs |
| Reliability | Submit job idempotent and crash-safe (claim the record before the HTTP call); polling safe to run twice; retries capped with backoff |
| Performance | Submit is async (never blocks the deal save); poll cost ≤ number of non-terminal records per interval |
| Observability | Correlation ID across CRM job, HTTP calls, Error Log, and portal display |
| Privacy | No raw upstream payloads in the portal; redacted logs; retention per CRM audit policy |

## 9. MVP acceptance criteria

1. An HFR-synced facility row shows the FID auto-populated from `facility_fid`; a row
   with only an MFL code resolves its FID via the existing MFL lookup; zero/multiple
   matches leave the row `FID unresolved (support)` and never call the API.
2. Invalid FID input is rejected with the TA-format message; a duplicate FID is
   rejected; the value locks after `Submitted`.
3. With provisioning enabled, a deal Won for a facility (valid FID + package) posts
   exactly one `provision_facility` call with the FR-4 payload and records `Submitted`
   + the returned `facility_setup` name. Re-running does not post a second time.
4. A genuine registry 400 ("No facility found in the registry…") lands in
   `Blocked (needs support)` with the upstream message visible to support, and is not
   retried in a storm.
5. The scheduler transitions a polled record `Draft → In Progress → Live` and the
   cx-portal card reflects each state with correct plain-language copy and progress.
6. The portal never renders credentials, raw payloads, or another facility's state for
   the same session.
7. A test with `provisioning_enabled` off produces no HTTP calls and leaves records in
   `Not Provisioned`.
8. A duplicate-draft 400 from upstream (`Multiple Facility Setup documents found…`) is
   surfaced to support verbatim and blocks until resolved.

## 10. Delivery slices

| Slice | Outcome |
|---|---|
| A | FID field + auto-population from HFR sync/MFL lookup + validation/uniqueness/locking |
| B | Settings section + provisioning client (HIE JWT, configurable gateway paths, timeouts) + `Test connection` |
| C | `CRM Provisioning Request` + deal-Won trigger job + idempotency guard + outcome mapping |
| D | Status poll scheduler + state machine + retry/backoff |
| E | cx-portal "Your deployment status" section + read API + email milestones |
| F | Hardening: audit log, ambiguity handling, e2e tests, runbook (credential rotation, blocked-state SOP) |

## 11. Upstream contract summary *(from TA — binding for the client)*

The proposed public APISIX routes and normalized request/response shapes are
documented in [`cx-portal-provisioning-gateway-api.md`](cx-portal-provisioning-gateway-api.md).
The method URLs below describe the current setup-side implementation; APISIX
publishes the stable `/v1/hmis/...` paths to CRM.

- `POST {base}/api/method/hmis_setup.api.external_provisioning.provision_facility` —
  JSON body §FR-4; 200 `{accepted, facility_setup, status:"Draft", message}`; 400s are
  field-named; 401 on bad credentials. **Creates a Draft; never deploys.**
- `GET …/get_provision_status?fid=<FID>` — 200 `{status, progress, log, error,
  last_attempt}`; 400 on missing/invalid FID, no match, or ambiguous (multiple drafts).
- Auth: direct access uses Frappe Basic API-key authentication with a dedicated
  service user. Current CRM status reads use this directly when the external
  setup credentials in `CRM HFR Settings` are populated; otherwise they use the
  HIE JWT fallback (D3). Submission remains outside the portal flow.
- FID: `^FID-\d{2}-[\w-]+$` (case-insensitive); registry lookup by `fr-code` upstream.
- No dedupe upstream; duplicate drafts ⇒ ambiguous status 400 ⇒ caller must clean up.
- Rotation: regenerate the setup-site API user's keys; old pairs stop immediately
  *(TA §7)*.

## 12. Open questions (before implementation)

Resolved in v0.2: ~~Q1 FID source~~ → D1; ~~Q2 trigger~~ → D2; ~~Q5 gateway auth~~ → D3.
Remaining:

1. **Status API publication.** The setup host returned 403 because
   `get_provision_status` was not whitelisted (checked 2026-10-21). Publish the
   method or the HIE APISIX status route before enabling live status tracking.
2. **FID on Pre-Qualified Facility.** Keep or drop (MVP = Deal Facility only)?
3. **Licence number source.** Which CRM document owns the `LIC-…` value (contract?
   quote? new field on the facility row)?
4. **Billing model + expiry derivation.** Where `License` vs `Token` and the two
   expiry dates come from — token package `billing_period`, contract end, or new
   fields?
5. **Email scope.** Customer emails for all milestones (proposed) or only `Live` /
   `Blocked-neutral`?
6. **Multiple facilities per deal.** Assumed: one provisioning request per facility
   row. Confirm.
7. **FID format confirmation.** Confirm the registry `facility_fid` value matches the
   TA `FID-XX-…` shape (the HFR integration already stores it as `hfr_facility_id`;
   spot-check against a live facility during slice A).
