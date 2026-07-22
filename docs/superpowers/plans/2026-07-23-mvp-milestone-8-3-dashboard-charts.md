# Milestone 8.3: Dashboard Occupancy and Maintenance Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The dashboard gains an occupancy-rate trend and a maintenance-status breakdown beside the existing monthly income chart.

**Architecture:** Occupancy is a pure function of data `dashboard_stats` already loads — it fetches every lease, and replacing its `count()` of properties with a fetch of `Property.created_at` yields both the total and the per-month denominators, so occupancy costs no extra query. Maintenance status adds one grouped query. Both charts reuse the existing Recharts setup.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, PostgreSQL, Next.js 16 App Router, Recharts, Playwright. **No migration** — no column and no table is added.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- Accessible names introduced: `Occupancy` and `Maintenance status`, both `Card` titles rendered as `<h2>`. **Playwright matches names by substring**, and the dashboard already shows a `Maintenance requests` stat card, so `getByText("Maintenance")` would match several nodes. Assertions must use the full card title or `exact: true`.
- Backend commands run from `backend/`, frontend commands from `frontend/`. The shell keeps its working directory between commands — always `cd` explicitly.
- Never pipe a Playwright failure through `tail`: a strict-mode violation prints its matched-element list *above* the "waiting for..." line, so tailing hides the actual cause.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/schemas/stats.py` | `OccupancyPoint`, `MaintenanceStatusCount`, two `DashboardStats` fields |
| `backend/app/services/stats.py` | pure `occupancy_series`; maintenance grouping; wire both in |
| `backend/tests/test_dashboard_charts.py` | the pure series and the maintenance counts |
| `backend/tests/test_stats_api.py` | payload shape |
| `frontend/src/lib/stats.ts` | the two new types |
| `frontend/src/app/app/page.tsx` | the two chart cards |
| `frontend/e2e/dashboard-charts.spec.ts` | both cards render |

---

### Task 1: Pure `occupancy_series`

**Files:**
- Modify: `backend/app/schemas/stats.py`, `backend/app/services/stats.py`
- Test: `backend/tests/test_dashboard_charts.py`

**Interfaces:**
- Produces: `OccupancyPoint(month: str, occupied: int, total: int, rate: float)` and
  `occupancy_series(leases, property_dates, months) -> list[OccupancyPoint]`, where `leases` is any
  iterable of objects with `property_id`, `start_date` and `end_date`; `property_dates` is a
  `list[date]` of property creation dates; `months` is a `list[date]` of first-of-month dates.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_dashboard_charts.py`:

```python
import uuid
from dataclasses import dataclass
from datetime import date

from app.services.stats import occupancy_series


@dataclass
class FakeLease:
    """Only the three fields occupancy_series reads."""

    property_id: uuid.UUID
    start_date: date
    end_date: date


MONTHS = [date(2026, m, 1) for m in (2, 3, 4, 5, 6, 7)]


def test_lease_covering_part_of_the_window_marks_only_those_months():
    prop = uuid.uuid4()
    leases = [FakeLease(prop, date(2026, 4, 10), date(2026, 5, 20))]

    series = occupancy_series(leases, [date(2026, 1, 1)], MONTHS)

    assert [(p.month, p.occupied) for p in series] == [
        ("2026-02", 0),
        ("2026-03", 0),
        ("2026-04", 1),
        ("2026-05", 1),
        ("2026-06", 0),
        ("2026-07", 0),
    ]
    assert all(p.total == 1 for p in series)


def test_property_created_mid_window_is_not_in_earlier_denominators():
    """The denominator must be the properties that existed then, not today's count.

    Every other test still passes if this is got wrong, so it needs its own.
    """
    series = occupancy_series([], [date(2026, 1, 1), date(2026, 6, 15)], MONTHS)

    assert [(p.month, p.total) for p in series] == [
        ("2026-02", 1),
        ("2026-03", 1),
        ("2026-04", 1),
        ("2026-05", 1),
        ("2026-06", 2),
        ("2026-07", 2),
    ]


def test_zero_properties_gives_zero_rate_not_a_crash():
    series = occupancy_series([], [], MONTHS)

    assert [p.rate for p in series] == [0.0] * 6
    assert [p.total for p in series] == [0] * 6


def test_rate_is_rounded_to_one_decimal_place():
    props = [date(2026, 1, 1)] * 7
    occupied = [
        FakeLease(uuid.uuid4(), date(2026, 1, 1), date(2026, 12, 31)) for _ in range(3)
    ]

    series = occupancy_series(occupied, props, MONTHS)

    # 3/7 is 42.857142857142854 unrounded, which is what a tooltip would print.
    assert series[0].rate == 42.9
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_dashboard_charts.py -v`
Expected: FAIL with `ImportError: cannot import name 'occupancy_series'`.

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/stats.py`, add above `DashboardStats`:

```python
class OccupancyPoint(BaseModel):
    month: str
    occupied: int
    total: int
    rate: float
```

- [ ] **Step 4: Implement the helper**

In `backend/app/services/stats.py`, add `OccupancyPoint` to the `app.schemas.stats` import and add
this above `dashboard_stats`:

```python
def _month_end(month_start: date) -> date:
    return month_start + relativedelta(months=1) - timedelta(days=1)


def occupancy_series(
    leases, property_dates: list[date], months: list[date]
) -> list[OccupancyPoint]:
    """Occupied share of the portfolio for each month.

    Numerator: distinct properties whose lease covers any part of the month, so a
    tenancy ending on the 3rd still counts for that month. Denominator: properties
    created on or before the month's end, not today's count -- buying property
    later would otherwise turn earlier months into a decline that never happened.
    """
    points = []
    for start in months:
        end = _month_end(start)
        total = sum(1 for created in property_dates if created <= end)
        occupied = len(
            {
                lease.property_id
                for lease in leases
                if lease.start_date <= end and start <= lease.end_date
            }
        )
        rate = round(occupied * 100 / total, 1) if total else 0.0
        points.append(
            OccupancyPoint(
                month=f"{start.year:04d}-{start.month:02d}",
                occupied=occupied,
                total=total,
                rate=rate,
            )
        )
    return points
```

Add `timedelta` to the `datetime` import at the top of the file:

```python
from datetime import date, timedelta
```

The overlap test is the same inclusive form `overlapping_lease_exists` uses in
`app/routers/leases.py`: two ranges overlap when each starts on or before the other ends.

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/test_dashboard_charts.py -v`
Expected: 4 passed.

- [ ] **Step 6: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 7: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/schemas/stats.py backend/app/services/stats.py backend/tests/test_dashboard_charts.py
git commit -m "Add the pure occupancy series helper"
git push origin main
```

Then report and wait for approval.

---

### Task 2: Maintenance counts, wired into `dashboard_stats`

**Files:**
- Modify: `backend/app/schemas/stats.py`, `backend/app/services/stats.py`
- Test: `backend/tests/test_dashboard_charts.py`, `backend/tests/test_stats_api.py`

**Interfaces:**
- Consumes: `occupancy_series` and `OccupancyPoint` (Task 1).
- Produces: `MaintenanceStatusCount(status: str, count: int)`; `DashboardStats.occupancy:
  list[OccupancyPoint]` and `DashboardStats.maintenance_by_status: list[MaintenanceStatusCount]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_dashboard_charts.py`. Add these imports at the top of the file
(ruff E402 keeps imports there):

```python
from datetime import timedelta

from app.services.stats import dashboard_stats
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers
from tests.test_stats import _org_id
```

```python
REQ = {"title": "Tap", "description": "Drips", "priority": "low"}


async def _report(client, tenant_headers, lease_id):
    return (
        await client.post(
            f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant_headers
        )
    ).json()["id"]


async def test_counts_every_status_including_the_empty_ones(client, db_session):
    email = "mstat@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    lease_id = await make_lease(client, headers, "1 Status St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mstat-t@example.com")
    first = await _report(client, tenant, lease_id)
    await _report(client, tenant, lease_id)
    await client.patch(
        f"/api/v1/maintenance/{first}", json={"status": "resolved"}, headers=headers
    )

    stats = await dashboard_stats(db_session, org_id, date.today())
    counts = {c.status: c.count for c in stats.maintenance_by_status}

    assert counts["open"] == 1
    assert counts["resolved"] == 1
    # Absent statuses report zero rather than vanishing, so the legend is stable.
    assert counts["in_progress"] == 0
    assert counts["cancelled"] == 0


async def test_requests_older_than_the_window_are_excluded(client, db_session):
    email = "mold@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    lease_id = await make_lease(client, headers, "1 Old St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mold-t@example.com")
    await _report(client, tenant, lease_id)

    # Seven months on, the same request has fallen out of the six-month window.
    future = date.today() + relativedelta(months=7)
    stats = await dashboard_stats(db_session, org_id, future)

    assert sum(c.count for c in stats.maintenance_by_status) == 0
```

Add `from dateutil.relativedelta import relativedelta` to the file's imports.

Append to `backend/tests/test_stats_api.py`:

```python
async def test_stats_payload_carries_both_chart_series(client):
    headers = await landlord_headers(client, "statscharts@example.com")

    body = (await client.get("/api/v1/stats", headers=headers)).json()

    assert len(body["occupancy"]) == 6
    assert {c["status"] for c in body["maintenance_by_status"]} == {
        "open",
        "in_progress",
        "resolved",
        "cancelled",
    }
    # Recharts cannot plot strings; the rate must arrive as a JSON number.
    assert isinstance(body["occupancy"][0]["rate"], (int, float))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_dashboard_charts.py tests/test_stats_api.py -v`
Expected: the three new tests FAIL — `DashboardStats` has no `maintenance_by_status`.

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/stats.py`, add above `DashboardStats`:

```python
class MaintenanceStatusCount(BaseModel):
    status: str
    count: int
```

and two fields at the end of `DashboardStats`:

```python
    occupancy: list[OccupancyPoint]
    maintenance_by_status: list[MaintenanceStatusCount]
```

- [ ] **Step 4: Add the grouped query**

In `backend/app/services/stats.py`, add `MaintenanceStatusCount` to the `app.schemas.stats` import
and add above `dashboard_stats`:

```python
async def _maintenance_by_status(
    session: AsyncSession, organization_id, since: date
) -> list[MaintenanceStatusCount]:
    """Requests raised since the given date, counted per status.

    Statuses with no requests are reported as zero so the chart legend does not
    appear and disappear between loads.
    """
    result = await session.execute(
        select(MaintenanceRequest.status, func.count())
        .where(
            MaintenanceRequest.organization_id == organization_id,
            MaintenanceRequest.created_at >= since,
        )
        .group_by(MaintenanceRequest.status)
    )
    counts = {status: count for status, count in result.all()}
    return [
        MaintenanceStatusCount(status=status.value, count=counts.get(status, 0))
        for status in MaintenanceStatus
    ]
```

- [ ] **Step 5: Wire both into `dashboard_stats`**

In `backend/app/services/stats.py`, replace the `properties_total` block:

```python
    properties_total = await _count(
        session,
        select(func.count())
        .select_from(Property)
        .where(Property.organization_id == organization_id),
    )
```

with a fetch of the creation dates, which serves as both the count and the per-month denominators:

```python
    # created_at rather than a count(): the same rows give both the total and
    # each month's denominator, so the occupancy series costs no extra query.
    property_dates = [
        created.date()
        for (created,) in (
            await session.execute(
                select(Property.created_at).where(Property.organization_id == organization_id)
            )
        ).all()
    ]
    properties_total = len(property_dates)
```

and add the two fields to the returned `DashboardStats`, after `monthly_income`:

```python
        occupancy=occupancy_series(leases, property_dates, months),
        maintenance_by_status=await _maintenance_by_status(session, organization_id, months[0]),
```

with `months` computed once near the top of `dashboard_stats`:

```python
    months = _window_months(today)
```

Both charts must span the same months as the income chart, so extract the month list that
`_monthly_income` builds inline into a shared helper, placed above `_monthly_income`:

```python
def _window_months(today: date) -> list[date]:
    """The first of each of the last six months, oldest first."""
    return [today.replace(day=1) - relativedelta(months=i) for i in range(5, -1, -1)]
```

and change `_monthly_income`'s first line to use it:

```python
    months = _window_months(today)
```

One definition of the window, so the three charts cannot drift apart.

- [ ] **Step 6: Run the tests**

Run: `cd backend && uv run pytest tests/test_dashboard_charts.py tests/test_stats_api.py -v`
Expected: all pass.

- [ ] **Step 7: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass. `test_stats.py` and `test_stats_api.py` are the guard that
`properties_total` still reports the same number after switching from `count()` to `len()`.

- [ ] **Step 8: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 9: Commit and push**

```bash
git add backend/app/schemas/stats.py backend/app/services/stats.py backend/tests/test_dashboard_charts.py backend/tests/test_stats_api.py
git commit -m "Add occupancy and maintenance-status series to the dashboard stats"
git push origin main
```

Then report and wait for approval.

---

### Task 3: The two charts

**Files:**
- Modify: `frontend/src/lib/stats.ts`, `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: `DashboardStats.occupancy` and `.maintenance_by_status` (Task 2).
- Produces: the accessible names `Occupancy` and `Maintenance status`.

- [ ] **Step 1: Add the types**

In `frontend/src/lib/stats.ts`, add above `DashboardStats`:

```ts
export interface OccupancyPoint {
  month: string;
  occupied: number;
  total: number;
  rate: number;
}

export interface MaintenanceStatusCount {
  status: string;
  count: number;
}
```

and two fields at the end of the `DashboardStats` interface:

```ts
  occupancy: OccupancyPoint[];
  maintenance_by_status: MaintenanceStatusCount[];
}
```

- [ ] **Step 2: Extend the Recharts import**

In `frontend/src/app/app/page.tsx`, replace the existing recharts import line:

```tsx
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
```

with:

```tsx
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
```

- [ ] **Step 3: Add the shared chart styling constant**

In `frontend/src/app/app/page.tsx`, above the component, add:

```tsx
// Tokens, never hex: Recharts' own hardcoded #ccc was already caught glowing on
// a dark card, and any literal colour here would repeat that.
const TOOLTIP_STYLE = {
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: 12,
  color: "var(--ink)",
};

const STATUS_FILL: Record<string, string> = {
  open: "var(--brand)",
  in_progress: "var(--warning)",
  resolved: "var(--success)",
  cancelled: "var(--line-strong)",
};
```

- [ ] **Step 4: Add the two cards**

In `frontend/src/app/app/page.tsx`, immediately after the closing `</Card>` of the
`Monthly income` card, add:

```tsx
              <Card title="Occupancy" className="mt-5">
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={stats.occupancy}>
                    <XAxis dataKey="month" stroke="var(--ink-muted)" fontSize={12} />
                    {/* Fixed 0-100: left to auto-scale, a drift from 95% to 92%
                        is stretched into a cliff, which is the chart lying. */}
                    <YAxis
                      domain={[0, 100]}
                      unit="%"
                      stroke="var(--ink-muted)"
                      fontSize={12}
                    />
                    <Tooltip
                      cursor={{ stroke: "var(--surface-2)" }}
                      contentStyle={TOOLTIP_STYLE}
                      formatter={(value, _name, entry) =>
                        `${value}% (${entry.payload.occupied} of ${entry.payload.total})`
                      }
                    />
                    <Line
                      type="monotone"
                      dataKey="rate"
                      stroke="var(--brand)"
                      strokeWidth={2}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Maintenance status" className="mt-5">
                {stats.maintenance_by_status.every((s) => s.count === 0) ? (
                  <EmptyState>No maintenance requests yet.</EmptyState>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <PieChart>
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Pie
                        data={stats.maintenance_by_status}
                        dataKey="count"
                        nameKey="status"
                        innerRadius={55}
                        outerRadius={90}
                        isAnimationActive={false}
                      >
                        {stats.maintenance_by_status.map((s) => (
                          <Cell key={s.status} fill={STATUS_FILL[s.status]} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </Card>
```

A donut of all-zero slices renders as nothing at all rather than an error, which reads as a broken
card — hence the explicit empty state. `EmptyState` is already imported on this page.

- [ ] **Step 5: Lint, typecheck and build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: both clean. `npm run build` runs the TypeScript check.

- [ ] **Step 6: Check both charts by hand, in both themes**

The backend must be running. Sign in as a landlord and open `/app`. A fresh account shows a flat
0% occupancy line and the maintenance empty state. Then confirm with real data — create a property
and a lease covering today, reload, and the occupancy line should rise to 100 for the current
month. Toggle dark mode and confirm neither chart shows a light slab or an invisible line; that is
the failure the token rule exists to prevent.

**Also hover the occupancy line and check the tooltip actually renders.** Recharts has changed the
`formatter` callback's arguments between versions, so `entry.payload` carrying `occupied` and
`total` is an assumption, not a verified fact. If the tooltip is blank or throws, read the
installed version's signature under `node_modules/recharts` and adjust; the fallback is to drop
the formatter and show the bare percentage.

- [ ] **Step 7: Commit and push**

```bash
git add frontend/src/lib/stats.ts frontend/src/app/app/page.tsx
git commit -m "Add occupancy and maintenance status charts to the dashboard"
git push origin main
```

Then report and wait for approval.

---

### Task 4: End-to-end coverage

**Files:**
- Create: `frontend/e2e/dashboard-charts.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-3.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/dashboard-charts.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const email = `charts-${Date.now()}@example.com`;

// Card titles only. Chart internals are SVG, and asserting path coordinates
// would be brittle without being more convincing; the numbers are covered by
// backend/tests/test_dashboard_charts.py.
test("landlord sees the occupancy and maintenance charts", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Charts Landlord");
  await page.getByPlaceholder("Organization name").fill("Charts Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await expect(page.getByRole("heading", { name: "Monthly income" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Occupancy" })).toBeVisible();
  // exact: true — the dashboard also has a "Maintenance requests" stat card, and
  // Playwright matches names by substring.
  await expect(
    page.getByRole("heading", { name: "Maintenance status", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("No maintenance requests yet.")).toBeVisible();
});
```

- [ ] **Step 2: Restart the backend so the new payload is served**

The e2e hits a live backend. If it was started before Task 2, `/api/v1/stats` has no `occupancy`
field, the dashboard renders an empty chart, and this spec would still pass on the card titles
alone — passing for the wrong reason.

- [ ] **Step 3: Run the new spec**

Run: `cd frontend && npx playwright test dashboard-charts`
Expected: 1 passed.

- [ ] **Step 4: Run the whole e2e suite**

Run: `cd frontend && npx playwright test --workers=1`
Expected: all pass (28 existing plus this one). Use `--workers=1` to match CI.

- [ ] **Step 5: Full backend test run and ruff sequence**

```bash
cd backend
uv run pytest
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 6: Commit and push**

```bash
git add frontend/e2e/dashboard-charts.spec.ts
git commit -m "Add dashboard charts e2e"
git push origin main
```

- [ ] **Step 7: Confirm CI is green**

Run: `gh run list --limit 3`
Expected: the newest run for `main` succeeds. If it fails, read the log before changing anything — the failure is evidence, not noise.

Then report and wait for approval.
