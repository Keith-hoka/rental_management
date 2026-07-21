# Milestone 4.1: Rent Charges (Generation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily job generates a rent `Charge` for each lease period a lead time before it falls due, never double-generating a period, and managers see a read-only list of a lease's charges.

**Architecture:** A pure `generate_charges(session, today)` service holds all logic; the existing APScheduler (M3.4) gains a second daily job that calls it, plus a thin CLI. A `charges` table with `UNIQUE(lease_id, period_start)` makes generation idempotent under re-runs and concurrent workers.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, APScheduler (existing), python-dateutil (new), Next.js frontend.

## Global Constraints

- Package manager: `uv` only (`uv run ...`, `uv add ...`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before EVERY push, run from `backend/`, in this exact order:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- **Ruff gotcha:** test files must keep ALL imports at the top of the file (E402 is enabled by default). Do NOT append imports mid-file.
- Each task ends with: full test run -> ruff sequence -> commit -> `git push` (CI) -> report -> WAIT for approval.
- Migration is enum-free; verify upgrade -> downgrade -> upgrade round-trip. Current head: `5f2bdf7f2048`.
- Product rules: rent due in advance (`due_date = period_start`); generate when `period_start <= today + charge_lead_days` (default 7); periods anchored to `lease.start_date`, stepped by frequency, no proration; `amount_due` snapshots `lease.rent_amount` at generation.
- Backend tests: `cd backend && uv run pytest -q`. Frontend: `npm run lint`, `npm run build`, e2e `npx playwright test` from `frontend/`.
- The e2e backend must be restarted after new endpoints: `lsof -ti tcp:8000 | xargs kill` then `uv run uvicorn app.main:app --port 8000`.

---

## Task Overview

1. `Charge` model + migration + settings
2. Period helpers (`_period_start`, `_period_starts`) + `python-dateutil`
3. `generate_charges` service (horizon, snapshot, idempotency, backfill, end cap)
4. APScheduler second daily job
5. CLI entrypoint
6. `ChargeInfo` schema + `GET /leases/{id}/charges` endpoint
7. Frontend: lib client + read-only "Rent charges" section
8. e2e: empty-state section renders

---

### Task 1: `Charge` model + migration + settings

**Files:**
- Create: `backend/app/models/charge.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/alembic/versions/<rev>_add_charges.py` (via autogenerate)
- Test: `backend/tests/test_charge_model.py`

**Interfaces:**
- Produces: `Charge(id, organization_id, lease_id, period_start, period_end, due_date, amount_due, created_at)` importable from `app.models`; settings `charge_lead_days: int`, `charge_generation_hour: int`.

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/test_charge_model.py`:

```python
import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Charge, Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease(client, db_session, headers, property_id):
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    return lease


def _charge(lease, period_start=date(2026, 1, 1)):
    return Charge(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        period_start=period_start,
        period_end=date(2026, 1, 31),
        due_date=period_start,
        amount_due=1500,
    )


async def test_insert_and_read_charge(client, db_session):
    headers = await landlord_headers(client, "cmodel@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_charge(lease))
    await db_session.commit()

    rows = (
        (await db_session.execute(select(Charge).where(Charge.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].due_date == date(2026, 1, 1)
    assert float(rows[0].amount_due) == 1500.0


async def test_unique_lease_period_start(client, db_session):
    headers = await landlord_headers(client, "cunique@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_charge(lease))
    await db_session.commit()
    db_session.add(_charge(lease))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_delete_lease_cascades_charges(client, db_session):
    headers = await landlord_headers(client, "ccascade@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_charge(lease))
    await db_session.commit()

    await client.delete(f"/api/v1/leases/{lease.id}", headers=headers)

    rows = (
        (await db_session.execute(select(Charge).where(Charge.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert rows == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_charge_model.py -q`
Expected: FAIL with `ImportError: cannot import name 'Charge' from 'app.models'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/charge.py`:

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

- [ ] **Step 4: Register the model**

Edit `backend/app/models/__init__.py` — add the import (alphabetically, before `from app.models.invitation ...` is fine; group with the others) and the `__all__` entry:

```python
from app.models.charge import Charge
```

Add `"Charge",` to `__all__`.

- [ ] **Step 5: Add settings**

Edit `backend/app/core/config.py` — add after the reminder settings block (before `upload_dir`):

```python
    # Rent charges: daily generation job lead time (days before due) and run hour.
    charge_lead_days: int = 7
    charge_generation_hour: int = 6
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_charge_model.py -q`
Expected: PASS (3 tests; the `engine` fixture builds the table via `create_all`, honoring CASCADE).

- [ ] **Step 7: Generate and verify the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add charges"
```

Open the generated file. `upgrade()` should create the `charges` table with `organization_id`
FK, `lease_id` FK `ondelete='CASCADE'`, the three date columns, `amount_due` Numeric(10,2),
`created_at` with `server_default=sa.text('now()')`, `PrimaryKeyConstraint('id')`,
`UniqueConstraint('lease_id', 'period_start')`, and an index on `lease_id` and
`organization_id`. Confirm `down_revision = "5f2bdf7f2048"` and that `downgrade()` drops the
indexes then the table. Verify the round-trip:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all three succeed with no error.

- [ ] **Step 8: Full test run**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 9: Ruff sequence (from `backend/`)**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 10: Commit and push**

```bash
git add backend/app/models/charge.py backend/app/models/__init__.py \
        backend/app/core/config.py backend/alembic/versions backend/tests/test_charge_model.py
git commit -m "Add Charge model, migration, and charge-generation settings"
git push
```
Then report and wait for approval.

---

### Task 2: Period helpers + python-dateutil

**Files:**
- Create: `backend/app/services/charges.py`
- Modify: `backend/pyproject.toml` (via `uv add python-dateutil`)
- Test: `backend/tests/test_charges.py`

**Interfaces:**
- Consumes: `LeaseFrequency`, `Lease` from `app.models`.
- Produces: `_period_start(start_date: date, frequency: LeaseFrequency, n: int) -> date` and `_period_starts(lease, horizon: date) -> list[date]` in `app.services.charges`.

- [ ] **Step 1: Add the dependency**

```bash
cd backend && uv add python-dateutil
```
Expected: `python-dateutil` added to `pyproject.toml` dependencies and `uv.lock` updated.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_charges.py`:

```python
from datetime import date

from app.models import Lease, LeaseFrequency
from app.services.charges import _period_start, _period_starts


def test_period_start_monthly_clamps_month_end():
    assert _period_start(date(2026, 1, 31), LeaseFrequency.monthly, 1) == date(2026, 2, 28)
    assert _period_start(date(2026, 1, 31), LeaseFrequency.monthly, 2) == date(2026, 3, 31)


def test_period_start_weekly():
    assert _period_start(date(2026, 1, 1), LeaseFrequency.weekly, 3) == date(2026, 1, 22)


def test_period_start_fortnightly():
    assert _period_start(date(2026, 1, 1), LeaseFrequency.fortnightly, 2) == date(2026, 1, 29)


def test_period_starts_monthly_up_to_horizon():
    lease = Lease(
        start_date=date(2026, 1, 15),
        end_date=date(2026, 12, 31),
        rent_frequency=LeaseFrequency.monthly,
    )
    assert _period_starts(lease, date(2026, 3, 20)) == [
        date(2026, 1, 15),
        date(2026, 2, 15),
        date(2026, 3, 15),
    ]


def test_period_starts_stops_at_lease_end():
    lease = Lease(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 15),
        rent_frequency=LeaseFrequency.monthly,
    )
    # horizon is far out; the cap is lease.end_date, so only Jan 1 and Feb 1 qualify.
    assert _period_starts(lease, date(2026, 12, 31)) == [date(2026, 1, 1), date(2026, 2, 1)]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_charges.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.charges'`.

- [ ] **Step 4: Create the helpers**

Create `backend/app/services/charges.py`:

```python
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app.models import Lease, LeaseFrequency


def _period_start(start_date: date, frequency: LeaseFrequency, n: int) -> date:
    """The nth period's start date, anchored to start_date and stepped by frequency."""
    if frequency == LeaseFrequency.weekly:
        return start_date + timedelta(weeks=n)
    if frequency == LeaseFrequency.fortnightly:
        return start_date + timedelta(weeks=2 * n)
    return start_date + relativedelta(months=n)


def _period_starts(lease: Lease, horizon: date) -> list[date]:
    """Every period start from the lease start up to min(horizon, lease.end_date)."""
    limit = min(horizon, lease.end_date)
    starts: list[date] = []
    n = 0
    while True:
        ps = _period_start(lease.start_date, lease.rent_frequency, n)
        if ps > limit:
            break
        starts.append(ps)
        n += 1
    return starts
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_charges.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Ruff sequence (from `backend/`)**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/services/charges.py backend/tests/test_charges.py
git commit -m "Add rent-charge period helpers and python-dateutil"
git push
```
Then report and wait for approval.

---

### Task 3: `generate_charges` service

**Files:**
- Modify: `backend/app/services/charges.py`
- Test: `backend/tests/test_charges.py`

**Interfaces:**
- Consumes: `_period_start`, `_period_starts` (Task 2); `Charge` (Task 1); `settings.charge_lead_days`; models `Lease`.
- Produces: `async generate_charges(session: AsyncSession, today: date) -> int` in `app.services.charges` (returns count of charges created).

- [ ] **Step 1: Write the failing tests**

Add these imports to the TOP of `backend/tests/test_charges.py` (keep all imports at the top — do not append mid-file), so the import block becomes:

```python
from datetime import date

from sqlalchemy import select

from app.models import Charge, Lease, LeaseFrequency
from app.services.charges import _period_start, _period_starts, generate_charges
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers
```

Then append these tests to the file:

```python
async def _make_lease(client, headers, property_id, **overrides):
    body = lease_body(**overrides)
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=body, headers=headers
        )
    ).json()


async def test_generates_monthly_charges_up_to_horizon(client, db_session):
    headers = await landlord_headers(client, "chg1@example.com")
    property_id = await make_property(client, headers)
    await _make_lease(
        client,
        headers,
        property_id,
        start_date="2026-01-01",
        end_date="2026-12-31",
        rent_frequency="monthly",
        rent_amount=1500,
    )

    count = await generate_charges(db_session, date(2026, 3, 20))

    assert count == 3
    charges = (
        (await db_session.execute(select(Charge).order_by(Charge.period_start)))
        .scalars()
        .all()
    )
    assert [c.period_start for c in charges] == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    assert all(c.due_date == c.period_start for c in charges)
    assert charges[0].period_end == date(2026, 1, 31)
    assert float(charges[0].amount_due) == 1500.0


async def test_generation_is_idempotent(client, db_session):
    headers = await landlord_headers(client, "chgidem@example.com")
    property_id = await make_property(client, headers)
    await _make_lease(
        client, headers, property_id, start_date="2026-01-01", end_date="2026-12-31"
    )

    first = await generate_charges(db_session, date(2026, 3, 20))
    second = await generate_charges(db_session, date(2026, 3, 20))

    assert first == 3
    assert second == 0


async def test_horizon_boundary_is_inclusive(client, db_session):
    headers = await landlord_headers(client, "chghz@example.com")
    property_id = await make_property(client, headers)
    # Weekly from 2026-06-01; with lead 7, horizon = 2026-06-08.
    await _make_lease(
        client,
        headers,
        property_id,
        start_date="2026-06-01",
        end_date="2026-12-31",
        rent_frequency="weekly",
    )

    await generate_charges(db_session, date(2026, 6, 1))

    starts = {
        c.period_start
        for c in (await db_session.execute(select(Charge))).scalars().all()
    }
    assert date(2026, 6, 8) in starts  # today + 7 == horizon, included
    assert date(2026, 6, 15) not in starts  # beyond horizon, excluded


async def test_last_period_end_capped_at_lease_end(client, db_session):
    headers = await landlord_headers(client, "chgcap@example.com")
    property_id = await make_property(client, headers)
    await _make_lease(
        client,
        headers,
        property_id,
        start_date="2026-01-01",
        end_date="2026-03-15",
        rent_frequency="monthly",
    )

    await generate_charges(db_session, date(2026, 3, 15))

    charges = (
        (await db_session.execute(select(Charge).order_by(Charge.period_start)))
        .scalars()
        .all()
    )
    assert [c.period_start for c in charges] == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    assert charges[-1].period_end == date(2026, 3, 15)


async def test_backfills_past_periods(client, db_session):
    headers = await landlord_headers(client, "chgback@example.com")
    property_id = await make_property(client, headers)
    await _make_lease(
        client, headers, property_id, start_date="2026-01-01", end_date="2026-12-31"
    )

    count = await generate_charges(db_session, date(2026, 4, 1))

    assert count == 4  # Jan, Feb, Mar, Apr (Apr 1 <= horizon Apr 8)


async def test_amount_snapshot_unchanged_after_rent_edit(client, db_session):
    headers = await landlord_headers(client, "chgsnap@example.com")
    property_id = await make_property(client, headers)
    created = await _make_lease(
        client,
        headers,
        property_id,
        start_date="2026-01-01",
        end_date="2026-12-31",
        rent_frequency="monthly",
        rent_amount=1500,
    )

    await generate_charges(db_session, date(2026, 1, 20))  # Jan charge at 1500
    await client.patch(
        f"/api/v1/leases/{created['id']}", json={"rent_amount": 2000}, headers=headers
    )
    # Mimic a fresh scheduler run: drop cached lease state so the new rent is read.
    db_session.expire_all()
    await generate_charges(db_session, date(2026, 2, 20))  # Feb charge at 2000

    amounts = {
        c.period_start: float(c.amount_due)
        for c in (await db_session.execute(select(Charge))).scalars().all()
    }
    assert amounts[date(2026, 1, 1)] == 1500.0
    assert amounts[date(2026, 2, 1)] == 2000.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_charges.py -q`
Expected: FAIL with `ImportError: cannot import name 'generate_charges'`.

- [ ] **Step 3: Implement the service**

Append to `backend/app/services/charges.py` (module already imports `date`, `timedelta`,
`relativedelta`, `Lease`, `LeaseFrequency`; add the new imports at the top of the file):

Add to the top import block:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Charge
```

Append the functions:

```python
async def _existing_period_starts(session: AsyncSession, lease_id) -> set[date]:
    result = await session.execute(
        select(Charge.period_start).where(Charge.lease_id == lease_id)
    )
    return {ps for (ps,) in result.all()}


async def generate_charges(session: AsyncSession, today: date) -> int:
    """Generate rent charges for every lease period due within the lead window.

    Returns the number of charges created this run.
    """
    horizon = today + timedelta(days=settings.charge_lead_days)
    leases = (
        (await session.execute(select(Lease).where(Lease.start_date <= horizon)))
        .scalars()
        .all()
    )
    created = 0
    for lease in leases:
        starts = _period_starts(lease, horizon)
        if not starts:
            continue
        existing = await _existing_period_starts(session, lease.id)
        new_count = 0
        for i, ps in enumerate(starts):
            if ps in existing:
                continue
            next_start = _period_start(lease.start_date, lease.rent_frequency, i + 1)
            period_end = min(next_start - timedelta(days=1), lease.end_date)
            session.add(
                Charge(
                    organization_id=lease.organization_id,
                    lease_id=lease.id,
                    period_start=ps,
                    period_end=period_end,
                    due_date=ps,
                    amount_due=lease.rent_amount,
                )
            )
            new_count += 1
        if new_count:
            await session.commit()
            created += new_count
    return created
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_charges.py -q`
Expected: PASS (helpers + all generation tests).

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Ruff sequence (from `backend/`)**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/services/charges.py backend/tests/test_charges.py
git commit -m "Add generate_charges service (horizon, snapshot, idempotency, backfill)"
git push
```
Then report and wait for approval.

---

### Task 4: APScheduler second daily job

**Files:**
- Modify: `backend/app/core/scheduler.py`
- Test: `backend/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `generate_charges` (Task 3); `SessionLocal`; `settings.charge_generation_hour`.
- Produces: a registered `generate_charges` APScheduler job alongside the existing `expiry_reminders` job.

- [ ] **Step 1: Update the scheduler test to assert both jobs**

Replace the body of `backend/tests/test_scheduler.py` with:

```python
from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler


async def test_start_scheduler_registers_both_daily_jobs():
    try:
        start_scheduler()

        reminders = scheduler.get_job("expiry_reminders")
        assert reminders is not None
        assert f"hour='{settings.reminder_hour}'" in str(reminders.trigger)

        charges = scheduler.get_job("generate_charges")
        assert charges is not None
        assert f"hour='{settings.charge_generation_hour}'" in str(charges.trigger)
    finally:
        scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scheduler.py -q`
Expected: FAIL — `generate_charges` job is `None` (not registered yet).

- [ ] **Step 3: Add the second job**

Edit `backend/app/core/scheduler.py`. Add the import near the existing service import:

```python
from app.services.charges import generate_charges
```

Add a second job function after `_run_job`:

```python
async def _charges_job() -> None:
    """Open a session and generate rent charges due within the lead window."""
    async with SessionLocal() as session:
        count = await generate_charges(session, datetime.now(UTC).date())
    logger.info("rent charges: generated %s", count)
```

In `start_scheduler()`, after the existing `expiry_reminders` `add_job(...)` and before
`scheduler.start()`, add:

```python
    scheduler.add_job(
        _charges_job,
        CronTrigger(hour=settings.charge_generation_hour),
        id="generate_charges",
        replace_existing=True,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_scheduler.py -q`
Expected: PASS.

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest -q`
Expected: all pass (lifespan does not run under the test client, so no job fires).

- [ ] **Step 6: Manual smoke test (both jobs start under uvicorn)**

```bash
cd backend && uv run uvicorn app.main:app --port 8000
```
Expected: startup logs show APScheduler added jobs `expiry_reminders` and `generate_charges`,
`Scheduler started`, `Application startup complete`. Stop with Ctrl-C.

- [ ] **Step 7: Ruff sequence (from `backend/`)**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/core/scheduler.py backend/tests/test_scheduler.py
git commit -m "Generate rent charges daily via a second APScheduler job"
git push
```
Then report and wait for approval.

---

### Task 5: CLI entrypoint

**Files:**
- Create: `backend/app/jobs/generate_charges.py`
- Test: `backend/tests/test_charges_cli.py`

**Interfaces:**
- Consumes: `generate_charges` (Task 3); `SessionLocal`.
- Produces: `async _main()` in `app.jobs.generate_charges`, runnable via `uv run python -m app.jobs.generate_charges`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_charges_cli.py`:

```python
from contextlib import asynccontextmanager

from app.jobs import generate_charges as cli


async def test_main_prints_count(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    async def fake_generate(session, today):
        return 5

    monkeypatch.setattr(cli, "SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr(cli, "generate_charges", fake_generate)

    await cli._main()

    assert "rent charges: generated 5" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_charges_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jobs.generate_charges'`.

- [ ] **Step 3: Create the CLI**

Create `backend/app/jobs/generate_charges.py`:

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

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_charges_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Ruff sequence (from `backend/`)**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/jobs/generate_charges.py backend/tests/test_charges_cli.py
git commit -m "Add rent-charge generation CLI entrypoint"
git push
```
Then report and wait for approval.

---

### Task 6: `ChargeInfo` schema + endpoint

**Files:**
- Create: `backend/app/schemas/charge.py`
- Modify: `backend/app/routers/leases.py`
- Test: `backend/tests/test_charge_history.py`

**Interfaces:**
- Consumes: `Charge` (Task 1); existing `manager` dep, `get_owned_lease` in `app.routers.leases`.
- Produces: `ChargeInfo(id, period_start, period_end, due_date, amount_due)` in `app.schemas.charge`; `GET /api/v1/leases/{lease_id}/charges -> list[ChargeInfo]` (newest `due_date` first).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_charge_history.py`:

```python
import uuid
from datetime import date

from sqlalchemy import select

from app.models import Charge, Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease(client, db_session, headers, property_id):
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    return (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()


def _charge(lease, period_start):
    return Charge(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        period_start=period_start,
        period_end=period_start,
        due_date=period_start,
        amount_due=1500,
    )


async def test_charge_history_newest_first(client, db_session):
    headers = await landlord_headers(client, "ch@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_charge(lease, date(2026, 1, 1)))
    db_session.add(_charge(lease, date(2026, 2, 1)))
    await db_session.commit()

    response = await client.get(f"/api/v1/leases/{lease.id}/charges", headers=headers)
    assert response.status_code == 200
    assert [c["due_date"] for c in response.json()] == ["2026-02-01", "2026-01-01"]


async def test_charge_history_cross_org_is_404(client, db_session):
    org_a = await landlord_headers(client, "cha@example.com")
    org_b = await landlord_headers(client, "chb@example.com")
    property_id = await make_property(client, org_a)
    lease = await _lease(client, db_session, org_a, property_id)
    response = await client.get(f"/api/v1/leases/{lease.id}/charges", headers=org_b)
    assert response.status_code == 404


async def test_charge_history_requires_auth(client, db_session):
    headers = await landlord_headers(client, "chauth@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)
    response = await client.get(f"/api/v1/leases/{lease.id}/charges")
    assert response.status_code == 401
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_charge_history.py -q`
Expected: FAIL (route missing -> 404/401 mismatches; newest-first gets 404).

- [ ] **Step 3: Add the schema**

Create `backend/app/schemas/charge.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ChargeInfo(BaseModel):
    id: uuid.UUID
    period_start: date
    period_end: date
    due_date: date
    amount_due: Decimal
```

- [ ] **Step 4: Add the endpoint**

Edit `backend/app/routers/leases.py`. Add `Charge` to the `from app.models import (...)` block
(alphabetically first) and add a new import line for the schema:

```python
from app.schemas.charge import ChargeInfo
```

Append this endpoint at the end of the file (mirrors `list_lease_reminders` — select columns
and construct `ChargeInfo`, so it does not depend on Pydantic `from_attributes`):

```python
@router.get("/leases/{lease_id}/charges", response_model=list[ChargeInfo])
async def list_lease_charges(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[ChargeInfo]:
    """List rent charges for the given lease, newest due date first."""
    await get_owned_lease(lease_id, membership, session)
    result = await session.execute(
        select(
            Charge.id,
            Charge.period_start,
            Charge.period_end,
            Charge.due_date,
            Charge.amount_due,
        )
        .where(Charge.lease_id == lease_id)
        .order_by(Charge.due_date.desc())
    )
    return [
        ChargeInfo(
            id=id_,
            period_start=period_start,
            period_end=period_end,
            due_date=due_date,
            amount_due=amount_due,
        )
        for id_, period_start, period_end, due_date, amount_due in result.all()
    ]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_charge_history.py -q`
Expected: PASS (3 tests). `ChargeInfo` reads the ORM objects via Pydantic attribute access.

- [ ] **Step 6: Full test run**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Ruff sequence (from `backend/`)**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/schemas/charge.py backend/app/routers/leases.py backend/tests/test_charge_history.py
git commit -m "Add GET /leases/{id}/charges endpoint"
git push
```
Then report and wait for approval.

---

### Task 7: Frontend lib client + "Rent charges" section

**Files:**
- Create: `frontend/src/lib/charges.ts`
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/leases/{id}/charges` (Task 6).
- Produces: `ChargeInfo`, `listLeaseCharges(leaseId)` in `@/lib/charges`.

- [ ] **Step 1: Create the lib client**

Create `frontend/src/lib/charges.ts`:

```typescript
import { apiFetch } from "@/lib/api";

export interface ChargeInfo {
  id: string;
  period_start: string;
  period_end: string;
  due_date: string;
  amount_due: number;
}

export function listLeaseCharges(leaseId: string) {
  return apiFetch<ChargeInfo[]>(`/api/v1/leases/${leaseId}/charges`);
}
```

- [ ] **Step 2: Wire charges into the lease-detail page**

Edit `frontend/src/app/app/leases/[leaseId]/page.tsx`.

Add the import near the other `@/lib` imports:

```tsx
import { listLeaseCharges, type ChargeInfo } from "@/lib/charges";
```

Add charge state next to `reminders`:

```tsx
  const [charges, setCharges] = useState<ChargeInfo[]>([]);
```

In the `useEffect`, add a fetch alongside the existing `listLeaseReminders` block (respecting the `active` guard):

```tsx
    listLeaseCharges(leaseId)
      .then((c) => {
        if (active) setCharges(c);
      })
      .catch(() => {
        if (active) setCharges([]);
      });
```

- [ ] **Step 3: Render the read-only section**

In the same file, add this `<section>` immediately after the closing `</section>` of the
Expiry-reminders block (still inside the non-editing `<>...</>`, right before `</>`):

```tsx
          <section className="mt-8">
            <h2 className="mb-2 font-semibold">Rent charges</h2>
            {charges.length === 0 ? (
              <p className="text-sm text-gray-500">No charges yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-gray-700">
                {charges.map((c) => (
                  <li key={c.id} className="flex justify-between">
                    <span>
                      {c.period_start} – {c.period_end} · due {c.due_date}
                      {new Date(c.due_date) > new Date() && (
                        <span className="ml-2 rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
                          Upcoming
                        </span>
                      )}
                    </span>
                    <span className="font-medium text-gray-800">${c.amount_due}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
```

- [ ] **Step 4: Lint and build**

Run from `frontend/`:
```bash
npm run lint
npm run build
```
Expected: no lint errors; build succeeds.

- [ ] **Step 5: Ruff sequence (from `backend/`, keeps CI green)**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean (no backend changes; confirms nothing drifted).

- [ ] **Step 6: Commit and push**

```bash
git add frontend/src/lib/charges.ts "frontend/src/app/app/leases/[leaseId]/page.tsx"
git commit -m "Show rent charges on the lease detail page"
git push
```
Then report and wait for approval.

---

### Task 8: e2e — empty-state section renders

**Files:**
- Modify: `frontend/e2e/tenant-invite.spec.ts`

**Interfaces:**
- Consumes: the "Rent charges" section (Task 7); the charges endpoint (Task 6).

- [ ] **Step 1: Restart the local backend (new endpoint)**

```bash
lsof -ti tcp:8000 | xargs kill
cd backend && uv run uvicorn app.main:app --port 8000
```
(Leave it running in a second shell for the e2e run.)

- [ ] **Step 2: Add the assertions**

Edit `frontend/e2e/tenant-invite.spec.ts`. After the existing "Expiry reminders" empty-state
assertions (before the closing `});`), add:

```typescript
  // A fresh lease has no charges yet — the read-only section shows its empty state.
  await expect(page.getByRole("heading", { name: "Rent charges" })).toBeVisible();
  await expect(page.getByText("No charges yet.")).toBeVisible();
```

- [ ] **Step 3: Run the e2e suite (serial, CI-safe)**

Run from `frontend/`:
```bash
npx playwright test
```
Expected: all specs pass, including the extended `tenant-invite` test.

- [ ] **Step 4: Lint and build**

Run from `frontend/`:
```bash
npm run lint
npm run build
```
Expected: clean.

- [ ] **Step 5: Ruff sequence (from `backend/`, keeps CI green)**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 6: Commit, push, watch CI green**

```bash
git add "frontend/e2e/tenant-invite.spec.ts"
git commit -m "Assert rent-charges empty-state renders on lease detail"
git push
gh run watch --exit-status
```
Expected: all three CI jobs (backend, frontend, e2e) green.

- [ ] **Step 7: Report — Milestone 4.1 complete**

Report: rent charges now generate daily per lease period a lead time before they fall due
(dedup by `UNIQUE(lease_id, period_start)`), driven by a second APScheduler job with a
`uv run python -m app.jobs.generate_charges` CLI, and managers see the charge list on the lease
detail page. Wait for approval to plan **Milestone 4.2** (payment recording + balances).

---

## Self-Review

**Spec coverage:**
- Charge model + UNIQUE + CASCADE + migration -> Task 1, verified in `test_charge_model.py`. ✓
- Settings (`charge_lead_days`, `charge_generation_hour`) -> Task 1. ✓
- Period anchoring + month-end clamp + frequency stepping -> Task 2 `_period_start`/`_period_starts`, verified `test_period_start_*` + `test_period_starts_*`. ✓
- Due-in-advance, horizon/lead, per-lease commit, backfill, end cap, amount snapshot, idempotency -> Task 3 `generate_charges`, verified `test_generates_monthly...`, `test_generation_is_idempotent`, `test_horizon_boundary_is_inclusive`, `test_last_period_end_capped...`, `test_backfills_past_periods`, `test_amount_snapshot_unchanged...`. ✓
- python-dateutil -> Task 2. ✓
- Second scheduler job -> Task 4. ✓
- CLI -> Task 5. ✓
- ChargeInfo + endpoint -> Task 6. ✓
- Frontend lib + section -> Task 7; e2e empty-state -> Task 8. ✓
- Out of scope (payments, status, balance, dashboard, proration) -> not planned. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the only `<rev>` is the Alembic-generated revision id. ✓

**Type consistency:** `generate_charges(session, today) -> int`, `_period_start(start_date, frequency, n) -> date`, `_period_starts(lease, horizon) -> list[date]`, `Charge(organization_id, lease_id, period_start, period_end, due_date, amount_due)`, `ChargeInfo(id, period_start, period_end, due_date, amount_due)` used identically across tasks; frontend `ChargeInfo { id, period_start, period_end, due_date, amount_due: number }` and `listLeaseCharges(leaseId)` match the endpoint. ✓
