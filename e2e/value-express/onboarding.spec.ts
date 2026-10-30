import { expect, test } from "@playwright/test";

import { mockOnboarding, noHorizontalScroll, toPackages, verify } from "./helpers";

test("verify: one line of help, the stepper lines up with the card, the resend timer counts down", async ({ page }) => {
  await mockOnboarding(page);
  await page.goto("/facility-onboarding");
  const stepper = await page.locator(".stepper").boundingBox();
  const card = await page.locator("form.card").boundingBox();
  expect(Math.round(stepper!.x)).toBe(Math.round(card!.x));
  expect(Math.round(stepper!.width)).toBe(Math.round(card!.width));
  await page.getByPlaceholder("Enter your ID number").fill("12345678");
  await page.getByRole("button", { name: "Verify & Find My Facility" }).click();
  const timer = page.getByText(/Resend code in 0:\d\d/);
  const first = await timer.innerText();
  await page.waitForTimeout(2100);
  expect(await timer.innerText()).not.toBe(first);
  await noHorizontalScroll(page);
});

test("facility: not eligible and already onboarded facilities cannot be selected", async ({ page }) => {
  await mockOnboarding(page);
  await verify(page);
  const above = page.locator(".fac", { hasText: "Synthetic Hospital C" });
  await expect(above).toHaveAttribute("aria-disabled", "true");
  await expect(above.locator('input[type="checkbox"]')).toHaveCount(0);
  await expect(above).toContainText("Value Express is for Level 2 and Level 3");
  await expect(page.locator(".fac", { hasText: "Synthetic Clinic D" }).getByTestId("facility-already-onboarded")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue to Packages →" })).toBeDisabled();
});

test("package: nothing is preselected, the hint says why, and Next moves to the other facility", async ({ page }) => {
  await mockOnboarding(page);
  await verify(page);
  await toPackages(page, ["Synthetic Clinic A", "Synthetic Nursing Home B"]);
  await expect(page.locator(".hintline")).toHaveText("Choose a package for each facility to continue.");
  const buttons = page.getByTestId("package-grid").locator(".pkg > .btn");
  const tops = await buttons.evaluateAll((all) => all.map((b) => Math.round(b.getBoundingClientRect().top)));
  if (page.viewportSize()!.width > 1000) expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(2);
  await buttons.first().click();
  await page.getByRole("button", { name: /^Next: Synthetic Nursing Home B/ }).click();
  await expect(page.getByRole("tab", { name: /Synthetic Nursing Home B/ })).toHaveAttribute("aria-selected", "true");
  await noHorizontalScroll(page);
});

test("package: Fixed shows only the price for the facility's own level", async ({ page }) => {
  await mockOnboarding(page);
  await verify(page);
  await toPackages(page, ["Synthetic Nursing Home B"]);
  const fixed = page.getByTestId("plan-fixed");
  test.skip(!(await fixed.count()), "No Fixed packages are published on this site");
  await expect(fixed).toContainText("for your Level 3B facility");
  await fixed.click();
  const tiers = page.getByTestId("fixed-tier");
  await expect(tiers.filter({ hasText: "Matches your facility level" })).toHaveCount(1);
  await expect(tiers.filter({ hasText: "Matches your facility level" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".hintline")).toHaveCount(0);
});

test("a calculator result carried as Fixed is preselected at each facility's own level", async ({ page }) => {
  await mockOnboarding(page);
  await verify(page, "?plan=fixed");
  await toPackages(page, ["Synthetic Clinic A", "Synthetic Nursing Home B"]);
  test.skip(!(await page.getByTestId("plan-fixed").count()), "No Fixed packages are published on this site");
  await expect(page.getByTestId("carried-choice")).toContainText("Value Express Fixed");
  await expect(page.getByTestId("plan-fixed")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("next-facility")).toContainText("All 2 facilities are set");
});

test("a Custom amount is carried, priced and submitted for the server to re-price", async ({ page }) => {
  const submitted = await mockOnboarding(page);
  await verify(page, "?plan=custom&amount=7000");
  await toPackages(page, ["Synthetic Clinic A"]);
  const custom = page.getByTestId("custom-package");
  test.skip(!(await custom.count()), "Custom is not offered on this site");
  await expect(custom.locator(".rec")).toHaveText("Popular choice for you");
  await expect(custom).toContainText("1,166");
  await custom.locator("#custom-amount").fill("5000");
  await expect(page.locator(".sumbar button.primary")).toBeDisabled();
  await custom.locator("#custom-amount").fill("20000");
  await expect(custom).toContainText("3,731");
  await page.locator(".sumbar").getByRole("button", { name: "Continue to Review →" }).click();

  await expect(page.getByRole("heading", { name: "Review and confirm" })).toBeVisible();
  await expect(page.locator(".rv tfoot")).toContainText("Total to pay");
  const confirm = page.getByTestId("confirm-submit");
  await expect(confirm).toHaveAttribute("aria-disabled", "true");
  // aria-disabled keeps the button focusable and clickable, so a click can explain what is missing.
  await confirm.click({ force: true });
  await expect(page.locator("#agree-row")).toHaveClass(/nudge/);
  await expect(page.getByTestId("terms-acceptance")).toBeFocused();
  await page.getByTestId("terms-acceptance").check();
  await confirm.click();
  await expect(page.getByRole("heading", { name: "Your request has been submitted" })).toBeVisible();
  expect(JSON.parse(submitted[0].facility_package_items)).toEqual({ "FID-00-VXTEST-1": { custom_amount: 20000 } });
});

test("review: Change goes back to that facility's package", async ({ page }) => {
  await mockOnboarding(page);
  await verify(page, "?plan=flex");
  await toPackages(page, ["Synthetic Clinic A", "Synthetic Nursing Home B"]);
  for (const name of ["Synthetic Clinic A", "Synthetic Nursing Home B"]) {
    await page.getByRole("tab", { name: new RegExp(name) }).click();
    await page.getByTestId("package-grid").locator(".pkg > .btn").first().click();
  }
  await page.locator(".sumbar").getByRole("button", { name: "Continue to Review →" }).click();
  await page.getByTestId("change-FID-00-VXTEST-2").click();
  await expect(page.getByRole("tab", { name: /Synthetic Nursing Home B/ })).toHaveAttribute("aria-selected", "true");
});

const SYN_PKG = {
  item_code: "CV-TOKEN-STARTER",
  display_name: "Starter",
  description: "Synthetic starter package",
  price_ex_vat: 6000,
  currency: "KES",
  vat_label: "VAT",
  token_quantity: 1000,
  audience: "Small clinics",
  plan: "flex",
};

test("url: a carried Partner Coupon is validated and shows the network name", async ({ page }) => {
  await mockOnboarding(page, {
    catalog: {
      ok: {
        network: { name: "NET-SYN-1", slug: "synthetic-net", display_name: "Synthetic Network Ltd" },
        packages: [SYN_PKG],
        fixed_packages: [],
        custom_offer: null,
        calculator_config: {},
        welcome_bonus_tokens: 0,
        partner_coupon_tokens: 500,
      },
    },
  });
  await verify(page, "?partner_coupon=123456");
  await toPackages(page, ["Synthetic Clinic A"]);
  await expect(page.getByTestId("partner-coupon-toggle")).toHaveText("Partner Coupon: 123456");
  await page.getByTestId("partner-coupon-toggle").click();
  await expect(page.getByTestId("partner-coupon-applied")).toBeVisible();
  await expect(page.getByTestId("partner-coupon-network")).toHaveText("Synthetic Network Ltd");
});

test("url: an unknown Partner Coupon is dropped silently and the catalog still loads", async ({ page }) => {
  await mockOnboarding(page, {
    catalog: [
      { error: { status: 417, body: { exception: true, _server_messages: "[\"That Partner Coupon is not available.\"]" } } },
      {
        ok: {
          network: {},
          packages: [SYN_PKG],
          fixed_packages: [],
          custom_offer: null,
          calculator_config: {},
          welcome_bonus_tokens: 0,
          partner_coupon_tokens: 0,
        },
      },
    ],
  });
  await verify(page, "?partner_coupon=999999");
  await toPackages(page, ["Synthetic Clinic A"]);
  await expect(page.getByTestId("partner-coupon-toggle")).toHaveText("Have a Partner Coupon?");
  await expect(page.getByTestId("catalog-error")).toHaveCount(0);
  await expect(page.getByTestId("package-grid")).toBeVisible();
});
