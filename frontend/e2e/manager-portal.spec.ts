import { expect, test } from "@playwright/test";
import { invitationToken } from "./invitation-token";

const stamp = Date.now();
const landlord = `pm-owner-${stamp}@example.com`;
const manager = `pm-member-${stamp}@example.com`;

test("an invited property manager works in the org", async ({ page }) => {
  // The landlord creates a property, then invites a property manager.
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("PM Owner");
  await page.getByPlaceholder("Organization name").fill("PM Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("3 Manager Court");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.getByRole("link", { name: "Team" }).click();
  await page.getByPlaceholder("Email to invite").fill(manager);
  await page.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByText(manager)).toBeVisible();

  // The manager accepts, which signs them straight in.
  const token = await invitationToken(manager);
  await page.goto(`/accept-invite?token=${token}`);
  await page.getByPlaceholder("Your name").fill("Pat Manager");
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page).toHaveURL(/\/app$/);

  // The manager shell, with the full sidebar.
  await expect(page.getByTestId("welcome")).toContainText("Pat Manager (property_manager)");
  const nav = page.getByRole("navigation", { name: "Main" });
  for (const label of ["Dashboard", "Properties", "Leases", "Tenants", "Payments", "Team"]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }

  // They see the landlord's property, because they joined that organization.
  await nav.getByRole("link", { name: "Properties" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);
  await expect(page.getByRole("link", { name: "3 Manager Court" })).toBeVisible();

  // And can add one of their own.
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("4 Manager Court");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);
  await expect(page.getByRole("link", { name: "4 Manager Court" })).toBeVisible();
});
