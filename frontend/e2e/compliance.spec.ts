import { expect, test } from "@playwright/test";

const LIVE = !!process.env.COMPLIANCE_E2E;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

async function openLeaseDetail(
  page: import("@playwright/test").Page,
  state?: string,
): Promise<void> {
  // Computed per call (not hoisted to module scope) so two LIVE tests in the
  // same run sign up as distinct organizations.
  const landlord = `comp-${Date.now()}@example.com`;
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Comp Owner");
  await page.getByPlaceholder("Organization name").fill("Comp Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("21 Compliance Way");
  if (state) await page.getByLabel("State").selectOption(state);
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "21 Compliance Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Cora Compliance");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent", { exact: true }).fill("600");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(364));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);

  await page.getByRole("link", { name: "21 Compliance Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
}

test("compliance section is hidden when the integration is disabled", async ({ page }) => {
  test.skip(LIVE, "backend is configured with compliance enabled");
  await openLeaseDetail(page);
  await expect(page.getByRole("heading", { name: "Documents", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "NSW compliance" })).toHaveCount(0);
});

test("check now renders findings and the disclaimer", async ({ page }) => {
  test.skip(!LIVE, "requires the local compliance service (set COMPLIANCE_E2E=1)");
  await openLeaseDetail(page, "NSW");
  await expect(page.getByRole("heading", { name: "NSW compliance" })).toBeVisible();
  await page.getByRole("button", { name: "Check now" }).click();
  await expect(page.getByText("compliant")).toBeVisible();
  await expect(page.getByText("Bond cap (s159)")).toBeVisible();
  await expect(page.getByText("not filled in for this lease").first()).toBeVisible();
  await expect(page.getByText("s42 was repealed on 13 Dec 2024")).toBeVisible();
  await expect(page.getByText("General information, not legal advice.")).toBeVisible();
});

test("VIC compliance audit runs against the real service", async ({ page }) => {
  test.skip(!LIVE, "requires the local compliance service (set COMPLIANCE_E2E=1)");
  await openLeaseDetail(page, "VIC");
  await expect(page.getByRole("heading", { name: "VIC compliance" })).toBeVisible();

  const auditResponse = page.waitForResponse(
    (r) => r.request().method() === "POST" && r.url().includes("/compliance-audit"),
  );
  await page.getByRole("button", { name: "Check now" }).click();
  const audit: { jurisdiction: string; findings: { rule_id: string }[] } = await (
    await auditResponse
  ).json();

  // The stored row and every deterministic finding are VIC, not NSW.
  expect(audit.jurisdiction).toBe("VIC");
  expect(audit.findings.length).toBeGreaterThan(0);
  expect(audit.findings.every((f) => f.rule_id.startsWith("vic."))).toBe(true);

  await expect(page.getByText("audited as VIC")).toBeVisible();
  await expect(page.getByText("General information, not legal advice.")).toBeVisible();
});
