import { expect, request, test } from "@playwright/test";

import { env, gatewayBalance, payInvoiceInCash, portalBalance, signedIn } from "./journey";

/**
 * P-76: the welcome bonus is dispensed once per facility, and a package is credited on full payment only.
 *
 * Needs crm.tests.e2e_express_fixture.setup with `admin_password`, `partner_coupon: false` and
 * `auto_dispense: false` for this run (a fresh synthetic facility, its draft order and a Deal listing
 * it), plus the metering journey's variables and: E2E_EXPRESS_MFL, E2E_EXPRESS_FACILITY,
 * E2E_EXPRESS_ORDER, E2E_EXPRESS_SITE_KEY, E2E_EXPRESS_PACKAGE_TOKENS, E2E_BONUS_DEAL, E2E_BONUS_FID,
 * E2E_BONUS_TOKENS, E2E_ADMIN_PASSWORD.
 *
 * 1. The facility has 0 tokens; the Deal's Metering tab offers the welcome bonus once.
 * 2. The admin dispenses it: the balance is the bonus, and the button is disabled for good.
 * 3. A repeat request through the API adds nothing.
 * 4. The order no longer carries the bonus line; the client confirms it and gets the invoice.
 * 5. A part payment is approved: no package tokens.
 * 6. The rest is paid: the balance is the bonus plus the package, never the bonus twice.
 */

const MFL = env("E2E_EXPRESS_MFL");
const FACILITY = env("E2E_EXPRESS_FACILITY");
const ORDER = env("E2E_EXPRESS_ORDER");
const DEAL = env("E2E_BONUS_DEAL");
const FID = env("E2E_BONUS_FID");
const PACKAGE_TOKENS = Number(env("E2E_EXPRESS_PACKAGE_TOKENS", "1000"));
const BONUS_TOKENS = Number(env("E2E_BONUS_TOKENS", "400"));
const CUSTOMER = env("E2E_CUSTOMER", "E2E Metering Facility Owner");
const KRA_PIN = "P051234567Q";

test("the welcome bonus is dispensed once and the package only on full payment", async ({
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
  const bonusCard = admin.getByTestId("welcome-bonus");
  const button = admin.getByTestId("dispense-welcome-bonus");
  let invoice = "";

  await test.step("The facility starts at 0 tokens and the bonus can be dispensed", async () => {
    expect((await gatewayBalance(gateway)).balance).toBe(0);
    await admin.goto(`/crm/deals/${DEAL}#metering`);
    await expect(bonusCard).toBeVisible();
    await expect(admin.getByTestId("welcome-bonus-state")).toContainText("Not dispensed yet");
    await expect(button).toBeEnabled();
    await expect(button).toContainText(`Dispense ${BONUS_TOKENS.toLocaleString("en-US")} bonus tokens`);
    await testInfo.attach("1-bonus-available", { body: await admin.screenshot(), contentType: "image/png" });
  });

  await test.step("The admin dispenses it once; the button stays disabled", async () => {
    await button.click();
    await admin.getByRole("button", { name: "Dispense bonus" }).click();
    await expect(admin.getByText(/welcome bonus tokens dispensed to/)).toBeVisible();
    await expect(button).toBeDisabled();
    await expect(button).toHaveText(/Bonus dispensed/);
    await expect(admin.getByTestId("welcome-bonus-state")).toContainText(/dispensed on .* by /);
    await admin.reload();
    await expect(admin.getByTestId("dispense-welcome-bonus")).toBeDisabled();
    await expect
      .poll(async () => (await gatewayBalance(gateway)).balance, { timeout: 60_000, intervals: [3_000] })
      .toBe(BONUS_TOKENS);
    await testInfo.attach("2-bonus-dispensed", { body: await admin.screenshot(), contentType: "image/png" });
  });

  await test.step("A repeated request adds nothing", async () => {
    const response = await admin.request.post("/api/method/crm.api.metering_admin.dispense_welcome_bonus", {
      form: { fid: FID },
      headers: { "X-Frappe-CSRF-Token": await admin.evaluate(() => (window as any).csrf_token) },
    });
    expect(response.status(), await response.text()).toBe(200);
    const result = (await response.json()).message;
    expect(result.changed).toBe(false);
    expect(result.dispensed).toBe(true);
    expect((await gatewayBalance(gateway)).balance).toBe(BONUS_TOKENS);
  });

  await test.step("The order no longer carries the bonus; the client confirms it", async () => {
    await owner.goto("/cx-portal");
    await owner.getByRole("button", { name: /Billing & Invoices/ }).first().click();
    await owner.getByTestId(`review-order-${ORDER}`).click();
    const dialog = owner.getByTestId("order-review");
    await expect(dialog.getByTestId("order-review-total")).toHaveText(/\d/);
    // Already dispensed, so the order shows no complimentary line and pays for the package only.
    await expect(dialog.getByTestId("order-review-bonus")).toHaveCount(0);
    await dialog.getByLabel("KRA PIN").fill(KRA_PIN.toLowerCase());
    const saved = dialog.getByLabel("Billing address");
    if (!(await saved.isVisible().catch(() => false))) {
      await dialog.getByLabel("Street address").fill("1 Synthetic Road");
      await dialog.getByLabel("Town").fill("Nairobi");
      await dialog.getByLabel("County").fill("Nairobi");
    }
    await dialog.getByText("One-time", { exact: true }).click();
    await testInfo.attach("3-review", { body: await owner.screenshot(), contentType: "image/png" });
    const [response] = await Promise.all([
      owner.waitForResponse((r) => r.url().includes("customer_experience.confirm_draft_order")),
      dialog.getByRole("button", { name: "Confirm order & generate invoice" }).click(),
    ]);
    expect(response.status(), await response.text()).toBe(200);
    invoice = (await response.json()).message.data.invoice;
    expect(invoice).toBeTruthy();
    expect(await portalBalance(owner, MFL, FACILITY)).toBe(BONUS_TOKENS);
  });

  await test.step("A part payment grants no package tokens", async () => {
    await payInvoiceInCash(browser, CUSTOMER, invoice, testInfo, true);
    // Give the payment job time to run; the facility must still hold only the bonus.
    await owner.waitForTimeout(30_000);
    expect((await gatewayBalance(gateway)).balance).toBe(BONUS_TOKENS);
    expect(await portalBalance(owner, MFL, FACILITY)).toBe(BONUS_TOKENS);
  });

  await test.step("Paying the rest grants the package once, without a second bonus", async () => {
    await payInvoiceInCash(browser, CUSTOMER, invoice, testInfo);
    await expect
      .poll(() => portalBalance(owner, MFL, FACILITY), { timeout: 180_000, intervals: [5_000, 10_000] })
      .toBe(BONUS_TOKENS + PACKAGE_TOKENS);
    expect((await gatewayBalance(gateway)).balance).toBe(BONUS_TOKENS + PACKAGE_TOKENS);
    await testInfo.attach("4-package-after-full-payment", { body: await owner.screenshot(), contentType: "image/png" });
  });
});
