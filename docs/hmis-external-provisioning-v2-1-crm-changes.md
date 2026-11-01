# HMIS external provisioning v2.1: CRM changes

**Date:** 2026-10-30
**Setup service contract:** HMIS Setup external provisioning v2.1 (`provision_facility`, `get_provision_status`)
**CRM code:** `crm/api/hfr.py`, `frontend/src/pages/FacilityPortal/FacilitySingleView.vue`
**Related:** [`hmis-provisioning-status-api-requirements.md`](hmis-provisioning-status-api-requirements.md) (CRM contract v2), [`cx-portal-provisioning-gateway-api.md`](cx-portal-provisioning-gateway-api.md)

This note covers what CRM changes so it works with the setup service that is live today (v2.1). Contract v2 is what CRM asks the setup service for next. Where they differ, contract v2 wins; see [Against contract v2](#against-contract-v2).

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
- `login` is reduced to `owner_login = {email, status, email_sent}`. **The password is dropped while parsing. It never reaches the status CRM stores, polls or returns** (contract v2 §6.1).
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
- `Created`, email not sent: the credentials email could not be delivered; use "Forgot password".
- `Activated`: the account already existed; keep its current password or use "Forgot password".

`goLiveReady` in the portal now follows the journey phase. A bare `Deployed` no longer counts as go-live while the owner login is pending.

### 4. No temporary password in CRM

The setup service guide lets portals show `login.password` while the credentials email is unconfirmed. CRM does not: contract v2 §6.1 says CRM never shows, stores or logs credentials. When the email was not delivered, the portal points the administrator to "Forgot password". The setup service should stop returning `login.password` (contract v2 §6.1).

## Against contract v2

| Contract v2 item | This change |
|---|---|
| CRM-P1: stop sending billing and token fields | Partly done. `tokens_awarded`, `token_expiry_date` and `billing_model` are no longer sent. With the OpenMeter setting on, `token_source` and `token_purchase_url` are still sent until rollout step 3 (contract v2 §9), when CRM-P1 completes with CRM-P2 and CRM-P7. |
| §2.4: duplicate-FID responses keep `accepted` and `facility_setup` | `idempotent: true` is shown as `already_exists`. |
| §4 "Top level": S1–S3 at the top level | Until they are, CRM reads the site address and sign-in name from `login` and `target`. |
| §4 "Ready means signable" | Applied to v2.1: `Deployed` counts as live only when `login.status` is `Created`, `Activated` or `Skipped`. |
| §4 S15 `OWNER_LOGIN_FAILED` | Until it exists, CRM detects an owner-login failure from `login.status: Failed` or an `[Owner User]` error prefix. |
| §6.1: no credentials in any response | CRM drops `login.password` and offers no way to show it. |

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
