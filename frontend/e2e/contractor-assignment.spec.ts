import { expect, test } from "@playwright/test";
import { invitationToken } from "./invitation-token";

const stamp = Date.now();
const landlord = `contractor-owner-${stamp}@example.com`;
const tenant = `contractor-tenant-${stamp}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("a landlord assigns a contractor and the tenant sees who is coming", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Contractor Owner");
  await page.getByPlaceholder("Organization name").fill("Contractor Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // A contractor in the directory.
  await page.getByRole("link", { name: "Contractors" }).click();
  await expect(page).toHaveURL(/\/app\/contractors$/);
  await page.getByLabel("Name").fill("Bob's Plumbing");
  await page.getByLabel("Trade").fill("Plumber");
  await page.getByLabel("Phone").fill("0400 123 456");
  await page.getByRole("button", { name: "Add contractor" }).click();
  await expect(page.getByText("Bob's Plumbing")).toBeVisible();

  // A property, a lease, and an onboarded tenant to report the issue.
  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("7 Contractor Close");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "7 Contractor Close (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Tess Tenant");
  await page.getByPlaceholder("Tenant email").fill(tenant);
  await page.getByLabel("Rent").fill("400");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(60));
  await page.getByRole("button", { name: "Add lease" }).click();

  await page.getByRole("link", { name: "7 Contractor Close" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByRole("button", { name: "Invite" }).first().click();
  await expect(page.getByText(`Invitation sent to ${tenant}`)).toBeVisible();

  const token = await invitationToken(tenant);
  await page.goto(`/accept-invite?token=${token}`);
  await page.getByPlaceholder("Your name").fill("Tess Tenant");
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page).toHaveURL(/\/app$/);

  // The tenant reports an issue, then logs out.
  await page.getByPlaceholder("Issue title").fill("Burst pipe");
  await page.getByPlaceholder("Description").fill("Water under the sink");
  await page.getByRole("button", { name: "Report" }).click();
  await expect(page.getByText("Burst pipe")).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // The landlord assigns the contractor.
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password").fill("secret123");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();
  await page.getByRole("link", { name: "Maintenance" }).click();
  await expect(page.getByText("Burst pipe")).toBeVisible();
  await page.getByLabel("Contractor").selectOption({ label: "Bob's Plumbing" });
  await expect(page.getByText("Assigned to Bob's Plumbing (0400 123 456)")).toBeVisible();

  // Assignment records who does the work; it must not advance the status.
  // exact: true, or this also matches the page's "Filter status" select.
  await expect(page.getByLabel("Status", { exact: true })).toHaveValue("open");

  // The tenant sees who is coming. This is the cross-role rule the whole
  // feature turns on, and the part most likely to break silently.
  await page.getByRole("button", { name: "Log out" }).click();
  // The role radio is required: the login form defaults to landlord, and
  // signing in with the wrong role is refused (see auth.spec.ts).
  await page.getByRole("radio", { name: "Tenant" }).click();
  await page.getByPlaceholder("Email").fill(tenant);
  await page.getByPlaceholder("Password").fill("secret123");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText("Contractor: Bob's Plumbing (0400 123 456)")).toBeVisible();
});
