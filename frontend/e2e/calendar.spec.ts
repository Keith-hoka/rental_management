import { expect, test } from "@playwright/test";

const landlord = `cal-${Date.now()}@example.com`;

function dtLocal(d: Date, time: string): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}T${time}`;
}

test("a manager sees derived entries and manages a custom event", async ({ page }) => {
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Cal Owner");
  await page.getByPlaceholder("Organization name").fill("Cal Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("8 Cal Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // A lease whose start and end fall inside this month, so both show on the grid.
  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "8 Cal Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Cara Cal");
  await page.getByPlaceholder("Tenant email").fill(`cal-t-${Date.now()}@example.com`);
  await page.getByLabel("Rent").fill("500");
  await page.getByLabel("Start").fill(`${ym}-01`);
  await page.getByLabel("End").fill(`${ym}-28`);
  await page.getByRole("button", { name: "Add lease" }).click();
  // Wait for the create redirect to settle before navigating, or its pending
  // router.push would override the click below.
  await expect(page).toHaveURL(/\/app\/leases$/);

  await page.getByRole("link", { name: "Calendar" }).click();
  await expect(page).toHaveURL(/\/app\/calendar$/);
  await expect(page.getByText(/Lease ends/)).toBeVisible();

  // Add a single-day event (start/end prefilled to today), then rename and delete it.
  await page.getByRole("button", { name: "New event" }).click();
  const dialog = page.getByRole("dialog", { name: "New event" });
  await dialog.getByLabel("Title").fill("Team meeting");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Team meeting" })).toBeVisible();

  await page.getByRole("button", { name: "Team meeting" }).click();
  const editDialog = page.getByRole("dialog", { name: "Edit event" });
  await editDialog.getByLabel("Title").fill("Team sync");
  await editDialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Team sync" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Team meeting" })).toHaveCount(0);

  await page.getByRole("button", { name: "Team sync" }).click();
  await page
    .getByRole("dialog", { name: "Edit event" })
    .getByRole("button", { name: "Delete" })
    .click();
  const confirm = page.getByRole("dialog", { name: "Delete event" });
  await confirm.getByRole("button", { name: "Yes, delete" }).click();
  await expect(page.getByRole("button", { name: "Team sync" })).toHaveCount(0);

  // A multi-day event (Monday to the Wednesday of the same week) renders as one
  // bar spanning several columns.
  const monday = new Date(now.getFullYear(), now.getMonth(), 1);
  while (monday.getDay() !== 1) monday.setDate(monday.getDate() + 1);
  const wednesday = new Date(monday);
  wednesday.setDate(monday.getDate() + 2);

  await page.getByRole("button", { name: "New event" }).click();
  const multi = page.getByRole("dialog", { name: "New event" });
  await multi.getByLabel("Title").fill("Conference");
  await multi.getByLabel("Start").fill(dtLocal(monday, "09:00"));
  await multi.getByLabel("End").fill(dtLocal(wednesday, "17:00"));
  await multi.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("button", { name: "Conference" })).toBeVisible();

  const span = await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll("button")).find(
      (b) => b.textContent === "Conference",
    );
    const match = el?.style.gridColumn.match(/span (\d+)/);
    return match ? Number(match[1]) : 0;
  });
  expect(span).toBe(3);
});
