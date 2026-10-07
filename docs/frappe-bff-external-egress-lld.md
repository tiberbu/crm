# Frappe BFF Security Proposal F360, Careverse, F360 v2 Web

**Audience:** Security, SRE, platform, backend, Next.js, React Native, and QA teams
**Status:** Proposed guideline
**Date:** 2026-10-06

## Security starts where identity lives

The application that owns the user, session, data, and business rules should also own authorization.

This proposal recommends that every Frappe application act as the backend-for-frontend (BFF) for its Next.js and React Native clients. APISIX remains an outbound gateway for Frappe-to-external API traffic. Client applications do not use APISIX as their business API or authorization layer.

The goal is simple: one authenticated identity, one authorization authority, one auditable path.

## Proposed architecture

For the web application, Frappe is a private backend. The browser reaches the public
web edge, not Frappe. Next.js Server Components, Server Actions, and Route Handlers
call Frappe over the private Kubernetes network.

```text
Browser
   │
   ▼
Public web load balancer / ingress
   │                         └─ access logs → Grafana
   ▼
Next.js pods
   │  Server Components / Server Actions / Route Handlers
   ▼
Internal Frappe load balancer or ClusterIP service
   │                         └─ access logs → Grafana
   ▼
Frappe BFF (private; no public route)
  ├─ authentication and sessions
  ├─ authorization and business rules
  ├─ local CRUD and safe projections
  └─ external integration adapters
                         │
                         ▼
                    APISIX egress
                         │
                         ▼
                    External APIs
```

### Boundary decision

| Traffic | Path | Authentication | Authorization owner |
|---|---|---|---|
| Browser → Next.js | Public HTTPS through the web load balancer | Next.js web session | Next.js entry point; Frappe remains the data authorization authority |
| Next.js server → Frappe | Private Kubernetes service or internal load balancer | Forwarded, validated Frappe session context | Frappe |
| React Native → Frappe | Public authenticated mobile edge or managed VPN/private connectivity | OAuth2 Authorization Code + PKCE | Frappe |
| Frappe → local data | In-process | Authenticated Frappe context | Frappe domain service |
| Frappe → external API | Frappe → APISIX → external API | mTLS or service credential | Frappe for user intent; APISIX for egress policy |

APISIX must not translate one shared password into user identity or make decisions about access to business objects.

## SDK rule

`frappe-react-sdk` is a client transport and data-access library. It supports cookie authentication, bearer/API-token authentication, whitelisted method calls, direct DocType CRUD, file upload, and SWR caching. It does not provide object-level authorization.

Therefore:

- In private-web mode, browser components must not point `frappe-react-sdk` directly at Frappe.
  Browser components call the public Next.js application; Next.js server code calls the
  private Frappe service.
- Next.js Server Components and Route Handlers may use a server-only `frappe-js-sdk` or
  `fetch` adapter with `FRAPPE_INTERNAL_URL`. Never expose that URL or a Frappe secret in
  `NEXT_PUBLIC_*` configuration.
- Client-side `useFrappeGetDoc`-style hooks are permitted only behind an allow-listed Next.js
  proxy if client-side refresh is required. They must not expose a generic public proxy for
  arbitrary DocTypes, fields, filters, or methods.
- React Native may reuse the API contract, but must use native secure storage and a system-browser PKCE flow. Do not use `localStorage` for tokens.
- Ordinary local CRUD may use the SDK's typed DocType hooks when Frappe's native permissions fully express the access rule.
- Sensitive workflows must call purpose-built, typed Frappe methods that validate business state and object scope.
- No client contains a Frappe API secret, APISIX credential, or external partner credential.

The SDK is not the security boundary. Frappe is.

### `frappe-react-sdk` CRUD hooks

These hooks are valid Frappe client tools; they are not separate authorization systems.
In private-web mode, they must run in the server-side adapter or call an explicit
Next.js allow-listed proxy. They must not point the browser directly at Frappe:

| SDK hook/API | Frappe operation | Use when |
|---|---|---|
| `useFrappeGetDoc` | Read one DocType document | The user has normal read permission and the document-level scope is correct |
| `useFrappeGetDocList` | List a DocType with fields, filters, and pagination | The server can safely enforce the requested filters, fields, and User Permissions |
| `useFrappeGetDocCount` | Count documents | The count is not a sensitive existence oracle and permissions are applied |
| `useFrappeCreateDoc` | Create a DocType document | Frappe validation, mandatory fields, permissions, and ownership rules are sufficient |
| `useFrappeUpdateDoc` | Update a DocType document | Only permitted fields can change and workflow rules are enforced server-side |
| `useFrappeDeleteDoc` | Delete a DocType document | Deletion is explicitly allowed and cannot bypass retention or business rules |
| `useFrappeGetCall` / mutation call | Call a whitelisted Frappe method | A business action needs server-owned pricing, transitions, external calls, idempotency, or additional authorization |

The hook does not authorize the request. It sends the request to Frappe; Frappe authenticates the session and applies its permission system. Frappe's generated REST API supports document CRUD, and its permission-aware APIs apply Role Permissions and User Permissions when used correctly. Never use `ignore_permissions=True` in a client-facing request path.

Use a purpose-built method instead of generic CRUD when the operation is a business action rather than simple document editing. Examples include approving an invoice, starting payment, changing membership, signing a contract, issuing an OTP, or calling an external registry.

## SDK → Frappe BFF pathway

The BFF is implemented inside the Frappe application. The SDK is the client adapter; it is not a second backend.

### 1. Client setup

For a private web deployment, do not point a browser `FrappeProvider` at Frappe. Use
Server Components for reads and Server Actions or Route Handlers for mutations. The
server-only adapter calls the internal Frappe service and forwards only a validated
Frappe session context. Never put a Frappe API secret or the internal Frappe URL in
browser code or `NEXT_PUBLIC_*` configuration.

Client Components can call a public Next.js Route Handler when interactive refresh is
needed. The Route Handler must use an explicit operation allow-list and then call the
private Frappe service. It must not become a transparent generic Frappe REST proxy.

For React Native, use the Frappe OAuth2 authorization-code flow with PKCE and platform secure storage. Do not assume that a browser-oriented React hook package provides safe native token storage.

### 2. Authentication

In private-web mode, the browser authenticates through the public Next.js application.
Next.js forwards only the validated Frappe session context to the internal Frappe
service; Frappe must validate the session and must never trust an arbitrary user or
role header. For React Native or another direct Frappe client, the SDK delegates
authentication to Frappe and uses the Frappe session or OAuth bearer token.

The Frappe server remains responsible for session validity, CSRF validation for unsafe cookie-authenticated requests, login throttling, and permission evaluation.

### 3. Local read/write paths

```text
Browser interaction
        → Next.js Server Action / Route Handler
        → private Frappe service

server-side Frappe adapter
        → GET/POST /api/resource/{doctype}            (allow-listed)
        → POST      /api/method/{whitelisted.method}  (purpose-built)
```

For the first six operations, Frappe applies its normal DocType permissions, User Permissions, document checks, validation, and controller hooks. The client may provide a document name, fields, filters, or pagination, but those values are never authorization. Frappe must enforce the allowed DocType, fields, scope, and action.

Use `useFrappePostCall` in a permitted client path, or call the same purpose-built
method from the server-side adapter, for business actions. That method is the Frappe
BFF boundary:

```text
Browser → Next.js → private Frappe /api/method/facility.api.start_payment
        ├─ authenticate session/token
        ├─ check role and object scope
        ├─ validate workflow and idempotency
        ├─ read/write local DocTypes
        └─ call external adapter through APISIX if required
```

### 4. External API path

The client never receives the external API credential and never calls APISIX directly:

```text
SDK → Frappe BFF → Frappe integration adapter → APISIX → external API
```

Frappe decides whether the authenticated user may perform the business action. APISIX enforces the egress route, destination, service identity, limits, and partner credential handling. The external response is validated and reduced to a safe Frappe response before it is returned to the client.

### 5. What is visible

For every request, carry one `X-Request-ID` and, where tracing is enabled, one W3C `traceparent` across the Frappe and APISIX legs.

| Leg | Authoritative record |
|---|---|
| Browser/client → Next.js edge | Public load-balancer/ingress access log with route, status, latency, and request ID |
| Next.js → private Frappe | Internal gateway and Frappe request/application logs with method, status, duration, and request ID |
| Frappe authorization | Frappe security/business audit event with allow/deny reason |
| Frappe → APISIX | Frappe integration event with external operation and request ID |
| APISIX → external API | APISIX access log with route, upstream, status, latency, and request ID |

Client browser or mobile network logs are useful for debugging but are not the security audit record because the client is not trusted.

## Is the Frappe SDK the best choice?

**Yes for client-to-Frappe integration; no as a complete authorization-lifecycle solution.**

The Frappe SDK is the best default when Frappe owns the users, sessions, DocTypes, workflows, and business data. It keeps the request path short, uses Frappe's native authentication and CSRF behavior, avoids synchronizing application data into another platform, and lets the BFF enforce authorization next to the data.

It does not by itself provide:

- centralized relationship-based authorization across multiple Frappe applications;
- a policy administration lifecycle;
- delegated access and revocation workflows;
- cross-service permission graphs;
- complete authorization decision auditing; or
- protection from insecure use of generic CRUD hooks.

The recommendation is therefore:

| Client or need | Recommended choice |
|---|---|
| Next.js web application | Server Components/Actions + server-only `frappe-js-sdk` or `fetch`; client hooks only behind an allow-listed Next.js proxy |
| React Native application | Frappe OAuth2 PKCE + native secure-storage adapter; use `frappe-js-sdk` only if the selected version is React Native compatible |
| One Frappe application | Native Frappe roles, User Permissions, DocType permissions, and explicit object checks |
| Multiple applications sharing resource relationships | Add OpenFGA or SpiceDB behind the Frappe BFF |
| Central policy-as-code across heterogeneous services | Evaluate Cerbos |
| Managed policy administration and audit UI | Evaluate Permit.io |

## Authorization alternatives and trade-offs

These tools complement Frappe; they do not replace Frappe as the owner of users or business data.

| Alternative | Strength | Trade-off | Recommendation |
|---|---|---|---|
| Native Frappe authorization | Lowest complexity; no extra service; permissions remain next to the data | More application code for complex relationships; policy consistency across apps must be maintained manually | Default for one Frappe application |
| `frappe-react-sdk` | Fast Next.js integration; session/token support; Frappe API and CRUD hooks | Client library is not an authorization engine; generic CRUD can create BOLA risk; documented token examples must not be copied to mobile | Best web transport layer, with typed BFF methods |
| `frappe-js-sdk` | Lower-level JavaScript client; easier to wrap for non-React clients | Still does not provide authorization lifecycle or object-level policy | Candidate for React Native/Node adapters after compatibility testing |
| OpenFGA | ReBAC for users, facilities, networks, groups, and delegated access; open-source SDK ecosystem | Requires relationship synchronization, consistency design, and another service to operate | Best external option for relationship-heavy authorization |
| SpiceDB/AuthZed | ReBAC, bulk checks, resource lookup, consistency tokens, and strong modeling tools | Adds operational and data-synchronization complexity; some audit capabilities depend on deployment tier | Strong alternative to OpenFGA |
| Cerbos | Policy-as-code PDP with RBAC/ABAC and multiple SDKs | Less natural than ReBAC for large membership graphs; adds a policy service | Use when policy rules matter more than relationship graphs |
| Permit.io | Managed RBAC/ABAC/ReBAC, policy lifecycle, synchronization, and decision logs | SaaS/vendor dependency, data synchronization, and recurring cost | Use when Security requires managed administration and audit UI |
| Casbin | Lightweight embedded RBAC/ABAC library with many language implementations | Policy storage, distribution, audit, and lifecycle remain application responsibilities | Suitable for a small single-service deployment, not the preferred shared platform |

OpenFGA is designed for fine-grained relationship-based authorization and provides SDKs for common languages. [OpenFGA](https://openfga.dev/)
SpiceDB provides relationship checks, bulk checks, resource lookup, and consistency controls. [SpiceDB](https://authzed.com/docs)
Cerbos exposes a policy decision point through HTTP/gRPC and SDKs for JavaScript, Python, Go, and other languages. [Cerbos API](https://docs.cerbos.dev/cerbos/latest/api/index.html)
Permit supports RBAC, ABAC, ReBAC, policy lifecycle, synchronization, and decision logs. [Permit lifecycle](https://docs.permit.io/how-to/sdlc/modeling-implementation-components/)
Casbin supports RBAC, ABAC, multiple languages, policy adapters, and runtime policy management. [Casbin](https://casbin.apache.org/)

## Recommended authorization lifecycle

Start with native Frappe authorization. Add an external authorization engine only when a requirement justifies the extra failure mode and operational cost.

```text
Frappe user/data change
        ↓
Frappe transaction + outbox event
        ↓
OpenFGA or SpiceDB relationship update
        ↓
Frappe BFF permission check
        ↓
Frappe query filtered to authorized objects
```

Frappe remains the source of truth. The external engine stores authorization relationships and answers permission questions; it does not become the source of business records. All relationship grants and revocations must be initiated by Frappe domain services, not by clients.

For sensitive writes, fail closed if the external authorization service is unavailable. For an immediately revoked permission, use the engine's strongest consistency option or perform a final local Frappe check before committing the business transaction.

Do not copy every Frappe role into OpenFGA, SpiceDB, Cerbos, or Permit. Use Frappe for document integrity and workflow, and use an external engine only for authorization concerns that Frappe cannot manage consistently across applications.

## Mandatory Frappe authorization rules

Every request must:

1. Authenticate the user or service.
2. Check the required role or capability.
3. Scope the database query to the user’s tenant, facility, network, or membership.
4. Authorize the exact object before every read or mutation.
5. Return only an explicit field allow-list.

Additional rules:

- Deny by default.
- Never trust client-supplied owner, tenant, role, price, status, or permission fields.
- Validate workflow state before transitions.
- Use idempotency keys for business writes.
- Use safe, uniform responses to reduce ID enumeration.
- Rate-limit login, OTP, search, uploads, exports, and payment actions.
- Treat opaque IDs as identifiers, never as authorization.
- Keep external APIs behind server-side adapters with strict URL and method allow-lists.

Example object-level check:

```python
record = frappe.db.get_value(
    "Facility Case",
    {"name": case_id, "owner_user": frappe.session.user},
    ["name", "status", "progress"],
    as_dict=True,
)

if not record:
    raise_safe_not_found()
```

The authorization scope belongs in the query. Do not fetch by ID and perform an optional ownership check afterwards. This is the primary control against IDOR/BOLA. See [OWASP API Security Top 10](https://api-security.owasp.org/editions/2023/en/0x11-t10/).

## Security hardening and live traffic monitoring

### Private Frappe boundary

The web-facing Frappe BFF is not a public service endpoint. It is exposed as a
Kubernetes `ClusterIP` service or an internal/private load balancer. There is no public
DNS record, public Ingress, or public APISIX route for Frappe.

Kubernetes NetworkPolicy and the cloud security group/firewall allow inbound Frappe
traffic only from the Next.js workload or the internal ingress/load-balancer path.
An Envoy or other sidecar may be added for mTLS and telemetry, but it is not required
to make Frappe private; the private Service/load balancer and network policy provide
that boundary.
Administrative access to the private network is through VPN or an approved private
access mechanism with MFA. VPN is an operator/private-network control; it is not a
replacement for Frappe authentication and authorization.

This prevents direct Internet/Postman access to Frappe. It does not prevent a user from
modifying a browser request to the public Next.js application with Burp Suite. Every
Next.js request must therefore be authenticated, and every Frappe operation must still
perform server-side role, tenant, object, field, and workflow checks.

### Server Component hardening

For the web application:

```text
Browser → public web edge → Next.js Server Component/Action → private Frappe BFF
```

Server Components and server-side adapters keep the Frappe URL, service credentials,
and internal response path out of browser JavaScript. They also prevent the browser from
calling generic Frappe DocType endpoints directly.

They do not make browser requests trusted. A public Next.js Route Handler or Server
Action must use an operation allow-list, safe input validation, no-store/private caching
for user-specific data, and CSRF/session protections appropriate to the chosen session
model. Frappe remains the final authorization authority.

### Grafana monitoring path

Use Grafana as the operational dashboard, with a log backend and metrics backend:

```text
Browser / SDK request
          ↓
Public web load balancer / ingress
          ├─ access logs → log shipper → Loki → Grafana
          ↓
Next.js pods
          ├─ application logs → log shipper → Loki
          ↓
Internal Frappe load balancer / ingress
          ├─ access logs → log shipper → Loki → Grafana
          ↓
Private Frappe service
          ├─ Frappe request/application logs → Loki
          └─ metrics/health → Prometheus → Grafana/Alertmanager

Frappe outbound request → APISIX → external API
          └─ APISIX access logs → Loki → Grafana
```

The public edge dashboard shows traffic from the browser to Next.js. The internal
gateway dashboard shows Next.js-to-Frappe traffic. Frappe logs show the authenticated
principal, method, authorization result, business outcome, and request ID.

Use one server-generated or normalized `X-Request-ID` across the request. Do not trust
an arbitrary client-supplied identity header, and do not log cookies, authorization
headers, tokens, secrets, or full sensitive payloads.

### What happens when Frappe is down

Frappe cannot produce its own application logs while it is unreachable. The gateways
and independent probes provide the evidence instead:

| Condition | What Grafana shows |
|---|---|
| Browser reaches Next.js but Frappe is unavailable | Next.js 502/503/504 and internal gateway upstream failure |
| Frappe pods are down | Internal gateway connection failures and Kubernetes service/pod alerts |
| Frappe is slow | Internal gateway upstream latency and Next.js response latency |
| Next.js is down | Public web edge 502/503/504 or failed external probe |
| DNS/TLS/network failure | External black-box probe failure and load-balancer telemetry |
| Frappe returns an application error | Frappe status, error logs, and request ID |

Add an external black-box probe for the public web URL and an internal probe for the
private Frappe readiness path. The public probe proves user-visible availability; the
internal probe proves whether the web application can reach Frappe. Neither probe should
return credentials, stack traces, dependency details, or regulated data.

The dashboard therefore remains useful even when Frappe produces no logs: the edge and
internal gateway record the attempted request and the failure to reach the upstream.

Minimum Grafana panels and alerts:

- request rate by public route and client;
- Next.js 4xx/5xx and latency;
- internal gateway 502/503/504 and upstream latency;
- Frappe authorization denials and application errors;
- Frappe readiness and pod availability;
- APISIX external upstream failures;
- missing log ingestion and probe failures.

Client browser or mobile network logs remain useful for debugging but are not the
authoritative audit record because the client can be modified.

Record:

- authentication success/failure;
- session creation, expiry, and revocation;
- authorization allow/deny and reason;
- cross-tenant or cross-resource access attempts;
- role and permission changes;
- sensitive reads and business mutations;
- outbound integration status, latency, and failures.

Never log passwords, tokens, secrets, OTPs, raw identity numbers, or full business payloads. Do not use user IDs, document IDs, emails, phone numbers, or IP addresses as unbounded metric labels.

Minimum alerts:

- elevated 5xx, 401, or 403 rates;
- p95 latency above the agreed SLO;
- abnormal authorization-denial spikes;
- external API timeouts or circuit opens;
- failed black-box probes or readiness checks;
- missing telemetry or audit pipeline delay.

## QA security gates

Release approval requires automated evidence that:

| Area | Required test |
|---|---|
| Authentication | Expired, revoked, replayed, and invalid sessions/tokens fail |
| Authorization | User A cannot read or mutate User B’s objects |
| Tenant isolation | Cross-tenant, facility, network, and membership access is denied |
| Enumeration | Unknown and unauthorized IDs have safe equivalent responses |
| Mass assignment | Client cannot change owner, role, price, tenant, or status |
| CRUD exposure | Sensitive generic DocType CRUD is disabled or correctly permissioned |
| CSRF | Unsafe browser requests without a valid CSRF token fail |
| Business abuse | OTP, search, upload, payment, and order flows are rate-limited and idempotent |
| Egress | Only Frappe can call approved APISIX routes and external destinations |
| Leakage | Errors, logs, traces, and responses contain no credentials or sensitive payloads |
| Observability | Every request has a correlation ID and produces usable audit telemetry |

## Security approval requested

Security is asked to approve this as the standard for new applications and as the migration target for existing applications:

1. Frappe is the authentication and authorization authority.
2. Next.js uses secure Frappe sessions; React Native uses OAuth2 PKCE.
3. APISIX is retained for controlled external egress.
4. Local CRUD remains inside the owning Frappe application.
5. Public and internal load-balancer/ingress logs are shipped to Loki and viewed in Grafana; Prometheus and Alertmanager provide health metrics and alerts.
6. The QA gates above are mandatory release criteria.

### References

- [Frappe React SDK](https://github.com/frappe/frappe-react-sdk)
- [Frappe REST API](https://docs.frappe.io/framework/user/en/guides/integration/rest_api)
- [Frappe debugging and monitoring](https://docs.frappe.io/framework/user/en/debugging)
- [Frappe OAuth2](https://docs.frappe.io/framework/user/en/guides/integration/rest_api/oauth-2)
- [Frappe users and permissions](https://docs.frappe.io/framework/user/en/basics/users-and-permissions)
- [Next.js Server and Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components)
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [OWASP API Security Top 10](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
- [OpenFGA](https://openfga.dev/)
- [SpiceDB](https://authzed.com/docs)
- [Cerbos API](https://docs.cerbos.dev/cerbos/latest/api/index.html)
- [Permit authorization lifecycle](https://docs.permit.io/how-to/sdlc/modeling-implementation-components/)
- [Casbin](https://casbin.apache.org/)
