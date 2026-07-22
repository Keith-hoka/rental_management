import { expect, test } from "@playwright/test";

// The rest of the suite runs at the default 1280px, which is above the md
// breakpoint and so only ever exercises the persistent sidebar.
test.use({ viewport: { width: 390, height: 844 } });

const email = `mobile-nav-${Date.now()}@example.com`;

test("the sidebar collapses behind a menu button on a narrow screen", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Mobile User");
  await page.getByPlaceholder("Organization name").fill("Mobile Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  const nav = page.getByRole("navigation", { name: "Main" });
  const menu = page.getByRole("button", { name: "Menu" });

  // Collapsed: the brand and the button show, the destinations do not.
  await expect(menu).toBeVisible();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await expect(nav.getByRole("link", { name: "Properties" })).toBeHidden();

  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await expect(nav.getByRole("link", { name: "Properties" })).toBeVisible();

  // Choosing a destination navigates and puts the menu away again.
  await nav.getByRole("link", { name: "Properties" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);
  await expect(page.getByRole("heading", { name: "Properties" })).toBeVisible();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
});
