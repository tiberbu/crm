# CX Portal HMIS Provisioning API Contract

**Status:** Proposed HIE APISIX v1 contract  
**Consumers:** CRM provisioning workflow and the signed-in CX Portal  
**Upstream:** HIE APISIX → HMIS setup service

This contract gives the CX Portal a stable, versioned API shape. The upstream
setup-side contract is in [`EXTERNAL_PROVISIONING_API (1).md`](../../EXTERNAL_PROVISIONING_API%20(1).md)
at the bench root. CX Portal status reads use this source precedence:

1. When the `CRM HFR Settings` external setup URL, service API key, and service
   API secret are all populated, CRM calls the setup service status method
   directly using Frappe Basic API-key authentication.
2. Otherwise CRM uses the HIE APISIX status route and existing HIE Bearer JWT.

If any external setup credential field is populated but the set is incomplete,
CRM reports that configuration as incomplete and does not silently fall back to
HIE.

The portal does not send setup requests itself. When the external setup service
is configured, its status RPC checks the status and automatically attempts one
draft submission if the upstream status is `not_submitted` and CRM has every
required value from approved facility, purchase, and administrator records. If
required source data is missing, CRM returns a blocked state with the missing
field names and does not call POST. The direct setup credentials stay
server-side and must belong to a dedicated service user.

## Routes

| Method | Route | Use |
|---|---|---|
| `POST` | `/api/method/hmis_setup.api.external_provisioning.provision_facility` | CRM creates a draft when the status check returns `not_submitted` and all required data is available. |
| `GET` | `/api/method/hmis_setup.api.external_provisioning.get_provision_status?fid={fid}` | CRM checks status before any draft submission and reloads status after an accepted submission. |

Without a complete external setup configuration, CRM uses the HIE gateway for
status reads only. The current HIE fallback does not submit drafts.

`fid` is the HFR Facility ID and must match `^FID-\d{2}-[\w-]+$` (case-insensitive).
CRM resolves it from a facility the signed-in user is authorized to view. The
browser does not send an arbitrary FID to the gateway.

## Shared headers

Direct setup calls use HTTP Basic authentication with the configured Frappe API
key and secret. HIE fallback status calls use the existing Bearer JWT. Both use
`Accept: application/json` and an `X-Correlation-Id`. The setup endpoint does
not deduplicate drafts. CRM serializes requests
by FID, rechecks status before POST, and will not automatically repeat a request
after an ambiguous response because a duplicate draft makes status ambiguous.

## Submit a facility

```http
POST /v1/hmis/provisioning/facilities
```

Request body follows the existing setup contract. CRM builds it from verified
HFR data, the approved facility package, and the verified facility administrator:

```json
{
  "fid": "FID-29-116804-5",
  "licence": "LIC-2026-0001",
  "tokens_awarded": 5000,
  "token_expiry_date": "2027-10-05",
  "admin_email": "admin@example.go.ke",
  "admin_name": "Jane Doe",
  "billing_model": "Token",
  "admin_mobile": "+254712345678",
  "facility_name": "Example Health Centre",
  "facility_level": "LEVEL 3",
  "county": "Nairobi",
  "sub_county": "Westlands"
}
```

Successful submission returns `202 Accepted`. It means a draft was created; it
does not mean the HMIS site has been deployed.

```json
{
  "data": {
    "fid": "FID-29-116804-5",
    "request_id": "SETUP-00042",
    "status": "Draft",
    "accepted_at": "2026-10-20T10:30:00Z"
  },
  "meta": { "correlation_id": "req-123" }
}
```

## Read implementation status

```http
GET /v1/hmis/provisioning/facilities/FID-29-116804-5/status
```

```json
{
  "data": {
    "fid": "FID-29-116804-5",
    "status": "In Progress",
    "progress": 65,
    "last_attempt": "2026-10-20T10:30:00Z",
    "site_status": "Provisioning",
    "service_units": ["Outpatient", "Maternity", "Laboratory"],
    "service_unit_count": 3
  },
  "meta": { "correlation_id": "req-456" }
}
```

`status` is one of `Not Submitted`, `Draft`, `Queued`, `In Progress`, `Deployed`,
or `Error`. `progress` is an integer from 0 to 100 when known. `site_status`,
`service_units`, and `service_unit_count` are optional until the setup service
can provide them. The current v1.2 upstream status method reports only
`status`, `progress`, `log`, `error`, and `last_attempt`. An authenticated GET
probe on 2026-10-21 reached the direct setup status method; a synthetic,
well-formed FID with no draft returned HTTP 417 and
`ValidationError: No Facility Setup found…`. The TA documents HTTP 400 for this
case. CRM normalizes both responses to “Not submitted”. The POST endpoint was
not probed in this pass because it has no upstream deduplication and a valid
request creates a persistent Draft Facility Setup. CRM must show “Not reported”
for site health and service-unit details when those fields are absent and must
never infer them from progress or a Draft status.

The raw `log` and `error` are internal diagnostic fields. The customer portal
must not receive them. CRM may log a redacted correlation ID and error code for
support.

## Error response and retry behavior

```json
{
  "error": {
    "code": "FACILITY_SETUP_NOT_FOUND",
    "message": "No setup request exists for this facility.",
    "retryable": false
  },
  "meta": { "correlation_id": "req-789" }
}
```

| HTTP | Code | CRM behavior |
|---|---|---|
| `400` | `VALIDATION_ERROR` | Mark submission blocked for review; do not retry automatically. |
| `401` / `403` | `AUTHENTICATION_FAILED` / `FORBIDDEN` | Show a neutral unavailable message; log a configuration incident with correlation ID. |
| `404` | `FACILITY_SETUP_NOT_FOUND` | Render “HMIS setup not started” for status reads. |
| `404` | `ROUTE_NOT_PROVISIONED` or an unrecognized gateway 404 | Render “Implementation tracking is not available yet”; keep the rest of the portal usable and allow retry. |
| `409` | `DUPLICATE_FACILITY_SETUP` | Do not resubmit; flag for support reconciliation. |
| `429`, `5xx`, timeout | any | Render temporary unavailability; retry status reads on user action. Submission retries require the same idempotency key and bounded backoff. |

CRM maps gateway errors to customer-safe messages. It does not show gateway HTML,
raw upstream response bodies, setup logs, or credentials.

## Current implementation boundary

The single-facility view has no direct submit control. Its status RPC performs
the automatic draft flow described above when direct setup credentials are
configured. It serializes requests by FID, checks status again before POST, and
will not repost an ambiguous request because the setup endpoint does not dedupe
drafts. The HIE fallback currently reads status only. Missing routes, timeouts,
and gateway errors leave billing and facility access available.
