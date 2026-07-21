# Milestone 4.3: Dashboard Stats + Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The landlord/PM dashboard shows org-wide money and portfolio stat cards plus a 6-month income bar chart, all aggregated from existing charges and payments.

**Architecture:** A `dashboard_stats(session, organization_id, today)` service computes every figure (reusing `lease_balance` for outstanding/overdue), exposed by one `GET /api/v1/stats` endpoint. The dashboard fetches it once and renders stat cards + a Recharts bar chart. No new persistence, no migration.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, PostgreSQL, python-dateutil (existing); Next.js + Recharts (new).

## Global Constraints

- Package manager: `uv` only (`uv run ...`, `uv add ...`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before EVERY push, from `backend/`, in order:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- **Ruff gotcha:** test files keep ALL imports at the top (E402).
- Each task ends with: full test run -> ruff sequence -> commit -> `git push` (CI) -> report -> WAIT for approval.
- **No migration this milestone** (no new models); head stays `4f6bf92b0607`.
- Backend tests: `cd backend && uv run pytest -q`. Frontend: `npm run lint`, `npm run build`, e2e `npx playwright test` from `frontend/`.
- Restart the e2e backend after new endpoints: `lsof -ti tcp:8000 | xargs kill` then `uv run uvicorn app.main:app --port 8000`.

---

## Task Overview

1. `DashboardStats` schema + `dashboard_stats` service
2. `GET /api/v1/stats` endpoint
3. Frontend: Recharts + stats lib + dashboard cards & chart (build-compat checkpoint)
4. e2e + CI green

---

### Task 1: Schema + `dashboard_stats` service

**Files:**
- Create: `backend/app/schemas/stats.py`
- Create: `backend/app/services/stats.py`
- Test: `backend/tests/test_stats.py`

**Interfaces:**
- Consumes: `lease_balance` from `app.services.payments`; models `Lease`, `Membership`, `Payment`, `Property`, `Role`.
- Produces: `MonthlyIncome{month: str, amount: Decimal}`, `DashboardStats{...}` in `app.schemas.stats`; `async dashboard_stats(session, organization_id, today: date) -> DashboardStats` in `app.services.stats`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_stats.py`:

```python
import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.models import Charge, Membership, Property, User
from app.services.stats import dashboard_stats
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _org_id(db_session, email):
    return (
        await db_session.execute(
            select(Membership.organization_id)
            .join(User, User.id == Membership.user_id)
            .where(User.email == email)
        )
    ).scalar_one()


async def test_dashboard_stats(client, db_session):
    email = "stats1@example.com"
    headers = await landlord_headers(client, email)
    property_id = await make_property(client, headers)
    today = date.today()
    lease = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=30)),
                rent_amount=1000,
            ),
            headers=headers,
        )
    ).json()
    org_id = await _org_id(db_session, email)

    # A past-due charge of 1000, and a payment of 300 made today.
    db_session.add(
        Charge(
            organization_id=org_id,
            lease_id=uuid.UUID(lease["id"]),
            period_start=date(2020, 1, 1),
            period_end=date(2020, 1, 31),
            due_date=date(2020, 1, 1),
            amount_due=1000,
        )
    )
    await db_session.commit()
    await client.post(
        f"/api/v1/leases/{lease['id']}/payments",
        json={"amount": 300, "paid_on": str(today), "method": "cash", "note": None},
        headers=headers,
    )

    stats = await dashboard_stats(db_session, org_id, today)

    assert float(stats.collected_this_month) == 300.0
    assert float(stats.outstanding) == 700.0
    assert float(stats.overdue) == 700.0
    assert stats.properties_total == 1
    assert stats.properties_occupied == 1
    assert stats.active_leases == 1
    assert stats.tenants == 0
    assert len(stats.monthly_income) == 6
    assert stats.monthly_income[-1].month == f"{today.year:04d}-{today.month:02d}"
    assert float(stats.monthly_income[-1].amount) == 300.0


async def test_empty_org_zeros(client, db_session):
    email = "statsempty@example.com"
    await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)

    stats = await dashboard_stats(db_session, org_id, date.today())

    assert float(stats.outstanding) == 0.0
    assert float(stats.overdue) == 0.0
    assert float(stats.collected_this_month) == 0.0
    assert stats.properties_total == 0
    assert stats.properties_occupied == 0
    assert stats.active_leases == 0
    assert stats.tenants == 0
    assert len(stats.monthly_income) == 6
    assert all(float(m.amount) == 0.0 for m in stats.monthly_income)


async def test_stats_org_isolation(client, db_session):
    a_email = "statsa@example.com"
    a_headers = await landlord_headers(client, a_email)
    a_property = await make_property(client, a_headers)
    today = date.today()
    a_lease = (
        await client.post(
            f"/api/v1/properties/{a_property}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)), end_date=str(today + timedelta(days=30))
            ),
            headers=a_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/leases/{a_lease['id']}/payments",
        json={"amount": 500, "paid_on": str(today), "method": "cash", "note": None},
        headers=a_headers,
    )

    await landlord_headers(client, "statsb@example.com")
    b_org = await _org_id(db_session, "statsb@example.com")

    stats = await dashboard_stats(db_session, b_org, today)
    assert float(stats.collected_this_month) == 0.0
    assert stats.properties_total == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_stats.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.stats'`.

- [ ] **Step 3: Create the schema**

Create `backend/app/schemas/stats.py`:

```python
from decimal import Decimal

from pydantic import BaseModel


class MonthlyIncome(BaseModel):
    month: str
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

- [ ] **Step 4: Create the service**

Create `backend/app/services/stats.py`:

```python
from collections import defaultdict
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lease, Membership, Payment, Property, Role
from app.schemas.stats import DashboardStats, MonthlyIncome
from app.services.payments import lease_balance


async def _count(session: AsyncSession, stmt) -> int:
    return (await session.execute(stmt)).scalar_one()


async def _collected_since(session: AsyncSession, organization_id, since: date) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.organization_id == organization_id, Payment.paid_on >= since
        )
    )
    return Decimal(result.scalar_one())


async def _monthly_income(
    session: AsyncSession, organization_id, today: date
) -> list[MonthlyIncome]:
    months = [today.replace(day=1) - relativedelta(months=i) for i in range(5, -1, -1)]
    result = await session.execute(
        select(Payment.paid_on, Payment.amount).where(
            Payment.organization_id == organization_id, Payment.paid_on >= months[0]
        )
    )
    buckets: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
    for paid_on, amount in result.all():
        buckets[(paid_on.year, paid_on.month)] += amount
    return [
        MonthlyIncome(month=f"{d.year:04d}-{d.month:02d}", amount=buckets[(d.year, d.month)])
        for d in months
    ]


async def dashboard_stats(
    session: AsyncSession, organization_id, today: date
) -> DashboardStats:
    """Aggregate the organization's money and portfolio figures for the dashboard."""
    leases = (
        (await session.execute(select(Lease).where(Lease.organization_id == organization_id)))
        .scalars()
        .all()
    )
    outstanding = Decimal("0")
    overdue = Decimal("0")
    for lease in leases:
        balance = await lease_balance(session, lease.id, today)
        outstanding += balance.outstanding
        overdue += balance.overdue_amount

    active = [lease for lease in leases if lease.start_date <= today <= lease.end_date]
    properties_total = await _count(
        session,
        select(func.count()).select_from(Property).where(Property.organization_id == organization_id),
    )
    tenants = await _count(
        session,
        select(func.count())
        .select_from(Membership)
        .where(Membership.organization_id == organization_id, Membership.role == Role.tenant),
    )
    return DashboardStats(
        outstanding=outstanding,
        overdue=overdue,
        collected_this_month=await _collected_since(session, organization_id, today.replace(day=1)),
        properties_total=properties_total,
        properties_occupied=len({lease.property_id for lease in active}),
        active_leases=len(active),
        tenants=tenants,
        monthly_income=await _monthly_income(session, organization_id, today),
    )
```

- [ ] **Step 5: Run to verify they pass**

Run: `cd backend && uv run pytest tests/test_stats.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/schemas/stats.py backend/app/services/stats.py backend/tests/test_stats.py
git commit -m "Add dashboard stats aggregation service"
git push
```
Then report and wait for approval.

---

### Task 2: `GET /api/v1/stats` endpoint

**Files:**
- Create: `backend/app/routers/stats.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_stats_api.py`

**Interfaces:**
- Consumes: `dashboard_stats` (Task 1); `manager` from `app.routers.leases`.
- Produces: `GET /api/v1/stats -> DashboardStats`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_stats_api.py`:

```python
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def test_stats_endpoint(client):
    headers = await landlord_headers(client, "statsapi@example.com")
    response = await client.get("/api/v1/stats", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["properties_total"] == 0
    assert len(body["monthly_income"]) == 6


async def test_stats_requires_auth(client):
    response = await client.get("/api/v1/stats")
    assert response.status_code == 401


async def test_stats_forbidden_for_tenant(client, db_session):
    headers = await landlord_headers(client, "statsttl@example.com")
    lease_id = await make_lease(client, headers, "Stats St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "statst@example.com")
    response = await client.get("/api/v1/stats", headers=tenant)
    assert response.status_code == 403
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_stats_api.py -q`
Expected: FAIL — route missing (`test_stats_endpoint` gets 404; `test_stats_requires_auth` gets 404 not 401).

- [ ] **Step 3: Create the router**

Create `backend/app/routers/stats.py`:

```python
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Membership
from app.routers.leases import manager
from app.schemas.stats import DashboardStats
from app.services.stats import dashboard_stats

router = APIRouter(prefix="/api/v1", tags=["stats"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> DashboardStats:
    """Dashboard aggregates for the caller's organization."""
    return await dashboard_stats(session, membership.organization_id, datetime.now(UTC).date())
```

- [ ] **Step 4: Mount the router**

Edit `backend/app/main.py`: add `from app.routers.stats import router as stats_router` with the
other router imports, and `app.include_router(stats_router)` after the other `include_router`
calls.

- [ ] **Step 5: Run to verify they pass + full suite + ruff**

```bash
cd backend && uv run pytest tests/test_stats_api.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 6: Commit and push**

```bash
git add backend/app/routers/stats.py backend/app/main.py backend/tests/test_stats_api.py
git commit -m "Add GET /stats dashboard endpoint"
git push
```
Then report and wait for approval.

---

### Task 3: Frontend — Recharts + stats lib + dashboard cards & chart

**Files:**
- Modify: `frontend/package.json` (recharts)
- Create: `frontend/src/lib/stats.ts`
- Modify: `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/stats` (Task 2).
- Produces: `DashboardStats`, `MonthlyIncome`, `getDashboardStats()` in `@/lib/stats`.

- [ ] **Step 1: Install Recharts**

Run from `frontend/`: `npm install recharts`
Expected: `recharts` added to `package.json` dependencies (3.x) and `package-lock.json` updated.

- [ ] **Step 2: Create the stats lib**

Create `frontend/src/lib/stats.ts`:

```typescript
import { apiFetch } from "@/lib/api";

export interface MonthlyIncome {
  month: string;
  amount: number;
}

export interface DashboardStats {
  outstanding: number;
  overdue: number;
  collected_this_month: number;
  properties_total: number;
  properties_occupied: number;
  active_leases: number;
  tenants: number;
  monthly_income: MonthlyIncome[];
}

export function getDashboardStats() {
  return apiFetch<DashboardStats>("/api/v1/stats");
}
```

- [ ] **Step 3: Wire stats into the dashboard**

Edit `frontend/src/app/app/page.tsx`.

Add imports (with the other imports):

```tsx
import { getDashboardStats, type DashboardStats } from "@/lib/stats";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
```

Add a `StatCard` helper near the top of the file (after the imports, before `DashboardPage`):

```tsx
function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-lg font-semibold text-gray-800">{value}</p>
    </div>
  );
}
```

Add stats state (next to `me`):

```tsx
  const [stats, setStats] = useState<DashboardStats | null>(null);
```

In the effect, after the `if (m.role === "tenant") { ... }` block (which `return`s the tenant
fetch), add a non-tenant fetch so it becomes:

```tsx
        if (m.role === "tenant") {
          return listMyLeases().then(async (l) => {
            if (!active) return;
            setMyLeases(l);
            const entries = await Promise.all(
              l.map((lease) =>
                listMyLeaseCharges(lease.id)
                  .then((c) => [lease.id, c] as const)
                  .catch(() => [lease.id, []] as const),
              ),
            );
            if (active) setChargesByLease(Object.fromEntries(entries));
          });
        }
        return getDashboardStats()
          .then((s) => {
            if (active) setStats(s);
          })
          .catch(() => {
            if (active) setStats(null);
          });
```

(The stats fetch has its own `.catch` so a stats error never triggers the outer auth-failure
logout.)

- [ ] **Step 4: Render cards + chart in the manager branch**

In the non-tenant `return (...)`, insert between the welcome `<p data-testid="welcome">...</p>`
and the nav-links `<div className="mt-4 flex gap-3">`:

```tsx
      {stats && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard label="Outstanding" value={`$${stats.outstanding}`} />
            <StatCard label="Overdue" value={`$${stats.overdue}`} />
            <StatCard label="Collected this month" value={`$${stats.collected_this_month}`} />
            <StatCard
              label="Properties"
              value={`${stats.properties_occupied} of ${stats.properties_total} occupied`}
            />
            <StatCard label="Active leases" value={String(stats.active_leases)} />
            <StatCard label="Tenants" value={String(stats.tenants)} />
          </div>
          <h2 className="mb-2 mt-6 font-semibold">Monthly income</h2>
          <div className="mb-2">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={stats.monthly_income}>
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="amount" fill="#2563eb" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
```

- [ ] **Step 5: Lint + build (BUILD-COMPAT CHECKPOINT)**

Run from `frontend/`: `npm run lint` then `npm run build`.
Expected: lint clean; **build succeeds**.

If `npm run build` FAILS due to Recharts being incompatible with Next 16 / React 19:
1. Remove the recharts import and the `<ResponsiveContainer>...</ResponsiveContainer>` block.
2. Replace the chart with a hand-rolled inline SVG bar chart of `stats.monthly_income` under the
   same `"Monthly income"` heading:

```tsx
          <h2 className="mb-2 mt-6 font-semibold">Monthly income</h2>
          <svg viewBox="0 0 320 140" className="mb-2 w-full" role="img" aria-label="Monthly income">
            {(() => {
              const max = Math.max(1, ...stats.monthly_income.map((m) => m.amount));
              const bw = 320 / stats.monthly_income.length;
              return stats.monthly_income.map((m, i) => {
                const h = (m.amount / max) * 110;
                return (
                  <g key={m.month}>
                    <rect x={i * bw + 6} y={120 - h} width={bw - 12} height={h} fill="#2563eb" />
                    <text x={i * bw + bw / 2} y={135} textAnchor="middle" fontSize="8" fill="#6b7280">
                      {m.month.slice(5)}
                    </text>
                  </g>
                );
              });
            })()}
          </svg>
```
3. Run `npm uninstall recharts`, then re-run `npm run lint` and `npm run build`.

Record in the Step 7 report which path shipped (Recharts or the SVG fallback).

- [ ] **Step 6: Ruff (backend, keeps CI green)**

```bash
cd backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 7: Commit and push**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/stats.ts frontend/src/app/app/page.tsx
git commit -m "Add dashboard stat cards and monthly-income chart"
git push
```
Then report (noting Recharts vs SVG fallback) and wait for approval.

---

### Task 4: e2e — dashboard stats render

**Files:**
- Create: `frontend/e2e/dashboard-stats.spec.ts`

**Interfaces:**
- Consumes: the dashboard stats UI (Task 3); the stats endpoint (Task 2).

- [ ] **Step 1: Restart the local backend (new endpoint)**

```bash
lsof -ti tcp:8000 | xargs kill
cd backend && uv run uvicorn app.main:app --port 8000
```
(Leave running in a second shell for the e2e run.)

- [ ] **Step 2: Write the spec**

Create `frontend/e2e/dashboard-stats.spec.ts`:

```typescript
import { expect, test } from "@playwright/test";

const landlord = `stats-${Date.now()}@example.com`;

test("landlord dashboard shows stat cards and the income chart", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Stats Landlord");
  await page.getByPlaceholder("Organization name").fill("Stats Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // The dashboard aggregates render for a manager.
  await expect(page.getByText("Outstanding")).toBeVisible();
  await expect(page.getByText("Collected this month")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Monthly income" })).toBeVisible();
});
```

- [ ] **Step 3: Run the e2e suite (serial, CI-safe)**

Run from `frontend/`: `npx playwright test`
Expected: all specs pass, including `dashboard-stats`.

- [ ] **Step 4: Lint + build + ruff**

```bash
cd frontend && npm run lint && npm run build
cd ../backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: clean.

- [ ] **Step 5: Commit, push, watch CI green**

```bash
git add "frontend/e2e/dashboard-stats.spec.ts"
git commit -m "Add dashboard-stats e2e"
git push
gh run watch --exit-status
```
Expected: all three CI jobs (backend, frontend, e2e) green.

- [ ] **Step 6: Report — Milestone 4.3 and Milestone 4 complete**

Report: the landlord/PM dashboard now shows outstanding/overdue/collected-this-month plus
properties/active-leases/tenants counts and a 6-month income chart, from `GET /api/v1/stats`.
This completes **Milestone 4** (charges -> payments/balances -> dashboard stats). Note whether the
chart shipped with Recharts or the SVG fallback. Wait for direction.

---

## Self-Review

**Spec coverage:**
- Metrics (outstanding, overdue, collected_this_month, properties_total/occupied, active_leases, tenants, monthly_income) -> Task 1 `dashboard_stats`, verified in `test_dashboard_stats` + `test_empty_org_zeros` + `test_stats_org_isolation`. ✓
- Endpoint (manager, 401/403) -> Task 2, verified in `test_stats_api.py`. ✓
- Frontend cards + Recharts chart + build-compat fallback -> Task 3. ✓
- e2e cards + chart heading -> Task 4. ✓
- No migration -> confirmed (head unchanged). ✓
- Out of scope (export, filters, drilldown, multi-currency, caching) -> not planned. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code (including the SVG fallback). ✓

**Type consistency:** `dashboard_stats(session, organization_id, today) -> DashboardStats`;
`DashboardStats` fields (`outstanding`, `overdue`, `collected_this_month`, `properties_total`,
`properties_occupied`, `active_leases`, `tenants`, `monthly_income`) identical across schema,
service, endpoint, and the frontend `DashboardStats` interface; `MonthlyIncome{month, amount}`
matches the Recharts `dataKey="month"`/`dataKey="amount"` and the SVG fallback. ✓
