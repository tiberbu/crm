# CX Portal HMIS provisioning API contract

**Status:** Implemented CRM adapter contract
**Upstream:** HIE registry and HMIS setup service
**Canonical requirements:** [`hmis-implementation-prd.md`](hmis-implementation-prd.md)

## CRM endpoints

| Method | CRM method | Purpose |
|---|---|---|
| GET | `crm.api.hfr.get_provisioning_status(mfl_code)` | Read status only. This endpoint never creates a draft. |
| POST | `crm.api.hfr.ensure_provisioning_draft(mfl_code)` | Ensure a TA draft exists: read, create only on exact no-draft, then reload. Used by Single Facility initial load and retry. |

CRM first authorizes the signed-in user against the facility portfolio, resolves the facility by MFL and uses its HFR `facility_fid` as the deployment FID. A generic HIE ID is never used as a substitute. The browser cannot choose an arbitrary FID.

## TA requests

When all dedicated external setup settings are populated, CRM uses Frappe Basic API-key authentication over HTTPS:

- `GET /api/method/hmis_setup.api.external_provisioning.get_provision_status?fid={FID}`
- `POST /api/method/hmis_setup.api.external_provisioning.provision_facility`

Every call includes `Accept: application/json` and an `X-Correlation-Id`. Credentials remain server-side. If any external setting is present but the set is incomplete, CRM returns a configuration error and does not silently switch services. HIE status fallback remains read-only.

## Ensure behavior

1. Read status from TA.
2. If a draft exists, return that status without POST.
3. If TA returns its exact documented no-setup validation (HTTP 400 or Frappe HTTP 417, message `No Facility Setup found`), build and validate the request from server-owned CRM records.
4. POST only when payload validation succeeds. Reload status after an accepted response.
5. Auth failures, timeouts, unknown errors, duplicate records and non-matching validation errors do not trigger POST.

A per-FID lock and a second status GET immediately before POST serialize concurrent portal attempts. TA currently has no idempotency key or deduplication. After an ambiguous POST outcome, a later explicit ensure reconciles with GET; it retries only if TA still authoritatively reports no draft. A duplicate TA setup result is sent to support review.

## Payload rules

CRM supplies the TA-required `fid`, `licence`, `tokens_awarded`, `token_expiry_date`, `admin_email`, `admin_name`, `billing_model` and `admin_mobile` fields, plus available facility description/location fields.

- `fid`: verified HFR Facility ID.
- `licence`: HFR facility license number, falling back to registration number.
- `tokens_awarded`: selected facility token package quantity, or `0` when none is selected.
- `billing_model`: `Token` for the CRM token-package flow.
- `token_expiry_date`: facility CRM onboarding date plus 30 calendar days. CRM uses the linked facility row creation date; a lead without a persisted facility row uses the first ensure request date.
- Admin contact: one processed Opt-In facility signatory matching the MFL. CRM will not fabricate or arbitrarily choose a contact.

If required HFR or administrator values are missing or ambiguous, CRM returns `submission.state=blocked` with exact field names and makes no malformed POST. No Won-deal or paid-invoice condition is used as an additional draft gate.

## Status and diagnostics

The upstream contract reports draft/provisioning status and may return `log`, `error`, and `last_attempt`. CRM exposes detailed upstream content only to System Managers, with credentials redacted. Facility users see safe error messages, retry state and actionable missing fields.

CRM records the TA correlation ID and HTTP status in its Error Log. If TA returns only `Internal Server Error`, CRM cannot display a remote traceback that the response did not contain; use the correlation ID to locate the traceback in the TA site's Error Log.

Creating a setup draft does not deploy the facility. A human still reviews and starts deployment in the TA tool.
