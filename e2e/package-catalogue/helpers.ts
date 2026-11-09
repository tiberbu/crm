import { Browser, expect, Page } from "@playwright/test";

export const RUN = `E2E ${Date.now().toString(36).toUpperCase()}`;

/** A signed-in page for one of the synthetic users. */
export async function signIn(browser: Browser, email = process.env.SM_EMAIL, password = process.env.SM_PASSWORD) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const response = await page.request.post("/api/method/login", { data: { usr: email, pwd: password } });
  expect(response.ok(), "sign-in").toBeTruthy();
  return page;
}

export async function openPackages(page: Page) {
  await page.goto("/crm");
  await page.locator("button", { hasText: /Synthetic|SalesManager|SalesUser/ }).first().click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await page.getByRole("dialog").getByText("Packages", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Packages" })).toBeVisible();
}

export const card = (page: Page, name: string) => page.locator(`[data-testid="package-card"][data-package="${name}"]`);

export async function cardAction(page: Page, name: string, action: string) {
  await card(page, name).getByTestId("package-actions").click();
  await page.getByRole("menuitem", { name: action, exact: true }).click();
}

export async function fillPackage(page: Page, values: { plan?: string; name?: string; tokens?: string; price?: string; period?: string; levels?: string; description?: string }) {
  const dialog = page.getByRole("dialog").last();
  const choose = async (label: string, option: string) => {
    await dialog.getByRole("combobox", { name: label }).click();
    await page.getByRole("option", { name: new RegExp(`^${option}`) }).click();
  };
  if (values.plan) await choose("Plan", values.plan);
  if (values.name !== undefined) await dialog.getByLabel("Name facilities see").fill(values.name);
  if (values.tokens !== undefined) await dialog.getByLabel("Tokens", { exact: true }).fill(values.tokens);
  if (values.price !== undefined) await dialog.getByLabel(/^Price/).fill(values.price);
  if (values.period) await choose("Billing period", values.period);
  if (values.levels !== undefined) await dialog.getByLabel("Facility levels (one per line)").fill(values.levels);
  if (values.description !== undefined) await dialog.getByLabel("Description on the card").fill(values.description);
  await dialog.getByRole("button", { name: /^(Add|Save) package$/ }).click();
}

/** Columns a card grid is laid out in: distinct left edges of its cards. */
export async function columns(page: Page, selector: string) {
  const lefts = await page.locator(selector).evaluateAll((cards) => cards.map((c) => Math.round(c.getBoundingClientRect().left)));
  return new Set(lefts).size;
}

export async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}
