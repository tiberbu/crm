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
