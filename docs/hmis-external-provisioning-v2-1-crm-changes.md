# HMIS external provisioning v2.1: CRM changes

**Date:** 2026-10-30
**Setup service contract:** HMIS Setup external provisioning v2.1 (`provision_facility`, `get_provision_status`)
**CRM code:** `crm/api/hfr.py`, `frontend/src/pages/FacilityPortal/FacilitySingleView.vue`
**Related:** [`hmis-provisioning-status-api-requirements.md`](hmis-provisioning-status-api-requirements.md) (CRM contract v2), [`cx-portal-provisioning-gateway-api.md`](cx-portal-provisioning-gateway-api.md)

This note covers what CRM changes so it works with the setup service that is live today (v2.1). The setup service team's later contract document, "External Facility Provisioning API v2.0" (shared 2026-11-01), describes the same live service; see [Setup service API v2.0 (2026-11-01)](#setup-service-api-v20-2026-11-01).  Its v2.1 / v2.2 revision is in [Setup service API v2.1 / v2.2](#setup-service-api-v21--v22-2026-11-01). Contract v2 is what CRM asks the setup service for next. Where they differ, contract v2 wins; see [Against contract v2](#against-contract-v2).

## What changed in the setup service

| Area | v1.x (what CRM was built against) | v2.1 |
|---|---|---|
| Required request fields | `fid`, `licence`, `tokens_awarded`, `token_expiry_date`, `billing_model`, `admin_email`, `admin_name`, `admin_mobile` | `fid`, `licence`, `admin_email`, `admin_name`, `admin_mobile` |
| Billing fields | Validated and pushed to the HMIS tenant | Ignored; billing belongs to the independent metering system |
| Owner administrator | Created as a practitioner during deployment | Separate System User created **asynchronously** (`provision_owner_user`), plus an `Owner User (retry)` deploy step at 21% |
| Duplicate FID | No idempotency | Returns the existing record with `idempotent: true` |
| Status response | `status`, `progress`, `log`, `error`, `last_attempt` | Adds `target {instance, url}`, `login {email, url, status, email_sent, password?}`, `deployed_on`, `facility_setup` |
| Terminal success | `Deployed` | `Deployed` **and** `login.status` is `Created` or `Activated` |

These responses were checked against the live setup service from the dev site on 2026-10-30. Identifiers are omitted.

- `provision_facility` with only `fid` and `licence` → HTTP 417 `Missing required field(s): admin_email, admin_name, admin_mobile.` No billing field is listed.
- `provision_facility` with a malformed FID → HTTP 417 `... does not look like a valid FR code (FID-XX-...)`.
- `get_provision_status` for an unknown FID → HTTP 417 `No Facility Setup found for FID ...` (unchanged).
- `get_provision_status` for an existing Draft returns `target` and `login` (`login.status: null`, `email_sent: false`). It also returns an undocumented `target.frontend_url`.

## CRM changes

### 1. Provisioning request (`_build_external_provisioning_payload`)

- CRM no longer sends or requires `tokens_awarded`, `token_expiry_date`, `billing_model` or `license_expiry_date`. `_token_expiry_from_onboarding_date` is removed.
- The required fields are `fid`, `licence`, `admin_email`, `admin_name`, `admin_mobile`. The admin contact is still the accepted Opt-In signatory or the OTP-verified self-onboarding owner. `admin_email` is lower-cased.
- The OpenMeter token source path still adds `token_source`, `token_purchase_url` and the `metering_site_key`. These belong to the metering integration, not the v2.1 billing fields. It no longer forces `tokens_awarded: 0`. The metering hooks still receive `package_tokens` from the selected package.
- Previously rejected requests are fingerprinted by payload. Because the payload changed, facilities blocked only by the old billing validation retry on their next ensure.
- An `idempotent: true` acceptance is reported as `already_exists`, not `created`.

### 2. Status parsing (`_reported_setup_details`)

- Site address: `login.url`, then `target.url`, then `target.frontend_url`.
- `login` is reduced to `owner_login = {email, status, email_sent, password_available}`. **The password is dropped while parsing. It never reaches the status CRM stores, polls or returns.** Only whether one is on offer is kept; see section 4.
- `login.email` becomes the sign-in name shown on the portal.
- A `Failed` deployment whose error starts with `[Owner User]` sets `owner_user_failed`.

### 3. Setup journey (`_journey_phase`, `_provisioning_journey`)

| Setup service state | Portal phase | Stepper |
|---|---|---|
| `Draft` | Request received | request ✓, deploy current |
| `In Progress` (including the 21% owner retry step) | Deploying | deploy current |
| `Deployed` + `login.status` `Created` / `Activated` / `Skipped` | Live | all done |
| `Deployed` + `login.status` null | Configuring: "Creating your administrator account" (keeps polling) | configure current |
| `Deployed` + `login.status` `Failed` | Needs attention: "Administrator account needs attention" | configure ✗ |
| `Failed` with an `[Owner User]` error | Needs attention | configure ✗ |
| `Failed`, any other error | Needs attention | deploy ✗ |
| `Deployed` with no `login` block (older service) | Live (unchanged behaviour) | all done |

`Skipped` means the setup record had no admin email, which only happens with drafts created before v2.0. The site is usable, so the portal shows the generic sign-in steps.

The third sign-in instruction follows the owner login:

- `Created`, email sent: use the password in the credentials email.
- `Created`, email not sent, password on offer: the facility administrator can view the temporary password once (section 4), then change it.
- `Created`, email not sent, no password: use "Forgot password", or contact Network Support if no reset email arrives.
- `Activated`: the account already existed; keep its current password or use "Forgot password".

`goLiveReady` in the portal now follows the journey phase. A bare `Deployed` no longer counts as go-live while the owner login is pending.

### 4. One-time view of the temporary password (decided 2026-11-01)

The setup service returns `login.password` while its credentials email is undelivered. Both the credentials email and "Forgot password" depend on mail that a new HMIS site may not be able to send yet, so a first sign-in could otherwise be impossible without support. CRM therefore shows the password **once**, to the facility's HMIS owner. Decisions P-1 to P-9: `_bmad-output/hmis-provisioning/implementation-artifacts/party-review-owner-password-one-time-view-2026-11-01.md`.

- **Polled status:** carries `journey.site.credentials = {status, email_sent, password_available, owner_email_masked, viewed_on, viewed_by_you, can_view}`. Never the password.
- **On offer** only when the site is live, `login.status` is `Created`, `email_sent` is false and a password is present.
- **Who:** the signed-in portal user whose verified email equals `login.email`. CRM sent that address as `admin_email`: the accepted Opt-In signatory or the OTP-verified self-onboarded owner. Other portal users see that the administrator (masked email) can view it. System Managers get no view either.
- **`POST crm.api.hfr.reveal_hmis_owner_password(mfl_code)`:** rate-limited (5 per hour). Under a per-FID lock, it refuses if the FID and setup record already have a `Viewed` record, fetches the password from `get_provision_status` server to server, inserts and commits a `CRM HMIS Credential View` record (who, when, setup record; no password), then returns `{email, password, viewed_on}`. If the fetch fails or the email has since been sent, nothing is recorded.
- **Portal:** a confirm step ("shown one time only"), then a dialog with the sign-in email, the password and **Copy**. Escape and the backdrop do not close it. **Close** stays disabled until "I have copied and saved this password" is ticked. The browser's leave-page warning is on while it is open. The password is cleared from memory on close, and the card then says when it was viewed, with a link to Network Support.
- **Lost password:** a System Manager sets the `CRM HMIS Credential View` record to `Re-armed`, which allows one more view. The audit row is kept.

## Against contract v2

| Contract v2 item | This change |
|---|---|
| CRM-P1: stop sending billing and token fields | Partly done. `tokens_awarded`, `token_expiry_date` and `billing_model` are no longer sent. With the OpenMeter setting on, `token_source` and `token_purchase_url` are still sent until rollout step 3 (contract v2 §9), when CRM-P1 completes with CRM-P2 and CRM-P7. |
| §2.4: duplicate-FID responses keep `accepted` and `facility_setup` | `idempotent: true` is shown as `already_exists`. |
| §4 "Top level": S1–S3 at the top level | Until they are, CRM reads the site address and sign-in name from `login` and `target`. |
| §4 "Ready means signable" | Applied to v2.1: `Deployed` counts as live only when `login.status` is `Created`, `Activated` or `Skipped`. |
| §4 S15 `OWNER_LOGIN_FAILED` | Until it exists, CRM detects an owner-login failure from `login.status: Failed` or an `[Owner User]` error prefix. |
| §6.1: credentials in responses (amended 2026-11-01) | CRM drops `login.password` from the polled status and shows it once to the owner through `reveal_hmis_owner_password`. |

## Configuration and deployment

- No new settings or migrations. The existing CRM HFR Settings external provisioning URL, key and secret are used.
- The setup service must be on v2.1. Against a v1.x service, CRM's request now omits fields that v1.x required, and v1.x rejects it with a validation error. CRM shows that error in the submission panel.

## Verification

- Python unit tests (`test_hmis_provisioning_journey`, `test_hfr_provisioning_status`, `test_hmis_token_source`): 73 tests, all pass on the test site.
- Playwright `frontend/playwright.facility.config.ts`: all 10 facility single view tests pass, including the three owner-login journeys (configuring → live, undelivered email points to "Forgot password", owner failure). The 6 `facility-onboarding-network` tests fail on `develop` without this change, because the "Start your onboarding" button they click no longer exists.
- Frontend unit tests: 233 pass.
- Live read-only check from the dev site (2026-10-30, before the password display was removed): the new parsing was run against the real setup service for every facility with an FID. No password appears in any parsed status.

## Not covered yet

- No facility on the dev site has reached `Deployed` under v2.1 yet. The live `Created` / `Activated` / `Failed` states are covered by unit and mocked UI tests only. Re-run `frontend/e2e/proof/hmis_provisioning_live.spec.ts` once one does.

## Setup service API v2.0 (2026-11-01)

The setup service team shared "External Facility Provisioning API — Contract, Version 2.0". It names the live service v2.0, while this note calls it v2.1 (raised with that team). The party review and decisions D-A to D-L are in `_bmad-output/hmis-provisioning/implementation-artifacts/party-review-provisioning-api-v2-0-2026-11-01.md`.

### What v2.0 adds that CRM now uses

| v2.0 item | CRM behaviour |
|---|---|
| `auto_deploy` | CRM sends `auto_deploy: true`. CRM HFR Settings → **Review HMIS Deployments Before They Start** sends `false` instead, leaving the record as a Draft for the implementation team. The setting is off by default, so a site that has not saved it deploys automatically (contract v2 D2). |
| `auto_deploy_queued` and the `WARNING:` message on a failed enqueue | Recorded as `submission.deploy_queued`. A requested deploy that was not queued is logged ("External HMIS auto-deploy not queued") and remembered for 7 days per FID; the queued phase then says the implementation team will start deployment. The setup service's own message is never shown to customers. |
| `completion.fully_provisioned` | When present, the only "live" signal. `Deployed` or progress 100 alone is not live. |
| `Provisioning` (deployment done, owner login in flight) | With `completion.deployment_complete`, shown as Configuring: "Creating your administrator account". |
| `target.frontend_url` | Site address order is now `login.url`, then `target.frontend_url`, then `target.url` (the backend address, last resort). |
| `steps[]` (12 named steps) | The setup card shows "Step N of 12 · <plain label>" while deploying, or "Stopped at step N of 12 · <plain label>" on failure. Only step names and states are kept; step error text stays in System Manager diagnostics. |
| Owner-user failure | Also detected from `Failed` with `deployment_complete` true and `owner_user_complete` false, or a failed "Owner User (retry)" step. |
| `deployed_on` | "Live since <date>" on the live card. |
| Polling 30–60 s | The journey returns `poll_after_seconds`: 60 while deploying or configuring, 300 while preparing or queued. Hidden tabs still skip checks. |
| `Cancelled`; Inactive/Maintenance instance block | Own copy: "Setup was cancelled"; "HMIS server paused" (matched on the error text until an `error_code` exists). |
| `Facility registry lookup failed (HTTP …)` (a 400) | Treated as an outage: retryable, never cached as a rejection. "No facility found in the registry" is still a rejection. |
| `login.password` | Dropped while parsing; shown once to the owner on request (section 4). |

Not used: the `workflow` block, forcing `hmis_instance`, and the optional billing fields (contract v2 D1).

### Configuration and deployment

- `bench migrate` adds the CRM HFR Settings check. No data patch.
- The request fingerprint now includes `auto_deploy`, so changing the setting lets a previously rejected facility retry once.

### Verification (2026-11-01)

- Python: `test_hmis_provisioning_api_v2_0` (23 new) with `test_hmis_provisioning_journey`, `test_hfr_provisioning_status` and `test_hmis_token_source`: 96 tests pass. The wider onboarding, portal, facility and HMIS suites (261 tests) show the same 20 failures with and without this change, all in `test_facility_onboarding`, `test_partner_portal` and `test_cx_onboarding_e2e`.
- Playwright `frontend/playwright.facility.config.ts`: all 12 facility single view tests pass against the built bundle, including the running step with 60 s polling, "Live since", and the stopped step. Two FID tests were fixed to scope their locator to the header ID strip; they failed on the baseline build too.
- `yarn test:run`: 241 pass.
- Live read-only check from the dev site: status for every facility with an FID was parsed with the new code (GET only). The live service returns `completion`; no password appears in any parsed status or journey.

## Setup service API v2.1 / v2.2 (2026-11-01)

The setup service team shared the contract again as "Version 2.1", with change notes for v2.1 and v2.2. The versions are now numbered in the document itself, which closes the naming question above. The party review and decisions V22-A to V22-E are in `_bmad-output/hmis-provisioning/implementation-artifacts/party-review-provisioning-api-v2-2-2026-11-01.md`.

| Change | CRM behaviour |
|---|---|
| v2.1 removes `tokens_awarded`, `token_expiry_date`, `billing_model`, `license_expiry_date` | Already not sent. A test pins it. |
| v2.2: `auto_deploy` defaults to true | No change. CRM always sends `auto_deploy`; an explicit `false` is now the only way **Review HMIS Deployments Before They Start** keeps a Draft, so CRM must keep sending it. |
| §4.5: an idempotent re-post never starts deployment | An idempotent response with a queued status (e.g. `Draft`) after CRM asked for auto-deploy is recorded as not queued (`submission.deploy_queued: false`, 7-day flag), so the portal says the implementation team will start deployment instead of "starts automatically". |
| §5: a malformed FID is a 400 on the status call | CRM checks the FID against the service's pattern (`^FID-\d{2}-[\w-]+$`) first. A malformed FID is not sent; the portal shows "This facility's HFR Facility ID is not in the expected format" and no support Error Log is written on each refresh. |
| Validation errors documented as 400 | Frappe 15 raises `ValidationError` as 417. CRM treats 400 and 417 the same. |

Still asked of the setup service team: confirm `token_source`, `token_purchase_url` and `metering_site_key` are accepted and never written to the deployment log; an `error_code` for the instance block and owner-user failure; `X-Correlation-Id` on responses. The earlier ask to stop returning `login.password` is withdrawn (section 4: shown once to the owner).

Deployment: Python only; no migration or setting.

Verification (2026-11-01): `test_hmis_provisioning_api_v2_2` (9 new) with the v2.0, journey, status, token source and facility ID suites: 121 tests pass. Full CRM suite (797 tests): the failures with this change are a subset of those without it (all in checkout, customer experience, onboarding and other suites that do not touch provisioning).
