# PR: Finance Cockpit access and signed-facility accounting handoff

## Summary

This change makes the CRM-to-accounting handoff begin when the facility signatory reaches native `Signed` and aligns Finance Cockpit access with Accounts roles.

## Included

- Native Year 1 Quotation submission at facility signature.
- Immediate native Year 1/Q1 Sales Order generation and submission.
- Sales Invoice generation only when the Network billing schedule permits invoice issuance at signature.
- Idempotent retry behavior and persisted actionable schedule errors.
- Native CRM Deal transition to `Won`.
- Historical signed Opt-In reconciliation patch.
- Accounts User/Accounts Manager access policy across page, route, API, migration, and CRM navigation.
- Finance Cockpit frontend retry/error-state improvements and role alignment.
- Focused unit tests and existing Opt-In regression coverage.

## Native lifecycle decision

No custom statuses are introduced. Quotation acceptance is represented by native ERPNext quotation submission and native quotation status. CRM Deals use native `Won`. Sales Orders, Sales Invoices, and Payment Entries use native ERPNext document states and validations.

## Files of interest

- `crm/automation/optin_billing.py`
- `crm/api/contracts.py`
- `crm/finance/access.py`
- `crm/finance/api.py`
- `crm/patches/v1_0/reconcile_signed_optin_finance_handoffs_v1.py`
- `crm/patches/v1_0/restrict_finance_cockpit_to_accounts.py`
- `frontend/src/components/Layouts/AppSidebar.vue`
- `frontend/src/pages/FinanceCockpit/components/crud/*`

## Verification

- `bench --site cr-dev.tiberbu.app run-tests --app crm --module crm.tests.test_finance_access`
- `bench --site cr-dev.tiberbu.app run-tests --app crm --module crm.tests.test_optin_billing`
- `bench --site cr-dev.tiberbu.app run-tests --app crm --module crm.tests.test_optin_bundles`
- `bench --site cr-dev.tiberbu.app run-tests --app crm --module crm.tests.test_optin`
- `yarn build` from `apps/crm/frontend`
- `git diff --check`

## Rollout

1. Deploy the CRM app.
2. Run `bench --site <site> migrate` so the access and historical reconciliation patches execute.
3. Confirm Network billing timing and ERPNext company/customer/item/tax configuration before enabling production handoff.
4. Verify one configured-billing and one no-billing facility in Finance Cockpit.
5. Confirm Accounts User, Accounts Manager, Administrator, and unauthorized-role behavior.

## Recovery and rollback

- Failed handoffs retain an actionable schedule error and can be retried after configuration is corrected.
- Existing native documents are not silently mutated to repair failures.
- If deployment must be rolled back, stop the handoff worker, retain already-submitted native documents, and redeploy the prior app version; do not delete accounting documents as a rollback action.

## Follow-up

The full senior UX/frontend overhaul is planned in `docs/finance-cockpit-frontend-overhaul-sprint.md`. This PR delivers the access, handoff, and frontend foundation; the overhaul remains a separate implementation sprint.

## Known warnings

The frontend build reports existing bundle-size and missing Lucide GitHub icon warnings. They do not block this change and are tracked for the frontend overhaul sprint.
