# HMIS provisioning status API: fields CRM needs

**For:** the HMIS provisioning (setup service) team
**From:** CRM / Customer Experience
**Date:** 2026-10-25
**Endpoint:** `GET /api/method/hmis_setup.api.external_provisioning.get_provision_status?fid={FID}`
**Related:**
- [`hmis-implementation-prd.md`](hmis-implementation-prd.md)
- [`cx-portal-provisioning-gateway-api.md`](cx-portal-provisioning-gateway-api.md)

## Why

A facility administrator onboards in CRM. CRM sends the setup request at once. Deployment runs on a separate site. The CX portal checks this endpoint every 5 minutes. It should tell the administrator:

1. where setup is;
2. roughly how long remains;
3. once the site is provisioned, which URL to open and how to sign in.

Today the portal can only say "check the welcome email" and fall back to a configured typical time (1 hour). This is because the response carries none of the details listed below.

## What the endpoint returns today

Observed on 2026-10-25 on the CRM dev site, for five real facilities (identifiers omitted):

```json
{"message": {"status": "Deployed", "progress": 100.0, "log": "<6.8 KB deployment log>", "error": "", "last_attempt": "2026-04-24 11:14:32.468907"}}
{"message": {"status": "Approved", "progress": 0.0, "log": null, "error": null, "last_attempt": null}}
{"message": {"status": "Draft", "progress": 0.0, "log": "<205 chars>", "error": null, "last_attempt": null}}
```

For a facility with no setup, the endpoint returns HTTP 417 `ValidationError` with "No Facility Setup found".

| Field today | What CRM uses it for |
|---|---|
| `status` (`Draft`, `Approved`, `Deployed`, and presumably `Error`) | The phase. Other wordings are guessed. |
| `progress` (0–100) | The progress bar and a progress-based estimate. It stays at 0 until deployment. |
| `last_attempt` | The start time for estimates. It is `null` until a deployment attempt. |
| `error`, `log` | Shown to CRM System Managers only. The log is raw text, so customers get nothing from it. |

## Not available today, but required by CRM

| # | Field | Type | Needed for | Priority |
|---|---|---|---|---|
| 1 | `site_url` | string, absolute https URL | The **Open HMIS** button and link on the live card | **Required** |
| 2 | `login_url` | string, absolute https URL | Direct sign-in link, if different from `site_url` | Recommended |
| 3 | `admin_username` | string | "Sign in with …". Without it, CRM falls back to the admin email it sent. | **Required** |
| 4 | `password_setup` | enum: `email_sent`, `reset_link`, `set_by_admin` | Accurate first-sign-in instructions | **Required** |
| 5 | `credentials_sent_to` | string, masked email | Tells the user which inbox has the welcome or password email | Recommended |
| 6 | `status` as a **fixed, documented enum** | enum (below) | Reliable phase mapping instead of guessed wordings | **Required** |
| 7 | `stage` + `stages[]` | current step and ordered step list | Stepper that matches the real pipeline | Recommended |
| 8 | `estimated_completion` | ISO-8601 datetime with timezone | "About N min remaining" | **Required** |
| 9 | `eta_minutes` | integer | Alternative to #8 if easier | Optional (#8 or #9) |
| 10 | `started_at` | ISO-8601 datetime with timezone | Elapsed time and estimates | **Required** |
| 11 | `completed_at` | ISO-8601 datetime with timezone | "Live since …" | Recommended |
| 12 | `updated_at` | ISO-8601 datetime with timezone | "Last updated" and stale-status detection | Recommended |
| 13 | `site_health` | enum: `up`, `down`, `unknown` | Avoid sending users to a site that is not answering | Recommended |
| 14 | `customer_message` | string, safe to show to customers | Human explanation of the current step or blocker | Recommended |
| 15 | `error_code` | stable string, e.g. `DNS_PENDING`, `DEPLOY_FAILED` | Actionable failure copy. `error`/`log` are internal only. | **Required** when `status=failed` |
| 16 | `setup_id` | string, the Facility Setup name | Support reference | Recommended |
| 17 | `retryable` | boolean | Whether a failure will be retried automatically | Recommended |

Other conventions CRM needs:

- **Timestamps:** use ISO-8601 with a timezone offset (e.g. `2026-10-25T10:00:00+03:00`). Today `last_attempt` is a naive local string.
- **No setup yet:** keep the documented "No Facility Setup found" condition. A structured `{"status": "not_found"}` with HTTP 200 or 404 would be easier to rely on than parsing the message text.
- **Idempotency:** POST `provision_facility` should accept an idempotency key, or deduplicate by FID. CRM now creates the request as soon as onboarding commits, and again if the user opens the facility before it lands. CRM serializes per FID and checks status first, but a lost POST response can still produce a duplicate.

### Proposed `status` enum

| Value | Meaning | CRM phase |
|---|---|---|
| `draft` | Request received, awaiting review | queued |
| `approved` | Reviewed, waiting to deploy | queued |
| `queued` | In the deployment queue | queued |
| `deploying` | Site being created | deploying |
| `configuring` | Site up; facility, users and settings being configured | configuring |
| `deployed` | Ready for sign-in | live |
| `failed` | Needs the implementation team | needs attention |
| `cancelled` | Withdrawn | needs attention |

## Proposed response

```json
{
  "message": {
    "fid": "<FID>",
    "setup_id": "FS-000123",
    "status": "deploying",
    "stage": "create_site",
    "stages": [
      {"key": "review", "label": "Request reviewed", "state": "done"},
      {"key": "create_site", "label": "Creating HMIS site", "state": "current"},
      {"key": "configure", "label": "Configuring facility and administrator", "state": "pending"},
      {"key": "verify", "label": "Final checks", "state": "pending"}
    ],
    "progress": 45,
    "started_at": "2026-10-25T09:40:00+03:00",
    "updated_at": "2026-10-25T09:52:10+03:00",
    "estimated_completion": "2026-10-25T10:25:00+03:00",
    "eta_minutes": 33,
    "completed_at": null,
    "site_url": null,
    "login_url": null,
    "admin_username": "<administrator email>",
    "password_setup": "email_sent",
    "credentials_sent_to": "<masked administrator email>",
    "site_health": "unknown",
    "customer_message": "Your site is being created. This usually takes about an hour.",
    "error_code": null,
    "retryable": null,
    "error": null,
    "log": null,
    "last_attempt": "2026-10-25 09:40:00"
  }
}
```

Once deployed:

```json
{
  "message": {
    "fid": "<FID>",
    "setup_id": "FS-000123",
    "status": "deployed",
    "stage": "verify",
    "progress": 100,
    "started_at": "2026-10-25T09:40:00+03:00",
    "completed_at": "2026-10-25T10:21:44+03:00",
    "updated_at": "2026-10-25T10:21:44+03:00",
    "site_url": "<https site URL>",
    "login_url": "<https sign-in URL>",
    "admin_username": "<administrator email>",
    "password_setup": "email_sent",
    "credentials_sent_to": "<masked administrator email>",
    "site_health": "up",
    "customer_message": "Your HMIS site is ready."
  }
}
```

Keep the existing fields (`status`, `progress`, `log`, `error`, `last_attempt`) for compatibility. New fields can ship one at a time.

## What CRM already does with these fields

CRM reads the following now, so no further CRM release is needed for them:
- `site_url` (also `site`, `site_name`, `url`, `domain`);
- `login_url`;
- `admin_username` (also `admin_email`);
- `eta_minutes`;
- `estimated_completion`;
- `started_at`.

A bare host name gets the https scheme. Non-https or credential-bearing URLs are ignored.

The `status` words `approved`, `deploying`, `configuring`, `failed` and `cancelled` are already mapped. Any other status on an existing setup is shown as deploying, with the raw status named.

`stages[]`, `password_setup`, `credentials_sent_to`, `site_health`, `customer_message`, `error_code`, `completed_at` and `setup_id` need a small CRM follow-up once the field names are agreed.
