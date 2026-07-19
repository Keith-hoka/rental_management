import { expect, test } from "@playwright/test";

test("forgot password request flow from login", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page).toHaveURL(/\/forgot-password/);

  await page.getByPlaceholder("Email").fill("someone@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();

  await expect(page.getByTestId("confirmation")).toBeVisible();
});

test("login shows confirmation after a completed reset", async ({ page }) => {
  await page.goto("/login?reset=success");
  await expect(page.getByTestId("reset-success")).toContainText("Password updated");
});

test("reset page rejects a missing token", async ({ page }) => {
  await page.goto("/reset-password");
  await expect(page.getByTestId("missing-token")).toBeVisible();
});
