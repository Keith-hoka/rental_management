import { expect, test } from "@playwright/test";

const landlord = `payments-${Date.now()}@example.com`;

test("landlord records a payment on a lease", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Pay Landlord");
  await page.getByPlaceholder("Organization name").fill("Pay Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("9 Pay Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app");
  await page.getByRole("link", { name: "Leases" }).click();
  await page.getByRole("link", { name: "New lease" }).click();
  await page.getByLabel("Property").selectOption({ label: "9 Pay Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Pat Payer");
  await page.getByPlaceholder("Tenant email").fill("pat@example.com");
  await page.getByLabel("Rent").fill("1200");
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 1);
  const end = new Date(today);
  end.setDate(end.getDate() + 30);
  await page.getByLabel("Start").fill(start.toISOString().slice(0, 10));
  await page.getByLabel("End").fill(end.toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page.getByText("Pat Payer", { exact: false })).toBeVisible();

  // Open the lease detail and record a payment (no charges yet -> becomes a credit).
  await page.getByRole("link", { name: "9 Pay Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByPlaceholder("Amount").fill("500");
  await page.getByLabel("Payment date").fill(today.toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Record payment" }).click();

  // The payment appears in the list and the balance shows a credit.
  await expect(page.getByText("bank_transfer", { exact: false })).toBeVisible();
  await expect(page.getByText("Credit", { exact: false })).toBeVisible();
});
