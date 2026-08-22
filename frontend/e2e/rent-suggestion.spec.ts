import { expect, test } from "@playwright/test";

const LIVE = !!process.env.RENT_SUGGESTION_E2E;

const NO_MARKET_DATA_TEXT =
  "No market data for this area - the suggestion is capped guidance only, not a market comparison.";

const STALE_MARKET_TEXT =
  "Market data runs to 2025-09-30, more than six months before the as-at date - treat the comparison as indicative.";

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const CANNED_SUGGESTION = {
  current_weekly: "600",
  suggested_weekly: "720",
  range: { low: "600", high: "690" },
  market_gap: "within",
  market: {
    area_label: "2000",
    period: "2026-07",
    period_end: "2026-07-31",
    stale: false,
    median: "760",
    p25: "698",
    p75: "886",
    sample_size: 170,
    fallback: null,
    source: {
      name: "NSW Fair Trading rental bond lodgements",
      url: "https://www.nsw.gov.au/housing-and-construction/rental-forms-surveys-and-data/rental-bond-data",
      licence: "NSW Government open data (terms on the source page)",
    },
  },
  law_card: [
    {
      rule_id: "nsw.rent_increase_frequency",
      verdict: "green",
      summary: "Rent last increased more than 12 months before this renewal.",
      citations: [
        {
          act: "Residential Tenancies Act 2010 (NSW)",
          section_no: "41",
          as_at: "2026-08-06",
          label: null,
        },
      ],
      skip_reason: null,
    },
  ],
  law_blocked: false,
  reasoning: "Median 760 supports 720.",
  model: "claude-sonnet-5",
  engine_version: "1.6.0",
  disclaimer: "General information, not legal advice.",
};

const CANNED_STALE_SUGGESTION = {
  current_weekly: "600",
  suggested_weekly: "645",
  range: { low: "600", high: "690" },
  market_gap: "within",
  market: {
    area_label: "2148",
    period: "2025-Q3",
    period_end: "2025-09-30",
    stale: true,
    median: "705",
    p25: "650",
    p75: "780",
    sample_size: 96,
    fallback: null,
    source: {
      name: "NSW Fair Trading rental bond lodgements",
      url: "https://www.nsw.gov.au/housing-and-construction/rental-forms-surveys-and-data/rental-bond-data",
      licence: "NSW Government open data (terms on the source page)",
    },
  },
  law_card: [],
  law_blocked: false,
  reasoning: "Median 705 is several quarters old; treat 645 as indicative only.",
  model: "claude-sonnet-5",
  engine_version: "1.6.0",
  disclaimer: "General information, not legal advice.",
};

const CANNED_NO_DATA_SUGGESTION = {
  current_weekly: "600",
  suggested_weekly: "675",
  range: { low: "600", high: "690" },
  market_gap: "no_data",
  market: null,
  law_card: [],
  law_blocked: false,
  reasoning: "No comparable market data was found for this area; capped at 15% above current.",
  model: "claude-sonnet-5",
  engine_version: "1.6.0",
  disclaimer: "General information, not legal advice.",
};

/** Signs up a fresh landlord, creates an NSW property and a (monthly, $600) lease,
 * and lands on that lease's renew page. Returns the renew page's URL. */
async function openRenewPage(page: import("@playwright/test").Page): Promise<string> {
  const landlord = `rent-suggest-${Date.now()}@example.com`;
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Suggest Owner");
  await page.getByPlaceholder("Organization name").fill("Suggest Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("41 Suggest Way");
  await page.getByLabel("State").selectOption("NSW");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "41 Suggest Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Sam Suggest");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent", { exact: true }).fill("600");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(20));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);

  await page.getByRole("link", { name: "41 Suggest Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);

  await page.getByRole("link", { name: "Renew lease" }).click();
  await expect(page).toHaveURL(/\/renew$/);
  return page.url();
}

async function enableRentAi(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/app/settings/ai");
  const toggle = page.getByRole("switch", { name: /rent ai/i });
  await toggle.click();
  await expect(toggle).toBeChecked();
}

test("unconsented renew page shows the AI consent prompt after Suggest rent", async ({
  page,
}) => {
  await openRenewPage(page);

  await page.getByRole("button", { name: "Suggest rent" }).click();

  await expect(page.getByTestId("ai-consent-card")).toBeVisible();
  await expect(page.getByText(/AI features are disabled/)).toBeVisible();
});

test("consented renew page shows a mocked suggestion and fills the rent field", async ({
  page,
}) => {
  const renewUrl = await openRenewPage(page);
  await enableRentAi(page);
  await page.goto(renewUrl);

  await page.route("**/rent-suggestion", (route) =>
    route.fulfill({ json: CANNED_SUGGESTION }),
  );
  await page.getByRole("button", { name: "Suggest rent" }).click();

  await expect(page.getByText("$720")).toBeVisible();
  await expect(page.getByTestId("ai-consent-card")).not.toBeVisible();
  await expect(page.getByText("Market (2000)", { exact: false })).toBeVisible();
  await expect(page.getByText(NO_MARKET_DATA_TEXT)).not.toBeVisible();
  await expect(page.getByText(STALE_MARKET_TEXT)).not.toBeVisible();

  await page.getByRole("button", { name: "Use suggestion" }).click();
  // The lease defaults to monthly: 720 weekly -> round(720 * 52 / 12) = 3120.
  await expect(page.getByLabel("Rent", { exact: true })).toHaveValue("3120");

  // Editing the renewal start invalidates the card: it was computed for the
  // old date, and the (date-driven) law card could disagree with the new one.
  await page.getByLabel("Start").fill(isoDate(35));
  await expect(page.getByText("$720")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Use suggestion" })).not.toBeVisible();
});

test("no market data renders capped guidance instead of a market comparison", async ({
  page,
}) => {
  const renewUrl = await openRenewPage(page);
  await enableRentAi(page);
  await page.goto(renewUrl);

  await page.route("**/rent-suggestion", (route) =>
    route.fulfill({ json: CANNED_NO_DATA_SUGGESTION }),
  );
  await page.getByRole("button", { name: "Suggest rent" }).click();

  await expect(page.getByText("$675")).toBeVisible();
  await expect(page.getByText(NO_MARKET_DATA_TEXT)).toBeVisible();
});

test("stale market data renders a staleness warning alongside the comparison", async ({
  page,
}) => {
  const renewUrl = await openRenewPage(page);
  await enableRentAi(page);
  await page.goto(renewUrl);

  await page.route("**/rent-suggestion", (route) =>
    route.fulfill({ json: CANNED_STALE_SUGGESTION }),
  );
  await page.getByRole("button", { name: "Suggest rent" }).click();

  await expect(page.getByText("$645")).toBeVisible();
  await expect(page.getByText(STALE_MARKET_TEXT)).toBeVisible();
});

test("live: suggests a renewal rent from the real compliance service", async ({ page }) => {
  test.skip(!LIVE, "requires the local compliance service (set RENT_SUGGESTION_E2E=1)");
  const renewUrl = await openRenewPage(page);
  await enableRentAi(page);
  await page.goto(renewUrl);

  await page.getByRole("button", { name: "Suggest rent" }).click();

  await expect(page.getByRole("heading", { name: "Suggested rent" })).toBeVisible();
  await expect(page.getByText("General information, not legal advice.")).toBeVisible();
});
