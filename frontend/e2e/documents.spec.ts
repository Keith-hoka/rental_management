import { expect, test } from "@playwright/test";

const landlord = `docs-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const PDF = Buffer.from("%PDF-1.4 e2e minimal");

test("a landlord uploads, versions, previews and deletes a document", async ({ page }) => {
  // The native "Save As" picker cannot be driven headlessly, so stand in a fake
  // that records what saveBlob hands it. This proves the Chromium path flows the
  // file through the picker with the right name and content.
  await page.addInitScript(() => {
    const w = window as unknown as {
      __saved?: { name?: string; size: number };
      showSaveFilePicker?: (o?: { suggestedName?: string }) => Promise<unknown>;
    };
    w.showSaveFilePicker = async (opts) => ({
      createWritable: async () => ({
        write: async (data: Blob) => {
          w.__saved = { name: opts?.suggestedName, size: data.size };
        },
        close: async () => {},
      }),
    });
  });

  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Docs Owner");
  await page.getByPlaceholder("Organization name").fill("Docs Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("13 Docs Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "13 Docs Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Dana Docs");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent").fill("600");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(60));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);

  await page.getByRole("link", { name: "13 Docs Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: "Documents", exact: true })).toBeVisible();

  // Upload the first version.
  await page.getByLabel("Title").fill("Signed Lease");
  await page
    .locator("label")
    .filter({ hasText: "Add document" })
    .locator('input[type="file"]')
    .setInputFiles({ name: "lease.pdf", mimeType: "application/pdf", buffer: PDF });

  // The document lists as its own row at v1. Scope to that row: a bare
  // "Delete" would otherwise match the lease-level delete button, which
  // precedes the Documents card in the DOM.
  const docRow = page.locator("li").filter({ hasText: "Signed Lease" });
  await expect(docRow).toBeVisible();
  await expect(docRow.getByText("v1")).toBeVisible();

  // A new version bumps the counter.
  await docRow
    .locator("label")
    .filter({ hasText: "New version" })
    .locator('input[type="file"]')
    .setInputFiles({ name: "lease-v2.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(docRow.getByText("v2")).toBeVisible();

  // Every version stays reachable: expanding the history still lists the
  // original v1, which the header (showing only the latest) no longer names.
  await docRow.getByRole("button", { name: "Versions" }).click();
  const oldVersion = docRow.locator("li").filter({ hasText: "lease.pdf" });
  await expect(oldVersion).toBeVisible();

  // The old version previews from its own history row.
  await oldVersion.getByRole("button", { name: "Preview" }).click();
  const preview = page.getByRole("dialog", { name: "Preview lease.pdf" });
  await expect(preview).toBeVisible();
  await preview.getByRole("button", { name: "Close" }).click();
  await expect(preview).toBeHidden();

  // The old version downloads under its own name, flowing through the picker.
  await oldVersion.getByRole("button", { name: "Download" }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () => (window as unknown as { __saved?: { name?: string } }).__saved?.name,
      ),
    )
    .toBe("lease.pdf");
  const savedSize = await page.evaluate(
    () => (window as unknown as { __saved?: { size: number } }).__saved?.size ?? 0,
  );
  expect(savedSize).toBeGreaterThan(0);

  // Delete through the confirmation, and the empty state returns.
  await docRow.getByRole("button", { name: "Delete" }).click();
  const confirm = page.getByRole("dialog", { name: "Delete document" });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "Yes, delete" }).click();
  await expect(page.getByText("No documents yet.")).toBeVisible();
});
