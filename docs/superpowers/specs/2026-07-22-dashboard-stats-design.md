# Milestone 4.3: Dashboard Stats + Charts — Design

**Date:** 2026-07-22
**Status:** Approved (pending spec review)
**Part of:** Milestone 4 (rent charges -> payments+balances -> dashboard stats). Sub-project 3 of 3 — completes Milestone 4.

## Goal

The landlord/PM dashboard shows an at-a-glance summary of the organization: money owed and
collected, portfolio counts, and a 6-month income chart — all derived from the existing charges
and payments.

## Architecture

- A pure-ish service `dashboard_stats(session, organization_id, today)` computes every figure,
  reusing `lease_balance` (M4.2) for outstanding/overdue and plain aggregate queries for the
  rest. One read endpoint returns them together.
- The frontend fetches the stats once and renders stat cards plus a Recharts bar chart of
  monthly income. No new persistence — everything is aggregated on read.

## Tech Stack

- Backend: FastAPI, async SQLAlchemy 2.0, PostgreSQL (existing). No migration (no new models).
  Reuses `python-dateutil` (already a dependency) for month stepping.
- Frontend: Next.js + **Recharts** (new dependency, React-19-compatible 3.x).

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- No migration this milestone. Current head stays `4f6bf92b0607`.

---

## Metrics (all org-scoped, manager-only, computed on read)

`today = datetime.now(UTC).date()`; `organization_id` from the caller's membership.

- **outstanding** — sum over the org's leases of `lease_balance(lease).outstanding` (M4.2
  waterfall, per lease, summed).
- **overdue** — same, summing `overdue_amount`.
- **collected_this_month** — `sum(Payment.amount)` for the org where
  `paid_on >= today.replace(day=1)` (coalesced to 0).
- **properties_total** — count of the org's properties.
- **properties_occupied** — count of distinct `property_id` among the org's leases that are
  active today (`start_date <= today <= end_date`).
- **active_leases** — count of the org's leases active today.
- **tenants** — count of `Membership` rows in the org with `role == tenant`.
- **monthly_income** — the last 6 calendar months including the current one, each
  `{month: "YYYY-MM", amount: Decimal}`, from summing `Payment.amount` bucketed by month
  (missing months filled with 0). Month keys built by stepping back with
  `relativedelta(months=i)` from `today.replace(day=1)`.

Iterating the org's leases and calling `lease_balance` per lease is O(leases) queries — fine for
a dashboard; acceptable for the current scale.

## Service

New file `app/services/stats.py`:

```python
async def dashboard_stats(session: AsyncSession, organization_id, today: date) -> DashboardStats:
    """Aggregate the organization's money and portfolio figures for the dashboard."""
```

Helpers: `_collected_since(session, org_id, since) -> Decimal`,
`_monthly_income(session, org_id, today) -> list[MonthlyIncome]`,
`_count(session, stmt) -> int`. Reuses `lease_balance` from `app.services.payments`.

## Schema

New file `app/schemas/stats.py`:

```python
class MonthlyIncome(BaseModel):
    month: str          # "YYYY-MM"
    amount: Decimal


class DashboardStats(BaseModel):
    outstanding: Decimal
    overdue: Decimal
    collected_this_month: Decimal
    properties_total: int
    properties_occupied: int
    active_leases: int
    tenants: int
    monthly_income: list[MonthlyIncome]
```

## Endpoint

New file `app/routers/stats.py`:
`GET /api/v1/stats` (dep `manager = require_roles(landlord, property_manager)`) ->
`DashboardStats`, for the caller's organization. Mount `stats_router` in `app/main.py`.

## Frontend

- **Dependency:** `npm install recharts` (3.x, React 19 compatible).
- `frontend/src/lib/stats.ts`: `MonthlyIncome`, `DashboardStats` types; `getDashboardStats()` ->
  `GET /api/v1/stats`.
- **Manager dashboard** (`app/page.tsx`, the non-tenant branch): fetch stats in the effect;
  render a grid of stat cards — **Outstanding**, **Overdue**, **Collected this month**,
  **Properties** (`{occupied} of {total} occupied`), **Active leases**, **Tenants** — above a
  **"Monthly income"** Recharts `BarChart` (last 6 months). Keep the existing nav links below.
  A small `StatCard` helper renders label + value.

Recharts usage (inside the already-`"use client"` dashboard):

```tsx
<ResponsiveContainer width="100%" height={240}>
  <BarChart data={stats.monthly_income}>
    <XAxis dataKey="month" />
    <YAxis />
    <Tooltip />
    <Bar dataKey="amount" fill="#2563eb" />
  </BarChart>
</ResponsiveContainer>
```

**Build-compatibility fallback:** if `npm run build` fails because Recharts is incompatible with
Next 16 / React 19, replace the chart with a hand-rolled SVG bar chart (same data, same
"Monthly income" heading) and drop the dependency. The plan makes this a checkpoint.

## Testing

**Backend (pytest, primary):** in `tests/test_stats.py`, build one org with a property, an
active lease, a past-due charge, and a payment, then assert:

- `collected_this_month` equals the payment sum for the current month; a payment dated in a
  prior month is excluded.
- `outstanding` / `overdue` match `summarize` for the seeded charges/payments.
- `properties_total`, `properties_occupied`, `active_leases`, `tenants` counts are correct.
- `monthly_income` has exactly 6 entries ending at the current month, with the seeded payment in
  the right bucket and other months 0.
- Org isolation: a second org's data does not affect the first; a fresh org returns all zeros
  and six 0-valued months.
- `GET /api/v1/stats` requires auth (401) and manager role.

**Frontend:** `npm run lint` + `npm run build` — **the build must confirm Recharts compiles under
Next 16 / React 19** (else take the SVG fallback). e2e (light): after a landlord logs in, the
dashboard shows the **Outstanding** card and the **Monthly income** heading.

## Out of Scope (M4.3 / later)

- CSV/PDF export, custom date-range filters, per-property breakdowns, an overdue-tenant drilldown
  list, multi-currency, caching/materialized aggregates.

## File Structure

- Create: `backend/app/services/stats.py`
- Create: `backend/app/schemas/stats.py`
- Create: `backend/app/routers/stats.py`
- Modify: `backend/app/main.py` (mount stats router)
- Create: `backend/tests/test_stats.py`
- Modify: `frontend/package.json` (recharts)
- Create: `frontend/src/lib/stats.ts`
- Modify: `frontend/src/app/app/page.tsx` (manager dashboard: cards + chart)
- Modify: `frontend/e2e/` (assert a stat card + chart heading on the dashboard)
