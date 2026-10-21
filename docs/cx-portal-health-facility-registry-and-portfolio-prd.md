# Product Requirements Document (PRD)
## Multi-Facility Portfolio Management, Identity Governance & Health Facility Registry Integration in Tiberbu Customer Experience Portal

**Document Reference:** `PRD-CX-PORTFOLIO-002`  
**System Boundary:** `apps/crm` (Backend APIs, Frappe DocTypes, Vue 3 Frontend) + Health Facility Registry (HFR) API  
**Status:** Under Product & Engineering Review  
**Target Release:** Customer Experience (CX) Portal v2.2  
**Author:** Tiberbu Product & Engineering Pair  
**Date:** 2026-10-18  

---

## 1. Executive Summary

The Tiberbu Customer Experience (CX) Portal is the self-service operating environment for healthcare providers, clinic directors, medical superintendents, and healthcare proprietors across Kenya. Through this portal, providers manage digital health operations, monitor Care Token capacity, reconcile billing, and connect to accredited partner networks (e.g., CHAK, MEDS).

Recent customer feedback and operational audits identified five critical UX, architectural, and domain issues:
1. **Alphabetical Hierarchy Distortion ("A.P. Embakasi" Effect):** The system erroneously promotes whichever facility sorts first alphabetically (or was first inserted, such as *A.P. Embakasi*) to the status of primary organization and default target for all actions, obscuring the true parent customer entity (*Zuhri Medicare Limited*) and treating sibling facilities inequitably.
2. **Missing Per-Facility Attribution:** The portal aggregates token balances, recent orders, and invoices at a global level without visibly attributing the affiliated network, recent token purchase history, and outstanding invoices to each specific facility.
3. **Absence of a "My Profile" View with National ID Governance:** Users have no dedicated profile page to inspect their verified identity credentials, specifically their **Kenyan National ID Number**, contact details, and registered practice entities.
4. **Frictional Facility Discovery (Manual Entry vs. ID-on-File):** When onboarding additional clinic branches, the user is forced to manually re-enter 5-digit MFL codes or FIDs, ignoring the fact that their National ID is already verified on file and can automatically discover all registered facilities from the national Health Facility Registry (HFR) in a single click.
5. **Deprecated Terminology:** Continued usage of deprecated or confusing acronyms (`KMHFR`, `KHFMR`) instead of the official, statutory designation: **Health Facility Registry**.

This PRD establishes the comprehensive product requirements, data models, UX architecture, and API contracts to resolve these deficiencies into an enterprise-grade multi-facility portfolio management experience.

---

## 2. Root Cause Analysis (RCA)

### 2.1 The "A.P. Embakasi" Hierarchy Distortion
- **Observed Behavior:** In multi-facility provider accounts, the portal header, profile badge, top-up modal, and calculator default to "A.P. Embakasi". The user feels that the system creates an "unhealthy hierarchy" where one facility appears to own the account.
- **Codebase Root Cause:**
  1. In `crm/api/facility_onboarding.py` (lines 1757–1759):
     ```python
     customer_target = _text(facilities[0].get("facility_name")) if facilities else account_email
     customer = existing_customer or _ensure_customer(customer_target, commit=False)
     ```
     When an onboarding batch with multiple facilities is first processed, the ERPNext `Customer` entity is named after the first facility in the list (`facilities[0]`, e.g. "A.P. EMBAKASI") rather than the customer's legal operating name or practice identity.
  2. In `crm/api/website_redirect.py` (lines 918, 952):
     ```python
     primary_deal = cust_deals[0]
     ...
     "organization": cstr(primary_deal.get("organization") or customer),
     ```
     The first deal returned without explicit sorting becomes `primary_deal`, and its organization becomes the entire account's display organization.
  3. In `frontend/src/pages/FacilityPortal/FacilityPortal.vue` (lines 249, 273–280):
     `selectedFacility` fell back to `allFacilities.value[0] || null`.
     Whenever a general action was triggered, it arbitrarily executed against `allFacilities[0]`.

### 2.2 Unattributed Financial & Network Data
- **Observed Behavior:** Invoices and orders are presented in a disconnected billing tab. Clinic managers operating multiple branches cannot see at a glance: *Which facility bought tokens last week? Which facility has an overdue invoice? Which network accredits this specific facility?*
- **Codebase Root Cause:**
  - `_customer_invoices` in `website_redirect.py` queried `Sales Invoice` filtered only by `customer`, ignoring `crm_token_facility_mfl` even though the column exists on `Sales Invoice`.
  - `_customer_orders` queried `Sales Order` without propagating the facility display name or network binding to the facility list rows.
  - The frontend data table contained columns for level, MFL, status, and tokens, but lacked explicit columns or drawers for **Affiliated Network**, **Recent Purchase History**, and **Facility Invoices**.

### 2.3 Absence of "My Profile" & National ID on File
- **Observed Behavior:** There is no "My Profile" navigation item. A facility director cannot verify what National ID number the system has stored for them.
- **Codebase Root Cause:**
  - Navigation was restricted to Dashboard, Facilities, Pricing, Billing, HFR Sync, and Support.
  - The user's National ID was stored in transient onboarding sessions or buried in `CRM Opt-In Submission.raw_json` and `CRM Deal.cx_onboarding_identity_ref` without a first-class user profile readout or update endpoint.

### 2.4 Frictional Facility Discovery vs. ID-Based Query
- **Observed Behavior:** Adding a facility requires the user to remember and type their 5-digit MFL code.
- **Codebase Root Cause:**
  - The DHA national registry API supports `_hfr_facilities_for_owner(owner_id_number)` which returns *all* health facilities owned by or registered under a verified citizen's National ID.
  - The portal modal only offered a text input searching by MFL Code or Registration Number, completely neglecting the National ID saved on the user's profile.

### 2.5 Inconsistent Nomenclature
- **Observed Behavior:** References to `KMHFR` and `KHFMR` scattered across headers, status pills, and modals.
- **Standard Requirement:** In alignment with Kenya Digital Health Agency (DHA) and Ministry of Health standards, the official entity is the **Health Facility Registry (HFR)**.

---

## 3. Product Principles & Non-Negotiable Invariants

1. **Strict Entity Separation (Tenant vs. Facility):**
   - The **Customer / Organization** is the legal parent entity (e.g., *Zuhri Medicare Limited* or *Dr. Jane Doe Practice*).
   - **Facilities** are sibling operational nodes under that parent entity (e.g., *A.P. Embakasi*, *A.I.C Mbooni*, *Zuhri Medicare*).
   - No facility may ever be treated as the "parent" or "owner" of other facilities. No alphabetical favoritism.
2. **First-Class Per-Facility Financial Attribution:**
   - Every Care Token purchase, quotation, sales order, and sales invoice MUST be linked to a specific facility via `crm_token_facility_mfl`.
   - Every facility row in the portfolio MUST explicitly expose its **Affiliated Network**, its **Recent Token Purchase**, and its **Outstanding / Paid Invoices**.
3. **Separate Local Search from Registry Discovery:**
   - The facility portfolio and Ctrl+K search MUST find local portfolio facilities by name. MFL, FID, and registration numbers are not local search terms.
   - Health Facility Registry discovery MAY use a verified National ID to find owner-linked branches. Its manual lookup MUST support MFL, FID, and registration number with the identifier type shown explicitly.
   - The user's National ID remains visible in My Profile and is used only for the registry owner-discovery workflow.
4. **Universal Terminology:**
   - Every UI label, tooltip, table header, and notification must use **Health Facility Registry** (or "HFR" where abbreviation is necessary). `KMHFR` and `KHFMR` are strictly forbidden.
5. **Least Privilege & Data Integrity:**
   - A user may only discover, view, and link facilities returned by the Health Facility Registry for their National ID saved on the user profile or validly proved ownership.

---

## 4. User Personas & Core Journeys

### Portal implementation note (2026-10-20)

- Local facility search is name-only. Identifier lookup belongs in HFR discovery.
- Selecting a facility opens a dedicated single-facility view with its registry identity, network, outstanding invoices, invoice-linked payments, token orders, and HMIS deployment status.
- Facility linking resolves a six-digit Partner ID. Leaving the field empty uses `facility_onboarding_default_partner_id` from CRM Opt-In Settings.
- Provisioning status is read from the external setup service when its URL and dedicated API key/secret are configured in CRM HFR Settings; otherwise CRM uses `GET /v1/hmis/provisioning/facilities/{fid}/status` through the HIE APISIX gateway with HIE Bearer JWT. CRM resolves the FID from an authorized portfolio facility; the browser sends only its local MFL key to the CRM endpoint. See [CX Portal HMIS Provisioning API Contract](cx-portal-provisioning-gateway-api.md) and the bench handoff [`EXTERNAL_PROVISIONING_API (1).md`](../../EXTERNAL_PROVISIONING_API%20(1).md).
- The external provisioning contract currently reports setup status, progress, log, error, and last attempt. It does not report service-unit inventory or site URL health. The portal labels service-unit count as unavailable until that API is extended; it does not infer deployment completion from Draft status.

| Persona | Role | Key Needs in CX Portal |
| :--- | :--- | :--- |
| **Dr. Salim (Healthcare Proprietor)** | Owner of 3 medical centres in Nairobi & Makueni | Wants an executive overview of his practice entity (*Zuhri Medicare Limited*), equal visibility into all 3 clinics without one dominating, clear invoice status per clinic, and the ability to link new clinics using his National ID on file. |
| **Nurse In-Charge / Clinic Manager** | Operational Lead at a Level 2 Dispensary | Needs to know the current token balance and recent purchase date for *her specific clinic branch*, download invoices for her clinic, and verify Health Facility Registry accreditation status. |
| **Faith-Based Network Coordinator (e.g. CHAK)** | Network Account Manager | Needs assurance that the facility's network affiliation (*CHAK Partner Network*) is prominently displayed on each facility record, ensuring correct negotiated rebate pricing. |

### Journey A: Multi-Facility Portfolio Inspection
1. User logs into `/cx-portal`.
2. The sidebar displays their practice organization: **Zuhri Medicare Limited** (not an arbitrary clinic branch).
3. The Facilities table renders all clinics as equal portfolio rows:
   - Facility Name & Location
   - **Network** (e.g. `CHAK Partner Network`)
   - **KEPH Level** (e.g. `Level 2 Dispensary`)
   - **MFL Code** (with 1-click copy)
   - **Health Facility Registry Status** (`Live on HFR`)
   - **Care Tokens & Active Plan**
   - **Recent Token Purchase** (e.g. `1,000 tokens (Starter) on 15 Oct 2026`)
   - **Facility Invoices** (e.g. `KES 17,400 Due` with direct `[Pay]` action)
   - **Actions** (`Top Up`, `Calculator`, `Launch HMIS`)

### Journey B: Profile Verification & ID Inspection
1. User clicks **"My Profile"** in the left navigation sidebar.
2. The user sees their verified credentials:
   - Full Legal Name
   - Primary Email & Contact Number
   - **Kenyan National ID Number on File** (e.g., `••••••••` with verified checkmark)
   - Legal Organization / Practice Name
   - Linked Facilities Count & Network Affiliations
3. If an ID was not previously recorded, the user can provide and verify their National ID.

### Journey C: Zero-Input Facility Discovery via Health Facility Registry
1. User clicks **"+ Add Facility"** or navigates to **"Health Facility Registry Sync"**.
2. The primary prompt announces:
   > *"We found your National ID on file: **ID ••••••••**. Click below to automatically discover all health facilities registered under your ownership."*
3. User clicks **"🔍 Search Facilities by My National ID"**.
4. The system queries `_hfr_facilities_for_owner("••••••••")` via the national HFR API.
5. The UI displays matching facilities:
   - Facilities already in the portfolio are badged as `Already Linked`.
   - Newly discovered facilities are badged as `New Facility Available`.
6. User selects the new facility and clicks **"Link Facility to Portfolio"** with zero manual MFL or FID typing required.
7. Optional fallback: If a user needs to search for an institution-owned facility, an accordion allows searching by MFL Code or Registration Number.

---

## 5. Detailed Functional Requirements

### 5.1 Architecture & Entity Hierarchy
- **REQ-ARC-01: True Organization Identity Resolution:**
  - The portal MUST resolve the legal Customer name (`Customer.customer_name` or primary organization) as the account header, NOT the name of the first alphabetically sorted facility.
  - If a Customer record was historically created with a facility name, the system must provide an organization override derived from `CRM Deal.organization` or allow editing in My Profile.
- **REQ-ARC-02: Neutral Facility Sorting & Filtering:**
  - The Facilities view MUST sort neutrally (by default: Most Recently Active, or sortable by Name, KEPH Level, Token Balance, or Status).
  - No facility card or row shall receive disproportionate visual weight or permanent "selected" hero status merely because of alphabetical position.
  - Quick actions from global headers (e.g. `🪙 Top Up`) MUST prompt the user to choose *which* facility they are topping up if multiple facilities exist, rather than silently defaulting to the first facility.

### 5.2 Per-Facility Attribution
- **REQ-ATT-01: Affiliated Network Display:**
  - Each facility record MUST display its specific network affiliation (e.g. `CHAK Partner Network`, `MEDS Network`, or `CareVerse Direct`).
  - Network badge styling should reflect accredited partner status.
- **REQ-ATT-02: Recent Token Purchase Tracking:**
  - Each facility record MUST display its most recent token transaction:
    - Date of purchase (e.g. `15 Oct 2026`)
    - Package name & tokens added (e.g. `Starter Tier • +1,000 Tokens`)
    - Order / Reference ID (e.g. `SO-2026-00042`)
    - If no purchase has been made yet, display `No previous purchases • Free Trial Active`.
- **REQ-ATT-03: Per-Facility Invoice Attribution & Prioritized M-Pesa Settlement:**
  - Invoices MUST be associated with their specific facility using `Sales Invoice.crm_token_facility_mfl` (or mapped from `Sales Order.crm_token_facility_mfl`).
  - The Facilities table MUST display an **Invoices** column or quick badge:
    - Overdue / Open: `KES 17,400 Due • Pay M-Pesa →` (opens M-Pesa Paybill settlement directly for that facility's invoice).
    - Settled: `All Invoices Paid ✓`.
    - No Invoices: `Zero Balance`.
  - In the **Billing & Invoices** view, every invoice card and order row MUST display which facility it belongs to with facility name, MFL code, and clinic icon.

- **REQ-PAY-01: Prioritized M-Pesa Paybill Integration:**
  - In alignment with Kenyan healthcare standard payment practices, M-Pesa Paybill is the primary, first-class payment method across the CX portal:
    - **Business Number (Paybill)**: Prominently displayed with 1-click copy badge.
    - **Account Number**: Automatically set to the specific `Invoice Number` (e.g., `ACC-SINV-2026-00020`) or `Facility MFL Code`, with 1-click copy badge.
    - **Exact Amount**: Displayed in KES with 1-click copy badge.
    - **Step-by-Step Guidance**: Clear 4-step instructions: (1) Select Lipa na M-Pesa -> Paybill, (2) Enter Business No, (3) Enter Account No, (4) Enter Amount & PIN.
    - **M-Pesa Transaction Confirmation / Verification**: An input field allowing the clinic proprietor to paste their 10-character Safaricom transaction reference (e.g., `SB65A1TU7X`) to immediately mark or verify payment for automated reconciliation.
    - Alternative options: Online Card / STK Push and Bank Wire Transfer retained as secondary accordions.

### 5.3 "My Profile" Page & National ID Governance
- **REQ-PRF-01: Navigation Menu Addition:**
  - Add **"My Profile"** (`👤 My Profile`) as a permanent primary item in the persistent left navigation sidebar.
- **REQ-PRF-02: Identity Card & Fields (Masked National ID by Default):**
  - Display user information:
    - **Full Name** (from `User.full_name` or `CRM Opt-In Submission.facility_signatory_name`)
    - **Email Address** (read-only login identity)
    - **Phone / Mobile Number** (with edit/save capability)
    - **Kenyan National ID Number** (`id_number`):
      - **Masked by Default**: The National ID MUST be masked on display (e.g. `••••••10` or `28••••10`) for privacy protection.
      - **Reveal Toggle**: An eye icon (`👁️`) allows the authenticated user to toggle between masked and full unmasked view.
      - **Verification Badge**: Display `● Verified Citizen (Client Registry)`.
      - **Update / Save Action**: Allows the user to provide or update their National ID if missing or updated.
- **REQ-PRF-03: Practice & Entity Details:**
  - Display Organization Name (e.g., *Zuhri Medicare Limited*).
  - Display total count of registered facilities in the portfolio.
  - Display primary network partner lead contact.

### 5.4 Health Facility Registry (HFR) Sync via National ID
- **REQ-HFR-01: 1-Click ID Discovery Workflow:**
  - On the **Health Facility Registry Sync** page and inside the **"+ Add Facility"** modal:
    - Check if the user has a National ID on file.
    - If present, show a high-visibility discovery card:
      > **"Quick Sync via National ID on File"**  
      > Registered ID: `[National ID]`  
      > `[ 🔍 Discover My Facilities on Health Facility Registry ]`
  - Triggering this button calls backend `lookup_facilities_by_owner_id(id_number)`.
- **REQ-HFR-02: Automatic Candidate Comparison:**
  - Compare results returned from the national API against facilities already present in the user's portfolio.
  - Distinctly flag:
    - `Already in Portfolio`: disabled or linked indicator.
    - `Available to Link`: prominent `[ + Add to Portfolio ]` button.
- **REQ-HFR-03: 1-Click Linking Action:**
  - Clicking `[ + Add to Portfolio ]` automatically invokes `add_facility_from_hfr` with the selected facility's MFL code, pre-qualifying it, creating the `CRM Facility Membership`, and linking it to the active customer account without requiring manual input.
- **REQ-HFR-04: Manual Search Fallback:**
  - Retain an expandable secondary section: *"Searching for an institutional facility not tied to your National ID? Search by MFL Code or Registration Number"*.

### 5.5 Terminology Standardization
- **REQ-TRM-01: Absolute Replacement of KMHFR/KHFMR:**
  - Every string in `FacilityPortal.vue`, backend docstrings, API response keys, and notifications MUST be purged of `KMHFR` and `KHFMR`.
  - Use **Health Facility Registry** in all customer-facing text:
    - `KMHFR Status` -> `Health Facility Registry Status`
    - `Live on KMHFR` -> `Live on Health Facility Registry`
    - `KMHFR Registry Sync` -> `Health Facility Registry Sync`
    - `KMHFR Live` -> `Health Facility Registry Active`
    - `DHA Kenya Master Health Facility Registry (KMHFR)` -> `National Health Facility Registry (HFR)`

---

## 6. Technical Specifications & API Contracts

### 6.1 Backend API Extensions (`crm/api/customer_experience.py` & `website_redirect.py`)

#### 1. `get_user_profile()`
- **Endpoint:** `crm.api.customer_experience.get_user_profile`
- **Method:** `GET`, `POST` (whitelisted, authenticated portal user)
- **Response Payload:**
  ```json
  {
    "success": true,
    "data": {
      "user_id": "salim@tiberbu.com",
      "full_name": "Dr. Salim Ahmed",
      "email": "salim@tiberbu.com",
      "mobile_no": "+254712345678",
      "national_id": "••••••••",
      "national_id_verified": true,
      "organization": "ZUHRI MEDICARE LIMITED",
      "primary_network": "CHAK Partner Network",
      "facility_count": 3
    }
  }
  ```

#### 2. `update_user_profile(national_id, mobile_no, organization)`
- **Endpoint:** `crm.api.customer_experience.update_user_profile`
- **Method:** `POST`
- **Parameters:**
  - `national_id`: string (validated against Kenyan National ID regex `^\d{6,10}$`)
  - `mobile_no`: string (validated via phonenumbers)
  - `organization`: string (optional legal practice name)
- **Action:** Updates `User` custom fields / Contact and propagates identity reference to linked Deal records.

#### 3. `lookup_facilities_by_owner_id()`
- **Endpoint:** `crm.api.customer_experience.lookup_facilities_by_owner_id`
- **Method:** `POST`
- **Logic:**
  - Resolves user's verified `national_id` from profile/session.
  - Calls `crm.api.facility_onboarding._hfr_facilities_for_owner(national_id)`.
  - Annotates each returned record with `already_linked: boolean` by cross-referencing user's existing `CRM Facility Membership` and `CRM Deal Facility` records.
- **Response Payload:**
  ```json
  {
    "success": true,
    "data": {
      "national_id": "••••••••",
      "facilities": [
        {
          "fid": "FID-47-120942-5",
          "mfl_code": "12094",
          "name": "A.P. EMBAKASI",
          "county": "Nairobi",
          "subcounty": "Embakasi East",
          "level": "Level 2 Dispensary",
          "owner_type": "Private Practice",
          "already_linked": true
        },
        {
          "fid": "FID-17-109043-3",
          "mfl_code": "10904",
          "name": "A.I.C MBOONI SUB HEALTH CENTRE",
          "county": "Makueni",
          "subcounty": "Mbooni",
          "level": "Level 3 Medical Centre",
          "owner_type": "Faith-Based Organization",
          "already_linked": true
        },
        {
          "fid": "FID-47-993821-1",
          "mfl_code": "19938",
          "name": "ZUHRI MEDICARE WESTLANDS CLINIC",
          "county": "Nairobi",
          "subcounty": "Westlands",
          "level": "Level 2 Dispensary",
          "owner_type": "Private Practice",
          "already_linked": false
        }
      ]
    }
  }
  ```

#### 4. Enhanced `get_portal_context()` Payload
Enhance `crm.api.website_redirect.get_portal_context` to embed per-facility financial and purchase history:
- Under each item in `account.facilities`:
  ```json
  {
    "facility_name": "A.P. EMBAKASI",
    "mfl_code": "FID-47-120942-5",
    "keph_level": "Level 2 Dispensary",
    "network": "CHAK Partner Network",
    "membership_status": "Active",
    "go_live": true,
    "token_package": "Free Community Care",
    "token_quantity": 400,
    "recent_purchase": {
      "order_id": "SO-2026-00012",
      "date": "2026-10-15",
      "package_name": "Free Community Care",
      "tokens": 400,
      "amount": 0.0
    },
    "invoices": {
      "has_outstanding": false,
      "outstanding_amount": 0.0,
      "open_invoice_name": null
    }
  }
  ```

---

## 7. Frontend UI Architecture & Wireframes

### 7.1 Sidebar Navigation Structure
```text
+---------------------------------------+
|  [T] Tiberbu CareVerse                |
|      HMIS Enterprise                  |
+---------------------------------------+
|  📊  Dashboard                        |
|  🏥  Facilities                       |
|  💳  Plans & Pricing                  |
|  📄  Billing & Invoices               |
|  🔄  Health Facility Registry Sync    |
|  👤  My Profile             [NEW]     |
|  💬  Network Support                  |
+---------------------------------------+
|  🏢  ZUHRI MEDICARE LIMITED           |
|      salim@tiberbu.com           [->] |
+---------------------------------------+
```

### 7.2 Multi-Facility Portfolio Table Wireframe
```text
Facilities (3 registered clinics across your network)                  [🔄 Sync via National ID]  [+ Add Facility]
[ Search by name, MFL, county...     ] [ Status: All v ] [ Level: All v ] [ Network: All v ]

+----+------------------------+-------------------+---------+------------+-----------------------+-----------------------+-------------------+----------------------+
| [x]| Facility & Location    | Network           | KEPH    | MFL Code   | Registry Status       | Recent Purchase       | Invoices          | Care Tokens & Actions|
+----+------------------------+-------------------+---------+------------+-----------------------+-----------------------+-------------------+----------------------+
| [ ]| A.P. EMBAKASI          | CHAK Partner Net  | Level 2 | 12094 [cp] | [● Live on Registry]  | 400 tokens (15 Oct)   | Paid ✓            | 🪙 400   [Top Up] [🧮]|
| [ ]| A.I.C MBOONI SUB HC    | CHAK Partner Net  | Level 3 | 10904 [cp] | [● Live on Registry]  | 1,000 tokens (12 Oct) | Paid ✓            | 🪙 1,000 [Top Up] [🧮]|
| [ ]| ZUHRI MEDICARE LIMITED | Private Network   | Level 2 | 91569 [cp] | [● Live on Registry]  | 300 tokens (01 Oct)   | KES 17,400 Due [Pay]| 🪙 300 [Top Up] [🧮]|
+----+------------------------+-------------------+---------+------------+-----------------------+-----------------------+-------------------+----------------------+
```

### 7.3 "My Profile" Wireframe
```text
My Profile
Manage your verified personal identity, practice organization, and national registry credentials.

+---------------------------------------------------------------------------------------------------------+
| VERIFIED IDENTITY (KENYA DIGITAL HEALTH AGENCY / CLIENT REGISTRY)                                      |
+---------------------------------------------------------------------------------------------------------+
| Full Name:              Dr. Salim Ahmed                                                                 |
| Email Address:          salim@tiberbu.com  (Login credential)                                           |
| Mobile Number:          +254 712 345 678   [Edit]                                                       |
| National ID Number:     ••••••••           [● Verified Citizen]  [Update ID]                             |
|                                                                                                         |
| * Your National ID is used to automatically discover registered health facilities from the national      |
|   Health Facility Registry without needing to enter manual MFL codes.                                   |
+---------------------------------------------------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------------+
| PRACTICE & ORGANIZATION DETAILS                                                                         |
+---------------------------------------------------------------------------------------------------------+
| Legal Entity / Organization:  ZUHRI MEDICARE LIMITED                                                    |
| Primary Network Partner:      CHAK Partner Network                                                      |
| Registered Clinics:           3 Facilities Active on CareVerse HMIS                                     |
| Account Plan:                 Enterprise Multi-Facility License                                         |
+---------------------------------------------------------------------------------------------------------+
```

### 7.4 Zero-Input Health Facility Registry Sync Modal Wireframe
```text
+---------------------------------------------------------------------------------------------------------+
| Discover Facilities via Health Facility Registry                                                    [X] |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|  +---------------------------------------------------------------------------------------------------+  |
|  | 🪪 FAST SYNC USING NATIONAL ID ON FILE                                                             |  |
|  | We will look up all licensed facilities registered under your National ID saved on the user profile: ••••••••      |  |
|  |                                                                                                   |  |
|  | [ 🔍 Discover Facilities Registered Under ID •••••••• ]                                           |  |
|  +---------------------------------------------------------------------------------------------------+  |
|                                                                                                         |
|  Found 3 facilities in National Health Facility Registry:                                               |
|                                                                                                         |
|  1. A.P. EMBAKASI (MFL: 12094 • Level 2 Dispensary • Nairobi)                       [ Already Linked ]   |
|  2. A.I.C MBOONI SUB HEALTH CENTRE (MFL: 10904 • Level 3 • Makueni)                 [ Already Linked ]   |
|  3. ZUHRI MEDICARE WESTLANDS CLINIC (MFL: 19938 • Level 2 • Nairobi)                [ + Add to Portfolio]|
|                                                                                                         |
|  -----------------------------------------------------------------------------------------------------  |
|  > Or search manually by MFL Code or Registration Number (for institutional facilities)                  |
+---------------------------------------------------------------------------------------------------------+
```

---

## 8. Test Matrix & Acceptance Criteria

### 8.1 Automated Unit & Integration Tests
| Test Case ID | Test Target | Verification Criteria |
| :--- | :--- | :--- |
| `TC-CX-001` | Entity Hierarchy Resolution | When a customer account has multiple deals/facilities, `organization` returns the Customer's legal entity name, NOT `facilities[0]`. |
| `TC-CX-002` | Neutral Facility Sorting | Changing alphabetical order or facility names does not alter default selected state; no facility is given unrequested hero focus. |
| `TC-CX-003` | Per-Facility Invoice Attribution | Invoices with `crm_token_facility_mfl` map directly to that facility; unpaid invoices render direct `Pay` actions per row. |
| `TC-CX-004` | Per-Facility Purchase History | Recent token sales order for a facility correctly populates `recent_purchase` with date, package, and token count. |
| `TC-CX-005` | Profile API & ID Persistence | `get_user_profile` returns verified `national_id`; `update_user_profile` validates format and safely saves to the user's profile. |
| `TC-CX-006` | HFR Discovery by National ID | `lookup_facilities_by_owner_id` calls `_hfr_facilities_for_owner(national_id)` and accurately returns linked vs. unlinked facilities. |
| `TC-CX-007` | Terminology Ban | Regression test ensuring zero occurrences of `KMHFR` or `KHFMR` across all frontend templates and API error messages. |

### 8.2 User Acceptance Criteria
1. **No Alphabetical Dominance:** The top header, sidebar footer, and profile display *Zuhri Medicare Limited*. *A.P. Embakasi* appears as a normal row in the facility table.
2. **Every Facility Exposes Network & Financials:** On the Facilities page, each row displays its Network (e.g. `CHAK Partner Network`), its last token order date/amount, and its specific invoice status.
3. **My Profile Exists:** The user can navigate to `/cx-portal#profile` (or click `My Profile`), view their National ID, verify it is recorded, and update it if needed.
4. **1-Click Facility Addition:** The user clicks "Add Facility" -> clicks "Discover Facilities Registered Under ID ••••••••" -> sees their newly licensed clinic -> clicks "Add to Portfolio" -> facility appears in their table immediately without typing MFL code.
5. **No KMHFR/KHFMR:** All labels read **Health Facility Registry**.

---

## 9. Implementation Phasing

- **Phase 1: Terminology & Entity Decoupling (Foundation)**
  - Cleanse all `KMHFR` / `KHFMR` references to `Health Facility Registry`.
  - Fix `_customer_portal_accounts` and `primaryOrganizationName` to correctly resolve the parent Customer organization and neutralize facility sorting.
- **Phase 2: Per-Facility Financial & Network Attribution (Backend + Frontend)**
  - Map `crm_token_facility_mfl` across `Sales Invoice` and `Sales Order` into each facility record in `get_portal_context`.
  - Add Network, Recent Purchase, and Invoice columns/badges to the Facilities table and cards view.
- **Phase 3: "My Profile" & National ID on File (Identity Governance)**
  - Implement `get_user_profile` and `update_user_profile` endpoints.
  - Build the dedicated "My Profile" view in `FacilityPortal.vue` with National ID display and editing.
- **Phase 4: 1-Click Health Facility Registry Discovery (UX Automation)**
  - Implement `lookup_facilities_by_owner_id` endpoint.
  - Overhaul Add Facility Modal and Health Facility Registry Sync view with the 1-click National ID discovery workflow.
- **Phase 5: Verification & PR Update**
  - Run Vitest (202+ tests) and backend test suite.
  - Deploy to `cr-dev.tiberbu.app` and update PR #93.



## Portal UX pattern

Follow the interaction and visual rules in [CX Portal UX Design Pattern](cx-portal-ux-design-pattern.md) for future portal work. The examples in this PRD use masked placeholders; never put a real National ID in product documentation.
