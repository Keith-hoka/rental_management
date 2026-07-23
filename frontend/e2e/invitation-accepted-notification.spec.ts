import { expect, test } from "@playwright/test";
import { invitationToken } from "./invitation-token";

const landlord = `invnotif-${Date.now()}@example.com`;
const manager = `pmnotif-${Date.now()}@example.com`;

test("the landlord is notified in Messages when a manager accepts an invite", async ({
  page,
  browser,
}) => {
  // Landlord signs up and invites a property manager.
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Notif Landlord");
  await page.getByPlaceholder("Organization name").fill("Notif Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Team" }).click();
  await page.getByPlaceholder("Email to invite").fill(manager);
  await page.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByText(manager)).toBeVisible();

  // The manager accepts in a separate context so the landlord stays signed in.
  const token = await invitationToken(manager);
  const managerContext = await browser.newContext();
  const managerPage = await managerContext.newPage();
  await managerPage.goto(`/accept-invite?token=${token}`);
  await managerPage.getByPlaceholder("Your name").fill("Priya Manager");
  await managerPage.getByPlaceholder("Password (min 8 chars)").fill("pmsecret1");
  await managerPage.getByRole("button", { name: "Accept invitation" }).click();
  await expect(managerPage.getByTestId("welcome")).toBeVisible();
  await managerContext.close();

  // Back as the landlord: the acceptance appears in Messages.
  await page.getByRole("link", { name: "Messages" }).click();
  await expect(page.getByText("Invitation accepted")).toBeVisible();
  await expect(page.getByText("Priya Manager", { exact: false })).toBeVisible();
});
