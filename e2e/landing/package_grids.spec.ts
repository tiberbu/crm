import { expect, Locator, Page, test } from "@playwright/test";

/**
 * Package cards fill the content width: one column per package (up to four), no empty
 * column and no orphaned last card. Checked on the home page Flex packages, the onboarding package step
 * (identity, OTP and catalog calls are mocked; the page and its CSS are real), and, when
 * E2E_OWNER_PASSWORD is set, the CX portal pricing view.
 */

const WIDTHS = [1440, 1024, 390];

async function rows(cards: Locator): Promise<number[]> {
  const tops = await cards.evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().top)));
  return [...new Set(tops)];
}

async function expectRowSpansGrid(grid: Locator, cards: Locator, width: number) {
  // Retried: a step's entrance transition can still be moving the cards when first measured.
  await expect(async () => {
    const count = await cards.count();
    const rowTops = await rows(cards);
    const box = (await grid.boundingBox())!;
    const last = (await cards.last().boundingBox())!;
    const first = (await cards.first().boundingBox())!;
    if (width >= 1024 && count <= 4) {
      expect(rowTops, "all cards on one row").toHaveLength(1);
    } else if (width < 640) {
      expect(rowTops, "one card per row").toHaveLength(count);
    }
    // Each row reaches both edges of the grid: no empty trailing column.
    expect(Math.abs(first.x - box.x)).toBeLessThanOrEqual(2);
    expect(Math.abs(last.x + last.width - (box.x + box.width))).toBeLessThanOrEqual(2);
  }).toPass({ timeout: 10_000 });
}

const PACKAGES = [
  { item_code: "CV-TOKEN-STARTER", display_name: "Starter", price: 6000, price_ex_vat: 6000, gross_total: 6960, vat_amount: 960, vat_label: "VAT (16%)", currency: "KES", token_quantity: 1000 },
  { item_code: "CV-TOKEN-GROWTH", display_name: "Growth", price: 15000, price_ex_vat: 15000, gross_total: 17400, vat_amount: 2400, vat_label: "VAT (16%)", currency: "KES", token_quantity: 2800 },
  { item_code: "CV-TOKEN-SCALE", display_name: "Scale", price: 30000, price_ex_vat: 30000, gross_total: 34800, vat_amount: 4800, vat_label: "VAT (16%)", currency: "KES", token_quantity: 6250 },
];

async function mockExpress(page: Page) {
  const replies: Record<string, unknown> = {
    start_identity: { data: { session_token: "e2e-session", delivery: { status: "sent", resend_after: 60 } } },
    verify_otp: {
      data: {
        state: "ready",
        identity: { full_name: "E2E Owner" },
        account_email: "e2e.owner@example.test",
        facilities: [{ facility_id: "FID-E2E", facility_name: "E2E Grid Clinic", onboarding_eligible: true }],
      },
    },
    get_catalog: { data: { network: {}, packages: PACKAGES, welcome_bonus_tokens: 400, partner_coupon_tokens: 0 } },
  };
  await page.route(/\/api\/method\/crm\.api\.facility_onboarding\.(start_identity|verify_otp|get_catalog)/, (route) => {
    const method = route.request().url().match(/facility_onboarding\.(\w+)/)![1];
    return route.fulfill({ json: { message: replies[method] } });
  });
}

for (const width of WIDTHS) {
  test.describe(`at ${width}px`, () => {
    test.use({ viewport: { width, height: 1000 } });

    test("home page pricing cards span the content width", async ({ page }) => {
      await page.goto("/");
      const grid = page.locator("#flex-packages .pkgs");
      test.skip(!(await grid.count()), "No token packages are published on this site");
      await grid.scrollIntoViewIfNeeded();
      await expectRowSpansGrid(grid, grid.locator("> .pkg"), width);
    });

    test("Express package cards span the content width", async ({ page }) => {
      await mockExpress(page);
      await page.goto("/facility-onboarding");
      await page.getByPlaceholder("Enter your ID number").fill("12345678");
      await page.getByRole("button", { name: /Verify & Find My Facility/ }).click();
      const submit = page.getByRole("button", { name: "Verify code" });
      const digits = page.locator('form input[inputmode="numeric"]');
      await expect(digits).toHaveCount(6);
      for (const [index, digit] of [..."123456"].entries()) await digits.nth(index).fill(digit);
      await submit.click();
      await page.locator('form input[type="checkbox"]').first().check();
      await page.getByRole("button", { name: /Continue to Packages/ }).click();
      const grid = page.getByTestId("package-grid");
      await expect(grid.locator("> .pkg")).toHaveCount(PACKAGES.length);
      await expectRowSpansGrid(grid, grid.locator("> .pkg"), width);
      await page.screenshot({ path: test.info().outputPath(`express-${width}.png`), fullPage: false });
    });

    test("portal pricing cards span the content width", async ({ browser }) => {
      test.skip(!process.env.E2E_OWNER_PASSWORD, "Set E2E_OWNER_PASSWORD to check the signed-in portal");
      const context = await browser.newContext({ viewport: { width, height: 1000 }, ignoreHTTPSErrors: true });
      const login = await context.request.post("/api/method/login", {
        form: { usr: process.env.E2E_OWNER_EMAIL || "e2e.facility-owner@example.test", pwd: process.env.E2E_OWNER_PASSWORD! },
      });
      expect(login.ok()).toBeTruthy();
      const page = await context.newPage();
      await page.goto("/cx-portal");
      if (width < 768) {
        // Phones reach pricing through the bottom bar's More menu.
        await page.getByRole("button", { name: "More navigation options" }).click();
      }
      await page.getByRole("button", { name: /Plans & Pricing/ }).filter({ visible: true }).first().click();
      const grid = page.getByTestId("portal-package-grid");
      await expect(grid).toBeVisible();
      await expectRowSpansGrid(grid, grid.locator("> article"), width);
      await context.close();
    });
  });
}
