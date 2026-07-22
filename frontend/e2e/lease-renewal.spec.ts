import { expect, test } from "@playwright/test";

const stamp = Date.now();
const email = `renewal-${stamp}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("a landlord renews a lease and the two are linked", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Renewal Owner");
  await page.getByPlaceholder("Organization name").fill("Renewal Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("3 Renewal Road");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "3 Renewal Road (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Rita Renewal");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${stamp}@example.com`);
  await page.getByLabel("Rent").fill("500");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(20));
  await page.getByRole("button", { name: "Add lease" }).click();

  await page.getByRole("link", { name: "3 Renewal Road" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  const originalUrl = page.url();

  await page.getByRole("link", { name: "Renew lease" }).click();
  await expect(page).toHaveURL(/\/renew$/);
  // The tenants who carry over are shown, and everything but the term length
  // is prefilled. The rent arrives as "500.00": the API serialises Decimal as
  // a JSON string, so it is not the "500" that was typed in.
  await expect(page.getByText("Rita Renewal")).toBeVisible();
  await expect(page.getByLabel("Start")).toHaveValue(isoDate(21));
  await expect(page.getByLabel("Rent")).toHaveValue("500.00");
  await expect(page.getByLabel("End")).toHaveValue("");

  await page.getByLabel("Rent").fill("550");
  await page.getByLabel("End").fill(isoDate(385));
  await page.getByRole("button", { name: "Create renewal" }).click();

  // Lands on the successor. Wait for a lease URL that is not the one we came
  // from: both pages match the same pattern, so the pattern alone would be
  // satisfied before the navigation happened.
  await page.waitForURL(
    (url) => /\/app\/leases\/[0-9a-f-]+$/.test(url.pathname) && url.href !== originalUrl,
  );
  await expect(page.getByRole("link", { name: "View previous lease" })).toBeVisible();
  await expect(page.getByText("$550.00 / monthly")).toBeVisible();
  // The successor is itself renewable -- next year this lease needs renewing
  // too. Only renewing the same lease twice is refused.
  await expect(page.getByRole("link", { name: "Renew lease" })).toBeVisible();

  // The predecessor now offers the renewal instead of a second renew. Assert
  // the link is there before asserting the other is gone: a toHaveCount(0)
  // fired mid-navigation passes against an empty DOM and never retries.
  await page.goto(originalUrl);
  await expect(page.getByRole("link", { name: "View renewal" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Renew lease" })).toHaveCount(0);
});
