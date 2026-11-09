import { execFileSync } from "child_process";
import { mkdtempSync, readFileSync, rmSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

import { expect, Page, test } from "@playwright/test";

/**
 * Network Opt-In and Partner Coupon, side by side on one network, against the live backend.
 *
 * 1. A facility owner buys Value Express tokens with the network's Partner Coupon.
 * 2. The Partner Portal (F360) wins a deal for the same facility and the same email: the
 *    contact gets an Opt-In invitation, and the coupon row is left alone.
 * 3. That contact opens /opt-in and reaches their facility; a coupon-only buyer cannot.
 * 4. The network admin sees both links, each row labelled by its own journey, and an edit
 *    keeps both rows.
 * Only the external identity registry is mocked (start_identity); everything else is real.
 */

const SITE = process.env.SITE || "";
const BENCH_DIR = process.env.BENCH_DIR || "";
const RUN = Date.now().toString(36);
const FIXTURE = "crm.tests.e2e_journey_separation_fixture";

function bench(method: string, kwargs: Record<string, unknown> = {}): any {
  const out = execFileSync(
    "bench",
    [
      "--site",
      SITE,
      "execute",
      `${FIXTURE}.${method}`,
      "--kwargs",
      JSON.stringify(kwargs),
    ],
    { cwd: BENCH_DIR, encoding: "utf8", maxBuffer: 20 * 1024 * 1024 },
  );
  const start = out.search(/[[{"]/);
  return start === -1 ? null : JSON.parse(out.slice(start).trim());
}

function serverNow(): string {
  const out = execFileSync(
    "bench",
    ["--site", SITE, "execute", "frappe.utils.now"],
    { cwd: BENCH_DIR, encoding: "utf8" },
  );
  return JSON.parse(out.slice(out.indexOf('"')).trim());
}

let fx: any;
let secretDir = "";

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  expect(SITE && BENCH_DIR, "SITE and BENCH_DIR are required").toBeTruthy();
  secretDir = mkdtempSync(join(tmpdir(), "jse2e-"));
  fx = bench("setup", { run_id: RUN, secret_file: join(secretDir, "admin") });
});

test.afterAll(() => {
  if (fx) {
    const result = bench("teardown", { run_id: RUN, since: fx.started });
    console.log(`teardown: ${JSON.stringify(result)}`);
    expect(result.failed).toEqual([]);
    expect(result.leftovers).toEqual({
      facilities: 0,
      memberships: 0,
      networks: 0,
      users: 0,
      customers: 0,
    });
  }
  if (secretDir) rmSync(secretDir, { recursive: true, force: true });
});

const facilityA = () => fx.facilities[0];

test("Partner Coupon: the network's coupon link onboards a facility through Value Express", async ({
  page,
}) => {
  await page.route(
    /\/api\/method\/crm\.api\.facility_onboarding\.start_identity/,
    (route) =>
      route.fulfill({
        json: {
          message: {
            success: true,
            data: {
              session_token: fx.session_token,
              challenge_started: true,
              reused: false,
              delivery: fx.delivery,
            },
          },
        },
      }),
  );
  await page.goto(`/facility-onboarding?partner_coupon=${fx.partner_id}`);
  await page.getByPlaceholder("Enter your ID number").fill("00000000");
  await page.getByRole("button", { name: "Verify & Find My Facility" }).click();
  await expect(
    page.getByRole("heading", { name: "Enter your verification code" }),
  ).toBeVisible();
  await page.getByLabel(/Verification code: 1/).fill(fx.otp);
  await page.getByRole("button", { name: "Verify code" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Select the facility you want to onboard",
    }),
  ).toBeVisible();

  await page.getByLabel(`Select ${facilityA().facility_name}`).check();
  await page.getByRole("button", { name: "Continue to Packages →" }).click();
  await expect(page.getByTestId("partner-coupon-toggle")).toHaveText(
    `Partner Coupon: ${fx.partner_id}`,
  );
  await page.getByTestId("partner-coupon-toggle").click();
  await expect(page.getByTestId("partner-coupon-network")).toHaveText(
    fx.display_name,
  );
  await page.getByTestId("partner-coupon-close").click();
  await page.getByTestId("package-grid").locator(".pkg > .btn").first().click();
  await page
    .locator(".sumbar")
    .getByRole("button", { name: "Continue to Review →" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review and confirm" }),
  ).toBeVisible();
  await expect(page.getByTestId("review-partner-coupon")).toContainText(
    fx.partner_id,
  );
  await expect(page.getByTestId("review-partner-coupon")).toContainText(
    fx.display_name,
  );
  await page.getByTestId("terms-acceptance").check();
  await page.getByTestId("confirm-submit").click();
  await expect(
    page.getByRole("heading", { name: "Your request has been submitted" }),
  ).toBeVisible({ timeout: 60_000 });

  const rows = bench("state", { run_id: RUN }).a;
  expect(rows).toHaveLength(1);
  expect(rows[0].customer).toBeTruthy();
  expect(rows[0].partner_coupon).toBe(1);
  expect(rows[0].contact_email).toBe(fx.buyer_email);
});

test("F360 deal won on the same facility and email adds an Opt-In row and leaves the coupon row alone", async () => {
  const before = bench("state", { run_id: RUN }).a[0];
  const result = bench("deal_won", {
    run_id: RUN,
    mfl_code: facilityA().mfl_code,
    contact_email: fx.buyer_email,
  });
  expect(result.success).toBe(true);
  expect(result.email_sent, result.email_error || "").toBe(true);
  expect(result.invitation_url).toContain(`/opt-in?network=${fx.network}`);
  expect(result.email_links_optin).toBe(true);
  expect(result.email_links_express).toBe(false);

  const rows = bench("state", { run_id: RUN }).a;
  expect(rows).toHaveLength(2);
  const coupon = rows.find((r: any) => r.customer);
  const optin = rows.find((r: any) => !r.customer);
  expect(coupon).toMatchObject({
    name: before.name,
    customer: before.customer,
    partner_coupon: 1,
    contact_email: before.contact_email,
    contact_name: before.contact_name,
  });
  expect(coupon.price_list_override || "").toBe("");
  expect(optin.price_list_override).toBeTruthy();
  expect(optin.invite_sent_at).toBeTruthy();
});

async function startOptIn(page: Page, email: string) {
  await page.goto(`/opt-in?network=${fx.network}`);
  await page.getByRole("button", { name: "Continue with Opt-In" }).click();
  await page.getByPlaceholder("Jane", { exact: true }).fill("JSE2E");
  await page.getByPlaceholder("Doe", { exact: true }).fill("Contact");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="tel"]').fill("0700000003");
  await page
    .getByPlaceholder("Kenyatta National Hospital")
    .fill("JSE2E Clinic (synthetic)");
  await page.getByPlaceholder("Chief Executive Officer").fill("Administrator");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
}

test("Opt-In: the network contact verifies on /opt-in and reaches the enrolled facility", async ({
  page,
}) => {
  const since = serverNow();
  await startOptIn(page, fx.buyer_email);
  let code = "";
  for (let i = 0; i < 20 && !code; i++) {
    code = bench("optin_otp", { email: fx.buyer_email, since });
    if (!code) await page.waitForTimeout(2000);
  }
  expect(code, "Opt-In OTP email").toMatch(/^\d{6}$/);
  const digits = page.locator('input[inputmode="numeric"][maxlength="1"]');
  await expect(digits).toHaveCount(6);
  for (let i = 0; i < 6; i++) await digits.nth(i).fill(code[i]);
  await page
    .getByRole("button", { name: /Verify/ })
    .first()
    .click();
  await expect(page.getByText(facilityA().facility_name).first()).toBeVisible();
  await expect(page.getByText(/JSE2E Coupon Clinic/)).toHaveCount(0);
});

test("Opt-In: a Partner-Coupon-only buyer is not a network contact", async ({
  page,
}) => {
  await startOptIn(page, fx.coupon_only_email);
  await expect(
    page.getByText(
      "Only the contact your facility registered with can opt in.",
      { exact: false },
    ),
  ).toBeVisible();
});

test("Admin: Network Detail shows both links, labels rows by journey, and an edit keeps both rows", async ({
  page,
}) => {
  const password = readFileSync(join(secretDir, "admin"), "utf8");
  const login = await page.request.post("/api/method/login", {
    data: { usr: fx.admin_email, pwd: password },
  });
  expect(login.ok()).toBe(true);
  await page.goto(`/crm/networks/${fx.network}`);

  await expect(page.getByTestId("optin-invitation-link")).toContainText(
    `/opt-in?network=${fx.network}`,
  );
  await expect(page.getByTestId("partner-coupon-link")).toContainText(
    `partner_coupon=${fx.partner_id}`,
  );

  const rowA = page.locator("tr", { hasText: facilityA().facility_name });
  await expect(rowA.getByText("Network Opt-In", { exact: true })).toBeVisible();
  await expect(rowA.getByText("Also Partner Coupon")).toBeVisible();
  await expect(rowA.getByText("Resend Opt-In invitation")).toBeVisible();
  const rowC = page.locator("tr", { hasText: "JSE2E Coupon Clinic" });
  await expect(
    rowC.getByText("Self-Onboarding", { exact: true }),
  ).toBeVisible();

  // A new admin gets the "Getting started" panel over the table; close it.
  const gettingStarted = page.locator("div.fixed.z-50", {
    hasText: "Welcome to Frappe CRM",
  });
  if (await gettingStarted.isVisible())
    await gettingStarted.locator("button").nth(1).click();
  await expect(gettingStarted).toBeHidden();
  await rowA.getByRole("button", { name: "Edit" }).click();
  const form = page
    .locator("div", {
      has: page.getByRole("heading", { name: "Edit Contact" }),
    })
    .last();
  const inputs = form.locator("input");
  await expect(inputs.first()).toBeVisible();
  let renamed = false;
  for (let i = 0; i < (await inputs.count()); i++) {
    if ((await inputs.nth(i).inputValue()) === "JSE2E Network Contact") {
      await inputs.nth(i).fill("JSE2E Network Contact Renamed");
      renamed = true;
      break;
    }
  }
  expect(renamed, "contact name field").toBe(true);
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("heading", { name: "Edit Contact" })).toHaveCount(
    0,
  );

  const rows = bench("state", { run_id: RUN }).a;
  expect(rows).toHaveLength(2);
  expect(rows.find((r: any) => !r.customer).contact_name).toBe(
    "JSE2E Network Contact Renamed",
  );
  expect(rows.find((r: any) => r.customer)).toMatchObject({
    partner_coupon: 1,
    contact_email: fx.buyer_email,
  });
  const c = bench("state", { run_id: RUN }).c;
  expect(c).toHaveLength(1);
  expect(c[0]).toMatchObject({
    partner_coupon: 1,
    contact_email: fx.coupon_only_email,
  });
});
