import { randomUUID } from "crypto";

import { expect, Page } from "@playwright/test";

/** Synthetic facilities: two eligible (Level 2 and Level 3B), one above Value Express, one already onboarded. */
export const FACILITIES = [
  { facility_id: "FID-00-VXTEST-1", facility_name: "Synthetic Clinic A", mfl_code: "VX-01", facility_level: "Level 2", facility_type: "Medical Clinic", onboarding_eligible: true, onboarding_blocked: false },
  { facility_id: "FID-00-VXTEST-2", facility_name: "Synthetic Nursing Home B", mfl_code: "VX-02", facility_level: "Level 3B", facility_type: "Nursing Home", onboarding_eligible: true, onboarding_blocked: false },
  { facility_id: "FID-00-VXTEST-3", facility_name: "Synthetic Hospital C", mfl_code: "VX-03", facility_level: "Level 4", facility_type: "Hospital", onboarding_eligible: false, facility_eligibility_reason: "level_not_allowed", onboarding_blocked: false },
  { facility_id: "FID-00-VXTEST-4", facility_name: "Synthetic Clinic D", mfl_code: "VX-04", facility_level: "Level 2", facility_type: "Medical Clinic", onboarding_eligible: true, onboarding_blocked: true },
];

/** A mocked get_catalog response: a payload, or an HTTP error (for invalid-coupon flows). */
export type CatalogMock = { ok: unknown } | { error: { status?: number; body: unknown } };

/** Answers the identity, OTP, terms and submit endpoints; returns the submitted payloads. */
export async function mockOnboarding(page: Page, opts: { catalog?: CatalogMock | CatalogMock[] } = {}) {
  const submitted: Record<string, string>[] = [];
  const catalogQueue: CatalogMock[] | null =
    opts.catalog === undefined ? null : (Array.isArray(opts.catalog) ? [...opts.catalog] : [opts.catalog]);
  const identity = { full_name: "Synthetic Person", email: "s***n@example.test", phone: "071******00" };
  const answers = new Map<string, unknown>(Object.entries({
    start_identity: {
      session_token: randomUUID(),
      identity,
      delivery: { channel: "email", masked_destination: identity.email, status: "sent", resend_after: 45 },
    },
    verify_otp: { state: "ready", identity, account_email: "synthetic.owner@example.test", facilities: FACILITIES },
    get_self_onboarding_terms: { document: "Synthetic Value Express Terms", rendered_html: "<p>Synthetic terms.</p>", content_hash: "0".repeat(64) },
    check_onboarding_conflicts: { outcome: "new" },
    submit_onboarding: { outcome: "new", enrollments: [{ facility: "Synthetic Clinic A", mfl_code: "VX-01" }] },
  }));
  await page.route(/\/api\/method\/crm\.api\.facility_onboarding\.(\w+)/, async (route, request) => {
    const method = new URL(request.url()).pathname.split(".").pop() || "";
    if (method === "get_catalog" && catalogQueue) {
      const item = catalogQueue.length > 1 ? catalogQueue.shift()! : catalogQueue[0];
      if ("error" in item) {
        await route.fulfill({ status: item.error.status ?? 417, json: item.error.body });
      } else {
        await route.fulfill({ json: { message: item.ok } });
      }
      return;
    }
    if (!answers.has(method)) return route.continue();
    if (method === "submit_onboarding") {
      const body = request.postData() || "";
      submitted.push(body.trim().startsWith("{") ? JSON.parse(body) : Object.fromEntries(new URLSearchParams(body)));
    }
    await route.fulfill({ json: { message: answers.get(method) } });
  });
  return submitted;
}

export async function verify(page: Page, query = "") {
  await page.goto(`/facility-onboarding${query}`);
  await page.getByPlaceholder("Enter your ID number").fill("12345678");
  await page.getByRole("button", { name: "Verify & Find My Facility" }).click();
  await expect(page.getByRole("heading", { name: "Enter your verification code" })).toBeVisible();
  await page.getByLabel(/Verification code: 1/).fill("123456");
  await page.getByRole("button", { name: "Verify code" }).click();
  await expect(page.getByRole("heading", { name: "Select the facility you want to onboard" })).toBeVisible();
}

export async function toPackages(page: Page, names: string[]) {
  for (const name of names) await page.getByLabel(`Select ${name}`).check();
  await page.getByRole("button", { name: "Continue to Packages →" }).click();
  await expect(page.getByRole("heading", { name: "Choose how you want to use CareverseHIMS" })).toBeVisible();
  // A carried Fixed choice opens on the Fixed tiers instead of the Flex cards.
  await expect(page.getByTestId("package-grid").or(page.getByTestId("fixed-tier").first())).toBeVisible();
}

export async function noHorizontalScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}
