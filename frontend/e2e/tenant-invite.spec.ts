import { expect, test } from "@playwright/test";

const landlord = `tenant-invite-${Date.now()}@example.com`;

test("landlord invites a tenant from the lease detail", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Invite Landlord");
  await page.getByPlaceholder("Organization name").fill("Invite Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Create a property.
  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("5 Tenant Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Create a lease with a main tenant from the Leases page.
  await page.goto("/app");
  await page.getByRole("link", { name: "Leases" }).click();
  await page.getByLabel("Property").selectOption({ label: "5 Tenant Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Tessa Tenant");
  await page.getByPlaceholder("Tenant email").fill("tessa@example.com");
  await page.getByLabel("Rent").fill("1400");
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 1);
  const end = new Date(today);
  end.setDate(end.getDate() + 30);
  await page.getByLabel("Start").fill(start.toISOString().slice(0, 10));
  await page.getByLabel("End").fill(end.toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page.getByText("Tessa Tenant", { exact: false })).toBeVisible();

  // Open the lease detail and invite the main tenant.
  await page.getByRole("link", { name: "5 Tenant Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByRole("button", { name: "Invite" }).first().click();
  await expect(page.getByText("Invitation sent to tessa@example.com")).toBeVisible();

  // The invite is now pending — the button becomes Revoke.
  await expect(page.getByRole("button", { name: "Revoke" })).toBeVisible();

  // Revoking brings the Invite button back.
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByRole("button", { name: "Invite" })).toBeVisible();
});
