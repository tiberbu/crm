import { expect, Page, request, test } from "@playwright/test";

import {
  env,
  gatewayBalance,
  payInvoiceInCash,
  portalBalance as facilityBalance,
  signedIn,
} from "./journey";

const FACILITY = env("E2E_FACILITY_NAME", "E2E Metering Clinic (synthetic)");
const MFL = env("E2E_MFL", "E2E-0001");
const CUSTOMER = env("E2E_CUSTOMER", "E2E Metering Facility Owner");
const PACKAGE = env("E2E_PACKAGE", "Starter");
const PACKAGE_TOKENS = Number(env("E2E_PACKAGE_TOKENS", "1000"));
const BILLING_EVENT = env("E2E_BILLING_EVENT", "patient_registration");

const portalBalance = (page: Page) => facilityBalance(page, MFL, FACILITY);

test("a cash payment for a token package raises the balance in CRM and at the HMIS gateway", async ({
  browser,
}, testInfo) => {
  const gateway = await request.newContext({
    baseURL: env("GATEWAY_URL"),
    extraHTTPHeaders: { "X-OpenMeter-Site-Key": env("E2E_SITE_KEY") },
  });
  const owner = await signedIn(
    browser,
    env("E2E_OWNER_EMAIL", "e2e.facility-owner@example.test"),
    env("E2E_OWNER_PASSWORD"),
  );
  let before = 0;
  let invoice = "";

  await test.step("Record the available balance in CRM and at the gateway", async () => {
    before = await portalBalance(owner);
    const atGateway = await gatewayBalance(gateway);
    expect(atGateway.balance).toBeCloseTo(before, 4);
    await testInfo.attach("1-balance-before", {
      body: await owner.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step(`Order the ${PACKAGE} package in the portal and generate its invoice`, async () => {
    await owner.getByRole("button", { name: "Top up tokens" }).click();
    const dialog = owner.getByRole("dialog");
    await dialog.getByText(PACKAGE, { exact: true }).click();
    await dialog.getByRole("button", { name: /Confirm Order/ }).click();
    await expect(owner.getByText(/Order .+ created for/)).toBeVisible();
    const generate = owner.getByRole("button", { name: "Generate Invoice" });
    if (
      await generate
        .first()
        .isVisible({ timeout: 5_000 })
        .catch(() => false)
    ) {
      const [response] = await Promise.all([
        owner.waitForResponse((r) =>
          r.url().includes("customer_experience.start_token_payment"),
        ),
        generate.first().click(),
      ]);
      invoice = (await response.json()).message.data.invoice;
    } else {
      // A retried, unpaid purchase resumes its order, whose invoice is already listed.
      const due = owner
        .locator("div", { hasText: MFL })
        .filter({ hasText: "Payment due" })
        .last();
      invoice = ((await due.innerText()).match(/\b[A-Z]+-SINV-\d{4}-\d+\b/) || [
        "",
      ])[0];
    }
    expect(invoice).toBeTruthy();
    await testInfo.attach("2-invoice", {
      body: invoice,
      contentType: "text/plain",
    });
  });

  await test.step("Finance records the cash payment and an Accounts Manager approves it", async () => {
    await payInvoiceInCash(browser, CUSTOMER, invoice, testInfo);
  });

  await test.step("CRM shows the balance raised by the package", async () => {
    await expect
      .poll(() => portalBalance(owner), {
        timeout: 180_000,
        intervals: [5_000, 10_000],
      })
      .toBeCloseTo(before + PACKAGE_TOKENS, 4);
    await testInfo.attach("5-balance-after", {
      body: await owner.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step("The gateway gives HMIS the same balance and per-event allowance", async () => {
    const total = await gatewayBalance(gateway);
    expect(total.balance).toBeCloseTo(before + PACKAGE_TOKENS, 4);
    const perEvent = await gatewayBalance(gateway, BILLING_EVENT);
    expect(perEvent.event.affordable).toBe(
      Math.floor(perEvent.balance / perEvent.event.tokens),
    );
    await testInfo.attach("6-gateway", {
      body: JSON.stringify({ total, perEvent }, null, 2),
      contentType: "application/json",
    });
  });
});
