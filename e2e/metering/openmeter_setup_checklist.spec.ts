import { Browser, expect, Page, test } from "@playwright/test";
import { env } from "./journey";

/**
 * OpenMeter Settings › Gateway › Setup Checklist (openmeter_mediator OMM-53, P-77..P-84).
 *
 * 1. A Gateway URL that answers as OpenMeter itself (no gateway in front) is named as such by
 *    Test Connection and blocks the checklist, instead of "Gateway Credential is not set".
 * 2. Against a real metering gateway, Connect opens the checklist by itself, Apply creates
 *    only what is missing, and the token meter, token feature and prices end up Done.
 * 0. First-connection guidance (OMM-54): the banner names the step (no URL, then the address
 *    found), Gateway Credential cannot be typed, and Use Break-Glass Token refuses to save a
 *    token for an address that is OpenMeter itself.
 *
 * Variables: BASE_URL, E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD (an OpenMeter Admin),
 * E2E_EXPOSED_OPENMETER_URL (an address that answers as OpenMeter itself) and
 * optionally E2E_GATEWAY_URL (a metering gateway that trusts this CRM and can call it back;
 * step 2 is skipped without it) and E2E_MAP_HOST_TO_LOCALHOST (a site host name to resolve to
 * this server, for a bench site with no public DNS). The test puts the Gateway URL back as it found it.
 */

const SETTINGS = "/app/openmeter-settings";

// A bench site with no public DNS (such as the local test site) is reached through this
// server's nginx by mapping its host name to 127.0.0.1.
const mappedHost = process.env.E2E_MAP_HOST_TO_LOCALHOST;
if (mappedHost) test.use({ launchOptions: { args: [`--host-resolver-rules=MAP ${mappedHost} 127.0.0.1`] } });

/** Signs in from the page itself, so the browser's host mapping applies to the login too. */
async function signedIn(browser: Browser, email: string, password: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/login");
  const status = await page.evaluate(
    async ([usr, pwd]) =>
      (await fetch("/api/method/login", { method: "POST", body: new URLSearchParams({ usr, pwd }) })).status,
    [email, password],
  );
  expect(status, `login as ${email}`).toBe(200);
  return page;
}

function control(page: Page, fieldname: string) {
  const wrapper = page.locator(`.frappe-control[data-fieldname="${fieldname}"]`);
  return fieldname === "enabled" ? wrapper.getByRole("checkbox", { name: "Enabled" }) : wrapper.getByRole("textbox");
}

async function gatewayMenu(page: Page, item: string) {
  await page.getByRole("button", { name: "Gateway" }).click();
  await page.locator(".dropdown-menu.show").getByText(item, { exact: true }).click();
}

async function setGatewayUrl(page: Page, url: string) {
  await page.goto(SETTINGS);
  const enabled = control(page, "enabled");
  if (await enabled.isChecked()) await enabled.uncheck();
  const field = control(page, "base_url");
  await field.fill(url);
  await field.press("Tab");
  await page.keyboard.press("Control+s");
  await expect(page.locator(".indicator-pill").filter({ hasText: "Not Saved" })).toHaveCount(0);
}

function banner(page: Page) {
  return page.locator(".form-message[data-connection-state]");
}

function checklist(page: Page) {
  return page.locator(".modal.show").filter({ hasText: "OpenMeter Setup Checklist" });
}

function row(page: Page, key: string) {
  return checklist(page).locator(`tr[data-item="${key}"]`);
}

test("Setup Checklist diagnoses the Gateway URL and applies OpenMeter configuration", async ({ browser }, testInfo) => {
  const page = await signedIn(browser, env("E2E_ADMIN_EMAIL"), env("E2E_ADMIN_PASSWORD"));
  await page.goto(SETTINGS);
  const original = await control(page, "base_url").inputValue();

  try {
    await test.step("the banner guides the first connection; no token is ever typed", async () => {
      await setGatewayUrl(page, "");
      await expect(banner(page)).toHaveAttribute("data-connection-state", "no_url");
      await expect(banner(page)).toContainText("not OpenMeter's");
      await expect(control(page, "api_token")).toHaveCount(0); // read-only: shown, never an input
      await page.screenshot({ path: testInfo.outputPath("0a-banner-no-url.png") });

      await setGatewayUrl(page, env("E2E_EXPOSED_OPENMETER_URL"));
      await expect(banner(page)).toHaveAttribute("data-connection-state", "openmeter_exposed");
      await expect(banner(page)).toContainText("answers as OpenMeter itself");
      await page.screenshot({ path: testInfo.outputPath("0b-banner-exposed.png") });

      await gatewayMenu(page, "Use Break-Glass Token");
      const dialog = page.locator(".modal.show").filter({ hasText: "Use Break-Glass Token" });
      await expect(dialog).toContainText("Emergency only");
      await dialog.locator('input[data-fieldname="token"]').fill("not-a-real-token");
      await dialog.getByRole("button", { name: "Check and save" }).click();
      const refused = page.locator(".modal.show").filter({ hasText: "Nothing was saved" });
      await expect(refused).toContainText("answers as OpenMeter itself");
      await page.screenshot({ path: testInfo.outputPath("0c-break-glass-refused.png") });
      await refused.locator(".btn-modal-close").click();
      await page.keyboard.press("Escape");
    });

    await test.step("an exposed OpenMeter is named, not blamed on the credential", async () => {
      await setGatewayUrl(page, env("E2E_EXPOSED_OPENMETER_URL"));
      await gatewayMenu(page, "Test Connection");
      const msg = page.locator(".modal.show").filter({ hasText: "Not connected" });
      await expect(msg).toContainText("answers as OpenMeter itself");
      await expect(msg).not.toContainText("Gateway Credential is not set");
      await page.screenshot({ path: testInfo.outputPath("1-test-connection-exposed.png") });
      await msg.locator(".btn-modal-close").click();

      await gatewayMenu(page, "Setup Checklist");
      await expect(checklist(page)).toContainText("Overall: Blocked");
      await expect(row(page, "gateway")).toHaveAttribute("data-status", "fail");
      await expect(row(page, "openmeter_private")).toHaveAttribute("data-status", "fail");
      await expect(checklist(page).getByRole("button", { name: "Apply missing items" })).toHaveCount(0);
      await page.screenshot({ path: testInfo.outputPath("2-checklist-blocked.png") });
      await checklist(page).locator(".btn-modal-close").click();
      await expect(page.locator(`.frappe-control[data-fieldname="setup_status"]`)).toContainText("Blocked");
    });

    const gateway = process.env.E2E_GATEWAY_URL;
    if (gateway) await test.step("Connect to a real gateway opens the checklist; Apply leaves it done", async () => {
      await setGatewayUrl(page, gateway);
      await gatewayMenu(page, "Connect to Gateway");
      await expect(checklist(page)).toBeVisible({ timeout: 60_000 });
      for (const key of ["gateway", "openmeter_private", "credential", "gateway_config"]) {
        await expect(row(page, key), key).toHaveAttribute("data-status", "ok");
      }
      await page.screenshot({ path: testInfo.outputPath("3-checklist-after-connect.png"), fullPage: true });

      const apply = checklist(page).getByRole("button", { name: "Apply missing items" });
      if (await apply.count()) {
        await apply.click();
        await page.locator(".modal.show").getByRole("button", { name: "Yes" }).click();
        await expect(checklist(page).locator(".alert-info")).toBeVisible({ timeout: 120_000 });
      }
      for (const key of ["meter", "token_feature", "facilities"]) {
        await expect(row(page, key), key).toHaveAttribute("data-status", "ok");
      }
      // Prices may differ on purpose (set in OpenMeter): that is a warning, never "to do".
      await expect(row(page, "catalog")).toHaveAttribute("data-status", /ok|warn/);
      await page.screenshot({ path: testInfo.outputPath("4-checklist-applied.png"), fullPage: true });
      await checklist(page).locator(".btn-modal-close").click();
    });
  } finally {
    await setGatewayUrl(page, original);
  }
});
