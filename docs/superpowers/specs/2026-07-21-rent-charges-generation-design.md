# Milestone 4.1: Rent Charges (Generation) — Design

**Date:** 2026-07-21
**Status:** Approved (pending spec review)
**Part of:** Milestone 4 (rent charges -> payments+balances -> dashboard stats). This is sub-project 1 of 3.

## Goal

A daily scheduled job generates a rent `Charge` for each rent period of every lease,
a lead time before it falls due, without ever generating the same period twice. Managers
see a read-only list of a lease's charges.

## Architecture

- A pure service function `generate_charges(session, today)` holds all logic (which leases,
  which periods, snapshot amount, insert). It takes a session and a date, so it is fully
  unit-testable with no scheduler or clock.
- The existing in-process `AsyncIOScheduler` (from Milestone 3.4) gains a second daily job
  that calls it; a thin CLI calls the same function for manual runs.
- A `charges` table with `UNIQUE(lease_id, period_start)` is the idempotency guard: a re-run
  or a concurrent worker cannot double-generate a period (the second insert is skipped).

This mirrors the Milestone 3.4 lease-expiry-reminder architecture (service + scheduler job +
CLI + unique-constraint idempotency) so the patterns stay consistent.

## Tech Stack

- Backend: FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, APScheduler (existing).
- New dependency: `python-dateutil` (`uv add python-dateutil`) for correct month arithmetic.
- Frontend: Next.js lease-detail page gains one read-only section.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, run from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait for approval.
- Migration is enum-free; verify upgrade -> downgrade -> upgrade round-trip. Current head: `5f2bdf7f2048`.

---

## Product Rules (confirmed)

- **Due in advance:** a period's charge is due on the period's start date (`due_date = period_start`).
- **Lead time:** the job generates a period once `today >= period_start - charge_lead_days`
  (default 7). Equivalently it generates every period with `period_start <= today + charge_lead_days`.
- **Period anchoring:** periods are anchored to the lease's `start_date` and stepped by
  `rent_frequency`. No calendar alignment, no first-period proration. Example: a monthly lease
  starting on the 15th is charged on the 15th of each month.
- **Backfill:** a backdated lease (start_date in the past) generates all its past periods up to
  the horizon on the first run. This is correct (those periods were owed) and has no side effects
  (rows only, no email).
- **Amount snapshot:** `amount_due` is a snapshot of `lease.rent_amount` at generation time.
  Editing the lease's rent later does not change already-generated charges.
- **No status/paid tracking in M4.1:** paid/partial/unpaid/overdue and outstanding balance are
  derived from payments and belong to M4.2.

## Data Model

New file `app/models/charge.py`, modeled on `app/models/lease_reminder.py`:

```python
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Charge(Base):
    __tablename__ = "charges"
    __table_args__ = (UniqueConstraint("lease_id", "period_start"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    lease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Register `Charge` in `app/models/__init__.py` (`__all__` + import).

`ondelete="CASCADE"` cleans up charges when a lease is deleted (consistent with
`lease_tenants` / `lease_reminders`). `organization_id` is denormalized onto the charge for
straightforward org-scoping in later milestones (payments, dashboard). One Alembic migration
creates the table; downgrade drops it. No enums. Verify upgrade -> downgrade -> upgrade.

## Generation Algorithm

New file `app/services/charges.py`:

```python
async def generate_charges(session: AsyncSession, today: date) -> int:
    """Generate rent charges for every lease period due within the lead window.

    Returns the number of charges created this run.
    """
```

Helpers (small, focused, testable):

- `_period_start(start_date: date, frequency: LeaseFrequency, n: int) -> date` — the nth
  period's start: weekly -> `start_date + timedelta(weeks=n)`; fortnightly ->
  `start_date + timedelta(weeks=2 * n)`; monthly -> `start_date + relativedelta(months=n)`
  (computed from the original `start_date` each time, so month-ends clamp correctly:
  1/31 -> 2/28 -> 3/31).
- `_period_starts(lease, horizon) -> list[date]` — every `_period_start(...)` for
  `n = 0, 1, 2, ...` while the value is `<= min(horizon, lease.end_date)`.
- `_existing_period_starts(session, lease_id) -> set[date]` — the `period_start`s already
  stored for the lease.

Flow: `horizon = today + timedelta(days=settings.charge_lead_days)`; load leases with
`start_date <= horizon`; for each, walk `_period_starts(lease, horizon)`, skip any already
present, and for a new one insert
`Charge(organization_id=lease.organization_id, lease_id=lease.id, period_start=ps,
period_end=<next period start - 1 day, capped at lease.end_date>, due_date=ps,
amount_due=lease.rent_amount)`. Commit per lease (so a concurrent-run unique-constraint
conflict only rolls back that one lease's charges, and the next run picks them up). Return the
total count created.

`period_end` for period n is `_period_start(..., n + 1) - timedelta(days=1)`, capped so it
never exceeds `lease.end_date`.

## Scheduler + CLI

Edit `app/core/scheduler.py` to add a second job in `start_scheduler()`:

```python
from app.services.charges import generate_charges

async def _charges_job() -> None:
    async with SessionLocal() as session:
        count = await generate_charges(session, datetime.now(UTC).date())
    logger.info("rent charges: generated %s", count)
```

In `start_scheduler()`, after the existing reminder job:

```python
    scheduler.add_job(
        _charges_job,
        CronTrigger(hour=settings.charge_generation_hour),
        id="generate_charges",
        replace_existing=True,
    )
```

`main.py` already starts the scheduler in its lifespan; no change there. Tests are unaffected
(httpx `ASGITransport` does not run lifespan).

New file `app/jobs/generate_charges.py`, mirroring `app/jobs/expiry_reminders.py`:

```python
import asyncio
from datetime import UTC, datetime

from app.core.db import SessionLocal
from app.services.charges import generate_charges


async def _main() -> None:
    async with SessionLocal() as session:
        count = await generate_charges(session, datetime.now(UTC).date())
    print(f"rent charges: generated {count}")


if __name__ == "__main__":
    asyncio.run(_main())
```

Run: `uv run python -m app.jobs.generate_charges`.

## Settings

Add to `app/core/config.py`:

- `charge_lead_days: int = 7`
- `charge_generation_hour: int = 6`

## Read Endpoint + Frontend

**Schema** `app/schemas/charge.py`:

```python
class ChargeInfo(BaseModel):
    id: uuid.UUID
    period_start: date
    period_end: date
    due_date: date
    amount_due: Decimal
```

**Endpoint** in `app/routers/leases.py`:
`GET /api/v1/leases/{lease_id}/charges` (dep `manager`) -> `list[ChargeInfo]`, ordered by
`due_date` descending. 404 via `get_owned_lease`.

**Frontend** `frontend/src/lib/charges.ts`: `ChargeInfo { id: string; period_start: string;
period_end: string; due_date: string; amount_due: number }` and `listLeaseCharges(leaseId)` ->
`GET /api/v1/leases/{id}/charges`.

**Frontend** lease-detail page `app/leases/[leaseId]/page.tsx`: below the Expiry-reminders
section, a read-only **"Rent charges"** section. Fetched alongside the existing loads. Each row
shows the period (`period_start`–`period_end`), due date, and `amount_due`; if `due_date` is in
the future it shows an "Upcoming" badge. Empty state: "No charges yet."

## Testing

**Backend (pytest, primary):**

- `_period_start`: monthly 1/31 -> 2/28 -> 3/31; weekly +7; fortnightly +14.
- Monthly lease generates one charge per month up to the horizon; count and `period_start`s
  are correct; `due_date == period_start`; `period_end` is the day before the next period.
- Weekly and fortnightly stepping produce the right period_starts.
- Horizon: with `charge_lead_days=7`, a period starting `today+7` is generated but `today+8`
  is not.
- End cap: no charge with `period_start > lease.end_date`; the final `period_end` is clamped to
  `lease.end_date`.
- Idempotency: running twice generates each period once; a duplicate
  `(lease_id, period_start)` insert is prevented by the unique constraint.
- Backfill: a lease with `start_date` months in the past generates all past periods up to the
  horizon on one run.
- Amount snapshot: `amount_due == lease.rent_amount` at generation; editing rent afterward does
  not change existing charges.
- CASCADE: deleting a lease removes its charges.
- Endpoint: `GET /leases/{id}/charges` returns rows newest-first; cross-org lease -> 404;
  unauth -> 401.

**Frontend e2e (light):** on a freshly created lease (whose first charge is not yet within the
lead window, or before the job has run), the "Rent charges" section renders with its empty state
("No charges yet"). Generation depends on dates + the job, so it is covered by backend tests.

## Out of Scope (M4.1)

- Payment recording, paid/partial/unpaid/overdue status, outstanding balance, tenant-facing
  charge/balance views — **Milestone 4.2**.
- Dashboard stats and charts — **Milestone 4.3**.
- First-period proration, calendar-aligned due dates, per-lease custom due days, late fees,
  multi-currency display.

## File Structure

- Create: `backend/app/models/charge.py`
- Modify: `backend/app/models/__init__.py` (register `Charge`)
- Create: `backend/alembic/versions/<rev>_add_charges.py`
- Create: `backend/app/services/charges.py`
- Modify: `backend/app/core/scheduler.py` (second daily job)
- Create: `backend/app/jobs/generate_charges.py`
- Modify: `backend/app/core/config.py` (two settings)
- Modify: `backend/pyproject.toml` (`python-dateutil` dependency)
- Create: `backend/app/schemas/charge.py` (`ChargeInfo`)
- Modify: `backend/app/routers/leases.py` (`GET /leases/{id}/charges`)
- Create: `backend/tests/test_charges.py` (generation)
- Create: `backend/tests/test_charge_history.py` (endpoint)
- Create: `backend/tests/test_charges_cli.py` (CLI)
- Create: `frontend/src/lib/charges.ts`
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx` (Rent charges section)
- Modify: `frontend/e2e/tenant-invite.spec.ts` (assert empty-state section) or a new spec
