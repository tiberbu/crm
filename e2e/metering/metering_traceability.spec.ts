import { expect, test, type Locator, type Page } from "@playwright/test";

import { env, signedIn } from "./journey";

/** reka-ui opens on pointermove and ignores moves while the pointer is "in transit";
 * settle after the hover, then nudge 2px inside the trigger for a fresh, non-transit
 * pointermove that opens the tooltip. */
async function hoverForTooltip(page: Page, target: Locator) {
  await target.hover();
  await page.waitForTimeout(1200);
  const box = await target.boundingBox();
  if (box) await page.mouse.move(box.x + box.width / 2 + 2, box.y + box.height / 2);
}

/** The visible tooltip bubble (reka renders role="tooltip" on an off-screen a11y copy). */
function tooltip(page: Page, hasText: string | RegExp) {
  return page.locator("div.bg-surface-gray-10").filter({ hasText });
}

/**
 * Post-implementation review — token traceability & metering affordances
 * (.pi/feats/metering-token-traceability.md). Runs against real data on the CRM site:
 *
 * - Deal TRACE_DEAL: the facility's welcome bonus rode a paid invoice, the same invoice
 *   bought the package tokens, and a Partner Coupon grant is present -> all three lines
 *   must render separately, each with a clickable identifier.
 * - Deal ORDER_DEAL: the bonus was auto-assigned by a Sales Order -> the bonus line links
 *   the order; the facility has no coupon, so the coupon line must be absent.
 * - Deal INITIAL_DEAL: the Initial Package grant traces to the deal facility -> the source
 *   tooltip carries a link to the parent CRM Deal.
 * - The Grants table explains its Status and Source values on hover.
 * - The header buttons (Test connection / Import sites from CRM / More) explain what they
 *   do on hover, before the user commits to a click.
 *
 * Needs: BASE_URL, E2E_USER, E2E_PASS (a System Manager with metering access) and the
 * three deals (E2E_TRACE_DEAL=16511, E2E_ORDER_DEAL=10269, E2E_INITIAL_DEAL=10501 on
 * crm-dev.tiberbu.app).
 */

const TRACE_DEAL = env("E2E_TRACE_DEAL", "16511");
const ORDER_DEAL = env("E2E_ORDER_DEAL", "10269");
const INITIAL_DEAL = env("E2E_INITIAL_DEAL", "10501");
const INVOICE = "ACC-SINV-2026-00009";
const ORDER = "SAL-ORD-2026-00027";
const PURCHASE_INVOICE = "ACC-SINV-2026-00021";

test("the metering tab separates bonus, purchase and coupon tokens with traceable links", async ({
  browser,
}, testInfo) => {
  const admin = await signedIn(browser, env("E2E_USER"), env("E2E_PASS"));

  await test.step("Header buttons explain what they do on hover", async () => {
    await admin.goto(`/crm/deals/${TRACE_DEAL}#metering`);
    await expect(admin.getByTestId("token-grants").first()).toBeVisible();

    const tcBtn = admin.getByRole("button", { name: "Test connection" });
    await hoverForTooltip(admin, tcBtn);
    await expect(tooltip(admin, "Read-only")).toBeVisible();
    await hoverForTooltip(admin, admin.getByRole("button", { name: "Import sites from CRM" }));
    await expect(tooltip(admin, "metering site")).toBeVisible();

    await admin.getByRole("button", { name: "More" }).click();
    await expect(admin.getByText("Backstop for the 15-minute scan")).toBeVisible();
    await expect(admin.getByText("List facilities whose HMIS site exists")).toBeVisible();
    await admin.keyboard.press("Escape");
    await testInfo.attach("header-tooltips", {
      body: await admin.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step("Bonus, purchase and coupon tokens are separate lines with links", async () => {
    const bonus = admin.getByTestId("welcome-bonus");
    await expect(bonus).toContainText(
      new RegExp(`400 tokens dispensed on .+ with paid invoice`),
    );
    // The bonus line must not bleed the invoice purchase into itself.
    await expect(bonus).not.toContainText("1,000 tokens");

    const purchase = admin.getByTestId("token-purchase");
    await expect(purchase).toContainText(
      new RegExp(`1,000 tokens · paid invoice`),
    );
    await expect(purchase).not.toContainText("400 tokens");

    const coupon = admin.getByTestId("partner-coupon");
    await expect(coupon).toContainText(new RegExp(`Partner CX E2E Network \\(synthetic\\) \\(909091\\)`));
    await expect(coupon).toContainText(new RegExp(`150 tokens via invoice`));

    // Identifiers are links to the Finance Cockpit record views.
    for (const panel of [bonus, purchase, coupon]) {
      const link = panel
        .getByRole("link", { name: INVOICE })
        .first();
      await expect(link).toBeVisible();
      const href = await link.getAttribute("href");
      expect(href).toContain("/finance-cockpit#/");
      expect(href).toContain("doctype=Sales+Invoice");
      expect(href).toContain(`name=${INVOICE}`);
    }
    const partnerLink = coupon.getByRole("link", {
      name: /CX E2E Network \(synthetic\)/,
    });
    await expect(partnerLink).toBeVisible();
    expect(await partnerLink.getAttribute("href")).toContain(
      "doctype=CRM+Opt-In+Network",
    );
    await testInfo.attach("token-lines", {
      body: await admin.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step("Clicking an identifier opens the linked record", async () => {
    const [popup] = await Promise.all([
      admin.context().waitForEvent("page"),
      admin
        .getByTestId("token-purchase")
        .getByRole("link", { name: INVOICE })
        .click(),
    ]);
    await popup.waitForLoadState("domcontentloaded");
    await expect(popup.getByText(INVOICE).first()).toBeVisible({
      timeout: 30000,
    });
    await testInfo.attach("invoice-record", {
      body: await popup.screenshot(),
      contentType: "image/png",
    });
    await popup.close();
  });

  await test.step("Grants table explains status and source on hover", async () => {
    const skipped = admin.locator("tr", { hasText: "Initial Package" }).first();
    await expect(skipped.getByTestId("grant-status")).toHaveText("Skipped");
    await hoverForTooltip(admin, skipped.getByTestId("grant-status"));
    await expect(tooltip(admin, "No tokens were granted from this source")).toBeVisible();
    await expect(tooltip(admin, "Paid package:")).toBeVisible();

    await hoverForTooltip(admin, skipped.getByText("Initial Package").first());
    await expect(tooltip(admin, "selected for this facility during onboarding")).toBeVisible();

    const welcomeRow = admin.locator("tr", { hasText: "Welcome Bonus" }).first();
    await hoverForTooltip(admin, welcomeRow.getByText("Welcome Bonus", { exact: true }));
    await expect(tooltip(admin, "one-time welcome bonus")).toBeVisible();
    const openLink = tooltip(admin, "one-time welcome bonus").getByRole(
      "link",
      { name: /Open Sales Invoice/ },
    );
    await expect(openLink).toBeVisible();
    expect(await openLink.getAttribute("href")).toContain(`name=${INVOICE}`);
    await testInfo.attach("grants-tooltips", {
      body: await admin.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step("Initial Package traces to the deal where the package was selected", async () => {
    await admin.goto(`/crm/deals/${INITIAL_DEAL}#metering`);
    const initialRow = admin.locator("tr", { hasText: "Initial Package" }).first();
    await hoverForTooltip(admin, initialRow.getByText("Initial Package").first());
    await expect(
      tooltip(admin, "opens the deal where the package was selected"),
    ).toBeVisible();
    const dealLink = tooltip(admin, "opens the deal").getByRole("link", {
      name: /Open CRM Deal/,
    });
    await expect(dealLink).toBeVisible();
    expect(await dealLink.getAttribute("href")).toContain(`name=${INITIAL_DEAL}`);
  });

  await test.step("A bonus auto-assigned by an order links that order; no coupon line when none exists", async () => {
    await admin.goto(`/crm/deals/${ORDER_DEAL}#metering`);
    const bonus = admin.getByTestId("welcome-bonus");
    await expect(bonus).toContainText(
      new RegExp(`2,500 tokens dispensed on .+ automatically when order`),
    );
    const orderLink = bonus.getByRole("link", { name: ORDER });
    await expect(orderLink).toBeVisible();
    const href = await orderLink.getAttribute("href");
    expect(href).toContain("doctype=Sales+Order");
    expect(href).toContain(`name=${ORDER}`);

    await expect(admin.getByTestId("token-purchase")).toContainText(
      new RegExp(`1,000 tokens · paid invoice`),
    );
    await expect(admin.getByTestId("token-purchase").getByRole("link", { name: PURCHASE_INVOICE })).toBeVisible();

    await expect(admin.getByTestId("partner-coupon")).toHaveCount(0);
    await testInfo.attach("order-bonus", {
      body: await admin.screenshot(),
      contentType: "image/png",
    });
  });
});
