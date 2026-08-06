import { expect, test } from "@playwright/test";

const LIVE = !!process.env.CLAUSE_AUDIT_E2E;
const landlord = `clause-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const PDF = Buffer.from(
  "%PDF-1.4\nRESIDENTIAL TENANCY AGREEMENT. The tenant must have the carpet " +
    "professionally cleaned at the end of the tenancy.\n%%EOF",
);

async function openLeaseDetail(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Clause Owner");
  await page.getByPlaceholder("Organization name").fill("Clause Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("31 Clause Way");
  await page.getByLabel("State").selectOption("NSW");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "31 Clause Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Cleo Clause");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent", { exact: true }).fill("600");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(364));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);

  await page.getByRole("link", { name: "31 Clause Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
}

test("run clause audit queues a job for an uploaded lease PDF", async ({ page }) => {
  test.skip(!LIVE, "requires the local compliance service (set CLAUSE_AUDIT_E2E=1)");
  await openLeaseDetail(page);

  await expect(page.getByRole("heading", { name: "Documents", exact: true })).toBeVisible();
  await page.getByLabel("Title").fill("Signed Lease");
  await page
    .locator("label")
    .filter({ hasText: "Add document" })
    .locator('input[type="file"]')
    .setInputFiles({ name: "lease.pdf", mimeType: "application/pdf", buffer: PDF });
  const docRow = page.locator("li").filter({ hasText: "Signed Lease" });
  await expect(docRow).toBeVisible();

  await expect(page.getByRole("heading", { name: "Clause audit" })).toBeVisible();
  await page.getByRole("button", { name: "Run clause audit" }).first().click();
  await expect(page.getByText("Queued").or(page.getByText("Running..."))).toBeVisible();
  await expect(page.getByText("General information, not legal advice.").first()).toBeVisible();
});
