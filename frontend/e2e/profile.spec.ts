import { expect, test } from "@playwright/test";

const owner = `profile-e2e-${Date.now()}@example.com`;

test("a user can edit their contact info", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Profile Owner");
  await page.getByPlaceholder("Organization name").fill("Profile Org");
  await page.getByPlaceholder("Email").fill(owner);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Contact info" }).click();
  await expect(page).toHaveURL(/\/app\/profile$/);
  await page.getByPlaceholder("Phone (optional)").fill("555-4242");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved")).toBeVisible();

  // Reload — the saved phone is fetched back.
  await page.reload();
  await expect(page.getByPlaceholder("Phone (optional)")).toHaveValue("555-4242");
});
