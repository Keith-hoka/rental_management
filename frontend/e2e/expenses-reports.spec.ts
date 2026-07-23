import { expect, test } from "@playwright/test";

const landlord = `exp-${Date.now()}@example.com`;

test("a manager records an expense and sees it in the reports", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Exp Owner");
  await page.getByPlaceholder("Organization name").fill("Exp Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Record an expense (date is prefilled to today).
  await page.getByRole("link", { name: "Expenses" }).click();
  await expect(page).toHaveURL(/\/app\/expenses$/);
  await page.getByLabel("Amount").fill("300");
  await page.getByLabel("Category").selectOption("insurance");
  await page.getByRole("button", { name: "Add expense" }).click();
  await expect(
    page.getByRole("button", { name: /Delete expense of \$300\.00/ }),
  ).toBeVisible();

  // The reports page aggregates it into the insurance category.
  await page.getByRole("link", { name: "Reports" }).click();
  await expect(page).toHaveURL(/\/app\/reports$/);
  const categoryRow = page.locator("li").filter({ hasText: "insurance" });
  await expect(categoryRow).toContainText("$300.00");
});
