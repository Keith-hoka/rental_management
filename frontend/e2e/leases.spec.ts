import { expect, test } from "@playwright/test";

const landlord = `lease-e2e-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("adding a lease makes a property occupied, deleting it makes it vacant", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Lease Landlord");
  await page.getByPlaceholder("Organization name").fill("Lease Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Create a property.
  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("7 Lease Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Open it — starts vacant — and go to lease management.
  await page.getByRole("link", { name: "7 Lease Way" }).click();
  await expect(page.getByText("Vacant — no active lease.")).toBeVisible();
  await page.getByRole("link", { name: "Manage leases" }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+\/leases$/);

  // Add a lease covering today.
  await page.getByPlaceholder("Tenant name").fill("Tina Tenant");
  await page.getByPlaceholder("Tenant email").fill("tina@example.com");
  await page.getByLabel("Rent").fill("1500");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(30));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page.getByText("Tina Tenant", { exact: false })).toBeVisible();

  // Property detail now shows occupied.
  await page.getByRole("link", { name: "Back to property" }).click();
  await expect(page.getByText("Occupied")).toBeVisible();
  await expect(page.getByText("Tina Tenant", { exact: false })).toBeVisible();

  // Delete the lease -> vacant again.
  await page.getByRole("link", { name: "Manage leases" }).click();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("No leases yet.")).toBeVisible();
  await page.getByRole("link", { name: "Back to property" }).click();
  await expect(page.getByText("Vacant — no active lease.")).toBeVisible();
});
