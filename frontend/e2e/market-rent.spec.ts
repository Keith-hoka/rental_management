import { expect, test } from "@playwright/test";

const LIVE = !!process.env.MARKET_RENT_E2E;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const MARKET = {
  jurisdiction: "NSW",
  area: "2000",
  area_label: "2000",
  dwelling_type: "unit",
  bedrooms: 2,
  estimate_weekly: "760",
  band: { low: "698", high: "886" },
  basis: "median",
  period: "2026-07",
  period_end: "2026-07-31",
  stale: false,
  sample_size: 170,
  fallback: null,
  series: [],
  trend: { from_period: "2025-07", from_median: "700.00", change_pct: "8.6" },
  source: {
    name: "NSW Fair Trading rental bond lodgements",
    url: "https://www.nsw.gov.au/housing-and-construction/rental-forms-surveys-and-data/rental-bond-data",
    licence: "NSW Government open data (terms on the source page)",
  },
  disclaimer: "General information, not legal advice.",
};

const ENVELOPE = { market: MARKET, current_weekly: "346", gap_pct: "-54.5" };
const NO_DATA = {
  market: { ...MARKET, area_label: null, estimate_weekly: null, band: null, period: null, period_end: null, sample_size: null, trend: null },
  current_weekly: "346",
  gap_pct: null,
};

/** Signs up a fresh landlord, creates an NSW property (postcode 2000) and a monthly $1500 lease,
 * and returns the property page URL. */
async function createProperty(page: import("@playwright/test").Page): Promise<string> {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Market Owner");
  await page.getByPlaceholder("Organization name").fill("Market Org");
  await page.getByPlaceholder("Email").fill(`market-${Date.now()}@example.com`);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("9 Market Way");
  await page.getByLabel("State").selectOption("NSW");
  await page.getByPlaceholder("Postcode").fill("2000");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "9 Market Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Mia Market");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent", { exact: true }).fill("1500");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(300));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);

  await page.goto("/app/properties");
  await page.getByRole("link", { name: "9 Market Way" }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+$/);
  return page.url();
}

test("property page shows the market estimate and the current-rent gap", async ({ page }) => {
  await page.route("**/market-rent", (route) => route.fulfill({ json: ENVELOPE }));
  await createProperty(page);
  await expect(page.getByTestId("market-estimate")).toContainText("$760");
  await expect(page.getByText("Band $698 to $886", { exact: false })).toBeVisible();
  await expect(page.getByText("8.6% vs 2025-07", { exact: false })).toBeVisible();
  await expect(page.getByTestId("market-gap")).toHaveText(
    "Current rent $346/week, 54.5% below the market median",
  );
});

test("property page says when there is no market data", async ({ page }) => {
  await page.route("**/market-rent", (route) => route.fulfill({ json: NO_DATA }));
  await createProperty(page);
  await expect(page.getByText("No market data for this area")).toBeVisible();
  await expect(page.getByTestId("market-gap")).toHaveCount(0);
});

test("live: the real compliance service estimates postcode 2000", async ({ page }) => {
  test.skip(!LIVE, "set MARKET_RENT_E2E=1 to hit the real service");
  await createProperty(page);
  await expect(page.getByTestId("market-estimate")).toContainText("$");
  await expect(page.getByTestId("market-gap")).toContainText("the market median");
});
