import { expect, test } from "@playwright/test";

const landlord = `landlord-${Date.now()}@example.com`;

test("landlord invites a team member, sees it pending, and revokes it", async ({ page }) => {
  // Sign up as a landlord.
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Landlord");
  await page.getByPlaceholder("Organization name").fill("Landlord Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Go to Team and invite a property manager.
  await page.getByRole("link", { name: "Team" }).click();
  await expect(page).toHaveURL(/\/app\/team/);
  await page.getByPlaceholder("Email to invite").fill("pm@example.com");
  await page.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByText("pm@example.com")).toBeVisible();

  // Revoke it. Revoking is destructive, so it goes through a confirmation.
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByRole("dialog", { name: "Revoke invitation" })).toBeVisible();
  await page.getByRole("button", { name: "Yes, revoke" }).click();
  await expect(page.getByText("pm@example.com")).toHaveCount(0);
});

test("accept-invite page shows an error without a token", async ({ page }) => {
  await page.goto("/accept-invite");
  await expect(page.getByTestId("missing-token")).toBeVisible();
});
