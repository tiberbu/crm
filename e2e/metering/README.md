# Metering journey (Playwright)

Checks that a cash payment for a token package raises the facility's balance in CRM and at the HMIS metering gateway (openmeter_mediator ADR-004).

Steps:
1. Record the facility's Available tokens in the CX portal and at the gateway.
2. Order a package in the portal and generate its invoice.
3. Record a cash payment in the Finance cockpit, then approve it as a second Accounts Manager. The approval workflow refuses self-approval.
4. Confirm the portal balance rises by the package's tokens.
5. Confirm the gateway returns the same balance, and how many of a billing event that balance covers.

## Setup

The site needs the `openmeter_mediator` app with OpenMeter configured. Create the synthetic fixture once; re-run it to rotate the passwords or the site key:

```bash
bench --site <site> execute openmeter_mediator.tests.e2e_fixture.setup \
  --kwargs '{"owner_password": "...", "finance_password": "...", "approver_password": "...", "key_file": "/secure/site_key"}'
```

## Run

```bash
BASE_URL=https://<crm-site> GATEWAY_URL=https://<billing-host> E2E_SITE_KEY="$(cat /secure/site_key)" \
E2E_OWNER_PASSWORD=... E2E_FINANCE_PASSWORD=... E2E_APPROVER_PASSWORD=... \
npx playwright test --config e2e/metering/playwright.config.ts
```

Each run buys a package with a real invoice and cash Payment Entry on the synthetic customer. After a key rotation, the gateway accepts the new key within 5 minutes, or straight away after a gateway restart.

## Express draft order journey

`express_draft_order.spec.ts` checks that an Express package is credited only after its invoice is paid:
the facility starts at 0 tokens with a draft order, the client reviews it (billing address, KRA PIN,
one-time or recurring) and generates the invoice, finance records and approves a cash payment, and the
portal and gateway then show the package's tokens.

Each run needs a fresh synthetic facility. Create one after the fixture above:

```bash
bench --site <site> execute crm.tests.e2e_express_fixture.setup \
  --kwargs '{"run_id": "<unique alphanumeric>", "key_file": "/secure/express_site_key"}'
```

It prints the facility's MFL, name and draft order. Pass them with the metering variables:

```bash
E2E_EXPRESS_MFL=... E2E_EXPRESS_FACILITY="..." E2E_EXPRESS_ORDER=... E2E_EXPRESS_PACKAGE_TOKENS=1000 \
E2E_EXPRESS_SITE_KEY="$(cat /secure/express_site_key)" \
npx playwright test --config e2e/metering/playwright.config.ts express_draft_order
```

## Welcome bonus journeys (P-76)

`welcome_bonus_dispense.spec.ts`: an OpenMeter Admin dispenses the welcome bonus from Deal › Metering,
the button stays disabled, a repeat request adds nothing, the order loses its bonus line, a part
payment grants nothing, and the full payment grants the package only. `welcome_bonus_auto_assign.spec.ts`:
with auto-assign on, selecting the package releases the bonus and payment adds the package only.

Create a facility per run with the admin user and a Deal:

```bash
# python (frappe.init/connect), not bench execute, so errors show:
crm.tests.e2e_express_fixture.setup(run_id="<unique>", key_file="/secure/express_site_key",
    partner_coupon=False, admin_password="...", auto_dispense=False)  # True for the auto-assign spec
```

Pass the Express variables plus `E2E_ADMIN_PASSWORD`, `E2E_BONUS_DEAL` (the returned deal),
`E2E_BONUS_FID` (the returned fid) and `E2E_BONUS_TOKENS` (the Opt-In bonus quantity).
