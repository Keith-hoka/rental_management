import { expect, test } from "@playwright/test";

const email = `charts-${Date.now()}@example.com`;

// Card titles only. Chart internals are SVG, and asserting path coordinates
// would be brittle without being more convincing; the numbers are covered by
// backend/tests/test_dashboard_charts.py.
test("landlord sees the occupancy and maintenance charts", async ({ page }) => {
  // The dashboard falls back to rendering nothing when /stats fails, so the
  // card titles alone would also pass against a stale backend without the new
  // fields. Assert the payload actually carried them.
  const stats = page.waitForResponse((r) => r.url().includes("/api/v1/stats"));

  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Charts Landlord");
  await page.getByPlaceholder("Organization name").fill("Charts Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  const body = await (await stats).json();
  expect(body.occupancy).toHaveLength(6);
  expect(body.maintenance_by_status).toHaveLength(4);

  await expect(page.getByRole("heading", { name: "Monthly income" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Occupancy" })).toBeVisible();
  // exact: true — the dashboard also has a "Maintenance requests" stat card, and
  // Playwright matches names by substring.
  await expect(
    page.getByRole("heading", { name: "Maintenance status", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("No maintenance requests yet.")).toBeVisible();
});
