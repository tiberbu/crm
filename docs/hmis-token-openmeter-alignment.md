# HMIS tokens: CRM changes for the OpenMeter alignment

**Status:** Proposed, 2026-10-25. Source of truth: `openmeter_mediator` ADR-003, "OpenMeter is the token balance authority".

CRM becomes the only place tokens are granted. Grants live in OpenMeter, keyed by the facility FID. HMIS pulls its balance from OpenMeter and no longer receives token loads from CRM's provisioning payload or Admin Central.

## Flow

1. CRM submits HMIS provisioning (`crm/api/hfr.py`, `_auto_submit_external_provisioning_impl`). On HTTP 200/202 it calls the `crm_on_hmis_provisioning_submitted` hook. The `openmeter_mediator` app grants the free plan for that FID and issues the site key.
2. The provisioning payload carries the site key so the new HMIS site can reach OpenMeter at first boot.
3. When tokens run out, the facility buys a package in the CX portal. The paid Sales Invoice becomes an OpenMeter grant on the invoice's FID.
4. HMIS sees the new balance on its next pull.

## CRM tasks

| ID | Change | Files |
|---|---|---|
| CRM-T1 | Call `frappe.get_hooks("crm_on_hmis_provisioning_submitted")` after an accepted submission, enqueued after commit. CRM does not import the mediator. | `crm/api/hfr.py` |
| CRM-T2 | Payload adds `metering_site_key` (from the hook's result), `token_source: "openmeter"` and `token_purchase_url`. `token_expiry_date` counts from the provisioning date if decision D-1 is approved. | `crm/api/hfr.py`, `docs/cx-portal-provisioning-gateway-api.md` |
| CRM-T3 | Send `tokens_awarded: 0` when `token_source` is `openmeter`. | `crm/api/hfr.py` |
| CRM-T4 | Stamp `crm_token_facility_fid` beside `crm_token_facility_mfl` on token-purchase Quotation, Sales Order and Sales Invoice. | `crm/api/facility_onboarding.py`, `crm/api/customer_experience.py`, a new patch |
| CRM-T5 | Phase 2, optional: CX portal balance card read through the mediator. Until then, keep the rule in `docs/cx-portal-ux-design-pattern.md` against calling package quantity a "token balance". | CX portal |

## Data and migration impact

- New custom field `crm_token_facility_fid` on Quotation, Sales Order and Sales Invoice; backfill from the facility's FID where the MFL maps to exactly one facility.
- The provisioning payload contract changes (three new fields, `tokens_awarded` becomes 0). The HMIS setup service must accept the new fields before CRM sends them.
