import { expect, test } from "@playwright/test";

import { noHorizontalScroll } from "./helpers";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("sections are numbered 01 to 08 in page order", async ({ page }) => {
  await expect(page.locator(".secno")).toHaveText(["01", "02", "03", "04", "05", "06", "07", "08"]);
  await expect(page.locator("h1")).toHaveCount(1);
  await noHorizontalScroll(page);
});

test("every primary button reads Get started and opens onboarding", async ({ page }) => {
  const labels = await page.locator("a.btn.primary").allInnerTexts();
  expect(new Set(labels.map((label) => label.trim()))).toEqual(new Set(["Get started"]));
  for (const href of await page.locator("a.btn.primary").evaluateAll((links) => links.map((a) => a.getAttribute("href")))) {
    expect(href).toMatch(/^\/facility-onboarding/);
  }
});

test("plans read Fixed then Flex, in the cards and the comparison table", async ({ page }) => {
  const fixed = page.getByTestId("plan-fixed");
  test.skip(!(await fixed.count()), "No Fixed packages are published on this site");
  const cards = await page.locator("#plans .plan .name small").allTextContents();
  expect(cards).toEqual(["Value Express Fixed", "Value Express Flex"]);
  await expect(page.locator("table.cmp thead th").nth(1)).toHaveText(/Fixed/);
  await expect(fixed.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/facility-onboarding?plan=fixed");
});

test("Flex package cards carry their package into onboarding", async ({ page }) => {
  const cards = page.getByTestId("flex-package");
  test.skip(!(await cards.count()), "No Flex packages are published on this site");
  for (const card of await cards.all()) {
    await expect(card.locator("dl")).toContainText("Tokens");
    await expect(card.locator("dl")).toContainText("Price per token");
    await expect(card.getByRole("link", { name: "Get started →" })).toHaveAttribute("href", /plan=flex&package=/);
    // Prices stay on one line.
    expect((await card.locator(".p").boundingBox())!.height).toBeLessThan(40);
  }
});

test("Custom works out tokens from the amount and refuses less than the minimum", async ({ page }) => {
  const custom = page.getByTestId("custom-package");
  test.skip(!(await custom.count()), "Custom is not offered on this site");
  const amount = custom.locator("#cu-kes");
  await amount.fill("7000");
  await expect(custom.locator("#cu-t")).toHaveText("1,166");
  await expect(custom.locator("#cu-c")).toHaveText(/6,996\.00/);
  await expect(custom.locator("#cu-go")).toHaveAttribute("href", "/facility-onboarding?plan=custom&amount=7000");
  await amount.fill("5000");
  await expect(custom.locator("#cu-err")).toBeVisible();
  await expect(custom.locator("#cu-go")).toHaveAttribute("aria-disabled", "true");
});

test("calculator presets give a verdict and carry it into onboarding", async ({ page }) => {
  const presets = page.locator("[data-preset]");
  test.skip(!(await presets.count()), "No calculator presets on this site");
  await expect(page.locator("#r-verdict")).not.toBeEmpty();
  await expect(page.locator("#r-go")).toHaveAttribute("href", /\/facility-onboarding\?plan=(flex&package=|fixed)/);
  await presets.last().click();
  await expect(presets.last()).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#r-gonote")).toContainText("preselected");
});

test("the zero-balance rule is visible outside the rules list", async ({ page }) => {
  await expect(page.getByText("When your balance reaches zero")).toBeVisible();
  await expect(page.locator("#flex-rules")).not.toHaveAttribute("open", "");
  await page.goto("/#flex-rules");
  await page.reload();
  await expect(page.locator("#flex-rules")).toHaveAttribute("open", "");
});

test("support details come from settings and the enquiry link picks its topic", async ({ page }) => {
  const details = page.getByTestId("contact-details");
  if (await details.count()) {
    for (const link of await details.locator('a[href^="tel:"]').all()) {
      expect(await link.getAttribute("href")).toMatch(/^tel:\+?\d+$/);
    }
  }
  await page.getByTestId("enterprise-enquiry").click();
  await expect(page.locator("#f-topic")).toHaveValue("CareverseHIMS Advanced & Enterprise");
});

test("the contact form explains what is missing", async ({ page }) => {
  await page.locator("#contactForm").getByRole("button", { name: "Send message" }).click();
  await expect(page.locator("#f-name-err")).toHaveText("Enter your name.");
  await expect(page.locator("#f-name")).toBeFocused();
});

test("primary buttons meet AA contrast", async ({ page }) => {
  const ratio = await page.locator("a.btn.primary").first().evaluate((el) => {
    const rgb = (value: string) => value.match(/\d+(\.\d+)?/g)!.slice(0, 3).map(Number);
    const lum = (c: number[]) => {
      const [r, g, b] = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const style = getComputedStyle(el);
    const [a, b] = [lum(rgb(style.color)), lum(rgb(style.backgroundColor))].sort((x, y) => y - x);
    return (a + 0.05) / (b + 0.05);
  });
  expect(ratio).toBeGreaterThanOrEqual(4.5);
});
