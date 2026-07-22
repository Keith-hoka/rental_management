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

  // The drawer is fixed, so the page must not scroll underneath it, and the bar
  // must stay put — otherwise scrolling reveals the page through the gap above
  // the drawer. mouse.wheel, not scrollTo: overflow:hidden blocks the user's
  // scroll but not a scripted one, so a scripted scroll proves nothing here.
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await page.mouse.move(195, 400);
  await page.mouse.wheel(0, 400);
  // Control. Without it a stationary page would satisfy the real assertion
  // below for the wrong reason, and the test would pass with no lock at all.
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

  await page.mouse.wheel(0, -400);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await page.mouse.wheel(0, 400);
  // Settle, then assert once. expect.poll is wrong for proving absence: it
  // succeeds on its first sample, which lands before the wheel has been
  // applied, so it passes and never retries.
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => Math.round(window.scrollY))).toBe(0);
  expect(
    await page.evaluate(() =>
      Math.round(document.querySelector("header")!.getBoundingClientRect().top),
    ),
  ).toBe(0);

  // Choosing a destination navigates and puts the menu away again.
  await nav.getByRole("link", { name: "Properties" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);
  await expect(page.getByRole("heading", { name: "Properties" })).toBeVisible();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
});
