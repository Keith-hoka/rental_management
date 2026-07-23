import { expect, test } from "@playwright/test";

const landlord = `export-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("a landlord exports the payment history as CSV", async ({ page }) => {
  // The native "Save As" picker cannot be driven headlessly. Disable it so the
  // export runs its fallback: a normal download, which fires a download event.
  await page.addInitScript(() => {
    (window as unknown as { showSaveFilePicker?: unknown }).showSaveFilePicker = undefined;
  });

  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Export Owner");
  await page.getByPlaceholder("Organization name").fill("Export Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("6 Export Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "6 Export Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Ed Exporter");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent").fill("700");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(60));
  await page.getByRole("button", { name: "Add lease" }).click();

  // Record a payment so the export has a row.
  await page.getByRole("link", { name: "6 Export Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByPlaceholder("Amount").fill("700");
  await page.getByLabel("Payment date").fill(isoDate(0));
  await page.getByRole("button", { name: "Record payment" }).click();

  // Export lives in the dashboard header, behind a dialog with a required range.
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await page.getByRole("button", { name: "Export CSV" }).click();

  const dialog = page.getByRole("dialog", { name: "Export payments" });
  await expect(dialog).toBeVisible();
  const download = dialog.getByRole("button", { name: "Download CSV" });
  // No range, no export: the download stays disabled until both dates are set.
  await expect(download).toBeDisabled();
  await dialog.getByLabel("Export from").fill(isoDate(-7));
  await expect(download).toBeDisabled();
  await dialog.getByLabel("Export to").fill(isoDate(1));
  await expect(download).toBeEnabled();

  // The download comes from a fetch + synthetic anchor, so it fires a real
  // download event rather than a navigation.
  const file = page.waitForEvent("download");
  await download.click();
  expect((await file).suggestedFilename()).toBe("payment history.csv");
});
