import { expect, test } from "@playwright/test";

test("the hero offers Contact us, which scrolls to the contact section", async ({ page }) => {
  await page.goto("/");
  const contact = page.getByTestId("hero-contact");
  await expect(contact).toBeVisible();
  await contact.click();
  await expect(page).toHaveURL(/#contact$/);
  await expect(page.getByRole("heading", { name: /Questions before you start/ })).toBeInViewport();
});

test("pricing cards show a price and its Care Tokens, with no billing period", async ({ page }) => {
  await page.goto("/");
  const pricing = page.locator("#pricing");
  test.skip(!(await pricing.count()), "No token packages are published on this site");
  const plans = pricing.locator("li.plan");
  await expect(plans.first()).toBeVisible();
  for (const plan of await plans.all()) {
    await expect(plan.locator(".tokens")).toHaveText(/^[\d,]+ Care Tokens$/);
  }
  await expect(pricing).not.toContainText(/\/\s*(month|quarter|year|mo)\b/i);
  await expect(pricing).not.toContainText(/each month/i);
});
