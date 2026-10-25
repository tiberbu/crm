import {
  APIRequestContext,
  Browser,
  expect,
  Page,
  request,
  test,
} from "@playwright/test";

/**
 * A facility buys a token package and pays cash; CRM and the HMIS gateway show the new balance.
 *
 * 1. Record the facility's available tokens in the CX portal (from OpenMeter) and at the gateway.
 * 2. The facility owner orders a package in the portal and generates its invoice.
 * 3. Finance records a cash payment in the Finance cockpit and a second Accounts Manager approves it
 *    (the approval workflow refuses self-approval).
 * 4. The portal shows the balance raised by the package's tokens.
 * 5. The gateway (what HMIS calls) returns the same balance and the per-event allowance.
 */

function env(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (!value) throw new Error(`Set ${name} to run the metering journey.`);
  return value;
}

const FACILITY = env("E2E_FACILITY_NAME", "E2E Metering Clinic (synthetic)");
const MFL = env("E2E_MFL", "E2E-0001");
const CUSTOMER = env("E2E_CUSTOMER", "E2E Metering Facility Owner");
const PACKAGE = env("E2E_PACKAGE", "Starter");
const PACKAGE_TOKENS = Number(env("E2E_PACKAGE_TOKENS", "1000"));
const BILLING_EVENT = env("E2E_BILLING_EVENT", "patient_registration");

async function signedIn(
  browser: Browser,
  email: string,
  password: string,
): Promise<Page> {
  const context = await browser.newContext();
  const login = await context.request.post("/api/method/login", {
    form: { usr: email, pwd: password },
  });
  expect(login.ok(), `login as ${email}`).toBeTruthy();
  return context.newPage();
}

async function portalBalance(page: Page): Promise<number> {
  await page.goto("/cx-portal");
  const card = page
    .locator("div")
    .filter({ hasText: `MFL: ${MFL}` })
    .filter({ has: page.getByRole("button", { name: /Details/ }) })
    .last();
  await card.getByRole("button", { name: /Details/ }).click();
  await expect(page.getByRole("heading", { name: FACILITY })).toBeVisible();
  const value = page.getByTestId("facility-available-tokens-value");
  await expect(value).toHaveText(/^[\d,.]+$/);
  return Number((await value.innerText()).replace(/,/g, ""));
}

async function gatewayBalance(gateway: APIRequestContext, event?: string) {
  const response = await gateway.get("/ingest/v1/balance", {
    params: event ? { event } : {},
  });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

test("a cash payment for a token package raises the balance in CRM and at the HMIS gateway", async ({
  browser,
}, testInfo) => {
  const gateway = await request.newContext({
    baseURL: env("GATEWAY_URL"),
    extraHTTPHeaders: { "X-OpenMeter-Site-Key": env("E2E_SITE_KEY") },
  });
  const owner = await signedIn(
    browser,
    env("E2E_OWNER_EMAIL", "e2e.facility-owner@example.test"),
    env("E2E_OWNER_PASSWORD"),
  );
  let before = 0;
  let invoice = "";

  await test.step("Record the available balance in CRM and at the gateway", async () => {
    before = await portalBalance(owner);
    const atGateway = await gatewayBalance(gateway);
    expect(atGateway.balance).toBeCloseTo(before, 4);
    await testInfo.attach("1-balance-before", {
      body: await owner.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step(`Order the ${PACKAGE} package in the portal and generate its invoice`, async () => {
    await owner.getByRole("button", { name: "Top up tokens" }).click();
    const dialog = owner.getByRole("dialog");
    await dialog.getByText(PACKAGE, { exact: true }).click();
    await dialog.getByRole("button", { name: /Confirm Order/ }).click();
    await expect(owner.getByText(/Order .+ created for/)).toBeVisible();
    const generate = owner.getByRole("button", { name: "Generate Invoice" });
    if (
      await generate
        .first()
        .isVisible({ timeout: 5_000 })
        .catch(() => false)
    ) {
      const [response] = await Promise.all([
        owner.waitForResponse((r) =>
          r.url().includes("customer_experience.start_token_payment"),
        ),
        generate.first().click(),
      ]);
      invoice = (await response.json()).message.data.invoice;
    } else {
      // A retried, unpaid purchase resumes its order, whose invoice is already listed.
      const due = owner
        .locator("div", { hasText: MFL })
        .filter({ hasText: "Payment due" })
        .last();
      invoice = ((await due.innerText()).match(/\b[A-Z]+-SINV-\d{4}-\d+\b/) || [
        "",
      ])[0];
    }
    expect(invoice).toBeTruthy();
    await testInfo.attach("2-invoice", {
      body: invoice,
      contentType: "text/plain",
    });
  });

  await test.step("Finance records the cash payment and an Accounts Manager approves it", async () => {
    const finance = await signedIn(
      browser,
      env("E2E_FINANCE_EMAIL", "e2e.finance@example.test"),
      env("E2E_FINANCE_PASSWORD"),
    );
    await finance.goto("/app/finance-cockpit");
    await finance.getByRole("button", { name: "Payments" }).first().click();
    await finance.getByRole("button", { name: "New", exact: true }).click();
    const customerSearch = finance.getByPlaceholder("Search customer...");
    await customerSearch.click();
    await customerSearch.pressSequentially(CUSTOMER.slice(0, 14), {
      delay: 40,
    });
    await finance.getByRole("option", { name: CUSTOMER }).click();
    await finance.getByRole("button", { name: "Cash", exact: true }).click();
    const row = finance.locator("tr", { hasText: invoice });
    await row.locator('input[type="checkbox"]').check();
    const allocated = await row.locator('input[type="number"]').inputValue();
    await finance.getByPlaceholder("0.00").first().fill(allocated);
    await finance.getByRole("button", { name: /Review/ }).click();
    await finance.getByRole("button", { name: /Send for Approval/ }).click();
    const sent = finance.getByText(/Payment \S+ sent for approval/).first();
    await expect(sent).toBeVisible();
    const payment = ((await sent.innerText()).match(/Payment (\S+) sent/) ||
      [])[1];
    expect(payment).toBeTruthy();
    await testInfo.attach("3-payment-sent", {
      body: await finance.screenshot(),
      contentType: "image/png",
    });
    await finance.context().close();

    const approver = await signedIn(
      browser,
      env("E2E_APPROVER_EMAIL", "e2e.finance-approver@example.test"),
      env("E2E_APPROVER_PASSWORD"),
    );
    await approver.goto("/app/finance-cockpit");
    await approver.getByRole("button", { name: "Payments" }).first().click();
    await approver.getByText(payment, { exact: true }).first().click();
    await approver.getByRole("button", { name: "Approve and Submit" }).click();
    await expect(
      approver.getByText("Submitted", { exact: true }).first(),
    ).toBeVisible();
    await testInfo.attach("4-payment-approved", {
      body: await approver.screenshot(),
      contentType: "image/png",
    });
    await approver.context().close();
  });

  await test.step("CRM shows the balance raised by the package", async () => {
    await expect
      .poll(() => portalBalance(owner), {
        timeout: 180_000,
        intervals: [5_000, 10_000],
      })
      .toBeCloseTo(before + PACKAGE_TOKENS, 4);
    await testInfo.attach("5-balance-after", {
      body: await owner.screenshot(),
      contentType: "image/png",
    });
  });

  await test.step("The gateway gives HMIS the same balance and per-event allowance", async () => {
    const total = await gatewayBalance(gateway);
    expect(total.balance).toBeCloseTo(before + PACKAGE_TOKENS, 4);
    const perEvent = await gatewayBalance(gateway, BILLING_EVENT);
    expect(perEvent.event.affordable).toBe(
      Math.floor(perEvent.balance / perEvent.event.tokens),
    );
    await testInfo.attach("6-gateway", {
      body: JSON.stringify({ total, perEvent }, null, 2),
      contentType: "application/json",
    });
  });
});
