# Milestone 8.2: Rent Overdue and Upcoming Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A manager opens Payments and sees who owes money now and what falls due next, grouped by lease and expandable to the individual charges.

**Architecture:** One service function, `org_charge_statuses`, loads an organization's charges and payment totals in a fixed number of queries and reuses the existing pure `allocate`. One endpoint, `GET /api/v1/rent/summary`, returns both buckets from that single pass. `dashboard_stats` switches to the same function, which removes the 2N-query loop it runs today.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, PostgreSQL, Next.js 16 App Router, Tailwind v4, Playwright. **No migration** — no column and no table is added.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- Accessible names introduced: `Overdue rent`, `Upcoming rent`, and a per-row `Show charges for {address}`. Playwright matches names by **substring**, so check each against what else is on the page. The payments page currently contains `Payments` (heading) and `Payment history` (card title); none of the new names collide.
- Backend commands run from `backend/`, frontend commands from `frontend/`. The shell keeps its working directory between commands — always `cd` explicitly.
- **Note on the payments page:** it hand-rolls its auth guard with `apiFetch<Me>("/api/v1/auth/me")` rather than using `useShell()` like newer pages. That inconsistency is pre-existing; this plan adds to the page without restructuring it.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/services/payments.py` | add `org_charge_statuses` beside the existing per-lease helpers |
| `backend/app/schemas/rent.py` | `LeaseChargeGroup`, `RentSummary` |
| `backend/app/routers/rent.py` | `GET /rent/summary`, mounted in `main.py` |
| `backend/app/services/stats.py` | use the org-wide pass instead of the per-lease loop |
| `backend/tests/test_rent_summary.py` | bucketing, scoping, query count |
| `backend/tests/test_stats.py` | the cross-check against the new endpoint |
| `frontend/src/lib/rent.ts` | `getRentSummary` |
| `frontend/src/app/app/payments/page.tsx` | the two cards and expandable rows |
| `frontend/e2e/rent-summary.spec.ts` | empty-state coverage |

---

### Task 1: `org_charge_statuses` and the query-count test

**Files:**
- Modify: `backend/app/services/payments.py`
- Test: `backend/tests/test_rent_summary.py`

**Interfaces:**
- Consumes: `allocate(charges, total_paid, today) -> list[ChargeStatus]` (existing, unchanged).
- Produces: `org_charge_statuses(session, organization_id, today) -> dict[uuid.UUID, list[ChargeStatus]]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_rent_summary.py`:

```python
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import event, select

from app.models import Charge, Membership, User
from app.services.payments import org_charge_statuses
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


async def _lease(client, headers, address):
    property_id = await make_property(client, headers, address)
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]


async def _charge(db_session, org_id, lease_id, due: date, amount="1000"):
    db_session.add(
        Charge(
            organization_id=org_id,
            lease_id=uuid.UUID(lease_id),
            period_start=due,
            period_end=due + timedelta(days=29),
            due_date=due,
            amount_due=Decimal(amount),
        )
    )
    await db_session.commit()


def _count_queries(db_session):
    """Count SQL statements issued on this session's connection."""
    counter = {"n": 0}
    engine = db_session.get_bind()

    def before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", before)
    counter["stop"] = lambda: event.remove(engine, "before_cursor_execute", before)
    return counter


async def test_query_count_does_not_grow_with_lease_count(client, db_session):
    email = "qcount@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()

    lease_id = await _lease(client, headers, "1 Query St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=3))

    counter = _count_queries(db_session)
    await org_charge_statuses(db_session, org_id, today)
    one_lease = counter["n"]
    counter["stop"]()

    for i in range(4):
        extra = await _lease(client, headers, f"{i + 2} Query St")
        await _charge(db_session, org_id, extra, today - timedelta(days=3))

    counter = _count_queries(db_session)
    await org_charge_statuses(db_session, org_id, today)
    five_leases = counter["n"]
    counter["stop"]()

    assert five_leases == one_lease, (
        f"query count grew from {one_lease} to {five_leases} with lease count; "
        "the per-lease loop is back"
    )
```

This test is the whole reason the function exists. An N+1 regression makes no ordinary assertion fail, so without a counter it would return unnoticed.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_rent_summary.py -v`
Expected: FAIL with `ImportError: cannot import name 'org_charge_statuses'`.

- [ ] **Step 3: Implement the function**

In `backend/app/services/payments.py`, add `uuid` to the imports at the top:

```python
import uuid
```

and append:

```python
async def org_charge_statuses(
    session: AsyncSession, organization_id, today: date
) -> dict[uuid.UUID, list[ChargeStatus]]:
    """Allocate payments across charges for every lease in the organization.

    Two queries regardless of lease count. The per-lease helpers issue two each,
    so looping them over an organization costs 2N.
    """
    charges = (
        (await session.execute(select(Charge).where(Charge.organization_id == organization_id)))
        .scalars()
        .all()
    )
    paid_rows = await session.execute(
        select(Payment.lease_id, func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.organization_id == organization_id)
        .group_by(Payment.lease_id)
    )
    paid = {lease_id: Decimal(total) for lease_id, total in paid_rows.all()}

    by_lease: dict[uuid.UUID, list[Charge]] = {}
    for charge in charges:
        by_lease.setdefault(charge.lease_id, []).append(charge)
    return {
        lease_id: allocate(rows, paid.get(lease_id, Decimal("0")), today)
        for lease_id, rows in by_lease.items()
    }
```

`allocate` is untouched: it takes plain lists, which is what makes one bulk fetch possible.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_rent_summary.py -v`
Expected: PASS. If the counts differ, the implementation still has a per-lease query — fix that rather than relaxing the assertion.

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 6: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/services/payments.py backend/tests/test_rent_summary.py
git commit -m "Add org-wide charge allocation in a fixed number of queries"
git push origin main
```

Then report and wait for approval.

---

### Task 2: `RentSummary` schema and the endpoint

**Files:**
- Create: `backend/app/schemas/rent.py`, `backend/app/routers/rent.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_rent_summary.py`

**Interfaces:**
- Consumes: `org_charge_statuses` (Task 1); `ChargeInfo` from `app/schemas/charge.py`.
- Produces: `LeaseChargeGroup`, `RentSummary`; `GET /api/v1/rent/summary`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_rent_summary.py`:

```python
async def test_buckets_overdue_upcoming_and_settled(client, db_session):
    email = "buckets@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Bucket St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=5))
    await _charge(db_session, org_id, lease_id, today + timedelta(days=5))

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    assert [g["property_address"] for g in body["overdue"]] == ["1 Bucket St"]
    assert [g["property_address"] for g in body["upcoming"]] == ["1 Bucket St"]
    assert float(body["overdue"][0]["total"]) == 1000.0
    assert float(body["upcoming"][0]["total"]) == 1000.0


async def test_two_overdue_charges_are_one_row_with_the_sum(client, db_session):
    email = "twoover@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Sum St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=40))
    await _charge(db_session, org_id, lease_id, today - timedelta(days=10))

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    assert len(body["overdue"]) == 1, "one lease must not produce two rows"
    group = body["overdue"][0]
    assert float(group["total"]) == 2000.0
    assert len(group["charges"]) == 2
    assert group["oldest_due"] == str(today - timedelta(days=40))


async def test_partly_paid_charge_counts_only_the_remainder(client, db_session):
    email = "partpaid@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Part St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=5))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 400, "paid_on": str(today), "method": "bank_transfer"},
        headers=headers,
    )

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    assert float(body["overdue"][0]["total"]) == 600.0


async def test_fully_paid_charge_appears_in_neither_bucket(client, db_session):
    email = "settled@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Settled St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=5))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 1000, "paid_on": str(today), "method": "bank_transfer"},
        headers=headers,
    )

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    assert body["overdue"] == []
    assert body["upcoming"] == []


async def test_prepaid_future_charge_drops_out_of_upcoming(client, db_session):
    email = "prepaid@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Prepaid St")
    await _charge(db_session, org_id, lease_id, today + timedelta(days=5))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 1000, "paid_on": str(today), "method": "bank_transfer"},
        headers=headers,
    )

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    # The same "still owed" rule governs both buckets: paying ahead settles the
    # future charge, so it drops out of upcoming exactly as a settled charge
    # drops out of overdue. Both cards answer "what is still owed".
    assert body["upcoming"] == []
    assert body["overdue"] == []


async def test_summary_is_org_scoped(client, db_session):
    email = "mineonly@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Mine St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=5))

    stranger = await landlord_headers(client, "notmine@example.com")
    body = (await client.get("/api/v1/rent/summary", headers=stranger)).json()

    assert body == {"overdue": [], "upcoming": []}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_rent_summary.py -v`
Expected: the six new tests FAIL with 404 — the route does not exist.

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/rent.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.charge import ChargeInfo


class LeaseChargeGroup(BaseModel):
    """One lease's unsettled charges in a single bucket."""

    lease_id: uuid.UUID
    property_address: str
    tenant_name: str
    total: Decimal
    oldest_due: date
    charges: list[ChargeInfo]


class RentSummary(BaseModel):
    overdue: list[LeaseChargeGroup]
    upcoming: list[LeaseChargeGroup]
```

- [ ] **Step 4: Write the router**

Create `backend/app/routers/rent.py`:

```python
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Lease, Membership, Property
from app.routers.leases import manager
from app.schemas.charge import ChargeInfo
from app.schemas.rent import LeaseChargeGroup, RentSummary
from app.services.payments import ChargeStatus, org_charge_statuses

router = APIRouter(prefix="/api/v1", tags=["rent"])


def _to_charge_info(status: ChargeStatus) -> ChargeInfo:
    return ChargeInfo(
        id=status.charge.id,
        period_start=status.charge.period_start,
        period_end=status.charge.period_end,
        due_date=status.charge.due_date,
        amount_due=status.charge.amount_due,
        amount_paid=status.amount_paid,
        status=status.status,
        overdue=status.overdue,
    )


def _group(
    lease_id: uuid.UUID,
    address: str,
    tenant_name: str,
    statuses: list[ChargeStatus],
) -> LeaseChargeGroup | None:
    """One bucket row, or None when nothing in it is still owed."""
    owing = [s for s in statuses if s.charge.amount_due > s.amount_paid]
    if not owing:
        return None
    return LeaseChargeGroup(
        lease_id=lease_id,
        property_address=address,
        tenant_name=tenant_name,
        total=sum((s.charge.amount_due - s.amount_paid for s in owing), Decimal("0")),
        oldest_due=min(s.charge.due_date for s in owing),
        charges=[_to_charge_info(s) for s in owing],
    )


@router.get("/rent/summary", response_model=RentSummary)
async def rent_summary(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> RentSummary:
    """Unsettled rent for the organization, split into overdue and upcoming."""
    today = datetime.now(UTC).date()
    by_lease = await org_charge_statuses(session, membership.organization_id, today)
    rows = (
        await session.execute(
            select(Lease.id, Lease.tenant_name, Property.address)
            .join(Property, Property.id == Lease.property_id)
            .where(Lease.organization_id == membership.organization_id)
        )
    ).all()

    overdue: list[LeaseChargeGroup] = []
    upcoming: list[LeaseChargeGroup] = []
    for lease_id, tenant_name, address in rows:
        statuses = by_lease.get(lease_id, [])
        _append(overdue, _group(lease_id, address, tenant_name, _past(statuses, today)))
        _append(upcoming, _group(lease_id, address, tenant_name, _future(statuses, today)))

    overdue.sort(key=lambda g: g.oldest_due)
    upcoming.sort(key=lambda g: g.oldest_due)
    return RentSummary(overdue=overdue, upcoming=upcoming)


def _past(statuses: list[ChargeStatus], today: date) -> list[ChargeStatus]:
    return [s for s in statuses if s.charge.due_date < today]


def _future(statuses: list[ChargeStatus], today: date) -> list[ChargeStatus]:
    return [s for s in statuses if s.charge.due_date >= today]


def _append(target: list[LeaseChargeGroup], group: LeaseChargeGroup | None) -> None:
    if group is not None:
        target.append(group)
```

Place `_past`, `_future` and `_append` directly after `_group` and before `rent_summary`, matching this codebase's habit of defining helpers above their caller.

The "still owed" filter lives in `_group` and so applies to both buckets: a tenant who pays ahead leaves a future charge with nothing owing, and it drops out of `upcoming` exactly as a settled charge drops out of `overdue`.

- [ ] **Step 5: Mount the router**

In `backend/app/main.py`, add the import in alphabetical position (after `properties_router`):

```python
from app.routers.rent import router as rent_router
```

and the mount after `app.include_router(properties_router)`:

```python
app.include_router(rent_router)
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && uv run pytest tests/test_rent_summary.py -v`
Expected: 7 passed.

- [ ] **Step 7: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

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
git add backend/app/schemas/rent.py backend/app/routers/rent.py backend/app/main.py backend/tests/test_rent_summary.py
git commit -m "Add the rent summary endpoint"
git push origin main
```

Then report and wait for approval.

---

### Task 3: Switch `dashboard_stats` to the org-wide pass

**Files:**
- Modify: `backend/app/services/stats.py`
- Test: `backend/tests/test_stats.py`

**Interfaces:**
- Consumes: `org_charge_statuses` (Task 1), `summarize(statuses, total_paid, today) -> Balance` (existing), `GET /api/v1/rent/summary` (Task 2).
- Produces: no new interface. `dashboard_stats(session, organization_id, today) -> DashboardStats` keeps its signature and its numbers.

- [ ] **Step 1: Write the failing cross-check test**

Append to `backend/tests/test_stats.py`. Its existing imports already cover `date`, `timedelta`, `select`, `Charge`, `dashboard_stats`, `lease_body`, `make_property` and `landlord_headers`; add `from decimal import Decimal` and `import uuid` at the top if they are not present.

```python
async def test_dashboard_overdue_matches_the_rent_summary(client, db_session):
    email = "xcheck@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    property_id = await make_property(client, headers, "1 Cross St")
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    for days in (40, 10):
        db_session.add(
            Charge(
                organization_id=org_id,
                lease_id=uuid.UUID(lease_id),
                period_start=today - timedelta(days=days),
                period_end=today - timedelta(days=days - 29),
                due_date=today - timedelta(days=days),
                amount_due=Decimal("1000"),
            )
        )
    await db_session.commit()

    stats = await dashboard_stats(db_session, org_id, today)
    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()
    summary_total = sum(Decimal(str(g["total"])) for g in body["overdue"])

    # Two code paths now compute "overdue" from the same rows. A divergence here
    # is a real bug and is otherwise invisible.
    assert stats.overdue == summary_total
```

- [ ] **Step 2: Run it to verify it passes already**

Run: `cd backend && uv run pytest tests/test_stats.py -k matches -v`
Expected: **PASS**, before any change to `stats.py`. Both paths currently agree because both use `allocate`. That is the point: the test is written first so the refactor in Step 3 has something holding it in place. **If it fails now, stop and report** — the two paths already disagree, which is a bug to understand before refactoring on top of it.

- [ ] **Step 3: Replace the per-lease loop**

In `backend/app/services/stats.py`, change the import:

```python
from app.services.payments import org_charge_statuses, summarize
```

and replace the loop inside `dashboard_stats`:

```python
    outstanding = Decimal("0")
    overdue = Decimal("0")
    for lease in leases:
        balance = await lease_balance(session, lease.id, today)
        outstanding += balance.outstanding
        overdue += balance.overdue_amount
```

with:

```python
    # One pass for the organization: lease_balance issues two queries each, so
    # the old loop cost 2N.
    by_lease = await org_charge_statuses(session, organization_id, today)
    outstanding = Decimal("0")
    overdue = Decimal("0")
    for statuses in by_lease.values():
        paid = sum((s.amount_paid for s in statuses), Decimal("0"))
        balance = summarize(statuses, paid, today)
        outstanding += balance.outstanding
        overdue += balance.overdue_amount
```

`summarize` needs `total_paid` only to compute `credit`, which the dashboard does not read; passing the allocated total keeps `credit` at zero without a third query.

- [ ] **Step 4: Run the stats tests**

Run: `cd backend && uv run pytest tests/test_stats.py tests/test_stats_api.py -v`
Expected: all pass, including the pre-existing ones. Those are the guard that the numbers did not move.

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 6: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/services/stats.py backend/tests/test_stats.py
git commit -m "Compute dashboard balances in one pass instead of per lease"
git push origin main
```

Then report and wait for approval.

---

### Task 4: The two cards on the Payments page

**Files:**
- Create: `frontend/src/lib/rent.ts`
- Modify: `frontend/src/app/app/payments/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/rent/summary` (Task 2).
- Produces: `getRentSummary()`; the accessible names `Overdue rent`, `Upcoming rent`, `Show charges for {address}`.

- [ ] **Step 1: Add the API client**

Create `frontend/src/lib/rent.ts`:

```ts
import { apiFetch } from "@/lib/api";
import type { ChargeInfo } from "@/lib/charges";

export interface LeaseChargeGroup {
  lease_id: string;
  property_address: string;
  tenant_name: string;
  total: number;
  oldest_due: string;
  charges: ChargeInfo[];
}

export interface RentSummary {
  overdue: LeaseChargeGroup[];
  upcoming: LeaseChargeGroup[];
}

export function getRentSummary() {
  return apiFetch<RentSummary>("/api/v1/rent/summary");
}
```

- [ ] **Step 2: Add the rows component**

Create `frontend/src/components/rent-groups.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { LeaseChargeGroup } from "@/lib/rent";
import { Badge, DataList, DataRow, EmptyState } from "@/components/ui";

function daysLate(oldestDue: string): number {
  const due = new Date(`${oldestDue}T00:00:00Z`);
  const today = new Date();
  return Math.floor((today.getTime() - due.getTime()) / 86_400_000);
}

/**
 * Lease rows for one rent bucket, each expandable to its charges. Several rows
 * can be open at once: chasing arrears means comparing tenants, not reading one.
 */
export function RentGroups({
  groups,
  empty,
  showDaysLate,
}: {
  groups: LeaseChargeGroup[];
  empty: string;
  showDaysLate: boolean;
}) {
  const [open, setOpen] = useState<Set<string>>(new Set());

  function toggle(leaseId: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(leaseId)) next.delete(leaseId);
      else next.add(leaseId);
      return next;
    });
  }

  if (groups.length === 0) {
    return (
      <DataList>
        <DataRow>
          <EmptyState>{empty}</EmptyState>
        </DataRow>
      </DataList>
    );
  }

  return (
    <DataList>
      {groups.map((g) => (
        <DataRow key={g.lease_id}>
          <button
            type="button"
            // Per-row label: identical names on sibling rows break Playwright's
            // strict mode.
            aria-label={`Show charges for ${g.property_address}`}
            aria-expanded={open.has(g.lease_id)}
            onClick={() => toggle(g.lease_id)}
            className="flex w-full flex-wrap items-center justify-between gap-2 text-left"
          >
            <span className="min-w-0">
              <span className="font-medium text-text">{g.property_address}</span>
              <span className="text-muted"> · {g.tenant_name}</span>
            </span>
            <span className="flex items-center gap-2">
              {showDaysLate ? (
                <Badge tone="danger">{daysLate(g.oldest_due)} days late</Badge>
              ) : (
                <span className="text-xs text-muted">due {g.oldest_due}</span>
              )}
              <span className="font-medium text-text">${Number(g.total).toFixed(2)}</span>
            </span>
          </button>
          {open.has(g.lease_id) && (
            <ul className="mt-2 space-y-1 border-t border-border pt-2 text-xs text-muted">
              {g.charges.map((c) => (
                <li key={c.id} className="flex justify-between gap-2">
                  <span>
                    {c.period_start} to {c.period_end} · due {c.due_date}
                  </span>
                  <span>
                    ${Number(c.amount_paid).toFixed(2)} of ${Number(c.amount_due).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </DataRow>
      ))}
    </DataList>
  );
}
```

- [ ] **Step 3: Add the cards to the Payments page**

In `frontend/src/app/app/payments/page.tsx`, add the imports:

```tsx
import { getRentSummary, type RentSummary } from "@/lib/rent";
import { RentGroups } from "@/components/rent-groups";
```

Add state beside the existing `payments` state:

```tsx
  const [rent, setRent] = useState<RentSummary>({ overdue: [], upcoming: [] });
```

Inside the existing `.then((m) => { ... })` block, next to the `listRecentPayments` call, add:

```tsx
        getRentSummary()
          .then((r) => active && setRent(r))
          .catch(() => active && setRent({ overdue: [], upcoming: [] }));
```

And in the returned JSX, insert both cards immediately before the existing `Card` titled `Payment history`:

```tsx
      <Card title="Overdue rent" className="mb-5">
        <RentGroups groups={rent.overdue} empty="Nothing overdue." showDaysLate />
      </Card>
      <Card title="Upcoming rent" className="mb-5">
        <RentGroups
          groups={rent.upcoming}
          empty="Nothing due in the next 7 days."
          showDaysLate={false}
        />
      </Card>
```

The upcoming empty state names seven days because `charge_lead_days` is 7 and charges do not exist beyond it. Saying "nothing upcoming" would imply a longer horizon than the data covers.

- [ ] **Step 4: Lint, typecheck and build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: both clean. `npm run build` runs the TypeScript check.

- [ ] **Step 5: Check the page by hand**

The backend must be running. Sign in as a landlord and open `/app/payments`: both cards appear above Payment history with their empty states. A fresh account has no charges, so empty is the correct result here — the bucketing itself is covered by the Task 2 tests.

- [ ] **Step 6: Commit and push**

```bash
git add frontend/src/lib/rent.ts frontend/src/components/rent-groups.tsx frontend/src/app/app/payments/page.tsx
git commit -m "Show overdue and upcoming rent on the payments page"
git push origin main
```

Then report and wait for approval.

---

### Task 5: End-to-end coverage

**Files:**
- Create: `frontend/e2e/rent-summary.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-4.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/rent-summary.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const email = `rent-${Date.now()}@example.com`;

// Empty-state coverage only, and deliberately so: generate_charges runs on a
// schedule rather than at startup, so a lease created inside a test has no
// charges and no overdue state can be staged through the UI. The bucketing
// rules are covered by backend/tests/test_rent_summary.py.
test("landlord sees the overdue and upcoming rent cards", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Rent Landlord");
  await page.getByPlaceholder("Organization name").fill("Rent Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Payments" }).click();
  await expect(page).toHaveURL(/\/app\/payments$/);
  await expect(page.getByRole("heading", { name: "Overdue rent" })).toBeVisible();
  await expect(page.getByText("Nothing overdue.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Upcoming rent" })).toBeVisible();
  await expect(page.getByText("Nothing due in the next 7 days.")).toBeVisible();
  // The existing history card must survive the two additions.
  await expect(page.getByRole("heading", { name: "Payment history" })).toBeVisible();
});
```

`Card` renders its `title` as an `<h2>` (see `frontend/src/components/ui/card.tsx`), so `getByRole("heading", ...)` is correct here.

- [ ] **Step 2: Restart the backend so the new route is served**

The e2e run hits a live backend. If it was started before Task 2, `/api/v1/rent/summary` returns 404 and both cards fall back to their empty states — which would make this spec pass for the wrong reason.

- [ ] **Step 3: Run the new spec**

Run: `cd frontend && npx playwright test rent-summary`
Expected: 1 passed.

- [ ] **Step 4: Run the whole e2e suite**

Run: `cd frontend && npx playwright test --workers=1`
Expected: all pass (27 existing plus this one). Use `--workers=1` to match CI.

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
git add frontend/e2e/rent-summary.spec.ts
git commit -m "Add rent summary e2e"
git push origin main
```

- [ ] **Step 7: Confirm CI is green**

Run: `gh run list --limit 3`
Expected: the newest run for `main` succeeds. If it fails, read the log before changing anything — the failure is evidence, not noise.

Then report and wait for approval.
