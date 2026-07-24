import { expect, test } from "@playwright/test";

const landlord = `insp-${Date.now()}@example.com`;

test("a manager schedules an inspection and marks it completed", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Insp Owner");
  await page.getByPlaceholder("Organization name").fill("Insp Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("17 Insp Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.getByRole("link", { name: "Inspections" }).click();
  await expect(page).toHaveURL(/\/app\/inspections$/);

  // Schedule a move-in inspection with one checklist item.
  await page.getByLabel("Property").selectOption({ label: "17 Insp Way" });
  await page.getByRole("button", { name: "Add item" }).click();
  await page.getByLabel("Item area").fill("Kitchen");
  await page.getByRole("button", { name: "Schedule inspection" }).click();

  const row = page.getByRole("listitem").filter({ hasText: "Move in" });
  await expect(row).toContainText("scheduled");
  await expect(row).toContainText("Kitchen");

  // Mark it completed via the inline editor.
  await row.getByRole("button", { name: "Edit" }).click();
  await row.getByLabel("Edit status").selectOption("completed");
  await row.getByRole("button", { name: "Save changes" }).click();

  // The editor closes only after the update resolves, so a persisted change is
  // what turns the badge to "completed".
  await expect(row.getByRole("button", { name: "Save changes" })).toBeHidden();
  await expect(row).toContainText("completed");
});
