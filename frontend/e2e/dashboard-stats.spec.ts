import { expect, test } from "@playwright/test";

const landlord = `stats-${Date.now()}@example.com`;

test("landlord dashboard shows stat cards and the income chart", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Stats Landlord");
  await page.getByPlaceholder("Organization name").fill("Stats Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // The dashboard aggregates render for a manager.
  await expect(page.getByText("Outstanding")).toBeVisible();
  await expect(page.getByText("Collected this month")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Monthly income" })).toBeVisible();
});
