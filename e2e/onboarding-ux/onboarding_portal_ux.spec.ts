import { readFileSync } from "fs";

import { expect, test } from "@playwright/test";

import { env, signedIn } from "../metering/journey";
import { mockOnboardingApi, reachFacilitiesStep, reachReviewStep, SYNTHETIC_TERMS } from "./onboarding";

/**
 * Review fixes for self-onboarding and the facility portal
 * (_bmad-output/onboarding-portal-ux/planning-artifacts). The email mask is covered by
 * crm/tests/test_facility_onboarding.py, since these onboarding steps use synthetic answers.
 */

test.describe("self-onboarding", () => {
  test.beforeEach(async ({ page }) => {
    await mockOnboardingApi(page, 25);
    await reachFacilitiesStep(page);
  });

  test("the facility list is paged and searchable, and keeps selections", async ({ page }) => {
    const cards = page.getByTestId("facility-select-checkbox");
    await expect(cards).toHaveCount(10);
    // Every facility shows its Facility ID beside the MFL code, and can be found by it.
    await expect(page.getByTestId("onboarding-facility-id")).toHaveCount(10);
    await expect(page.getByTestId("onboarding-facility-id").first()).toHaveText("Facility ID FID-00-TEST-01");
    await expect(page.getByTestId("facility-pager-status")).toHaveText("Showing 1–10 of 25");

    await cards.first().check();
    await page.getByRole("button", { name: /Next/ }).click();
    await expect(page.getByTestId("facility-pager-status")).toHaveText("Showing 11–20 of 25");
    await cards.first().check();
    await page.getByRole("button", { name: /Next/ }).click();
    await expect(cards).toHaveCount(5);
    // The last facility is already set up and cannot be chosen.
    await expect(cards.last()).toBeDisabled();

    await page.getByTestId("facility-search").fill("Clinic 01");
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toBeChecked();
    await expect(page.getByTestId("facility-pager")).toHaveCount(0);
    await page.getByTestId("facility-search").fill("FID-00-TEST-11");
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toBeChecked();
    await page.getByTestId("facility-search").fill("");

    await expect(page.getByTestId("facility-selected-count")).toHaveText("2 of 25 selected");
    await expect(page.getByTestId("facility-continue-count")).toHaveText("2");
  });

  test("the review step speaks of a Partner Coupon and the Terms can be downloaded", async ({ page }) => {
    await reachReviewStep(page);

    await expect(page.getByTestId("review-partner-coupon")).toHaveText("Not applied");
    await expect(page.getByTestId("no-partner-coupon-note")).toContainText("No Partner Coupon applied");
    await expect(page.getByRole("button", { name: "Add a Partner Coupon" })).toBeVisible();
    const review = page.locator("main");
    await expect(review).not.toContainText("No Network");
    await expect(review).not.toContainText("Network ID");

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("terms-download").click(),
    ]);
    expect(download.suggestedFilename()).toBe("synthetic-onboarding-terms.html");
    const saved = readFileSync(await download.path(), "utf8");
    expect(saved).toContain(`<title>${SYNTHETIC_TERMS}</title>`);
    expect(saved).toContain("Synthetic terms used by the UI checks.");
    expect(saved).toContain("default-src 'none'");
    expect(saved).toContain(`Reference: ${"0".repeat(64)}`);
  });
});

test.describe("facility portal", () => {
  const NO_PARTNER_MFL = env("E2E_NO_PARTNER_MFL");
  const NO_PARTNER_FACILITY = env("E2E_NO_PARTNER_FACILITY");

  test("Plans & Pricing cards line up and show KES prices", async ({ browser }) => {
    const owner = await signedIn(browser, env("E2E_OWNER_EMAIL", "e2e.facility-owner@example.test"), env("E2E_OWNER_PASSWORD"));
    await owner.goto("/cx-portal");
    await owner.getByRole("button", { name: /Plans & Pricing/ }).first().click();
    const cards = owner.getByTestId("portal-package-card");
    await expect(cards.first()).toBeVisible();
    const count = await cards.count();
    expect(count).toBeGreaterThan(1);

    const top = async (testId: string) =>
      Promise.all(
        Array.from({ length: count }, async (_, index) =>
          Math.round((await cards.nth(index).getByTestId(testId).boundingBox())!.y),
        ),
      );
    expect(new Set(await top("portal-package-tokens")).size).toBe(1);
    expect(new Set(await top("portal-package-price")).size).toBe(1);
    const buttonBottoms = await Promise.all(
      Array.from({ length: count }, async (_, index) => {
        const box = (await cards.nth(index).getByRole("button").boundingBox())!;
        return Math.round(box.y + box.height);
      }),
    );
    expect(new Set(buttonBottoms).size).toBe(1);

    const grid = owner.getByTestId("portal-package-grid");
    await expect(grid).toContainText("KES");
    await expect(grid).not.toContainText("Ksh");
    await expect(grid).toContainText("per token");
  });

  test("a facility without a partner shows none, and its page has orders to pay and billing details", async ({
    browser,
  }) => {
    const owner = await signedIn(browser, env("E2E_OWNER_EMAIL", "e2e.facility-owner@example.test"), env("E2E_OWNER_PASSWORD"));
    await owner.setViewportSize({ width: 1440, height: 1000 });
    await owner.goto("/cx-portal");
    await owner.getByRole("button", { name: /^Facilities/ }).first().click();
    const table = owner.locator("table").first();
    await expect(table.locator("th", { hasText: "Facility ID" })).toBeVisible();
    await expect(table.locator("th", { hasText: /MFL Code/i })).toHaveCount(0);
    const row = owner.locator("tr", { hasText: NO_PARTNER_MFL });
    await expect(row).toBeVisible();
    await expect(row.getByTestId("facility-id")).toHaveText(/^FID-/);
    await expect(row).toContainText(`MFL ${NO_PARTNER_MFL}`);
    await expect(row.getByTestId("facility-partner")).toHaveCount(0);
    await expect(owner.locator("main")).not.toContainText("No Network");
    // A facility onboarded with a Partner Coupon still shows its partner.
    await expect(owner.locator("tr", { hasText: env("E2E_PARTNER_MFL") }).getByTestId("facility-partner")).toBeVisible();

    await row.getByRole("button", { name: NO_PARTNER_FACILITY }).click();
    await expect(owner.getByRole("heading", { level: 1, name: NO_PARTNER_FACILITY })).toBeVisible();
    await expect(owner.getByTestId("facility-header-ids")).toHaveText(new RegExp(`^Facility ID FID-.* · MFL ${NO_PARTNER_MFL}$`));
    await expect(owner.locator("main")).not.toContainText("No Network");
    await expect(owner.getByTestId("facility-partner-card")).toHaveCount(0);

    const summary = owner.getByTestId("facility-summary").locator("article");
    await expect(summary).toHaveCount(3);
    const heights = await Promise.all(
      [0, 1, 2].map(async (index) => Math.round((await summary.nth(index).boundingBox())!.height)),
    );
    expect(new Set(heights).size).toBe(1);
    await expect(owner.getByTestId("facility-available-tokens-value")).toHaveText(/^[\d,.]+$/);
    await expect(owner.getByTestId("facility-amount-due")).toContainText("to review before invoicing");
    await expect(owner.getByTestId("facility-amount-due")).not.toContainText("KES 0");
    await expect(owner.getByTestId("facility-current-package")).toContainText("Ordered");

    const review = owner.locator('[data-testid^="facility-review-order-"]').first();
    await expect(review).toBeVisible();
    await review.click();
    await expect(owner.getByRole("dialog")).toContainText("KRA PIN");
    await owner.keyboard.press("Escape");

    const billing = owner.getByTestId("facility-billing");
    await expect(billing).toContainText("Billing information");
    await expect(owner.getByTestId("billing-customer")).not.toBeEmpty();
    await expect(billing).toContainText("KRA PIN");
    await expect(billing).toContainText("Billing address");
  });
});
