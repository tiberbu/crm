# CX Portal HMIS provisioning API contract

**Status:** Implemented CRM adapter contract
**Upstream:** HIE registry and HMIS setup service
**Canonical requirements:** [`hmis-implementation-prd.md`](hmis-implementation-prd.md)

## CRM endpoints

| Method | CRM method | Purpose |
|---|---|---|
| GET | `crm.api.hfr.get_provisioning_status(mfl_code)` | Read status only. This endpoint never creates a draft. |
| POST | `crm.api.hfr.ensure_provisioning_draft(mfl_code)` | Ensure a TA draft exists: read, create only on exact no-draft, then reload. Used by Single Facility initial load and retry, and by the background job queued when self-onboarding commits. |

CRM first authorizes the signed-in user against the facility portfolio, resolves the facility by MFL and uses its HFR `facility_fid` as the deployment FID. A generic HIE ID is never used as a substitute. The browser cannot choose an arbitrary FID.

## TA requests

When all dedicated external setup settings are populated, CRM uses Frappe Basic API-key authentication over HTTPS:

- `GET /api/method/hmis_setup.api.external_provisioning.get_provision_status?fid={FID}`
- `POST /api/method/hmis_setup.api.external_provisioning.provision_facility`
- `POST /api/method/hmis_setup.api.external_provisioning.update_metering_site_key` (requested from the setup service, see "Site keys for existing HMIS sites")

Every call includes `Accept: application/json` and an `X-Correlation-Id`. Credentials remain server-side. If any external setting is present but the set is incomplete, CRM returns a configuration error and does not silently switch services. HIE status fallback remains read-only.

## Ensure behavior

1. Read status from TA.
2. If a draft exists, return that status without POST.
3. If TA returns its exact documented no-setup validation (HTTP 400 or Frappe HTTP 417, message `No Facility Setup found`), build and validate the request from server-owned CRM records.
4. POST only when payload validation succeeds. Reload status after an accepted response.
5. Auth failures, timeouts, unknown errors, duplicate records and non-matching validation errors do not trigger POST.

A per-FID lock and a second status GET immediately before POST serialize concurrent portal attempts. TA currently has no idempotency key or deduplication. After an ambiguous POST outcome, a later explicit ensure reconciles with GET; it retries only if TA still authoritatively reports no draft. A duplicate TA setup result is sent to support review.

## Payload rules

> **Agreed change (2026-10-27):** the rules below describe CRM `develop` today. The agreed contract is in [`hmis-provisioning-status-api-requirements.md`](hmis-provisioning-status-api-requirements.md) (version 2): CRM will send no `tokens_awarded`, `token_expiry_date`, `billing_model`, `token_source` or `token_purchase_url`; it will always send `metering_site_key` and `metering_gateway_url`, plus `auto_deploy: true`; and nothing is granted at provisioning. CRM changes CRM-P1 to CRM-P7 in that spec apply the change.

CRM supplies the TA-required `fid`, `licence`, `tokens_awarded`, `token_expiry_date`, `admin_email`, `admin_name`, `billing_model` and `admin_mobile` fields, plus available facility description/location fields.

- `fid`: verified HFR Facility ID.
- `licence`: HFR facility license number, falling back to registration number.
- `tokens_awarded`: selected facility token package quantity, or `0` when none is selected.
- `billing_model`: `Token` for the CRM token-package flow.
- `token_expiry_date`: facility CRM onboarding date plus 30 calendar days. CRM uses the linked facility row creation date; a lead without a persisted facility row uses the first ensure request date.
- Admin contact: one processed Opt-In facility signatory matching the MFL. CRM will not fabricate or arbitrarily choose a contact.

### OpenMeter as the token source

**CRM HFR Settings → Use OpenMeter as the HMIS Token Source** is off by default. When it is on (openmeter_mediator ADR-003), CRM grants the facility's tokens in OpenMeter under its FID, and HMIS reads its balance there. The request then changes:

- `tokens_awarded` is `0`.
- `token_source` is `openmeter`.
- `token_purchase_url` is the configured Token Purchase URL, or this site's `/cx-portal`.
- `metering_site_key` is the facility's `omk2.<FID>.<secret>` key. CRM gets it from the `crm_issue_hmis_metering_site_key` hook (provided by the OpenMeter Mediator app), only after the fresh status GET confirms no draft exists. The key is sent in this request only. CRM never stores, caches, logs or returns it, and redacts it from upstream error details. The setup service hands it to the site in the signed `update_license` push.
- If no key can be issued, CRM returns `submission.state=blocked` with `missing_fields=["metering_site_key"]` and does not POST.

After every accepted request, whatever the token source, CRM enqueues the `crm_on_hmis_provisioning_submitted` hooks after commit with `fid`, `token_source` and `package_tokens`. The mediator uses this to make the free-plan grant. Under version 2 of the contract no tokens are granted at provisioning (D5); every token comes from a paid token invoice.

### Site keys for existing HMIS sites

A facility whose HMIS site was set up before metering never sends a provisioning request again, so it never receives a key that way. A System Manager runs **Site keys for existing facilities** on the OpenMeter Probe page, which calls `crm.api.hfr.deliver_metering_site_keys` and queues one background job. For each FID that the `crm_list_hmis_sites_needing_metering_key` hook returns, the job, under the same per-FID lock as provisioning:

1. Reads status. `not_submitted` is skipped, because provisioning will carry the key. An unavailable status is a failure, and no key is issued.
2. Gets a key from `crm_issue_hmis_metering_site_key` with `context.purpose = "existing_site"`. The mediator refuses if the facility already has a delivered key, and marks the free plan Skipped, because the facility's balance was awarded before metering.
3. Sends `{"fid": "<FID>", "metering_site_key": "omk2.<FID>.<secret>"}` to `update_metering_site_key`. Version 2 of the contract adds `metering_gateway_url` to this request (CRM-P7). The setup service must reply 200 or 202 with `accepted: true`, after it queues the signed `update_license` push that stores the key on the site. Until the setup service publishes the method, the job reports HTTP 404 for each facility.
4. On acceptance, calls the `crm_on_hmis_metering_site_key_delivered` hooks, and the mediator marks the key Pushed. Anything else leaves it Push pending, and the next run replaces it.

The key travels as in provisioning: never stored, cached, logged or returned. Failures are written to the Error Log as `HMIS metering key not delivered: <FID>`, with upstream details redacted.

If required HFR or administrator values are missing or ambiguous, CRM returns `submission.state=blocked` with exact field names and makes no malformed POST. No Won-deal or paid-invoice condition is used as an additional draft gate.

## Status and diagnostics

The upstream contract reports draft/provisioning status and may return `log`, `error`, and `last_attempt`. CRM exposes detailed upstream content only to System Managers, with credentials redacted. Facility users see safe error messages, retry state and actionable missing fields.

CRM records the TA correlation ID and HTTP status in its Error Log. If TA returns only `Internal Server Error`, CRM cannot display a remote traceback that the response did not contain; use the correlation ID to locate the traceback in the TA site's Error Log.

Creating a setup draft does not deploy the facility. A human still reviews and starts deployment in the TA tool.

## Customer journey

Both endpoints add `journey`, which the portal renders as-is:

```json
{
  "phase": "deploying",
  "headline": "Deploying your HMIS site",
  "detail": "Your HMIS site is being deployed. …",
  "steps": [
    {"key": "request", "label": "Setup request received", "state": "done"},
    {"key": "deploy", "label": "Deploying HMIS site", "state": "current"},
    {"key": "configure", "label": "Configuring facility and administrator", "state": "upcoming"},
    {"key": "live", "label": "Ready to sign in", "state": "upcoming"}
  ],
  "progress": 50,
  "estimate": {"minutes": 10, "source": "progress", "overdue": false, "label": "About 10 min remaining, based on progress so far"},
  "site": null,
  "poll": true,
  "checked_at": "2026-10-25T10:00:00"
}
```

When `phase` is `live`, `site` is `{url, login_url, admin_email, instructions[]}`. `url` is `null` unless TA reported a safe `https://` address. The admin email comes from TA, or else from the verified CRM administrator contact.

### Optional TA status fields CRM reads

TA does not return these yet. CRM uses each one only when it is present:

| Purpose | Accepted names |
|---|---|
| Site address | `site_url`, `site`, `site_name`, `url`, `domain` (a bare host gets `https://`) |
| Sign-in page | `login_url` |
| Admin username | `admin_username`, `admin_email`, `username` |
| ETA | `eta_minutes`, `estimated_minutes_remaining`, `minutes_remaining` (number) or `estimated_completion`, `eta` (datetime) |
| Deployment start | `started_at`, `deployment_started`, `deployment_started_at` (falls back to `last_attempt`) |

**Estimate order:** a TA ETA; then extrapolation from `progress` and the elapsed time since the start; then the CRM **Typical HMIS Setup Time** setting.

**Status words:**

| Phase | TA status words |
|---|---|
| live | `Deployed`, `Live`, `Active`, `Completed`, `Ready`, `Provisioned` |
| needs attention | `Error`, `Failed`, `Cancelled` |
| queued | `Draft`, `Pending`, `Queued`, `Submitted`, `Scheduled` |
| configuring | `Configuring`, `Setting Up`, `Post Deploy`, `Finalizing` |

Any other status on an existing setup record is treated as deploying.
