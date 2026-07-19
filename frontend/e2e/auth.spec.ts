import { expect, test } from "@playwright/test";

const email = `e2e-${Date.now()}@example.com`;
const password = "secret123";

test("signup, logout, login round trip", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("E2E User");
  await page.getByPlaceholder("Organization name").fill("E2E Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill(password);
  await page.getByRole("button", { name: "Sign up" }).click();

  await expect(page.getByTestId("welcome")).toContainText("E2E User (landlord)");

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByTestId("welcome")).toContainText("E2E User (landlord)");
});
