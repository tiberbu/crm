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

The CX Portal remains read-only. CRM does not submit new setup records from this
screen. The direct setup credentials must belong to a dedicated service user and
stay server-side; an Administrator login password is not an API key/secret.

## Routes

| Method | Route | Use |
|---|---|---|
| `POST` | `/v1/hmis/provisioning/facilities` | CRM submits a facility for draft setup after the approved commercial trigger and data checks. |
| `GET` | `/v1/hmis/provisioning/facilities/{fid}/status` | CRM reads the deployment state for a facility; the portal uses this read-only projection. |

`fid` is the HFR Facility ID and must match `^FID-\d{2}-[\w-]+$` (case-insensitive).
CRM resolves it from a facility the signed-in user is authorized to view. The
browser does not send an arbitrary FID to the gateway.

## Shared headers

```http
Authorization: Bearer <HIE-JWT>
Accept: application/json
Content-Type: application/json
X-Correlation-Id: <request-correlation-id>
```

For `POST`, CRM also sends an `Idempotency-Key` derived from the CRM facility
and provisioning version. APISIX should forward it and the setup adapter should
return the original result for a duplicate key. It must reject a second request
for the same active FID with `409` even if the caller uses a new key; the current
setup method does not deduplicate drafts.

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
`status`, `progress`, `log`, `error`, and `last_attempt`. The live setup host
returned HTTP 403 saying the method is not whitelisted when checked on
2026-10-21. CRM must show “Not reported” for site health and service-unit
details when those fields are absent and must never infer them from progress
or a Draft status.

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

The CX Portal currently implements the authorized, read-only status use case.
The `POST` shape is documented for the CRM commercial provisioning workflow;
submission remains gated on the approved trigger, complete payload mapping, and
CRM-side idempotency because the current upstream method can create duplicate
drafts. When direct setup-service credentials are configured, that source takes
precedence; otherwise CRM uses the HIE gateway. Until the selected source
publishes the status method, CRM treats missing routes, timeouts, and gateway
errors as “tracking unavailable” and leaves billing and facility access available.
