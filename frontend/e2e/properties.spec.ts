import { expect, test } from "@playwright/test";

const email = `prop-e2e-${Date.now()}@example.com`;

test("create, list, edit, and delete a property", async ({ page }) => {
  // Sign up (logs in and lands on the dashboard).
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Prop E2E");
  await page.getByPlaceholder("Organization name").fill("Prop Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Go to properties and create one.
  await page.getByRole("link", { name: "Properties" }).click();
  await expect(page).toHaveURL(/\/app\/properties/);
  await page.getByRole("link", { name: "New property" }).click();
  await expect(page).toHaveURL(/\/app\/properties\/new$/);
  // Exact match: "Address" must not also match the list page's "Search address".
  await page.getByPlaceholder("Address", { exact: true }).fill("42 Test Lane");
  await page.getByRole("button", { name: "Create property" }).click();

  // Returns to the list, where the new property appears.
  await expect(page).toHaveURL(/\/app\/properties$/);
  await expect(page.getByText("42 Test Lane")).toBeVisible();

  // Open it, change the bedroom count, save — returns to the list with the update.
  await page.getByRole("link", { name: "42 Test Lane" }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+/);
  await page.getByLabel("Bedrooms").fill("5");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);
  await expect(page.getByText(/5 bed/)).toBeVisible();

  // Delete it.
  await page.getByRole("link", { name: "42 Test Lane" }).click();
  await page.getByRole("button", { name: "Delete property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);
  await expect(page.getByText("42 Test Lane")).toHaveCount(0);
});
