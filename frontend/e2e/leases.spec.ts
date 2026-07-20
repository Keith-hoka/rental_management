import { expect, test } from "@playwright/test";

const landlord = `lease-e2e-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("adding a lease from the leases page makes a property occupied, deleting it makes it vacant", async ({
  page,
}) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Lease Landlord");
  await page.getByPlaceholder("Organization name").fill("Lease Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Create a property.
  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("7 Lease Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Add a lease from the leases page, selecting the property from the dropdown.
  await page.goto("/app");
  await page.getByRole("link", { name: "Leases" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);
  await page.getByLabel("Property").selectOption({ label: "7 Lease Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Tina Tenant");
  await page.getByPlaceholder("Tenant email").fill("tina@example.com");
  await page.getByLabel("Rent").fill("1500");
  await page.getByLabel("Bond (optional)").fill("3000");
  await page.getByLabel("Notice period (days)").fill("21");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(30));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page.getByText("Tina Tenant", { exact: false })).toBeVisible();

  // The property is now occupied (derived from the active lease).
  await page.goto("/app/properties");
  await page.getByRole("link", { name: "7 Lease Way" }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+$/);
  await expect(page.getByText("Occupied")).toBeVisible();
  await expect(page.getByText("Tina Tenant", { exact: false })).toBeVisible();

  // Open the lease from the overview — its detail page shows the tenant info —
  // and delete it there.
  await page.goto("/app/leases");
  await page.getByRole("link", { name: "7 Lease Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await expect(page.getByText("tina@example.com")).toBeVisible();
  await expect(page.getByText(/\$3000/)).toBeVisible();
  await expect(page.getByText("21 days")).toBeVisible();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);
  await expect(page.getByText("No leases yet.")).toBeVisible();

  // Property is vacant again.
  await page.goto("/app/properties");
  await page.getByRole("link", { name: "7 Lease Way" }).click();
  await expect(page.getByText("Vacant — no active lease.")).toBeVisible();
});

const navOwner = `lease-nav-${Date.now()}@example.com`;

test("leases are reachable from the dashboard and the properties list", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Nav Landlord");
  await page.getByPlaceholder("Organization name").fill("Nav Org");
  await page.getByPlaceholder("Email").fill(navOwner);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Create a property.
  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("9 Overview Ave");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Add a lease from the dashboard leases page.
  await page.goto("/app");
  await page.getByRole("link", { name: "Leases" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);
  await page.getByLabel("Property").selectOption({ label: "9 Overview Ave (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Nav Tenant");
  await page.getByPlaceholder("Tenant email").fill("nav@example.com");
  await page.getByLabel("Rent").fill("1200");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(20));
  await page.getByRole("button", { name: "Add lease" }).click();
  // The new lease shows in the overview list as active.
  await expect(page.getByRole("link", { name: "9 Overview Ave" })).toBeVisible();
  await expect(page.getByText("active")).toBeVisible();

  // The properties list offers a per-row shortcut to that property's leases.
  await page.goto("/app/properties");
  await page.getByRole("link", { name: "Leases" }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+\/leases$/);
});
