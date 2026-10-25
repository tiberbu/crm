# HMIS tokens: CRM changes for the OpenMeter alignment

**Status:** Accepted, 2026-10-25, with stakeholder answers recorded. Source of truth: `openmeter_mediator` ADR-003, "OpenMeter is the token balance authority".

CRM becomes the only place tokens are granted. Grants live in OpenMeter, keyed by the facility FID. HMIS pulls its balance from OpenMeter and no longer receives token loads from CRM's provisioning payload or Admin Central.

## Flow

1. CRM submits HMIS provisioning (`crm/api/hfr.py`, `_auto_submit_external_provisioning_impl`). On HTTP 200/202 it calls the `crm_on_hmis_provisioning_submitted` hook. The `openmeter_mediator` app grants the free plan for that FID and issues the site key.
2. Provisioning delivers the site key to the new HMIS site through the signed `update_license` push, so the site can reach OpenMeter at first boot.

Tokens never expire. Only an exhausted balance stops clinical work.
3. When tokens run out, the facility buys a package in the CX portal. The paid Sales Invoice becomes an OpenMeter grant on the invoice's FID.
4. HMIS sees the new balance on its next pull.

## CRM tasks

| ID | Change | Files |
|---|---|---|
| CRM-T1 | Call `frappe.get_hooks("crm_on_hmis_provisioning_submitted")` after an accepted submission, enqueued after commit. CRM does not import the mediator. | `crm/api/hfr.py` |
| CRM-T2 | Payload adds `metering_site_key` (from the hook's result, forwarded by provisioning in `update_license`), `token_source: "openmeter"` and `token_purchase_url`. `token_expiry_date` is still sent until the setup service drops it as a required field; HMIS ignores it for OpenMeter-mode sites. | `crm/api/hfr.py`, `docs/cx-portal-provisioning-gateway-api.md` |
| CRM-T3 | Send `tokens_awarded: 0` when `token_source` is `openmeter`. | `crm/api/hfr.py` |
| CRM-T4 | Stamp `crm_token_facility_fid` beside `crm_token_facility_mfl` on token-purchase Quotation, Sales Order and Sales Invoice. | `crm/api/facility_onboarding.py`, `crm/api/customer_experience.py`, a new patch |
| CRM-T5 | Phase 2, optional: CX portal balance card read through the mediator. Until then, keep the rule in `docs/cx-portal-ux-design-pattern.md` against calling package quantity a "token balance". | CX portal |

## Implementation status

| ID | Status |
|---|---|
| CRM-T1 | Done. `crm_on_hmis_provisioning_submitted` hooks run in a background job after every accepted submission. |
| CRM-T2 | Done, behind **CRM HFR Settings → Use OpenMeter as the HMIS Token Source** (off by default). The site key comes from the `crm_issue_hmis_metering_site_key` hook. |
| CRM-T3 | Done, behind the same setting. |
| CRM-T4 | Done. A `validate` hook on Quotation, Sales Order and Sales Invoice fills the FID from the MFL when exactly one FID is recorded for it. Patch `add_token_facility_fid` adds the field and backfills it. |
| CRM-T5 | Not started (phase 2). |

Turn the setting on only after the mediator implements both hooks (OMM-32, OMM-33) and HMIS can pull its balance (HMIS-H1). With the setting on and no key hook, every new provisioning request is blocked with `missing_fields=["metering_site_key"]`.

## Data and migration impact

- New custom field `crm_token_facility_fid` on Quotation, Sales Order and Sales Invoice; backfill from the facility's FID where the MFL maps to exactly one facility.
- The provisioning payload contract changes (three new fields, `tokens_awarded` becomes 0). The HMIS setup service must accept the new fields before CRM sends them.
