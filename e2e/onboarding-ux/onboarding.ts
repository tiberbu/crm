import { randomUUID } from "crypto";

import { expect, Page } from "@playwright/test";

/**
 * Self-onboarding steps with the identity, OTP and terms endpoints answered by synthetic data,
 * so the UI can be checked without a registry identity or an SMS. The package catalogue comes
 * from the site.
 */

export const SYNTHETIC_TERMS = "Synthetic Onboarding Terms";

export function syntheticFacilities(count: number) {
  return Array.from({ length: count }, (_, index) => {
    const n = String(index + 1).padStart(2, "0");
    return {
      facility_id: `FID-00-TEST-${n}`,
      facility_name: `Synthetic Clinic ${n}`,
      mfl_code: `TEST-${n}`,
      facility_level: "Level 3",
      facility_type: "Health Centre",
      classification: "Level 3",
      // The last facility is already set up, so it cannot be selected.
      onboarding_eligible: true,
      onboarding_blocked: index === count - 1,
    };
  });
}

export async function mockOnboardingApi(page: Page, facilityCount: number) {
  const identity = { full_name: "Synthetic Person", email: "s***n@example.test", phone: "071******00" };
  // Only these endpoints are answered; any other method goes to the site. A Map matches its own
  // keys only, never inherited ones such as "constructor".
  const answers = new Map<string, unknown>(Object.entries({
    start_identity: {
      session_token: randomUUID(),
      identity,
      delivery: { channel: "sms", masked_destination: identity.phone, status: "sent", resend_after: 60 },
    },
    verify_otp: {
      state: "ready",
      identity,
      account_email: "synthetic.owner@example.test",
      facilities: syntheticFacilities(facilityCount),
    },
    get_self_onboarding_terms: {
      document: SYNTHETIC_TERMS,
      rendered_html: "<h2>1. Scope</h2><p>Synthetic terms used by the UI checks.</p><h2>2. Payment</h2><p>Tokens are added once payment is received.</p>",
      content_hash: "0".repeat(64),
    },
    check_onboarding_conflicts: { conflicts: [] },
  }));
  await page.route(/\/api\/method\/crm\.api\.facility_onboarding\.(\w+)/, async (route, request) => {
    const method = new URL(request.url()).pathname.split(".").pop() || "";
    if (!answers.has(method)) return route.continue();
    await route.fulfill({ json: { message: answers.get(method) } });
  });
}

export async function reachFacilitiesStep(page: Page) {
  await page.goto("/facility-onboarding");
  await page.getByPlaceholder("Enter your ID number").fill("12345678");
  await page.getByRole("button", { name: /Verify & Find My Facility/ }).click();
  await page.getByLabel(/1 \/ 6/).click();
  await page.keyboard.type("123456");
  await page.locator("form button:not([type]), form button[type=submit]").first().click().catch(() => {});
  await expect(page.getByRole("heading", { name: "Select the facility you want to onboard" })).toBeVisible();
}

export async function reachReviewStep(page: Page) {
  await page.getByTestId("facility-select-checkbox").first().check();
  await page.getByRole("button", { name: /Continue to Packages/ }).click();
  await expect(page.getByTestId("package-grid")).toBeVisible();
  await page.getByTestId("package-grid").locator(".pkg > .btn").first().click();
  await page.locator(".sumbar").getByRole("button", { name: /Continue to Review/ }).click();
  await expect(page.getByTestId("self-onboarding-terms")).toBeVisible();
}
