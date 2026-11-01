import { expect, request, test } from "@playwright/test";

import { env, gatewayBalance, payInvoiceInCash, portalBalance, signedIn } from "./journey";

/**
 * P-76: with auto-assign on, selecting a Flex package releases the welcome bonus before payment;
 * paying the package then grants only the tokens bought.
 *
 * Needs crm.tests.e2e_express_fixture.setup with `admin_password`, `partner_coupon: false` and
 * `auto_dispense: true` for this run, and the same variables as welcome_bonus_dispense.spec.ts.
 */

const MFL = env("E2E_EXPRESS_MFL");
const FACILITY = env("E2E_EXPRESS_FACILITY");
const ORDER = env("E2E_EXPRESS_ORDER");
const DEAL = env("E2E_BONUS_DEAL");
const PACKAGE_TOKENS = Number(env("E2E_EXPRESS_PACKAGE_TOKENS", "1000"));
const BONUS_TOKENS = Number(env("E2E_BONUS_TOKENS", "400"));
const CUSTOMER = env("E2E_CUSTOMER", "E2E Metering Facility Owner");
const KRA_PIN = "P051234567Q";

test("auto-assign releases the welcome bonus on package selection, then the package on payment", async ({
  browser,
}, testInfo) => {
  const gateway = await request.newContext({
    baseURL: env("GATEWAY_URL"),
    extraHTTPHeaders: { "X-OpenMeter-Site-Key": env("E2E_EXPRESS_SITE_KEY") },
  });
  const admin = await signedIn(
    browser,
    env("E2E_ADMIN_EMAIL", "e2e.metering-admin@example.test"),
    env("E2E_ADMIN_PASSWORD"),
  );
  const owner = await signedIn(
    browser,
    env("E2E_OWNER_EMAIL", "e2e.facility-owner@example.test"),
    env("E2E_OWNER_PASSWORD"),
  );
  let invoice = "";

  await test.step("Selecting the package released the bonus; the button is disabled", async () => {
    await expect
      .poll(async () => (await gatewayBalance(gateway)).balance, { timeout: 90_000, intervals: [3_000] })
      .toBe(BONUS_TOKENS);
    await admin.goto(`/crm/deals/${DEAL}#metering`);
    await expect(admin.getByTestId("welcome-bonus-state")).toContainText(
      `automatically when package ${ORDER} was selected`,
    );
    await expect(admin.getByTestId("dispense-welcome-bonus")).toBeDisabled();
    await testInfo.attach("1-auto-assigned", { body: await admin.screenshot(), contentType: "image/png" });
  });

  await test.step("The client's order pays for the package with no second bonus", async () => {
    await owner.goto("/cx-portal");
    await owner.getByRole("button", { name: /Billing & Invoices/ }).first().click();
    await owner.getByTestId(`review-order-${ORDER}`).click();
    const dialog = owner.getByTestId("order-review");
    await expect(dialog.getByTestId("order-review-total")).toHaveText(/\d/);
    await expect(dialog.getByTestId("order-review-bonus")).toHaveCount(0);
    await dialog.getByLabel("KRA PIN").fill(KRA_PIN.toLowerCase());
    const saved = dialog.getByLabel("Billing address");
    if (!(await saved.isVisible().catch(() => false))) {
      await dialog.getByLabel("Street address").fill("1 Synthetic Road");
      await dialog.getByLabel("Town").fill("Nairobi");
      await dialog.getByLabel("County").fill("Nairobi");
    }
    await dialog.getByText("One-time", { exact: true }).click();
    const [response] = await Promise.all([
      owner.waitForResponse((r) => r.url().includes("customer_experience.confirm_draft_order")),
      dialog.getByRole("button", { name: "Confirm order & generate invoice" }).click(),
    ]);
    expect(response.status(), await response.text()).toBe(200);
    invoice = (await response.json()).message.data.invoice;
    expect(invoice).toBeTruthy();
  });

  await test.step("Full payment adds the package only", async () => {
    await payInvoiceInCash(browser, CUSTOMER, invoice, testInfo);
    await expect
      .poll(() => portalBalance(owner, MFL, FACILITY), { timeout: 180_000, intervals: [5_000, 10_000] })
      .toBe(BONUS_TOKENS + PACKAGE_TOKENS);
    expect((await gatewayBalance(gateway)).balance).toBe(BONUS_TOKENS + PACKAGE_TOKENS);
    await testInfo.attach("2-after-payment", { body: await owner.screenshot(), contentType: "image/png" });
  });
});
