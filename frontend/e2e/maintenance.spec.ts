import { expect, test } from "@playwright/test";

const landlord = `maint-${Date.now()}@example.com`;

test("landlord opens the maintenance page from the dashboard", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Maint Landlord");
  await page.getByPlaceholder("Organization name").fill("Maint Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Maintenance" }).click();
  await expect(page).toHaveURL(/\/app\/maintenance$/);
  await expect(page.getByRole("heading", { name: "Maintenance" })).toBeVisible();
  await expect(page.getByText("No maintenance requests yet.")).toBeVisible();
});
