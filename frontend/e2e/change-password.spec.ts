import { expect, test } from "@playwright/test";

const email = `change-e2e-${Date.now()}@example.com`;
const oldPw = "oldpass123";
const newPw = "newpass456";

async function signup(page: import("@playwright/test").Page) {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Change E2E");
  await page.getByPlaceholder("Organization name").fill("Change Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill(oldPw);
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();
}

test("change password from dashboard, then log in with the new password", async ({ page }) => {
  await signup(page);

  await page.getByRole("link", { name: "Change password" }).click();
  await expect(page).toHaveURL(/\/app\/change-password/);

  await page.getByPlaceholder("Current password").fill(oldPw);
  await page.getByPlaceholder("New password (min 8 chars)").fill(newPw);
  await page.getByPlaceholder("Confirm new password").fill(newPw);
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByTestId("change-success")).toBeVisible();

  await page.goto("/app");
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill(newPw);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();
});

test("mismatched confirmation is rejected before any request", async ({ page }) => {
  const other = `mismatch-${Date.now()}@example.com`;
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Mismatch");
  await page.getByPlaceholder("Organization name").fill("Mismatch Org");
  await page.getByPlaceholder("Email").fill(other);
  await page.getByPlaceholder("Password (min 8 chars)").fill(oldPw);
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/change-password");
  await page.getByPlaceholder("Current password").fill(oldPw);
  await page.getByPlaceholder("New password (min 8 chars)").fill(newPw);
  await page.getByPlaceholder("Confirm new password").fill("different1");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByTestId("change-error")).toContainText("do not match");
});
