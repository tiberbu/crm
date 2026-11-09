# Party review: HMIS setup service provisioning API v2.0

**Date:** 2026-11-01
**PR:** #126 (`docs/hmis-setup-service-crm-spec-v2` → `develop`)
**Input:** "External Facility Provisioning API — Contract, Version 2.0" from the HMIS setup service team (shared 2026-11-01). Identifiers in its examples are not copied here.
**Room:** Mary (analyst), John (PM), Winston (architect), Amelia (dev), Sally (UX), Murat (test architect)
**Baseline reviewed:** `crm/api/hfr.py` (`_reported_setup_details`, `_journey_phase`, `_provisioning_journey`, `_auto_submit_external_provisioning_impl`, `_external_submit_error`), `frontend/src/pages/FacilityPortal/FacilitySingleView.vue`, `docs/hmis-provisioning-status-api-requirements.md` (contract v2), `docs/hmis-external-provisioning-v2-1-crm-changes.md`.

## What v2.0 adds, against what CRM does today

| v2.0 item | CRM on PR #126 before this change | Gap |
|---|---|---|
| `auto_deploy` (opt-in, default false) | Not sent (contract v2 CRM-P4 open) | Deployment waits for a manual release |
| POST `auto_deploy_queued`, `owner_user_queued`, `WARNING:` message when the enqueue fails | Ignored; any `accepted: true` is recorded as `created` | A failed enqueue looks like success |
| `completion.{deployment_complete, owner_user_complete, fully_provisioned}`; "do not treat `progress == 100` alone as done" | Live = `Deployed` and `login.status` in Created/Activated/Skipped | Not using the authoritative boolean |
| `Provisioning` = deployment done, owner-user track in flight | Shown as "Deploying" | Wrong phase and copy |
| `target.frontend_url`: "hand this to the end user, not `target.url`" | Site URL order `login.url` → `target.url` → `target.frontend_url` | **Bug:** backend URL shown when `login.url` is empty |
| `steps[]`: 12 named steps with `Pending/Running/Done/Skipped/Failed` | Not read | Portal cannot say which step is running or failed |
| `Failed` when the owner-user track exhausts retries | Detected only from an `[Owner User]` error prefix | Misses the completion/step signals |
| `deployed_on` | Not read | No "Live since" |
| Status `Cancelled` | Generic "needs attention" | No specific copy |
| Inactive/Maintenance instance blocks deployment | Not recognized | Generic failure copy |
| `Facility registry lookup failed (HTTP <code>)` is a 400 | Every 400/417 on POST is cached as a rejection for a year | **Bug:** a registry outage blocks the facility until its details change |
| Polling every 30–60 s | Every 5 min | The portal stays stale through most of a ~15 min auto-deploy |
| `login.password` still returned while `email_sent` is false | Dropped while parsing | Keep dropping; ask again |
| `workflow` block, `hmis_instance` forcing, optional billing fields | n/a | Out of scope (D1 stands; CRM never forces an instance) |

## Decisions

| # | Decision | Owner of the argument |
|---|---|---|
| D-A | When `completion` is present, the phase is live only when `completion.fully_provisioned` is true. The `login.status` rule is the fallback for payloads without `completion`. | Winston |
| D-B | `Provisioning` / `In Progress` with `completion.deployment_complete` true (or `Deployed` without `fully_provisioned`) is the configuring phase: "Creating your administrator account". | Sally, Amelia |
| D-C | Site URL order: `login.url` → `target.frontend_url` → `target.url`. | Amelia |
| D-D | CRM sends `auto_deploy`. A new CRM HFR Settings check, **Review HMIS deployments before they start** (`external_provisioning_manual_review`, default off), sends `auto_deploy: false` when on. The check is inverted because a new Check field reads as 0 on an existing Single record, so "off" must mean the decided behaviour (contract v2 D2) without a patch. | Winston, John |
| D-E | The submission records `deploy_queued`. If auto-deploy was requested and the response says it was not queued (`auto_deploy_queued: false` or a `WARNING:` message), the portal says the implementation team will start deployment. The raw service message is never shown to customers. | Murat |
| D-F | A `Facility registry lookup failed` response is retryable (`unknown`, status-check retry) and is never cached as a rejection. | Murat |
| D-G | `steps[]` drives one line under the four-step stepper: "Step N of 12 · <plain label>" while running, "Stopped at step N of 12 · <plain label>" on failure. Known step names get plain labels; unknown names are shown as sent. Step error text stays in System Manager diagnostics only. | Sally |
| D-H | Owner-login failure is also detected from `status: Failed` with `deployment_complete` true and `owner_user_complete` false, or a `Failed` "Owner User (retry)" step. The `[Owner User]` prefix stays as a fallback. | Amelia |
| D-I | The live card shows "Live since <date>" from `deployed_on`. | Mary |
| D-J | The journey returns `poll_after_seconds`: 60 while deploying or configuring, 300 while preparing or queued. The portal follows it. Hidden tabs still skip polls. | Winston |
| D-K | `Cancelled` and an Inactive/Maintenance instance block each get their own customer copy (needs attention). The instance block is a text match until the setup service sends an `error_code`. | Sally, Mary |
| D-L | `login.password` is still dropped. A test feeds the full v2.0 payload and checks the password appears nowhere in the parsed status or journey. | Murat |

Queued-phase copy follows D-D: with auto-deploy on, "Deployment starts automatically"; with manual review on, the existing "once the implementation team releases it" copy (contract v2 CRM-P5).

## Asks back to the HMIS setup service team

1. Stop returning `login.password` (contract v2 §6.1). CRM never shows it.
2. Name the versions consistently: this document is "v2.0", while CRM's notes call the live service "v2.1".
3. Add an `error_code` for the Inactive-instance block and the owner-user failure (contract v2 S15), so CRM can stop matching text.
4. Return `X-Correlation-Id` on responses (contract v2 §1).

## Out of scope

- The `workflow` block (review trail): not customer-facing.
- Forcing `hmis_instance`: CRM lets the service resolve it.
- Billing fields: D1 stands; v2.0 makes them optional.
- Contract v2 CRM-P1/P2/P3/P7 (metering site key and gateway address): unchanged, still follow the rollout order in contract v2 §9.
