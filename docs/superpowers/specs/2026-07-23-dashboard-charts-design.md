# Milestone 8.3: Dashboard Occupancy and Maintenance Charts — Design

**Date:** 2026-07-23
**Status:** Approved (pending spec review)

**Part of:** Milestone 8, sub-project 3 of 3. M8.1 (contractor assignment) and M8.2 (rent overdue
and upcoming views) are complete. This finishes the Phase 1 MVP dashboard.

## Goal

The dashboard gains two charts beside the existing monthly income one: occupancy rate over the
last six months, and the status breakdown of maintenance requests raised in the same window.

## Architecture

- **Occupancy is a pure function of data `dashboard_stats` already loads.** It fetches every lease
  for the organization, and it already queries the properties table for a count. Replacing that
  `count()` with a fetch of `Property.created_at` yields both the total and the per-month
  denominators, so occupancy costs **no extra query at all**.
- The month-bucketing lives in a pure `occupancy_series(...)` with no session argument, matching
  how `allocate`, `summarize` and `_bucket` are pure and separately tested in this codebase.
- Maintenance status adds **one** grouped query.
- Rejected: a monthly snapshot table written by a scheduled job. It would survive retroactive
  edits to lease dates, but costs a model, a migration and a job for a benefit nothing has asked
  for. Also rejected: computing the series in SQL with `generate_series`, which would put a second
  copy of the month-window logic beside the one `_monthly_income` already has in Python.

## Tech Stack

- Backend: FastAPI, async SQLAlchemy 2.0, PostgreSQL (existing). **No migration.**
- Frontend: Next.js, Recharts (both existing). No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- Accessible names introduced: `Occupancy` and `Maintenance status` (card titles, rendered as
  `<h2>` by `Card`). Playwright matches names by **substring**: `Maintenance status` must not be
  reached by a bare `Maintenance` locator elsewhere, and the dashboard already contains a
  `Maintenance requests` stat card, so any new assertion needs `exact: true` or a distinct string.

---

## Product Rules (confirmed)

- **Occupancy is a six-month trend**, matching the monthly income chart's window, not a snapshot.
  The dashboard already answers "how are we now" with a stat card; a chart earns its space only by
  answering "is it getting better or worse".
- **The denominator is properties that existed in that month**, not today's total. Buying three
  properties last month would otherwise make five months of history look like a decline that never
  happened.
- **A property counts from the earlier of its row's creation and its first lease's start.**
  `Property.created_at` alone is wrong: a landlord joining today records tenancies that began long
  before, so the lease put the property in the numerator while the creation date kept it out of
  the denominator — producing `1 of 0` and a flat 0% for every month before they signed up. This
  was found by driving the real UI after the first implementation passed all six unit tests, none
  of which paired a backdated lease with a freshly created property.
- **Zero properties gives `rate = 0`**, not a crash and not `NaN`.
- **`rate` is rounded to one decimal place.** Three of seven properties is 42.857142857142854
  unrounded, and that is what a tooltip would print. Rounding belongs in the service, not in each
  place that displays the number.
- **A lease covering any part of a month makes that property occupied for the month.** A tenancy
  that ends on the 3rd still counts for that month; the alternative rules (whole month, or the
  month's midpoint) are no more correct and harder to explain.
- **Maintenance counts requests created in the last six months**, across all four statuses.
  All-time would let `resolved` grow until it flattens everything else; open-only would duplicate
  the existing stat card.

---

## Backend

**Pure helper (`backend/app/services/stats.py`):**

```python
def occupancy_series(
    leases: list[Lease], property_dates: list[date], months: list[date]
) -> list[OccupancyPoint]:
    """Occupied share per month.

    Numerator: distinct properties with a lease covering any part of the month.
    Denominator: properties created on or before the month's end.
    """
```

No session argument, so it is testable without a database — the same shape as `allocate` and
`_bucket`.

**Maintenance counts:** one query, `select(MaintenanceRequest.status, func.count()).where(
organization_id, created_at >= window_start).group_by(status)`. Statuses absent from the result
still appear with a count of zero, so the chart legend is stable rather than appearing and
disappearing.

**Schemas (`backend/app/schemas/stats.py`):**

```python
class OccupancyPoint(BaseModel):
    month: str      # "2026-07"
    occupied: int
    total: int
    rate: float     # 0-100, ready to display


class MaintenanceStatusCount(BaseModel):
    status: str
    count: int
```

`DashboardStats` gains `occupancy: list[OccupancyPoint]` and
`maintenance_by_status: list[MaintenanceStatusCount]`. The endpoint and its dependency are
unchanged; only the payload grows.

The month list is built the way `_monthly_income` already builds it (`today.replace(day=1) -
relativedelta(months=i)` for `i` in `5..0`), so both charts always span the same six months.

---

## Frontend (`frontend/src/app/app/page.tsx`)

Two `Card`s beside the existing `Monthly income`:

- **`Occupancy`** — a Recharts `LineChart`. A rate over time reads as a line; a second bar chart
  next to the income one would blur into it. **The Y axis is fixed to `domain={[0, 100]}`**: left
  to auto-scale, a drift from 95% to 92% is stretched into a cliff, which is the chart lying.
  The tooltip shows "3 of 5 occupied" as well as the percentage.
- **`Maintenance status`** — a `PieChart` with an `innerRadius` donut. Four statuses are parts of
  a whole, and the shape distinguishes it from the bar chart. When every count is zero the card
  shows `No maintenance requests yet.` instead of an empty ring.

Both charts set `isAnimationActive={false}`: under React StrictMode the entry animation can leave
the shapes stranded at their initial state, which this project has already hit once.

Slice and line colours come from the existing CSS variables (`--brand`, `--warning`, `--success`,
`--line-strong`), never hardcoded hex. Recharts' own hardcoded `#ccc` was already caught doing
exactly this in dark mode.

The occupancy chart with zero properties draws a flat 0% line. That is honest and stays.

---

## Testing

Backend (`backend/tests/test_dashboard_charts.py` unless noted):

1. A lease covering only part of the window makes only those months occupied.
2. **A property created mid-window is excluded from earlier months' denominators.** This is the
   rule most easily got wrong, and every other test still passes if the denominator quietly uses
   today's total — so it needs its own test.
3. Zero properties gives `rate == 0` for every month, with no exception and no `NaN`.
4. Each maintenance status is counted correctly, and a status with no requests reports zero rather
   than being absent.
5. A request created seven months ago is excluded; one created inside the window is included.
6. `GET /api/v1/stats` returns six occupancy points and four status counts
   (`backend/tests/test_stats_api.py`).

e2e (`frontend/e2e/dashboard-charts.spec.ts`): a landlord sees both card titles on the dashboard.
Chart internals are SVG; the e2e does not assert path coordinates. Numerical correctness is tests
1-6's job, and an e2e that scraped chart geometry would be brittle without being more convincing.

---

## Out of Scope

- Occupancy or maintenance history beyond six months, and any date-range picker.
- Per-property occupancy breakdown.
- A snapshot table recording occupancy as it was, independent of later lease edits.
- Exporting or printing charts.
- Charts for the tenant portal; these are org-wide manager views.

---

## File Structure

| File | Change |
|---|---|
| `backend/app/schemas/stats.py` | `OccupancyPoint`, `MaintenanceStatusCount`, two `DashboardStats` fields |
| `backend/app/services/stats.py` | pure `occupancy_series`; maintenance grouping; wire both in |
| `backend/tests/test_dashboard_charts.py` | new |
| `backend/tests/test_stats_api.py` | payload shape |
| `frontend/src/lib/stats.ts` | the two new types |
| `frontend/src/app/app/page.tsx` | the two cards |
| `frontend/e2e/dashboard-charts.spec.ts` | new |

## Task Breakdown

- **T1** pure `occupancy_series` + tests 1-3
- **T2** maintenance counts + schemas + wired into `dashboard_stats` + tests 4-6
- **T3** frontend: the two charts
- **T4** e2e + CI green
