import { expect, request, test } from "@playwright/test";

import { env, gatewayBalance, payInvoiceInCash, portalBalance, signedIn } from "./journey";

/**
 * Express onboarding credits no tokens until the package invoice is paid.
 *
 * Needs crm.tests.e2e_express_fixture.setup for this run (a fresh synthetic facility whose
 * provisioning deferred the package grant and whose draft order exists), and these variables
 * besides the metering journey's: E2E_EXPRESS_MFL, E2E_EXPRESS_FACILITY, E2E_EXPRESS_ORDER,
 * E2E_EXPRESS_SITE_KEY, E2E_EXPRESS_PACKAGE_TOKENS.
 *
 * 1. The portal shows the draft order to review and 0 tokens; the gateway reports 0.
 * 2. Pricing cards carry no billing period.
 * 3. The client reviews the order, adds a billing address (or reuses one) and the KRA PIN,
 *    keeps it one-time, and generates the invoice. Still 0 tokens.
 * 4. Finance records the cash payment and a second Accounts Manager approves it.
 * 5. The portal and the gateway show the package's tokens from OpenMeter.
 */

const MFL = env("E2E_EXPRESS_MFL");
const FACILITY = env("E2E_EXPRESS_FACILITY");
const ORDER = env("E2E_EXPRESS_ORDER");
const PACKAGE_TOKENS = Number(env("E2E_EXPRESS_PACKAGE_TOKENS", "1000"));
const CUSTOMER = env("E2E_CUSTOMER", "E2E Metering Facility Owner");
const KRA_PIN = "P051234567Q";

test("an Express package is credited only after its reviewed order's invoice is paid", async ({
  browser,
}, testInfo) => {
  const gateway = await request.newContext({
    baseURL: env("GATEWAY_URL"),
    extraHTTPHeaders: { "X-OpenMeter-Site-Key": env("E2E_EXPRESS_SITE_KEY") },
  });
  const owner = await signedIn(
    browser,
    env("E2E_OWNER_EMAIL", "e2e.facility-owner@example.test"),
    env("E2E_OWNER_PASSWORD"),
  );
  let invoice = "";

  await test.step("After submission the facility has 0 tokens and a draft order to review", async () => {
    await owner.goto("/cx-portal");
    await expect(owner.getByTestId("draft-orders-banner")).toBeVisible();
    await expect(owner.getByTestId(`facility-tokens-${MFL}`)).toHaveText(/^\s*0 tokens$/);
    expect(await portalBalance(owner, MFL, FACILITY)).toBe(0);
    expect((await gatewayBalance(gateway)).balance).toBe(0);
    await testInfo.attach("1-zero-tokens", {
      body: await owner.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step("Pricing cards show the package price without a billing period", async () => {
    await owner.goto("/cx-portal");
    await owner.getByRole("button", { name: /Plans & Pricing/ }).first().click();
    await expect(owner.getByText(/Care Tokens/).first()).toBeVisible();
    await expect(owner.locator("main")).not.toContainText(/\/\s*(monthly|month|mo)\b/i);
    await testInfo.attach("2-pricing", {
      body: await owner.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step("The client reviews the order, adds billing details and generates the invoice", async () => {
    await owner.getByRole("button", { name: /Billing & Invoices/ }).first().click();
    await owner.getByTestId(`review-order-${ORDER}`).click();
    const dialog = owner.getByTestId("order-review");
    await expect(dialog.getByTestId("order-review-total")).toHaveText(/\d/);
    const confirm = dialog.getByRole("button", { name: "Confirm order & generate invoice" });
    await expect(confirm).toBeDisabled();

    await dialog.getByLabel("KRA PIN").fill(KRA_PIN.toLowerCase());
    const saved = dialog.getByLabel("Billing address");
    if (await saved.isVisible().catch(() => false)) {
      // A billing address from an earlier order is offered and reused.
      await expect(saved).not.toHaveValue("");
    } else {
      await dialog.getByLabel("Street address").fill("1 Synthetic Road");
      await dialog.getByLabel("Town").fill("Nairobi");
      await dialog.getByLabel("County").fill("Nairobi");
    }
    await dialog.getByText("One-time", { exact: true }).click();
    await testInfo.attach("3-review", {
      body: await owner.screenshot(),
      contentType: "image/png",
    });

    const [response] = await Promise.all([
      owner.waitForResponse((r) => r.url().includes("customer_experience.confirm_draft_order")),
      confirm.click(),
    ]);
    expect(response.status(), await response.text()).toBe(200);
    invoice = (await response.json()).message.data.invoice;
    expect(invoice).toBeTruthy();
    await expect(owner.getByText(`invoice ${invoice} generated`)).toBeVisible();
    await expect(owner.getByTestId(`review-order-${ORDER}`)).toHaveCount(0);
    expect(await portalBalance(owner, MFL, FACILITY)).toBe(0);
    await testInfo.attach("4-invoice", { body: invoice, contentType: "text/plain" });
  });

  await test.step("Finance records the cash payment and an Accounts Manager approves it", async () => {
    await payInvoiceInCash(browser, CUSTOMER, invoice, testInfo);
  });

  await test.step("The portal and the gateway show the paid package's tokens from OpenMeter", async () => {
    await expect
      .poll(() => portalBalance(owner, MFL, FACILITY), {
        timeout: 180_000,
        intervals: [5_000, 10_000],
      })
      .toBe(PACKAGE_TOKENS);
    expect((await gatewayBalance(gateway)).balance).toBe(PACKAGE_TOKENS);
    await testInfo.attach("5-tokens-after-payment", {
      body: await owner.screenshot(),
      contentType: "image/png",
    });
  });
});
