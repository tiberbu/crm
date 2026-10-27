import { APIRequestContext, Browser, expect, Page, TestInfo } from "@playwright/test";

/** Steps shared by the metering journeys: sign-in, balances, and the approved cash payment. */

export function env(name: string, fallback?: string): string {
  const value = process.env[name] ?? fallback;
  if (!value) throw new Error(`Set ${name} to run the metering journey.`);
  return value;
}

export async function signedIn(
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

/** Available tokens on a facility's portal detail view, as read from OpenMeter. */
export async function portalBalance(
  page: Page,
  mfl: string,
  facility: string,
): Promise<number> {
  await page.goto("/cx-portal");
  await page.getByTestId(`facility-details-${mfl}`).click();
  await expect(page.getByRole("heading", { name: facility })).toBeVisible();
  const value = page.getByTestId("facility-available-tokens-value");
  await expect(value).toHaveText(/^[\d,.]+$/);
  return Number((await value.innerText()).replace(/,/g, ""));
}

export async function gatewayBalance(gateway: APIRequestContext, event?: string) {
  const response = await gateway.get("/ingest/v1/balance", {
    params: event ? { event } : {},
  });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

/** Finance records a cash receipt for the invoice; a second Accounts Manager approves it. */
export async function payInvoiceInCash(
  browser: Browser,
  customer: string,
  invoice: string,
  testInfo: TestInfo,
) {
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
  await customerSearch.pressSequentially(customer.slice(0, 14), {
    delay: 40,
  });
  await finance.getByRole("option", { name: customer }).click();
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
  await testInfo.attach("payment-sent", {
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
  await testInfo.attach("payment-approved", {
    body: await approver.screenshot(),
    contentType: "image/png",
  });
  await approver.context().close();
}
