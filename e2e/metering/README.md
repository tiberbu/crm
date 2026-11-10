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

## OpenMeter Setup Checklist journey (openmeter_mediator OMM-53)

`openmeter_setup_checklist.spec.ts` drives OpenMeter Settings as an OpenMeter Admin who may
open Desk (the site's `desk_access_users`). It sets the Gateway URL to an address that answers
as OpenMeter itself and checks that Test Connection and Gateway › Setup Checklist say so
(Blocked, no Apply). With `E2E_GATEWAY_URL` it then connects to a real gateway, checks that
the checklist opens by itself, applies missing items and expects the meter, token feature and
facilities to be Done. It puts the Gateway URL back as it found it.

Variables: `BASE_URL`, `E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD`, `E2E_EXPOSED_OPENMETER_URL`,
optional `E2E_GATEWAY_URL` (the gateway must be able to call the CRM back over HTTPS) and
`E2E_MAP_HOST_TO_LOCALHOST` (to reach a bench site with no public DNS through local nginx):

```bash
BASE_URL=http://<site> E2E_MAP_HOST_TO_LOCALHOST=<site> E2E_ADMIN_EMAIL=<admin> \
E2E_ADMIN_PASSWORD=... E2E_EXPOSED_OPENMETER_URL=https://<openmeter-host> \
npx playwright test --config e2e/metering/playwright.config.ts openmeter_setup_checklist
```

## Subscription lifecycle journey (openmeter_mediator ADR-007)

`subscription_lifecycle.spec.ts`: a fully paid Fixed-package invoice shows on Deal › Metering as an
active subscription with its activation, expiry and term; the admin suspends and reactivates the
site and cancels the subscription, each with a reason. It also checks the Plan section against the
brand guide (InterVar, weight ≤ 600). OpenMeter may be off on the site; HMIS's view
(`GET /ingest/v1/plan`) is covered by the gateway's tests and the `hmis-essentials` Postman collection.

```bash
bench --site <site> execute crm.tests.e2e_subscription_fixture.setup \
    --kwargs '{"run_id": "0001", "admin_password": "..."}'
# from its result:
BASE_URL=https://<crm-site> E2E_SUB_DEAL=<deal> E2E_SUB_FID=<fid> E2E_SUB_INVOICE=<invoice> \
E2E_ADMIN_PASSWORD=... npx playwright test --config e2e/metering/playwright.config.ts subscription_lifecycle
```

Use a new `run_id` for each run: the journey cancels the subscription it checks.

## Coupon rewards by facility level (P-116 to P-123)

`coupon_level_rewards.spec.ts`: one Partner Coupon rewards each facility level differently. The
admin sees the per-level lines on the coupon card and creates a level-rewarded coupon in the dialog;
the customer's four draft orders (Level 2 and Level 4 Flex, Level 2 and Level 3B Fixed) each show
their own level's tokens or discount; confirming records the level and the metering grant check lets
the Level 4 amount through.

```bash
bench --site <site> execute crm.tests.e2e_coupon_level_fixture.setup \
  --kwargs '{"run_id": "<alphanumeric>", "admin_password": "...", "owner_password": "..."}' > clr.out
# save the JSON object printed last to a file, then:
E2E_CLR_FIXTURE=/path/to/clr.json BENCH_DIR=... BENCH_SITE=<site> E2E_ADMIN_PASSWORD=... E2E_OWNER_PASSWORD=... \
npx playwright test --config e2e/metering/playwright.config.ts coupon_level_rewards
bench --site <site> execute crm.tests.e2e_coupon_level_fixture.teardown --kwargs '{"run_id": "<same>"}'
```
