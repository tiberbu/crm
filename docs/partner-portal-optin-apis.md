# Partner Portal Opt-In & Custom Pricing APIs

**Version:** 1.0  
**Module:** `crm/partner_portal/`  
**API Routes:** `/api/method/crm.partner_portal.*` (and `/api/method/crm.api.partner_portal.*`)  
**Base Protocol:** HTTPS  
**Content-Type:** `application/json`

---

## Overview

The Partner Portal APIs enable external partners and network coordinators to:
1. Negotiate and configure custom Year 1–5 pricing for individual health facilities under an Opt-In Network.
2. Query and search custom Year 1–5 pricing per facility.
3. Complete the deal-won onboarding workflow to enroll a facility into a network, attach custom Year 1–5 rates, and dispatch an opt-in invitation notification that leads into the CareverseHIMS contract signature flow.

---

## Architecture & Data Alignment

The APIs integrate directly with ERPNext's native pricing engine and Tiberbu CRM's multi-year Opt-In architecture:

- **Network Scope (`CRM Opt-In Network`):** Identifies the partner network via its six-digit public `partner_id`, network `name`, or `slug`.
- **Facility Master (`CRM Pre-Qualified Facility`):** Represents the pre-qualified health facility identified by its unique `mfl_code` (Master Facility List code) or document name.
- **Facility Membership (`CRM Facility Membership`):** Child table linking the facility to the partner network:
  - `price_list_overrides_json`: Stored JSON map (`{"1": "PL-Y1", "2": "PL-Y2", ...}`) holding effective selling Price Lists for Years 1 through 5.
  - `price_list_override`: Retained legacy pointer to Year 1's Price List.
  - `invite_email_queue`: Link to `Email Queue` tracking the invitation dispatch.
  - `invite_sent_at`: Timestamp of invitation dispatch.
  - `status`: Membership status (`Active`, `Opted In`, `Declined`).
- **ERPNext Pricing (`Price List` & `Item Price`):** When partners specify custom numeric rates, facility-specific selling price lists (`Custom - <MFL> - Year <Y>`) and corresponding `Item Price` records are provisioned or updated automatically.

---

## Endpoints

### 1. Configure Facility Custom Pricing (POST)

Configures or updates custom Year 1–5 pricing for a facility under a partner network. Operates idempotently.

- **Method:** `POST`
- **Path:** `/api/method/crm.partner_portal.configure_facility_pricing` (or `/api/method/crm.partner_portal.pricing.configure_facility_pricing`)
- **Headers:**
  - `Content-Type: application/json`
  - `X-Idempotency-Key`: *(Optional)* Client idempotency UUID/string.

#### Request Payload

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `facility` | `string` \| `dict` | Yes | Facility MFL code, name, docname, or dict (`{"mfl_code": "1001", "facility_name": "St. Jude Clinic", "keph_level": "Level 3"}`). |
| `partner_id` | `string` | Yes | 6-digit Partner ID (e.g. `"106191"`) or network name/slug. |
| `pricing` / `price_lists` | `dict` \| `list` | Yes | Pricing configuration for Years 1 to 5 (named Price Lists or numeric rates). |
| `idempotency_key` | `string` | No | Optional idempotency key in payload. |
| `currency` | `string` | No | Currency code (defaults to `"KES"`). |
| `contact_name` | `string` | No | Facility contact person name. |
| `contact_email` | `string` | No | Facility contact email. |
| `contact_phone` | `string` | No | Facility contact phone. |

#### Example 1: Standard Price Lists

```json
{
  "facility": "1001",
  "partner_id": "106191",
  "pricing": {
    "1": "Negotiated Year 1",
    "2": "Negotiated Year 2",
    "3": "Negotiated Year 3",
    "4": "Negotiated Year 4",
    "5": "Negotiated Year 5"
  },
  "idempotency_key": "pl-cfg-1001-20261026"
}
```

#### Example 2: Negotiated Custom Rates (creates facility Price Lists & Item Prices)

```json
{
  "facility": {
    "mfl_code": "12345",
    "facility_name": "Hope Medical Centre",
    "keph_level": "Level 4"
  },
  "partner_id": "106191",
  "pricing": {
    "1": 25000,
    "2": 26500,
    "3": 28000,
    "4": 29500,
    "5": 31000
  }
}
```

#### Success Response (`200 OK`)

```json
{
  "message": {
    "success": true,
    "message": "Custom Year 1-5 pricing successfully configured.",
    "facility": {
      "name": "5ls7figodk",
      "facility_name": "Hope Medical Centre",
      "mfl_code": "12345",
      "keph_level": "Level 4"
    },
    "network": {
      "name": "bahari-health",
      "partner_id": "106191",
      "display_name": "Bahari Health Network",
      "slug": "bahari-health"
    },
    "price_lists": {
      "1": "Custom - 12345 - Year 1",
      "2": "Custom - 12345 - Year 2",
      "3": "Custom - 12345 - Year 3",
      "4": "Custom - 12345 - Year 4",
      "5": "Custom - 12345 - Year 5"
    },
    "pricing_by_year": [
      {
        "year_number": 1,
        "price_list": "Custom - 12345 - Year 1",
        "item_code": "CV-HIMS-KEPH-4",
        "rate": 25000.0,
        "monthly_rate": 25000.0,
        "annual_rate": 300000.0,
        "currency": "KES"
      },
      {
        "year_number": 2,
        "price_list": "Custom - 12345 - Year 2",
        "item_code": "CV-HIMS-KEPH-4",
        "rate": 26500.0,
        "monthly_rate": 26500.0,
        "annual_rate": 318000.0,
        "currency": "KES"
      }
    ]
  }
}
```

---

### 2. Fetch / Search Facility Custom Pricing (GET)

Allows portal users to search and retrieve Year 1–5 custom pricing for a facility.

- **Method:** `GET` (or `POST`)
- **Path:** `/api/method/crm.partner_portal.get_facility_pricing` (or `/api/method/crm.partner_portal.pricing.get_facility_pricing`)

#### Query Parameters

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `facility` | `string` | No | Specific facility MFL code, facility name, or docname. |
| `search` | `string` | No | Search query across facility names and MFL codes. |
| `partner_id` | `string` | No | Optional Partner ID or network slug filter. |
| `year` | `integer` | No | Optional filter for a specific year (1 to 5). |

#### Example: Specific Facility Lookup

```http
GET /api/method/crm.partner_portal.get_facility_pricing?facility=12345&partner_id=106191
```

#### Example: Search by Name

```http
GET /api/method/crm.partner_portal.get_facility_pricing?search=Hope
```

#### Success Response (`200 OK`)

```json
{
  "message": {
    "success": true,
    "facility": {
      "name": "5ls7figodk",
      "facility_name": "Hope Medical Centre",
      "mfl_code": "12345",
      "keph_level": "Level 4"
    },
    "network": {
      "name": "bahari-health",
      "partner_id": "106191",
      "display_name": "Bahari Health Network"
    },
    "membership_status": "Active",
    "price_lists": {
      "1": "Custom - 12345 - Year 1",
      "2": "Custom - 12345 - Year 2",
      "3": "Custom - 12345 - Year 3",
      "4": "Custom - 12345 - Year 4",
      "5": "Custom - 12345 - Year 5"
    },
    "pricing_by_year": [
      {
        "year_number": 1,
        "price_list": "Custom - 12345 - Year 1",
        "item_code": "CV-HIMS-KEPH-4",
        "rate": 25000.0,
        "monthly_rate": 25000.0,
        "annual_rate": 300000.0,
        "currency": "KES"
      }
    ],
    "total": 1
  }
}
```

---

### 3. Deal-Won Opt-In Journey API (POST)

Adds a facility under the partner network with custom Year 1–5 pricing and immediately triggers the opt-in journey by queuing the branded invitation notification containing the secure onboarding URL.

- **Method:** `POST`
- **Path:** `/api/method/crm.partner_portal.deal_won` (or `/api/method/crm.partner_portal.deal.deal_won`)
- **Headers:**
  - `Content-Type: application/json`
  - `X-Idempotency-Key`: *(Optional)* Client idempotency UUID/string.

#### Request Payload

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `facility` | `string` \| `dict` | Yes | Facility MFL code, name, or dictionary (`{"mfl_code": "...", "facility_name": "...", "keph_level": "..."}`). |
| `partner_id` | `string` | Yes | 6-digit Partner ID or network name/slug. |
| `price_lists` / `pricing` | `dict` \| `list` | No | Year 1–5 custom pricing or price lists (falls back to network default if omitted). |
| `contact_email` / `facility_email` | `string` | Yes | Facility representative email address. |
| `contact_name` / `contact_person` | `string` | Yes | Facility representative full name. |
| `contact_phone` | `string` | No | Facility representative phone number. |
| `send_email` | `boolean` \| `int` | No | Whether to dispatch invitation email (`1` by default). |
| `idempotency_key` | `string` | No | Client idempotency key. |

#### Example Request

```json
{
  "facility": {
    "mfl_code": "29841",
    "facility_name": "St. Luke Comprehensive Hospital",
    "keph_level": "Level 4"
  },
  "partner_id": "106191",
  "contact_person": "Dr. Sarah Kimani",
  "contact_email": "s.kimani@stluke.example.com",
  "contact_phone": "+254712345678",
  "price_lists": {
    "1": 28000,
    "2": 30000,
    "3": 32000,
    "4": 34000,
    "5": 36000
  },
  "idempotency_key": "deal-won-29841-v1"
}
```

#### Success Response (`200 OK`)

```json
{
  "message": {
    "success": true,
    "message": "Facility successfully enrolled in network with custom pricing and opt-in invitation dispatched.",
    "deal_won": true,
    "facility": {
      "name": "68lstuad4r",
      "facility_name": "St. Luke Comprehensive Hospital",
      "mfl_code": "29841",
      "keph_level": "Level 4"
    },
    "network": {
      "name": "bahari-health",
      "partner_id": "106191",
      "display_name": "Bahari Health Network",
      "slug": "bahari-health"
    },
    "membership": {
      "name": "68lg70q41j",
      "status": "Active",
      "contact_name": "Dr. Sarah Kimani",
      "contact_email": "s.kimani@stluke.example.com",
      "contact_phone": "+254712345678",
      "invite_sent_at": "2026-10-26 21:00:00",
      "invite_email_queue": "EMQ-00219"
    },
    "invitation_url": "https://crm.tiberbu.app/facility-onboarding?network=bahari-health&facility=St.+Luke+Comprehensive+Hospital",
    "price_lists": {
      "1": "Custom - 29841 - Year 1",
      "2": "Custom - 29841 - Year 2",
      "3": "Custom - 29841 - Year 3",
      "4": "Custom - 29841 - Year 4",
      "5": "Custom - 29841 - Year 5"
    },
    "pricing_by_year": [ ... ],
    "email_sent": true,
    "email_error": null
  }
}
```

---

## Downstream Signature Flow

Upon receiving the invitation email, the facility contact follows this path:
1. Contact clicks the link in email: `/facility-onboarding?network=<slug>&facility=<facility_name>`.
2. Requests one-time passcode (OTP) delivered to their verified email/phone.
3. Enters OTP to authenticate and access their facility profile.
4. Reviews the negotiated Year 1–5 rates (pulled directly from `price_list_overrides_json`).
5. Agrees to terms and completes digital signature sign-off.
6. The subscription and contract are provisioned and transition the membership to `Opted In`.

---

## Idempotency & Safety

- **Cache-Backed Idempotency:** Any request providing an `idempotency_key` or `X-Idempotency-Key` header caches its completed response for 24 hours. Repeating calls with the same key immediately return the cached payload without re-running side effects.
- **Natural Idempotency:** Even without an explicit key, re-submitting an existing facility updates the existing record instead of creating duplicate facilities or memberships.
- **Opted-In Immutability:** Once a facility completes the opt-in journey and its membership reaches status `Opted In`, its price list overrides are protected against arbitrary replacement.

---

## Automated Unit Tests

A comprehensive test suite exercises all endpoints and error cases:

```bash
bench --site cr-dev.tiberbu.app run-tests --module crm.tests.test_partner_portal
```

Covered test scenarios:
- `test_configure_facility_pricing_standard_pricelists`
- `test_configure_facility_pricing_custom_rates`
- `test_configure_facility_pricing_idempotency`
- `test_get_facility_pricing_search_and_retrieval`
- `test_deal_won_api_full_flow`
- `test_deal_won_idempotency`
- `test_deal_won_validation_guards`
- `test_crm_api_partner_portal_router_exports`
- `test_resolve_network_by_partner_id_and_slug`
- `test_resolve_or_create_facility`
