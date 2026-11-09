import { expect, test } from "@playwright/test";

test("the hero's See how it works scrolls to the four steps", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "See how it works" }).click();
  await expect(page).toHaveURL(/#how$/);
  await expect(page.getByRole("heading", { name: /From enquiry to live in four simple steps/ })).toBeInViewport();
});

test("Flex package cards show a price and their tokens, with no billing period", async ({ page }) => {
  await page.goto("/");
  const cards = page.getByTestId("flex-package");
  test.skip(!(await cards.count()), "No token packages are published on this site");
  for (const card of await cards.all()) {
    await expect(card.locator(".p")).toHaveText(/^KES [\d,]+$/);
    await expect(card.locator("dl")).toContainText(/Tokens\s*[\d,]+/);
  }
  await expect(page.locator("#flex-packages")).not.toContainText(/\/\s*(month|quarter|year|mo)\b/i);
});
