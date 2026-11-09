import { expect, test } from "@playwright/test";

import { env, signedIn } from "./journey";

/**
 * ADR-007: a fully paid Fixed-package invoice is a subscription term, shown on the Deal's
 * Metering tab with its activation and expiry; an admin can suspend, reactivate and cancel it.
 *
 * Needs crm.tests.e2e_subscription_fixture.setup for this run (a synthetic facility with an
 * Active metering site, a Deal listing it and one paid Fixed invoice), plus:
 * BASE_URL, E2E_SUB_DEAL, E2E_SUB_FID, E2E_SUB_INVOICE, E2E_ADMIN_PASSWORD.
 * HMIS's view of the same plan (GET /ingest/v1/plan) is covered by the gateway's tests and the
 * hmis-essentials Postman collection.
 *
 * 1. The Plan section shows Subscription (Fixed), Active, the activation and expiry, and the term.
 * 2. Suspend and reactivate the site, each with a reason; the site badge follows.
 * 3. Cancel the subscription with a reason: it shows Cancelled, and Cancel is no longer offered.
 */

const DEAL = env("E2E_SUB_DEAL");
const FID = env("E2E_SUB_FID");
const INVOICE = env("E2E_SUB_INVOICE");

test("a paid Fixed invoice shows as a subscription that can be suspended and cancelled", async ({
  browser,
}, testInfo) => {
  const admin = await signedIn(
    browser,
    env("E2E_ADMIN_EMAIL", "e2e.metering-admin@example.test"),
    env("E2E_ADMIN_PASSWORD"),
  );
  const plan = admin.getByTestId("facility-plan");
  const reason = admin.getByRole("dialog").locator("textarea");
  const confirm = admin.getByTestId("lifecycle-confirm");

  await test.step("The paid term is an active subscription with its dates", async () => {
    await admin.goto(`/crm/deals/${DEAL}#metering`);
    await expect(admin.getByText(`Facility ID: ${FID}`)).toBeVisible();
    await expect(plan.getByTestId("plan-type")).toHaveText("Subscription (Fixed)");
    await expect(plan.getByTestId("subscription-status")).toHaveText("Active");
    await expect(plan.getByTestId("subscription-activated")).not.toHaveText("—");
    await expect(plan.getByTestId("subscription-expires")).not.toHaveText("—");
    const term = plan.getByTestId("subscription-terms").getByRole("row").filter({ hasText: INVOICE });
    await expect(term).toContainText("Active");
    // Brand guide: InterVar only, nothing heavier than 600.
    const styles = await plan.evaluate((root) =>
      [root, ...root.querySelectorAll("*")].map((el) => {
        const style = getComputedStyle(el);
        return { family: style.fontFamily, weight: Number(style.fontWeight) };
      }),
    );
    for (const style of styles) {
      expect(style.family).toMatch(/Inter/);
      expect(style.weight).toBeLessThanOrEqual(600);
    }
    await plan.scrollIntoViewIfNeeded();
    await testInfo.attach("1-active-subscription", { body: await admin.screenshot({ fullPage: true }), contentType: "image/png" });
  });

  await test.step("Suspend and reactivate the site, each with a reason", async () => {
    await plan.getByTestId("suspend-site").click();
    await expect(confirm).toBeDisabled();
    await reason.fill("E2E: suspension check");
    await testInfo.attach("2-suspend-dialog", { body: await admin.screenshot(), contentType: "image/png" });
    await confirm.click();
    await expect(admin.getByText("Site suspended")).toBeVisible();
    await expect(plan.getByTestId("reactivate-site")).toBeVisible();
    await plan.getByTestId("reactivate-site").click();
    await reason.fill("E2E: cleared");
    await confirm.click();
    await expect(admin.getByText("Site reactivated")).toBeVisible();
    await expect(plan.getByTestId("suspend-site")).toBeVisible();
  });

  await test.step("Cancel the subscription with a reason", async () => {
    await plan.getByTestId("cancel-subscription").click();
    await reason.fill("E2E: cancellation check");
    await confirm.click();
    await expect(admin.getByText("Subscription cancelled")).toBeVisible();
    await expect(plan.getByTestId("subscription-status")).toHaveText("Cancelled");
    await expect(plan.getByTestId("cancel-subscription")).toHaveCount(0);
    const term = plan.getByTestId("subscription-terms").getByRole("row").filter({ hasText: INVOICE });
    await expect(term).toContainText("Cancelled");
    await plan.scrollIntoViewIfNeeded();
    await testInfo.attach("3-cancelled", { body: await admin.screenshot({ fullPage: true }), contentType: "image/png" });
  });
});
