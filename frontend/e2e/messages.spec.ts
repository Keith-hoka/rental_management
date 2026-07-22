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

test("landlord deletes a message after confirming", async ({ page }) => {
  const email = `msg-del-${Date.now()}@example.com`;
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Del Landlord");
  await page.getByPlaceholder("Organization name").fill("Del Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Renewing a lease notifies the organization's managers, so this is the
  // cheapest way to get a real message without onboarding a tenant.
  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("2 Message Mews");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  const iso = (days: number) => {
    const d = new Date();
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  };
  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "2 Message Mews (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Msg Tenant");
  await page.getByPlaceholder("Tenant email").fill(`msg-t-${Date.now()}@example.com`);
  await page.getByLabel("Rent").fill("300");
  await page.getByLabel("Start").fill(iso(-1));
  await page.getByLabel("End").fill(iso(30));
  await page.getByRole("button", { name: "Add lease" }).click();

  await page.getByRole("link", { name: "2 Message Mews" }).click();
  await page.getByRole("link", { name: "Renew lease" }).click();
  await page.getByLabel("End").fill(iso(395));
  await page.getByRole("button", { name: "Create renewal" }).click();
  await expect(page.getByRole("link", { name: "View previous lease" })).toBeVisible();

  await page.getByRole("link", { name: "Messages" }).click();
  await expect(page.getByText("Lease renewed")).toBeVisible();

  // Deleting asks first, and cancelling leaves the message alone.
  await page.getByRole("button", { name: "Delete message Lease renewed" }).click();
  await expect(page.getByRole("dialog", { name: "Delete message" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("Lease renewed")).toBeVisible();

  await page.getByRole("button", { name: "Delete message Lease renewed" }).click();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(page.getByText("No messages yet.")).toBeVisible();
});
