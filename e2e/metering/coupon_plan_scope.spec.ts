import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

import { env, signedIn } from "./journey";

/** frappe-ui puts data-testid on the input itself or on its wrapper, depending on the control. */
const field = (scope, id: string, tag = "input") => scope.locator(`${tag}[data-testid="${id}"], [data-testid="${id}"] ${tag}`).first();

/**
 * Plan-scoped coupons (P-107 to P-115) and the customer's view of a Fixed subscription (P-114).
 *
 * Needs crm.tests.e2e_coupon_plan_fixture.setup for this run (a partner network with one Both
 * coupon: 500 tokens on Flex, 5% off Fixed; a Fixed and a Flex facility with their draft orders;
 * a Deal listing both), plus: BASE_URL, BENCH_DIR, BENCH_SITE, E2E_CPS_RUN, E2E_CPS_NETWORK_NAME,
 * E2E_CPS_FIXED_MFL, E2E_CPS_FIXED_FID, E2E_CPS_FLEX_FID, E2E_CPS_FIXED_ORDER, E2E_CPS_FLEX_ORDER,
 * E2E_CPS_DEAL, E2E_ADMIN_PASSWORD, E2E_OWNER_PASSWORD.
 *
 * 1. Settings › Coupons: the network's coupon reads "500 tokens on Flex · 5% off Fixed"; a new
 *    coupon offers Flex / Fixed / Both and shows only the fields of the chosen plan.
 * 2. The customer reviews both orders: the Fixed order shows the 5% discount and no free tokens;
 *    the Flex order shows its free token lines and no discount.
 * 3. The Fixed order is confirmed, invoiced and paid (through the fixture).
 * 4. The customer's Fixed facility shows its Subscription: active, with its expiry.
 * 5. Deal › Metering: the welcome bonus cannot be dispensed to the Fixed-only facility, and can
 *    to the Flex one.
 */

const RUN = env("E2E_CPS_RUN");
const FIXED_MFL = env("E2E_CPS_FIXED_MFL");
const FIXED_ORDER = env("E2E_CPS_FIXED_ORDER");
const FLEX_ORDER = env("E2E_CPS_FLEX_ORDER");

test("coupons are scoped to Flex or Fixed, and the customer sees the subscription", async ({ browser }, testInfo) => {
  const shot = async (page, name: string) =>
    testInfo.attach(name, { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });

  await test.step("Settings › Coupons shows each plan's benefit and asks which plans a coupon is for", async () => {
    const admin = await signedIn(browser, "e2e.coupon-admin@example.test", env("E2E_ADMIN_PASSWORD"));
    await admin.goto("/crm");
    await admin.locator("button", { hasText: "E2E Coupon Admin" }).first().click();
    await admin.getByRole("menuitem", { name: "Settings" }).click();
    await admin.getByRole("dialog").getByText("Coupons", { exact: true }).click();
    await field(admin, "coupon-search").fill(env("E2E_CPS_NETWORK_NAME"));
    const card = admin.getByTestId("coupon-card").first();
    await expect(card.getByTestId("coupon-value")).toHaveText("500 tokens on Flex · 5% off Fixed");
    await expect(card.getByTestId("coupon-applies-to-label")).toHaveText("Flex and Fixed");

    await admin.getByTestId("coupon-new").click();
    const dialog = admin.getByRole("dialog").last();
    await expect(dialog.getByTestId("coupon-applies-to-flex")).toBeChecked();
    await expect(field(dialog, "coupon-fixed-discount")).toHaveCount(0);
    await dialog.getByTestId("coupon-applies-to-fixed").check();
    await expect(field(dialog, "coupon-fixed-discount")).toBeVisible();
    await expect(dialog.getByRole("combobox", { name: "Value type" })).toHaveCount(0);
    await dialog.getByTestId("coupon-applies-to-both").check();
    await expect(field(dialog, "coupon-fixed-discount")).toBeVisible();
    await expect(dialog.getByRole("combobox", { name: "Value type" })).toBeVisible();
    // Brand guide: the checked radio is the brand red (#bc1823), not the forms-plugin blue.
    const radioColour = await dialog.getByTestId("coupon-applies-to-both").evaluate((el) => getComputedStyle(el).color);
    expect(radioColour).toBe("rgb(188, 24, 35)");
    await shot(admin, "1-coupon-dialog-both");

    // A Fixed-only CRM coupon (left Inactive, the default) saves as a discount with no tokens.
    await dialog.getByTestId("coupon-applies-to-fixed").check();
    await field(dialog, "coupon-title").fill(`E2E fixed only ${RUN}`);
    await field(dialog, "coupon-fixed-discount").fill("10");
    await dialog.getByRole("combobox", { name: "How facilities get this coupon" }).click();
    await admin.getByRole("option", { name: "Coupon code" }).click();
    await field(dialog, "coupon-code").fill(`E2E-CPS-${RUN}`);
    await dialog.getByTestId("coupon-save").click();
    await expect(admin.getByTestId("coupon-save")).toHaveCount(0);
    await field(admin, "coupon-search").fill(`E2E fixed only ${RUN}`);
    const fixedCard = admin.getByTestId("coupon-card").first();
    await expect(fixedCard.getByTestId("coupon-value")).toHaveText("10% off Fixed");
    await expect(fixedCard.getByTestId("coupon-applies-to-label")).toHaveText("Fixed");
    await shot(admin, "2-fixed-only-coupon");
    await admin.context().close();
  });

  const owner = await signedIn(browser, "e2e.facility-owner@example.test", env("E2E_OWNER_PASSWORD"));

  await test.step("The customer sees the discount on the Fixed order and tokens on the Flex order", async () => {
    await owner.goto("/cx-portal");
    await owner.getByRole("button", { name: /Billing & Invoices/ }).first().click();
    await owner.getByTestId(`review-order-${FIXED_ORDER}`).click();
    const review = owner.getByTestId("order-review");
    await expect(review.getByTestId("order-review-discount")).toContainText("5% off");
    await expect(review.getByTestId("order-review-bonus")).toHaveCount(0);
    await shot(owner, "3-fixed-order-review");
    await owner.keyboard.press("Escape");
    await expect(review).toBeHidden();

    await owner.getByTestId(`review-order-${FLEX_ORDER}`).click();
    await expect(review.getByTestId("order-review-bonus")).toHaveCount(2);
    await expect(review.getByTestId("order-review-bonus").last()).toContainText("500");
    await expect(review.getByTestId("order-review-discount")).toHaveCount(0);
    await shot(owner, "4-flex-order-review");
    await owner.keyboard.press("Escape");
  });

  await test.step("The Fixed order is confirmed, invoiced and paid in full", async () => {
    const out = execFileSync(
      "bench",
      ["--site", env("BENCH_SITE"), "execute", "crm.tests.e2e_coupon_plan_fixture.confirm_and_pay_fixed", "--kwargs", JSON.stringify({ run_id: RUN })],
      { cwd: env("BENCH_DIR"), encoding: "utf8" },
    );
    const paid = JSON.parse(out.slice(out.indexOf("{")));
    expect(paid.invoice_line_discount).toBe(5);
    expect(paid.redemption.plan).toBe("Fixed");
    expect(paid.redemption.status).toBe("Granted");
    expect(paid.plan.subscription.status).toBe("active");
  });

  await test.step("The customer's Fixed facility shows its subscription", async () => {
    await owner.goto("/cx-portal");
    await owner.getByTestId(`facility-details-${FIXED_MFL}`).click();
    const subscription = owner.getByTestId("facility-subscription");
    await expect(subscription.getByTestId("facility-subscription-value")).toContainText("Active until");
    await expect(subscription).toContainText("Active since");
    await subscription.scrollIntoViewIfNeeded();
    await shot(owner, "5-customer-subscription");
  });

  await test.step("Bonus tokens: refused for the Fixed-only facility, offered to the Flex one", async () => {
    const admin = await signedIn(browser, env("E2E_ADMIN_EMAIL", "e2e.metering-admin@example.test"), env("E2E_ADMIN_PASSWORD"));
    await admin.goto(`/crm/deals/${env("E2E_CPS_DEAL")}#metering`);
    const cards = admin.getByTestId("welcome-bonus");
    await expect(cards).toHaveCount(2);
    const fixedCard = admin.locator("div.rounded-lg", { hasText: `Facility ID: ${env("E2E_CPS_FIXED_FID")}` });
    const flexCard = admin.locator("div.rounded-lg", { hasText: `Facility ID: ${env("E2E_CPS_FLEX_FID")}` });
    await expect(fixedCard.getByTestId("welcome-bonus-state")).toContainText("bought a Flex token package");
    await expect(fixedCard.getByTestId("dispense-welcome-bonus")).toBeDisabled();
    await expect(flexCard.getByTestId("dispense-welcome-bonus")).toBeEnabled();
    await shot(admin, "6-bonus-gating");
  });
});
