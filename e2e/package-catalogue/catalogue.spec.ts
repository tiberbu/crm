import { expect, test } from "@playwright/test";

import { mockOnboarding, toPackages, verify } from "../value-express/helpers";
import { RUN, card, cardAction, columns, fillPackage, noHorizontalScroll, openPackages, signIn } from "./helpers";

// One journey through the catalogue: each step builds on the packages the last one left.
test.describe.configure({ mode: "serial" });

const FLEX = `${RUN} Flex`;
const FIXED = `${RUN} Fixed`;
const LEVEL = `${RUN} Level`;

test.beforeAll(() => {
  if (!process.env.SM_EMAIL || !process.env.SU_EMAIL) throw new Error("Set SM_EMAIL/SM_PASSWORD and SU_EMAIL/SU_PASSWORD");
});

test("a Sales User has no Packages page and the API refuses them", async ({ browser }) => {
  const page = await signIn(browser, process.env.SU_EMAIL, process.env.SU_PASSWORD);
  const response = await page.request.get("/api/method/crm.api.package_catalogue.get_package_catalogue");
  expect(response.status()).toBe(403);
  await page.goto("/crm");
  await page.locator("button", { hasText: /Synthetic|SalesUser/ }).first().click();
  await page.getByRole("menuitem", { name: "Settings" }).click();
  await expect(page.getByRole("dialog").getByText("Profile", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog").getByText("Packages", { exact: true })).toHaveCount(0);
  await page.context().close();
});

test("a Sales Manager adds a Flex package with its price and it goes on sale", async ({ browser }) => {
  const page = await signIn(browser);
  await openPackages(page);
  await expect(page.getByTestId("package-section-Flex").getByTestId("package-card").first()).toBeVisible();
  await page.getByTestId("package-new").click();
  await fillPackage(page, { name: FLEX, tokens: "1200", price: "7000", description: "Synthetic package for the catalogue journey" });
  await expect(card(page, FLEX)).toContainText("KES 7,000");
  await expect(card(page, FLEX)).toContainText("1,200");
  await expect(card(page, FLEX).getByTestId("package-status-badge")).toHaveText("Active");
  await page.context().close();

  const guest = await browser.newPage();
  await guest.goto("/");
  const landing = guest.getByTestId("flex-package").filter({ hasText: FLEX });
  await expect(landing).toContainText("KES 7,000");
  await expect(landing.getByRole("link", { name: "Get started →" })).toHaveAttribute("href", /package=VX-E2E-/);
  await guest.close();
});

test("editing the price and the order shows on the landing page", async ({ browser }) => {
  const page = await signIn(browser);
  await openPackages(page);
  await cardAction(page, FLEX, "Edit");
  await fillPackage(page, { price: "7200" });
  await expect(card(page, FLEX)).toContainText("KES 7,200");

  const flexNames = () => page.getByTestId("package-section-Flex").getByTestId("package-card").evaluateAll((cards) => cards.map((c) => c.getAttribute("data-package")));
  const before = await flexNames();
  await cardAction(page, FLEX, "Move earlier");
  await expect.poll(flexNames).not.toEqual(before);
  const moved = await flexNames();
  expect(moved.indexOf(FLEX)).toBe(before.indexOf(FLEX) - 1);
  await cardAction(page, FLEX, "Move later");
  await expect.poll(flexNames).toEqual(before);
  await page.context().close();

  const guest = await browser.newPage();
  await guest.goto("/");
  await expect(guest.getByTestId("flex-package").filter({ hasText: FLEX })).toContainText("KES 7,200");
  await guest.close();
});

test("disabling hides a package and enabling brings it back", async ({ browser }) => {
  const page = await signIn(browser);
  await openPackages(page);
  await cardAction(page, FLEX, "Disable");
  await expect(card(page, FLEX)).toHaveCount(0);
  await page.getByRole("radio", { name: /Disabled/ }).click();
  await expect(card(page, FLEX).getByTestId("package-status-badge")).toHaveText("Disabled");

  const guest = await browser.newPage();
  await guest.goto("/");
  await expect(guest.getByTestId("flex-package").filter({ hasText: FLEX })).toHaveCount(0);

  await cardAction(page, FLEX, "Enable");
  await page.getByRole("radio", { name: /Active/ }).click();
  await expect(card(page, FLEX).getByTestId("package-status-badge")).toHaveText("Active");
  await guest.reload();
  await expect(guest.getByTestId("flex-package").filter({ hasText: FLEX })).toHaveCount(1);
  await guest.close();
  await page.context().close();
});

test("a Quarterly Fixed package reads per quarter, then is discontinued for good", async ({ browser }) => {
  const page = await signIn(browser);
  await openPackages(page);
  await page.getByTestId("package-new").click();
  await fillPackage(page, { plan: "Fixed", name: FIXED, price: "42000", period: "Quarterly", levels: LEVEL, description: "Synthetic quarterly fee" });
  await expect(card(page, FIXED)).toContainText("KES 42,000");
  await expect(card(page, FIXED)).toContainText("per quarter");

  const guest = await browser.newPage();
  await guest.goto("/");
  const tier = guest.getByTestId("plan-fixed").getByTestId("fixed-tier").filter({ hasText: LEVEL });
  await expect(tier).toContainText("KES 42,000");
  await expect(tier).toContainText("per quarter");

  // The same level cannot have two active Fixed packages.
  await page.getByTestId("package-new").click();
  await fillPackage(page, { plan: "Fixed", name: `${FIXED} 2`, price: "15000", levels: LEVEL, description: "Overlaps" });
  await expect(page.getByRole("dialog").last()).toContainText("already has an active Fixed package");
  await page.getByRole("dialog").last().getByRole("button", { name: "Cancel" }).click();

  await cardAction(page, FIXED, "Discontinue");
  await page.getByRole("dialog").getByRole("button", { name: "Discontinue" }).click();
  await expect(card(page, FIXED)).toHaveCount(0);
  await page.getByRole("radio", { name: /Discontinued/ }).click();
  await expect(card(page, FIXED).getByTestId("package-status-badge")).toHaveText("Discontinued");
  await card(page, FIXED).getByTestId("package-actions").click();
  await expect(page.getByRole("menuitem")).toHaveText(["Duplicate as new"]);
  await page.keyboard.press("Escape");

  await guest.reload();
  await expect(guest.getByTestId("fixed-tier").filter({ hasText: LEVEL })).toHaveCount(0);
  await guest.close();
  await page.context().close();
});

test("seven cards lay out four and three, two a row on tablets, one on phones", async ({ browser }) => {
  const page = await signIn(browser);
  await openPackages(page);
  // Duplicate the journey's package until the landing page has seven Flex + Custom cards.
  const guest = await browser.newPage();
  await guest.goto("/");
  let cards = await guest.locator("#flex-packages .pkgs > *").count();
  for (let n = 2; cards < 7; n++, cards++) {
    await cardAction(page, FLEX, "Duplicate");
    await fillPackage(page, { name: `${FLEX} ${n}`, tokens: String(1200 + n * 100), price: String(7200 + n * 500) });
    await expect(card(page, `${FLEX} ${n}`)).toBeVisible();
  }
  await page.context().close();

  await guest.reload();
  const grid = "#flex-packages .pkgs > *";
  await expect(guest.locator(grid)).toHaveCount(7);
  expect(await columns(guest, grid)).toBe(4);
  await guest.setViewportSize({ width: 900, height: 900 });
  expect(await columns(guest, grid)).toBe(2);
  await guest.setViewportSize({ width: 360, height: 800 });
  expect(await columns(guest, grid)).toBe(1);
  await noHorizontalScroll(guest);
  await guest.close();
});

test("onboarding offers the new packages in the same balanced grid", async ({ page }) => {
  await mockOnboarding(page);
  await verify(page);
  await toPackages(page, ["Synthetic Clinic A"]);
  const grid = page.getByTestId("package-grid");
  await expect(grid).toContainText(FLEX);
  expect(await columns(page, '[data-testid="package-grid"] > .pkg')).toBe(4);
  await page.setViewportSize({ width: 360, height: 800 });
  expect(await columns(page, '[data-testid="package-grid"] > .pkg')).toBe(1);
  await noHorizontalScroll(page);
});

test("the journey's packages are discontinued and leave the landing page", async ({ browser }) => {
  const page = await signIn(browser);
  await openPackages(page);
  for (const name of await page.getByTestId("package-card").evaluateAll((cards) => cards.map((c) => c.getAttribute("data-package")))) {
    if (!name?.startsWith(RUN)) continue;
    await cardAction(page, name, "Discontinue");
    await page.getByRole("dialog").getByRole("button", { name: "Discontinue" }).click();
    await expect(card(page, name)).toHaveCount(0);
  }
  await page.context().close();
  const guest = await browser.newPage();
  await guest.goto("/");
  await expect(guest.getByTestId("flex-package").filter({ hasText: RUN })).toHaveCount(0);
  await guest.close();
});
