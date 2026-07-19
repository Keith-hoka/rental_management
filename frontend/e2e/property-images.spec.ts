import { expect, test } from "@playwright/test";

const email = `img-e2e-${Date.now()}@example.com`;

test("upload an image to a property and see it displayed", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Img E2E");
  await page.getByPlaceholder("Organization name").fill("Img Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Choose an image on the create form (below the description), then create.
  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("Image Lane");
  await page.getByLabel("Upload image").setInputFiles({
    name: "photo.png",
    mimeType: "image/png",
    buffer: Buffer.from("\x89PNG\r\n\x1a\n fake image bytes"),
  });
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Open the property; the uploaded image is displayed.
  await page.getByRole("link", { name: "Image Lane" }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+/);
  await expect(page.getByAltText("Property")).toBeVisible();
});
