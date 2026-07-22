import { expect, test } from "@playwright/test";
import { invitationToken } from "./invitation-token";

const stamp = Date.now();
const landlord = `portal-owner-${stamp}@example.com`;
const tenant = `portal-tenant-${stamp}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("a tenant accepts an invite and uses the portal", async ({ page }) => {
  // The landlord sets up a property and a lease, then invites the tenant.
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Portal Owner");
  await page.getByPlaceholder("Organization name").fill("Portal Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("8 Portal Street");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "8 Portal Street (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Portal Tenant");
  await page.getByPlaceholder("Tenant email").fill(tenant);
  await page.getByLabel("Rent").fill("600");
  // Set explicitly so the assertion below does not ride on the form default.
  await page.getByLabel("Frequency").selectOption("weekly");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(30));
  await page.getByRole("button", { name: "Add lease" }).click();

  await page.getByRole("link", { name: "8 Portal Street" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByRole("button", { name: "Invite" }).first().click();
  await expect(page.getByText(`Invitation sent to ${tenant}`)).toBeVisible();

  // The tenant accepts. Only the emailed token can reach this page.
  const token = await invitationToken(tenant);
  await page.goto(`/accept-invite?token=${token}`);
  await page.getByPlaceholder("Your name").fill("Portal Tenant");
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page).toHaveURL(/\/app$/);

  // The portal shell, not the manager sidebar: no Properties or Team link.
  await expect(page.getByTestId("welcome")).toContainText("Portal Tenant (tenant)");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link", { name: "Profile" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Properties" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Team" })).toHaveCount(0);

  // Their own lease, and nobody else's.
  await expect(page.getByRole("heading", { name: "8 Portal Street" })).toBeVisible();
  await expect(page.getByText("$600.00 / weekly")).toBeVisible();

  // Reporting maintenance puts the request in the list below the form.
  await page.getByPlaceholder("Issue title").fill("Leaking tap");
  await page.getByPlaceholder("Description").fill("Kitchen tap drips overnight");
  await page.getByLabel("Priority").selectOption("high");
  await page.getByRole("button", { name: "Report" }).click();
  await expect(page.getByText("Leaking tap")).toBeVisible();
  await expect(page.getByText("Kitchen tap drips overnight")).toBeVisible();

  // Every page a tenant can reach keeps the portal shell — no manager sidebar.
  await nav.getByRole("link", { name: "Messages" }).click();
  await expect(page).toHaveURL(/\/app\/messages$/);
  // Anchor on the new page having rendered first: a toHaveCount(0) fired
  // mid-navigation passes against a momentarily empty nav and never retries.
  await expect(page.getByRole("heading", { name: "Messages" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Properties" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Team" })).toHaveCount(0);

  await nav.getByRole("link", { name: "Profile" }).click();
  await expect(page).toHaveURL(/\/app\/profile$/);
  await expect(page.getByText(tenant)).toBeVisible();
  await nav.getByRole("link", { name: "Change password" }).click();
  await expect(page).toHaveURL(/\/app\/change-password$/);
  await expect(page.getByRole("button", { name: "Update password" })).toBeVisible();

  // Narrow: the portal nav collapses the same way the manager sidebar does.
  // Resizing here reuses this tenant rather than onboarding a second one.
  await page.setViewportSize({ width: 390, height: 844 });
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toBeVisible();
  await expect(nav.getByRole("link", { name: "Profile" })).toBeHidden();
  await menu.click();
  await expect(nav.getByRole("link", { name: "Profile" })).toBeVisible();
});
