import { expect, test } from "@playwright/test";

const landlord = `messages-${Date.now()}@example.com`;

test("landlord opens the messages inbox from the dashboard", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Msg Landlord");
  await page.getByPlaceholder("Organization name").fill("Msg Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Messages" }).click();
  await expect(page).toHaveURL(/\/app\/messages$/);
  await expect(page.getByRole("heading", { name: "Messages" })).toBeVisible();
  await expect(page.getByText("No messages yet.")).toBeVisible();
});
