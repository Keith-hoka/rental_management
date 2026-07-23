import { expect, test } from "@playwright/test";

const landlord = `search-${Date.now()}@example.com`;

test("a manager searches from the header and opens a property hit", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Search Owner");
  await page.getByPlaceholder("Organization name").fill("Search Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("42 Xanadu Lane");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Search from the header box (aria-label "Search"; the page input is "Search term").
  await page.getByLabel("Search", { exact: true }).fill("xanadu");
  await page.getByLabel("Search", { exact: true }).press("Enter");
  await expect(page).toHaveURL(/\/app\/search\?q=xanadu$/);

  // The property appears under Properties; clicking it opens the detail page.
  await expect(page.getByRole("heading", { name: "Properties" })).toBeVisible();
  await page.getByRole("link", { name: /42 Xanadu Lane/ }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+$/);
});
