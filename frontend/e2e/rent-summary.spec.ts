import { expect, test } from "@playwright/test";

const email = `rent-${Date.now()}@example.com`;

// Empty-state coverage only, and deliberately so: generate_charges runs on a
// schedule rather than at startup, so a lease created inside a test has no
// charges and no overdue state can be staged through the UI. The bucketing
// rules are covered by backend/tests/test_rent_summary.py.
test("landlord sees the overdue and upcoming rent cards", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Rent Landlord");
  await page.getByPlaceholder("Organization name").fill("Rent Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // The page falls back to empty cards when the request fails, so an empty
  // state alone would also pass against a 404. Assert the endpoint answered.
  const summary = page.waitForResponse((r) => r.url().includes("/rent/summary"));
  await page.getByRole("link", { name: "Payments" }).click();
  expect((await summary).status()).toBe(200);
  await expect(page).toHaveURL(/\/app\/payments$/);
  await expect(page.getByRole("heading", { name: "Overdue rent" })).toBeVisible();
  await expect(page.getByText("Nothing overdue.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Upcoming rent" })).toBeVisible();
  await expect(page.getByText("Nothing due in the next 7 days.")).toBeVisible();
  // The existing history card must survive the two additions.
  await expect(page.getByRole("heading", { name: "Payment history" })).toBeVisible();
});
