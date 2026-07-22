import { expect, test } from "@playwright/test";

const email = `e2e-${Date.now()}@example.com`;
const stale = `e2e-stale-${Date.now()}@example.com`;
const roleEmail = `e2e-role-${Date.now()}@example.com`;
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

test("the landing page leads to log in", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Simplify property management in one app" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Get started" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
});

test("logging in as the wrong role is refused", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Role User");
  await page.getByPlaceholder("Organization name").fill("Role Org");
  await page.getByPlaceholder("Email").fill(roleEmail);
  await page.getByPlaceholder("Password (min 8 chars)").fill(password);
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();

  // The account is a landlord; signing in as Tenant must not get through.
  await page.getByRole("radio", { name: "Tenant" }).click();
  await page.getByPlaceholder("Email").fill(roleEmail);
  await page.getByPlaceholder("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();

  // Not getByRole("alert"): Next renders its own route announcer with that role.
  await expect(page.getByText("This account signs in as landlord.")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);

  await page.getByRole("radio", { name: "Landlord" }).click();
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByTestId("welcome")).toContainText("Role User (landlord)");
});

test("an expired access token is refreshed instead of emptying the page", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Stale User");
  await page.getByPlaceholder("Organization name").fill("Stale Org");
  await page.getByPlaceholder("Email").fill(stale);
  await page.getByPlaceholder("Password (min 8 chars)").fill(password);
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Simulate the 30-minute expiry: keep the refresh token, break the access one.
  await page.evaluate(() => localStorage.setItem("access_token", "expired.token.value"));
  await page.reload();

  await expect(page.getByTestId("welcome")).toContainText("Stale User (landlord)");
  await expect(page.getByRole("heading", { name: "Recent payments" })).toBeVisible();
});
