# HMIS setup service: what CRM sends and needs back

**For:** the HMIS provisioning (setup service) team
**From:** CRM / Customer Experience
**Version:** 2 (2026-10-27). Replaces the 2026-10-25 version, which covered the status endpoint only.
**Baseline:** CRM `develop` at `dd06b063`. Statements about current CRM behaviour describe that code. Section 8 lists what CRM changes to meet this contract.
**Related:**
- [`cx-portal-provisioning-gateway-api.md`](cx-portal-provisioning-gateway-api.md)
- [`hmis-token-openmeter-alignment.md`](hmis-token-openmeter-alignment.md)
- [`hmis-implementation-prd.md`](hmis-implementation-prd.md)

## Decisions in this version

| # | Decision | Effect |
|---|---|---|
| D1 | Every facility gets its token balance from OpenMeter only. CRM sends no token amount, token expiry, billing model or token source. | §2.2, §2.3 |
| D2 | CRM sends `auto_deploy: true`. Deployment starts without a manual review step. | §2.1 |
| D3 | `site_url` is the facility's own HMIS address, not a shared instance address. Each site hosts one facility, because a site holds one metering key. | §4 |
| D4 | CRM creates the facility in OpenMeter and issues its site key before the POST. If that fails, nothing is sent. | §2.1 |
| D5 | No tokens before payment. Nothing is granted at provisioning; every token, including bonus and coupon tokens, comes from a paid token invoice. | §2.3 |
| D6 | CRM sends the metering gateway address with the site key, so a new site can reach the gateway at first boot without manual setup. | §2.2, §3 |
| D7 | A site that holds a metering site key is in OpenMeter mode. There is no separate `token_source` flag. | §2.3 |
| D8 | CRM sends no token purchase link, and HMIS shows none. Tokens are bought in the CRM CX portal only. | §2.2 |

## What changed since version 1

| Change | Source | Effect on the setup service |
|---|---|---|
| OpenMeter is the token balance authority | `8068b6a2`, D1, D7 | No token fields in the POST; the site key and gateway address are added (§2) |
| Existing sites get a metering site key | `4822df5b` | New endpoint `update_metering_site_key` (§3) |
| Paid packages are granted on payment | `93231e76`, D5 | Nothing is granted at provisioning |
| Deployment starts automatically | D2 | CRM sends `auto_deploy: true` |
| OpenMeter set up before provisioning | D4, D6 | Every POST carries a valid site key and the gateway address |
| Status-endpoint fields | none | Version 1 requirements stand, now numbered S1–S17, plus D3 (§4) |

Version 1 described only `get_provision_status`. It did not describe the POST, its token fields, the site-key endpoint, or the error strings CRM parses. Sections 2, 3 and 5 add them.

## 1. Connection

| Item | CRM today |
|---|---|
| Base URL | CRM HFR Settings → external provisioning URL. CRM refuses anything that is not `https://`. |
| Auth | HTTP Basic with the API key and secret from the same settings. |
| Tracing | CRM sends `X-Correlation-Id` on every call and logs the returned one with any failure. |
| Calls | `POST provision_facility`, `GET get_provision_status?fid=`, `POST update_metering_site_key` |

**Needed:** echo `X-Correlation-Id` on every response, including errors.

## 2. `POST provision_facility`

### 2.1 When CRM sends it

CRM sends the request when onboarding commits, and again if the user opens the facility before a setup exists. Before each POST, CRM holds a per-FID lock and re-reads status. It only posts when that read confirms no setup.

CRM first sets the facility up in OpenMeter (D4):

1. Create and sync the facility in OpenMeter, keyed by FID. No tokens are granted (D5).
2. Issue the facility's metering site key. Issuing a key revokes any earlier key for that FID.
3. Only then send the POST, with the key, the gateway address and `auto_deploy: true` (D2).

If any OpenMeter step fails, CRM does not send the POST. The portal shows setup as blocked, and CRM retries on the next attempt. The setup service therefore never receives a request without a usable site key.

### 2.2 Fields CRM sends

| Field | Source in CRM | Rule |
|---|---|---|
| `fid` | Facility HFR facility ID | `^FID-\d{2}-[\w-]+$`, case-insensitive |
| `licence` | HFR licence number, else registration number, else looked up from HFR by FID | non-empty |
| `admin_email` | Verified facility signatory, else self-onboarded owner | lowercased, contains `@` |
| `admin_name` | Same source | non-empty |
| `admin_mobile` | Same source | non-empty |
| `auto_deploy` | Always `true` | D2 |
| `metering_site_key` | Issued by the metering app in step 2 above | Always; format `omk2.<FID>.<secret>`; secret |
| `metering_gateway_url` | Metering gateway address configured in CRM (D6) | Always; absolute `https://` URL with no credentials; not secret |
| `facility_name`, `facility_level`, `county`, `sub_county` | HFR facility data | Optional, sent when known |

CRM does **not** send `tokens_awarded`, `token_expiry_date`, `billing_model`, `token_source` (D1, D7) or a token purchase link (D8). v2.1 of the setup service already ignores the first three.

CRM blocks the request itself if any field it must send is missing or invalid, and shows which ones.

### 2.3 Tokens and metering

OpenMeter is the only token balance authority (OpenMeter ADR-003). CRM grants tokens in OpenMeter by FID, and only when a token invoice is paid (D5). A new site therefore starts at 0 tokens until its first payment. HMIS reads its balance through the metering gateway, never from the setup service.

The setup service must:

1. Create no local token balance and no token expiry. Tokens do not expire; only an exhausted balance stops clinical work.
2. Deliver `metering_site_key` and `metering_gateway_url` to the new site in the signed `update_license` push. The site stores the key in a Password field and puts itself in OpenMeter mode (D7).
3. Reject a request without `metering_site_key` or `metering_gateway_url`, naming the field.
4. On a duplicate-FID request, replace the stored key and gateway address with the ones in the request. If the site is already deployed, push them again. CRM revokes the previous key whenever it issues a new one, so keeping the old key would leave the site with a dead key.
5. In the Verification Pass, call the gateway `ping` with the site's key. Fail the deployment with `error_code: "SITE_KEY_NOT_DELIVERED"` unless the reply is `active` for the same FID.

### 2.4 Responses CRM handles

| Response | CRM behaviour |
|---|---|
| 200/202 with `accepted: true` | Submission created. CRM reads `facility_setup`. |
| 200/202 without `accepted: true` | Outcome unknown. CRM re-checks status before any retry. |
| 5xx, 408, 429, network error | Outcome unknown, retryable. Same re-check. |
| Other 4xx | Error, shown to CRM System Managers with the upstream message. |

**Needed:** keep `accepted` and `facility_setup` in every success response, including duplicate-FID responses.

## 3. `POST update_metering_site_key`

For HMIS sites set up before metering. They never send a provisioning request again, so they never receive a key through §2.

- Request: `{"fid": "<FID>", "metering_site_key": "omk2.<FID>.<secret>", "metering_gateway_url": "https://<gateway host>/ingest/v1/"}`
- Expected: 200 or 202 with `accepted: true`, after the signed `update_license` push that stores the key and gateway address is queued.
- The site switches to OpenMeter mode when it stores the key (D7).
- CRM treats HTTP 404 as "the setup service does not offer this method yet", and anything else as a failure to retry on the next run.
- CRM calls it one FID at a time, under the same per-FID lock as provisioning.

## 4. `GET get_provision_status`

CRM polls every 5 minutes while setup is in progress. Version 1's requirements still stand, renumbered here with the screen each field drives.

| # | Field | Type | Drives | Priority | CRM reads it today |
|---|---|---|---|---|---|
| S1 | `site_url` | absolute https URL of the facility's own site, top level | **Open HMIS** button on the live card | Required | Yes (also `site`, `site_name`, `url`, `domain`) |
| S2 | `login_url` | absolute https URL, top level | Sign-in link, if different from S1 | Recommended | Yes |
| S3 | `admin_username` | string, top level | "Sign in with …" | Required | Yes (also `admin_email`, `username`) |
| S4 | `password_setup` | `email_sent` \| `reset_link` \| `set_by_admin` | First sign-in instructions | Required | No |
| S5 | `credentials_sent_to` | masked email | Which inbox to check | Recommended | No |
| S6 | `status` | fixed lowercase enum, below | Phase and stepper | Required | Mapped from known words |
| S7 | `stage` + `stages[]` | current key + ordered `{key, label, state}` | Stepper | Recommended | No |
| S8 | `estimated_completion` | ISO-8601 with offset | "About N min remaining" | Required (S8 or S9) | Yes |
| S9 | `eta_minutes` | integer | Same | Optional | Yes |
| S10 | `started_at` | ISO-8601 with offset | Elapsed time, estimate | Required | Yes |
| S11 | `completed_at` | ISO-8601 with offset | "Live since …" | Recommended | No |
| S12 | `updated_at` | ISO-8601 with offset | "Last updated", stale detection | Recommended | No |
| S13 | `site_health` | `up` \| `down` \| `unknown` | Hide **Open HMIS** when down | Recommended | No |
| S14 | `customer_message` | string safe for customers | Explanation of the current step | Recommended | No |
| S15 | `error_code` | stable string | Failure copy | Required when `failed` | No |
| S16 | `setup_id` | Facility Setup name | Support reference | Recommended | No |
| S17 | `retryable` | boolean | Whether a failure retries itself | Recommended | No |

Rules:

- **Facility address (D3).** `site_url` and `login_url` open the facility's own HMIS site. An address shared by several facilities does not meet S1.
- **One facility per site (D3).** A site holds one metering site key, which carries one FID. The metering gateway identifies the facility from that key. Several facilities on one site would share one key and one balance.
- **Top level.** CRM reads fields from the top level of `message`. Nested blocks such as `login` or `target` may stay, but S1–S3 must also appear at the top level.
- **Ready means signable.** Return `status: "deployed"` only once the administrator can sign in. If the site is up but the owner login failed, return `failed` with `error_code: "OWNER_LOGIN_FAILED"`.
- **Timestamps.** Every time field is ISO-8601 with a timezone offset. Today `last_attempt` is a naive local string.
- **Compatibility.** Keep `progress`, `log`, `error` and `last_attempt`. CRM shows `log` and `error` to its System Managers only.
- **Unknown fields** are ignored by CRM, so new fields can ship one at a time.

### `status` enum

| Value | Meaning | CRM phase |
|---|---|---|
| `draft` | Received, not yet queued | queued |
| `approved` | Accepted, waiting to deploy | queued |
| `queued` | In the deployment queue | queued |
| `deploying` | Site being created | deploying |
| `configuring` | Site up; facility, users and settings being configured | configuring |
| `deployed` | Administrator can sign in | live |
| `failed` | Needs the implementation team | needs attention |
| `cancelled` | Withdrawn | needs attention |

CRM today shows any other word on an existing setup as "deploying", with the raw word named. That is a fallback, not a contract.

### Suggested `error_code` values

`DEPLOY_FAILED`, `TARGET_UNREACHABLE`, `OWNER_LOGIN_FAILED`, `COMPANY_PERMISSION_PENDING`, `PREFLIGHT_INCOMPLETE`, `SITE_KEY_NOT_DELIVERED`. The setup service owns the final list. Each code keeps its meaning once published.

## 5. Conditions CRM parses from error text today

CRM detects these by matching message text in a 400 or 417 response. Both need a structured form.

| Condition | Text CRM matches | CRM shows | Needed instead |
|---|---|---|---|
| No setup for the FID | "No Facility Setup found" | Setup not started | HTTP 200 or 404 with `{"status": "not_found"}` |
| More than one setup for the FID | "Multiple Facility Setup" | Contact the implementation team | HTTP 409 with `{"status": "conflict", "error_code": "DUPLICATE_SETUP"}` |

## 6. Security requirements

1. **No credentials in any response.** Do not return passwords, reset tokens or site keys in `get_provision_status` or any other response CRM receives. CRM never shows, stores or logs credentials. First sign-in uses the welcome email or "Forgot password", reported through S4.
2. **Site key.** `metering_site_key` travels in the request body only. Do not log it, return it, or include it in error messages. Deliver it to the site only in the signed `update_license` push. Store it encrypted on the setup site, never in a JSON field or the deployment log. `metering_gateway_url` is not secret, but it must be `https://` and carry no credentials.
3. **Masking.** `credentials_sent_to` is masked, for example `a***@d***.org`.
4. **Errors.** Error text returned to CRM contains no stack traces, internal hostnames or secrets.
5. **Transport.** HTTPS only. API key pairs can be rotated without a CRM release.

## 7. Example responses for contract tests

Both teams test against these shapes. Values in angle brackets are placeholders.

Not found:

```json
{"message": {"fid": "<FID>", "status": "not_found"}}
```

Queued:

```json
{"message": {"fid": "<FID>", "setup_id": "<setup>", "status": "queued", "progress": 0,
  "started_at": null, "updated_at": "2026-10-25T09:40:00+03:00",
  "customer_message": "Your HMIS site is in the setup queue."}}
```

Deploying:

```json
{"message": {"fid": "<FID>", "setup_id": "<setup>", "status": "deploying", "progress": 45,
  "stage": "practitioners",
  "stages": [
    {"key": "company", "label": "Creating your facility", "state": "done"},
    {"key": "practitioners", "label": "Adding staff", "state": "current"},
    {"key": "settings", "label": "Applying settings", "state": "pending"},
    {"key": "verify", "label": "Final checks", "state": "pending"}],
  "started_at": "2026-10-25T09:40:00+03:00", "updated_at": "2026-10-25T09:52:10+03:00",
  "estimated_completion": "2026-10-25T10:25:00+03:00", "eta_minutes": 33}}
```

Failed:

```json
{"message": {"fid": "<FID>", "setup_id": "<setup>", "status": "failed", "progress": 21,
  "error_code": "OWNER_LOGIN_FAILED", "retryable": true,
  "customer_message": "We are finishing your administrator account. No action is needed.",
  "error": "<internal>", "updated_at": "2026-10-25T10:02:00+03:00"}}
```

Deployed:

```json
{"message": {"fid": "<FID>", "setup_id": "<setup>", "status": "deployed", "progress": 100,
  "started_at": "2026-10-25T09:40:00+03:00", "completed_at": "2026-10-25T10:21:44+03:00",
  "updated_at": "2026-10-25T10:21:44+03:00",
  "site_url": "<https facility site URL>", "login_url": "<https sign-in URL>",
  "admin_username": "<administrator email>", "password_setup": "email_sent",
  "credentials_sent_to": "<masked administrator email>", "site_health": "up",
  "customer_message": "Your HMIS site is ready."}}
```

## 8. CRM changes to meet this contract

CRM `develop` does not yet do the following:

| # | Change | Today on develop |
|---|---|---|
| CRM-P1 | Stop sending `tokens_awarded`, `token_expiry_date`, `billing_model`, `token_source` and `token_purchase_url` | Sends the package quantity, onboarding + 30 days and `billing_model: Token`; with the OpenMeter setting on, also `tokens_awarded: 0`, `token_source` and `token_purchase_url` |
| CRM-P2 | Make OpenMeter the only token source: always issue a site key, and block the POST without one | Behind CRM HFR Settings → Use OpenMeter as the HMIS Token Source, off by default |
| CRM-P3 | Grant nothing at provisioning (D5) | Paid packages are deferred to their invoice. The Free Trial package is retired (patch `add_token_bonus_and_partner_coupon`), but any zero-priced package is still granted when the setup service accepts |
| CRM-P4 | Send `auto_deploy: true` | Not sent |
| CRM-P5 | Change portal copy that says the implementation team reviews and starts deployment | Shown on the status card |
| CRM-P6 | Read S4, S5, S7, S11–S17, `not_found` and `DUPLICATE_SETUP` | Not read |
| CRM-P7 | Send `metering_gateway_url` in `provision_facility` and `update_metering_site_key` (D6) | No gateway address is configured anywhere in CRM or the metering app |

CRM already reads S1–S3, S8–S10 and the `status` words in §4.

The setup service live today is v2.1. [`hmis-external-provisioning-v2-1-crm-changes.md`](hmis-external-provisioning-v2-1-crm-changes.md) lists what CRM changes to work with it. That change does part of CRM-P1, reads S1 and S3 from the nested `login` and `target` blocks, and treats `Deployed` as live only when the owner login exists.

### Outside CRM

| # | Owner | Change |
|---|---|---|
| X1 | Metering app | Add a Metering Gateway URL setting and expose it to CRM through a hook. ADR-002 lists it under OMM-23, but it is not in the code. |
| X2 | Metering app | Remove the zero-priced package grant at provisioning (express paid-tokens plan, D2) |
| X3 | Metering app | Update the HMIS ingest contract: the gateway address arrives through provisioning (D6); OpenMeter mode is set by holding a key, not by `token_source` (D7); the out-of-tokens message has no purchase link (D8) |
| X4 | HMIS | HMIS-H2 switches on key presence (D7). HMIS-H3 shows no purchase link (D8). |

## 9. Rollout order

1. The setup service accepts `metering_site_key`, `metering_gateway_url` and `auto_deploy`, delivers the key and address in `update_license`, and implements §2.3 (§2, §3).
2. The metering app ships X1 to X3; HMIS ships HMIS-H1 (balance pull) and X4.
3. CRM ships CRM-P1 to CRM-P5 and CRM-P7. Steps 1 and 2 must be live first, or new sites cannot reach the gateway.
4. Status fields (§4, §5) and CRM-P6 follow one at a time, in either order.
