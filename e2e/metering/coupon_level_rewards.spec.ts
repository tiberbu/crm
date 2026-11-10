import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { env, signedIn } from "./journey";

/** frappe-ui puts data-testid on the input itself or on its wrapper, depending on the control. */
const field = (scope, id: string, tag = "input") => scope.locator(`${tag}[data-testid="${id}"], [data-testid="${id}"] ${tag}`).first();

/**
 * Coupon rewards by facility level (P-116 to P-123): one coupon, each facility gets its level's reward.
 *
 * Needs crm.tests.e2e_coupon_level_fixture.setup for this run, its JSON output saved to the file in
 * E2E_CLR_FIXTURE, plus BASE_URL, BENCH_DIR, BENCH_SITE, E2E_ADMIN_PASSWORD, E2E_OWNER_PASSWORD.
 *
 * 1. Settings › Coupons: the network's coupon reads "By facility level", with one line per level.
 *    A new coupon can be given level rows in the dialog (brand-red checkbox, suggested levels) and
 *    its card then lists them.
 * 2. The customer reviews the four orders of the same coupon: Level 2 Flex gets 1,000 coupon tokens,
 *    Level 4 Flex 2,500, Level 2 Fixed 10% off and Level 3B Fixed 4% off.
 * 3. Confirming records each facility's level on its redemption, and the metering grant check lets
 *    the Level 4 amount (2,500) through, not a base value.
 */

const fx = JSON.parse(readFileSync(env("E2E_CLR_FIXTURE"), "utf8"));
const RUN: string = fx.run;

test("one coupon gives each facility level its own reward", async ({ browser }, testInfo) => {
  const shot = async (page, name: string) =>
    testInfo.attach(name, { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });

  await test.step("Settings › Coupons shows the reward per level and lets an admin set it", async () => {
    const admin = await signedIn(browser, fx.coupon_admin, env("E2E_ADMIN_PASSWORD"));
    await admin.goto("/crm");
    await admin.locator("button", { hasText: "E2E Coupon Admin" }).first().click();
    await admin.getByRole("menuitem", { name: "Settings" }).click();
    await admin.getByRole("dialog").getByText("Coupons", { exact: true }).click();
    await field(admin, "coupon-search").fill(fx.network_name);
    const card = admin.getByTestId("coupon-card").first();
    await expect(card.getByTestId("coupon-value")).toHaveText("By facility level");
    await expect(card.getByTestId("coupon-level-line")).toHaveText([
      "1,000 tokens on Flex · 10% off Fixed",
      "1,800 tokens on Flex · 4% off Fixed",
      "2,500 tokens",
      "No reward",
    ]);
    await expect(card.getByTestId("coupon-level-lines")).toContainText("Level 4");
    await expect(card.getByTestId("coupon-level-lines")).toContainText("All other levels");
    await shot(admin, "1-level-coupon-card");

    await admin.getByTestId("coupon-new").click();
    const dialog = admin.getByRole("dialog").last();
    await expect(dialog.getByTestId("coupon-level-rewards")).toHaveCount(0);
    await dialog.getByTestId("coupon-reward-by-level").check();
    // Brand guide: the checked box is the brand red (#bc1823), not the forms-plugin blue.
    const boxColour = await dialog.getByTestId("coupon-reward-by-level").evaluate((el) => getComputedStyle(el).color);
    expect(boxColour).toBe("rgb(188, 24, 35)");
    // Suggested levels come from the self-onboarding levels, the Fixed packages and the levels on record.
    await expect.poll(() => admin.locator("#coupon-level-options option").count()).toBeGreaterThan(0);
    await expect(dialog.getByTestId("coupon-level-row")).toHaveCount(1);

    await field(dialog, "coupon-title").fill(`E2E levels in dialog ${RUN}`);
    await dialog.getByTestId("coupon-applies-to-both").check();
    const rows = dialog.getByTestId("coupon-level-row");
    await field(rows.nth(0), "coupon-level-name").fill("Level 2");
    await field(rows.nth(0), "coupon-level-flex").fill("1000");
    await field(rows.nth(0), "coupon-level-discount").fill("10");
    await dialog.getByTestId("coupon-level-add").click();
    await field(rows.nth(1), "coupon-level-name").fill("Level 4");
    await field(rows.nth(1), "coupon-level-flex").fill("2500");
    await field(rows.nth(1), "coupon-level-discount").fill("0");
    // All other levels: 300 tokens, 2% off Fixed.
    await field(dialog, "coupon-value").fill("300");
    await field(dialog, "coupon-fixed-discount").fill("2");
    await dialog.getByRole("combobox", { name: "How facilities get this coupon" }).click();
    await admin.getByRole("option", { name: "Coupon code" }).click();
    await field(dialog, "coupon-code").fill(`E2E-CLR-${RUN}`);
    await shot(admin, "2-level-coupon-dialog");
    await dialog.getByTestId("coupon-save").click();
    await expect(admin.getByTestId("coupon-save")).toHaveCount(0);

    await field(admin, "coupon-search").fill(`E2E levels in dialog ${RUN}`);
    const created = admin.getByTestId("coupon-card").first();
    await expect(created.getByTestId("coupon-value")).toHaveText("By facility level");
    await expect(created.getByTestId("coupon-level-line")).toHaveText([
      "1,000 tokens on Flex · 10% off Fixed",
      "2,500 tokens",
      "300 tokens on Flex · 2% off Fixed",
    ]);
    await shot(admin, "3-level-coupon-created");
    await admin.context().close();
  });

  await test.step("The customer's orders each carry their own level's reward", async () => {
    const owner = await signedIn(browser, fx.owner, env("E2E_OWNER_PASSWORD"));
    await owner.goto("/cx-portal");
    await owner.getByRole("button", { name: /Billing & Invoices/ }).first().click();
    const review = owner.getByTestId("order-review");

    const flexCases: [string, string][] = [
      ["l2_flex", "1,000"],
      ["l4_flex", "2,500"],
    ];
    for (const [key, tokens] of flexCases) {
      await owner.getByTestId(`review-order-${fx.orders[key]}`).click();
      await expect(review.getByTestId("order-review-bonus").filter({ hasText: "Partner Coupon" })).toContainText(tokens);
      await expect(review.getByTestId("order-review-discount")).toHaveCount(0);
      await shot(owner, `4-${key}-order-review`);
      await owner.keyboard.press("Escape");
      await expect(review).toBeHidden();
    }

    const fixedCases: [string, string][] = [
      ["l2_fixed", "10% off"],
      ["l3b_fixed", "4% off"],
    ];
    for (const [key, discount] of fixedCases) {
      await owner.getByTestId(`review-order-${fx.orders[key]}`).click();
      await expect(review.getByTestId("order-review-discount")).toContainText(discount);
      await expect(review.getByTestId("order-review-bonus")).toHaveCount(0);
      await shot(owner, `5-${key}-order-review`);
      await owner.keyboard.press("Escape");
      await expect(review).toBeHidden();
    }
    await owner.context().close();
  });

  await test.step("Confirming records the level, and the grant check honours the level amount", async () => {
    const out = execFileSync(
      "bench",
      ["--site", env("BENCH_SITE"), "execute", "crm.tests.e2e_coupon_level_fixture.confirm_orders", "--kwargs", JSON.stringify({ run_id: RUN })],
      { cwd: env("BENCH_DIR"), encoding: "utf8" },
    );
    const confirmed = JSON.parse(out.slice(out.indexOf("{")));
    expect(confirmed.l4_flex.redemption).toMatchObject({ status: "Reserved", plan: "Flex", facility_level: "Level 4", tokens_awarded: 2500 });
    expect(confirmed.l3b_fixed.redemption).toMatchObject({ status: "Reserved", plan: "Fixed", facility_level: "Level 3B", discount_percent: 4 });
    const couponLine = confirmed.l4_flex.grant_check.find((b) => b.type === "Partner Coupon");
    expect(couponLine).toMatchObject({ tokens: 2500, refused: null });
  });
});
