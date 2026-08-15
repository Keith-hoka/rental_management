import { expect, test } from "@playwright/test";

const PDF = Buffer.from(
  "%PDF-1.4\nRESIDENTIAL TENANCY AGREEMENT. The tenant must have the carpet " +
    "professionally cleaned at the end of the tenancy.\n%%EOF",
);

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

async function signupLandlord(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Consent Owner");
  await page.getByPlaceholder("Organization name").fill("Consent Org");
  await page.getByPlaceholder("Email").fill(`ai-consent-${Date.now()}@example.com`);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();
}

/** Signs up a fresh landlord, then creates a property, lease and lease document. */
async function createLeaseWithDocument(page: import("@playwright/test").Page): Promise<void> {
  await signupLandlord(page);

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

  await expect(page.getByRole("heading", { name: "Documents", exact: true })).toBeVisible();
  await page.getByLabel("Title").fill("Signed Lease");
  await page
    .locator("label")
    .filter({ hasText: "Add document" })
    .locator('input[type="file"]')
    .setInputFiles({ name: "lease.pdf", mimeType: "application/pdf", buffer: PDF });
  const docRow = page.locator("li").filter({ hasText: "Signed Lease" });
  await expect(docRow).toBeVisible();
}

test("landlord enables clause audit from the AI settings page", async ({ page }) => {
  await signupLandlord(page);
  await page.goto("/app/settings/ai");
  await expect(page.getByText("AI features disclosure")).toBeVisible();
  await expect(page.getByText("never sent")).toBeVisible();

  const toggle = page.getByRole("switch", { name: /clause audit/i });
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(toggle).toBeChecked();
});

test("unconsented lease page shows the enable prompt instead of the audit button", async ({
  page,
}) => {
  // log in, create a lease with a document via existing helpers,
  // do NOT enable consent
  await createLeaseWithDocument(page);

  await expect(page.getByText(/AI features are disabled/)).toBeVisible();
  // Scoped to the prompt card: the app-shell nav also has an "AI settings"
  // link, so the unscoped role query matches both.
  const card = page.getByTestId("ai-consent-card");
  await expect(card.getByRole("link", { name: /settings/i })).toBeVisible();
});
