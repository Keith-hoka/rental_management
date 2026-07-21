# Milestone 3.4: Lease-Expiry Reminders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily job emails landlords/PMs and tenants when a lease nears `end_date` (60/30/7-day thresholds), never sending the same reminder twice, and managers see the reminder history on the lease.

**Architecture:** A pure `run_expiry_reminders(session, today)` service holds all logic; an in-process APScheduler job (started from the FastAPI lifespan) and a thin CLI both call it. A `lease_reminders` table with `UNIQUE(lease_id, threshold_days)` is the dedup ledger, so re-runs and concurrent workers are idempotent.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, APScheduler (new), Next.js frontend.

## Global Constraints

- Package manager: `uv` only (`uv run ...`, `uv add ...`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before EVERY push, run from `backend/`, in this exact order:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Each task ends with: full test run -> ruff sequence -> commit -> `git push` (CI at https://github.com/Keith-hoka/rental_management) -> report -> WAIT for explicit approval before the next task.
- Migration is enum-free; verify upgrade -> downgrade -> upgrade round-trip. Current head: `bbba6bd9608b`.
- Backend tests: `cd backend && uv run pytest -q`. Frontend: `npm run lint`, `npm run build`, e2e `npm run test:e2e` (or `npx playwright test`) from `frontend/`.
- Local Postgres is on host port 5433; CI on 5432 (already handled by env). The e2e backend must be restarted after new endpoints are added: `lsof -ti tcp:8000 | xargs kill` then `uv run uvicorn app.main:app --port 8000`.

---

## Task Overview

1. `LeaseReminder` model + migration + settings
2. `_bucket` threshold helper (pure function)
3. `run_expiry_reminders` service (recipients, dedup, windows, email-failure safety)
4. APScheduler wiring + FastAPI lifespan + `apscheduler` dependency
5. CLI entrypoint
6. Reminder-history schema + `GET /leases/{id}/reminders` endpoint
7. Frontend: lib client + read-only "Expiry reminders" section
8. e2e: empty-state section renders

---

### Task 1: `LeaseReminder` model + migration + settings

**Files:**
- Create: `backend/app/models/lease_reminder.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/alembic/versions/<rev>_add_lease_reminders.py` (via autogenerate)
- Test: `backend/tests/test_lease_reminder_model.py`

**Interfaces:**
- Produces: `LeaseReminder(id: uuid, lease_id: uuid, threshold_days: int, sent_at: datetime)` importable from `app.models`; settings `reminders_enabled: bool`, `reminder_thresholds: list[int]`, `reminder_hour: int`.

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/test_lease_reminder_model.py`:

```python
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import LeaseReminder
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _make_lease_id(client, headers, property_id) -> str:
    created = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(),
        headers=headers,
    )
    return created.json()["id"]


async def test_insert_and_read_reminder(client, db_session):
    headers = await landlord_headers(client, "rmodel@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)

    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30))
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(LeaseReminder).where(LeaseReminder.lease_id == uuid.UUID(lease_id))
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].threshold_days == 30
    assert rows[0].sent_at is not None


async def test_unique_lease_threshold(client, db_session):
    headers = await landlord_headers(client, "runique@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)

    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30))
    await db_session.commit()
    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_delete_lease_cascades_reminders(client, db_session):
    headers = await landlord_headers(client, "rcascade@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)

    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30))
    await db_session.commit()

    await client.delete(f"/api/v1/leases/{lease_id}", headers=headers)

    rows = (
        await db_session.execute(
            select(LeaseReminder).where(LeaseReminder.lease_id == uuid.UUID(lease_id))
        )
    ).scalars().all()
    assert rows == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_lease_reminder_model.py -q`
Expected: FAIL with `ImportError: cannot import name 'LeaseReminder' from 'app.models'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/lease_reminder.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LeaseReminder(Base):
    __tablename__ = "lease_reminders"
    __table_args__ = (UniqueConstraint("lease_id", "threshold_days"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), index=True
    )
    threshold_days: Mapped[int] = mapped_column()
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Register the model**

Edit `backend/app/models/__init__.py` — add the import (after the `lease_tenant` import) and the `__all__` entry (keep alphabetical grouping):

```python
from app.models.lease_reminder import LeaseReminder
```

Add `"LeaseReminder",` to `__all__`.

- [ ] **Step 5: Add settings**

Edit `backend/app/core/config.py` — add these three lines after `frontend_url` (before the `upload_dir` block):

```python
    # Lease-expiry reminders: daily job thresholds (days before end_date) and run hour.
    reminders_enabled: bool = True
    reminder_thresholds: list[int] = [60, 30, 7]
    reminder_hour: int = 8
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_lease_reminder_model.py -q`
Expected: PASS (the `engine` fixture builds the table via `create_all`, honoring the CASCADE).

- [ ] **Step 7: Generate and verify the migration**

Prereq: local Postgres up, DB at head.

```bash
cd backend
uv run alembic revision --autogenerate -m "add lease_reminders"
```

Open the generated file. `upgrade()` should match (adjust if autogenerate reorders):

```python
def upgrade() -> None:
    op.create_table(
        "lease_reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=False),
        sa.Column("threshold_days", sa.Integer(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lease_id", "threshold_days"),
    )
    op.create_index(
        op.f("ix_lease_reminders_lease_id"), "lease_reminders", ["lease_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lease_reminders_lease_id"), table_name="lease_reminders")
    op.drop_table("lease_reminders")
```

Confirm `down_revision = "bbba6bd9608b"`. Verify the round-trip:

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
git add backend/app/models/lease_reminder.py backend/app/models/__init__.py \
        backend/app/core/config.py backend/alembic/versions backend/tests/test_lease_reminder_model.py
git commit -m "Add LeaseReminder model, migration, and reminder settings"
git push
```
Then report and wait for approval.

---

### Task 2: `_bucket` threshold helper

**Files:**
- Create: `backend/app/services/__init__.py` (empty)
- Create: `backend/app/services/reminders.py`
- Test: `backend/tests/test_reminders.py`

**Interfaces:**
- Produces: `_bucket(days_left: int, thresholds: list[int]) -> int | None` in `app.services.reminders`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_reminders.py`:

```python
import pytest

from app.services.reminders import _bucket

THRESHOLDS = [60, 30, 7]


@pytest.mark.parametrize(
    ("days_left", "expected"),
    [
        (61, None),
        (60, 60),
        (45, 60),
        (31, 60),
        (30, 30),
        (8, 30),
        (7, 7),
        (0, 7),
        (-1, None),
    ],
)
def test_bucket(days_left, expected):
    assert _bucket(days_left, THRESHOLDS) == expected
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_reminders.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services'`.

- [ ] **Step 3: Create the service module with `_bucket`**

Create `backend/app/services/__init__.py` (empty file).

Create `backend/app/services/reminders.py`:

```python
def _bucket(days_left: int, thresholds: list[int]) -> int | None:
    """Smallest threshold T with days_left <= T when days_left >= 0, else None."""
    if days_left < 0:
        return None
    for threshold in sorted(thresholds):
        if days_left <= threshold:
            return threshold
    return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_reminders.py -q`
Expected: PASS (9 cases).

- [ ] **Step 5: Ruff sequence (from `backend/`)**

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```
Expected: all clean.

- [ ] **Step 6: Commit and push**

```bash
git add backend/app/services/__init__.py backend/app/services/reminders.py backend/tests/test_reminders.py
git commit -m "Add expiry-reminder threshold bucketing helper"
git push
```
Then report and wait for approval.

---

### Task 3: `run_expiry_reminders` service

**Files:**
- Modify: `backend/app/services/reminders.py`
- Test: `backend/tests/test_reminders.py`

**Interfaces:**
- Consumes: `_bucket` (Task 2); `LeaseReminder` (Task 1); `settings.reminder_thresholds`; `app.core.email.send_email(to, subject, html)`; models `Lease`, `Membership`, `Property`, `Role`, `User`.
- Produces: `async run_expiry_reminders(session: AsyncSession, today: date) -> int` in `app.services.reminders` (returns count of (lease, bucket) reminders sent). Send-email calls are made via the name `send_email` bound in `app.services.reminders` — tests monkeypatch `app.services.reminders.send_email`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_reminders.py`:

```python
from datetime import date, timedelta

from sqlalchemy import select

from app.models import LeaseReminder
from app.services.reminders import run_expiry_reminders
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


@pytest.fixture
def captured(monkeypatch):
    """Collect (to, subject) for every send_email call the service makes."""
    calls: list[tuple[str, str]] = []

    async def fake_send(to, subject, html):
        calls.append((to, subject))

    monkeypatch.setattr("app.services.reminders.send_email", fake_send)
    return calls


async def _make_lease(client, headers, property_id, *, end_date, **overrides):
    body = lease_body(
        start_date=str(date.today() - timedelta(days=1)),
        end_date=str(end_date),
        **overrides,
    )
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=body, headers=headers
        )
    ).json()["id"]


async def test_sends_to_managers_and_roster(client, db_session, captured):
    headers = await landlord_headers(client, "send7@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await _make_lease(
        client,
        headers,
        property_id,
        end_date=today + timedelta(days=7),
        tenant_email="main@example.com",
        co_tenants=[{"name": "Co", "email": "co@example.com", "phone": ""}],
    )

    count = await run_expiry_reminders(db_session, today)

    assert count == 1
    recipients = {to for to, _ in captured}
    assert "send7@example.com" in recipients  # landlord (manager)
    assert "main@example.com" in recipients  # main tenant
    assert "co@example.com" in recipients  # co-tenant


async def test_dedup_runs_twice_sends_once(client, db_session, captured):
    headers = await landlord_headers(client, "dedup@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await _make_lease(client, headers, property_id, end_date=today + timedelta(days=7))

    first = await run_expiry_reminders(db_session, today)
    second = await run_expiry_reminders(db_session, today)

    assert first == 1
    assert second == 0


async def test_bucket_advances_over_time(client, db_session, captured):
    headers = await landlord_headers(client, "advance@example.com")
    property_id = await make_property(client, headers)
    base = date.today()
    end = base + timedelta(days=30)
    await _make_lease(client, headers, property_id, end_date=end)

    assert await run_expiry_reminders(db_session, base) == 1  # 30 days -> bucket 30
    assert await run_expiry_reminders(db_session, base + timedelta(days=22)) == 0  # 8 left
    assert await run_expiry_reminders(db_session, base + timedelta(days=23)) == 1  # 7 -> bucket 7


async def test_window_excludes_far(client, db_session, captured):
    headers = await landlord_headers(client, "windowfar@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    # 61 days out: outside the window.
    await _make_lease(client, headers, property_id, end_date=today + timedelta(days=61))
    assert await run_expiry_reminders(db_session, today) == 0


async def test_window_excludes_ended(client, db_session, captured):
    headers = await landlord_headers(client, "windowended@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    # Ended yesterday: end_date < today, excluded by the window.
    body = lease_body(
        start_date=str(today - timedelta(days=2)),
        end_date=str(today - timedelta(days=1)),
    )
    await client.post(
        f"/api/v1/properties/{property_id}/leases", json=body, headers=headers
    )
    assert await run_expiry_reminders(db_session, today) == 0


async def test_sends_on_expiry_day(client, db_session, captured):
    headers = await landlord_headers(client, "expiryday@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await _make_lease(client, headers, property_id, end_date=today)  # 0 days left
    assert await run_expiry_reminders(db_session, today) == 1


async def test_email_failure_still_records(client, db_session, monkeypatch):
    async def boom(to, subject, html):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("app.services.reminders.send_email", boom)
    headers = await landlord_headers(client, "boom@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    lease_id = await _make_lease(
        client, headers, property_id, end_date=today + timedelta(days=7)
    )

    count = await run_expiry_reminders(db_session, today)

    assert count == 1
    rows = (
        await db_session.execute(
            select(LeaseReminder).where(LeaseReminder.threshold_days == 7)
        )
    ).scalars().all()
    assert any(str(r.lease_id) == lease_id for r in rows)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_reminders.py -q`
Expected: FAIL with `ImportError: cannot import name 'run_expiry_reminders'`.

- [ ] **Step 3: Implement the service**

Replace the contents of `backend/app/services/reminders.py` with:

```python
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email
from app.models import Lease, LeaseReminder, Membership, Property, Role, User

logger = logging.getLogger(__name__)


def _bucket(days_left: int, thresholds: list[int]) -> int | None:
    """Smallest threshold T with days_left <= T when days_left >= 0, else None."""
    if days_left < 0:
        return None
    for threshold in sorted(thresholds):
        if days_left <= threshold:
            return threshold
    return None


async def _expiring_leases(
    session: AsyncSession, today: date, window_end: date
) -> list[tuple[Lease, str]]:
    """Leases (with property address) whose end_date is in [today, window_end], all orgs."""
    result = await session.execute(
        select(Lease, Property.address)
        .join(Property, Property.id == Lease.property_id)
        .where(Lease.end_date >= today, Lease.end_date <= window_end)
    )
    return list(result.all())


async def _manager_emails(session: AsyncSession, organization_id) -> list[str]:
    """Emails of the landlords and property managers in the organization."""
    result = await session.execute(
        select(User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == organization_id,
            Membership.role.in_([Role.landlord, Role.property_manager]),
        )
    )
    return [email for (email,) in result.all()]


def _roster_emails(lease: Lease) -> list[str]:
    """The tenant contact emails on the lease (main tenant plus co-tenants)."""
    return [lease.tenant_email] + [c["email"] for c in lease.co_tenants]


async def _already_sent(session: AsyncSession, lease_id, threshold: int) -> bool:
    result = await session.execute(
        select(LeaseReminder.id).where(
            LeaseReminder.lease_id == lease_id,
            LeaseReminder.threshold_days == threshold,
        )
    )
    return result.first() is not None


async def _safe_send(to: str, subject: str, html: str) -> None:
    """Send one reminder; a failure is logged and swallowed, never aborting the run."""
    try:
        await send_email(to, subject, html)
    except Exception:  # noqa: BLE001 - a failed email must not abort the run
        logger.exception("Failed to send expiry reminder to %s", to)


async def run_expiry_reminders(session: AsyncSession, today: date) -> int:
    """Email expiry reminders for leases entering a new threshold bucket.

    Returns the number of (lease, bucket) reminders sent this run.
    """
    thresholds = sorted(settings.reminder_thresholds)
    window_end = today + timedelta(days=thresholds[-1])
    sent = 0
    for lease, address in await _expiring_leases(session, today, window_end):
        days_left = (lease.end_date - today).days
        bucket = _bucket(days_left, thresholds)
        if bucket is None or await _already_sent(session, lease.id, bucket):
            continue

        link = f"{settings.frontend_url}/app/leases/{lease.id}"
        manager_subject = f"Lease expiring in {days_left} days - {address}"
        manager_html = (
            f"<p>The lease for {lease.tenant_name} at {address} expires on "
            f"{lease.end_date} ({days_left} days).</p>"
            f'<p><a href="{link}">View the lease</a></p>'
        )
        for email in await _manager_emails(session, lease.organization_id):
            await _safe_send(email, manager_subject, manager_html)

        tenant_subject = f"Your lease expires in {days_left} days - {address}"
        tenant_html = (
            f"<p>Your lease at {address} expires on {lease.end_date} "
            f"({days_left} days).</p>"
            "<p>Please contact your landlord about renewal.</p>"
            f'<p><a href="{settings.frontend_url}/app">Open your tenant portal</a></p>'
        )
        for email in _roster_emails(lease):
            await _safe_send(email, tenant_subject, tenant_html)

        session.add(LeaseReminder(lease_id=lease.id, threshold_days=bucket))
        await session.commit()
        sent += 1
    return sent
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_reminders.py -q`
Expected: PASS (bucket cases + all service tests).

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
git add backend/app/services/reminders.py backend/tests/test_reminders.py
git commit -m "Add run_expiry_reminders service (recipients, dedup, windows)"
git push
```
Then report and wait for approval.

---

### Task 4: APScheduler wiring + FastAPI lifespan

**Files:**
- Modify: `backend/pyproject.toml` (via `uv add apscheduler`)
- Create: `backend/app/core/scheduler.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `run_expiry_reminders` (Task 3); `SessionLocal` from `app.core.db`; `settings.reminders_enabled`, `settings.reminder_hour`.
- Produces: `scheduler` (an `AsyncIOScheduler`), `async _run_job()`, and `start_scheduler()` in `app.core.scheduler`; a `lifespan` in `app.main`.

- [ ] **Step 1: Add the dependency**

```bash
cd backend && uv add apscheduler
```
Expected: `apscheduler` added to `pyproject.toml` dependencies and `uv.lock` updated (APScheduler 3.x).

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_scheduler.py`:

```python
from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler


async def test_start_scheduler_registers_daily_job():
    try:
        start_scheduler()
        job = scheduler.get_job("expiry_reminders")
        assert job is not None
        assert job.trigger.fields[job.trigger.FIELD_NAMES.index("hour")].expressions[0].first == (
            settings.reminder_hour
        )
    finally:
        scheduler.shutdown(wait=False)
```

If the trigger-introspection assertion proves brittle across APScheduler versions, keep only `assert job is not None` — registering the job under the expected id is the behavior that matters.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scheduler.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.scheduler'`.

- [ ] **Step 4: Create the scheduler module**

Create `backend/app/core/scheduler.py`:

```python
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.reminders import run_expiry_reminders

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_job() -> None:
    """Open a session and run the expiry-reminder sweep for today."""
    async with SessionLocal() as session:
        count = await run_expiry_reminders(session, datetime.now(UTC).date())
    logger.info("expiry reminders: sent %s", count)


def start_scheduler() -> None:
    """Register the daily reminder job and start the scheduler."""
    scheduler.add_job(
        _run_job,
        CronTrigger(hour=settings.reminder_hour),
        id="expiry_reminders",
        replace_existing=True,
    )
    scheduler.start()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_scheduler.py -q`
Expected: PASS.

- [ ] **Step 6: Wire the lifespan into `main.py`**

Edit `backend/app/main.py`. Replace the module-level `mkdir` and add a lifespan. The full file becomes:

```python
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler
from app.routers.auth import router as auth_router
from app.routers.invitations import router as invitations_router
from app.routers.leases import router as leases_router
from app.routers.portal import router as portal_router
from app.routers.properties import router as properties_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the reminder scheduler on boot; stop it on shutdown."""
    if settings.reminders_enabled:
        start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Rental Management API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(properties_router)
app.include_router(invitations_router)
app.include_router(leases_router)
app.include_router(portal_router)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
```

- [ ] **Step 7: Full test run**

Run: `cd backend && uv run pytest -q`
Expected: all pass. (conftest uses httpx `ASGITransport`, which does not run lifespan, so the scheduler never starts during the suite.)

- [ ] **Step 8: Manual smoke test (scheduler starts under uvicorn)**

```bash
cd backend && uv run uvicorn app.main:app --port 8000
```
Expected: log line shows APScheduler added job `expiry_reminders`; no crash. Stop with Ctrl-C (clean shutdown). Then, optionally, prove the sweep runs by triggering it directly via the CLI in Task 5.

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
git add backend/pyproject.toml backend/uv.lock backend/app/core/scheduler.py \
        backend/app/main.py backend/tests/test_scheduler.py
git commit -m "Run expiry reminders daily via APScheduler in the app lifespan"
git push
```
Then report and wait for approval.

---

### Task 5: CLI entrypoint

**Files:**
- Create: `backend/app/jobs/__init__.py` (empty)
- Create: `backend/app/jobs/expiry_reminders.py`
- Test: `backend/tests/test_reminders_cli.py`

**Interfaces:**
- Consumes: `run_expiry_reminders` (Task 3); `SessionLocal` from `app.core.db`.
- Produces: `async _main()` in `app.jobs.expiry_reminders`, runnable via `uv run python -m app.jobs.expiry_reminders`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_reminders_cli.py`:

```python
from contextlib import asynccontextmanager

from app.jobs import expiry_reminders


async def test_main_prints_count(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    async def fake_run(session, today):
        return 3

    monkeypatch.setattr(expiry_reminders, "SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr(expiry_reminders, "run_expiry_reminders", fake_run)

    await expiry_reminders._main()

    assert "expiry reminders: sent 3" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_reminders_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jobs'`.

- [ ] **Step 3: Create the CLI**

Create `backend/app/jobs/__init__.py` (empty file).

Create `backend/app/jobs/expiry_reminders.py`:

```python
import asyncio
from datetime import UTC, datetime

from app.core.db import SessionLocal
from app.services.reminders import run_expiry_reminders


async def _main() -> None:
    async with SessionLocal() as session:
        count = await run_expiry_reminders(session, datetime.now(UTC).date())
    print(f"expiry reminders: sent {count}")


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_reminders_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Manual smoke test**

Prereq: local Postgres up, DB at head.
Run: `cd backend && uv run python -m app.jobs.expiry_reminders`
Expected: prints `expiry reminders: sent N` (N is however many buckets fire against local data; `0` on an empty DB) with no traceback.

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
git add backend/app/jobs backend/tests/test_reminders_cli.py
git commit -m "Add expiry-reminders CLI entrypoint"
git push
```
Then report and wait for approval.

---

### Task 6: Reminder-history schema + endpoint

**Files:**
- Modify: `backend/app/schemas/tenant.py`
- Modify: `backend/app/routers/leases.py`
- Test: `backend/tests/test_reminder_history.py`

**Interfaces:**
- Consumes: `LeaseReminder` (Task 1); existing `manager` dep, `get_owned_lease` in `app.routers.leases`.
- Produces: `LeaseReminderInfo(threshold_days: int, sent_at: datetime)` in `app.schemas.tenant`; `GET /api/v1/leases/{lease_id}/reminders -> list[LeaseReminderInfo]` (newest `sent_at` first).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_reminder_history.py`:

```python
import uuid
from datetime import datetime

from app.models import LeaseReminder
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _make_lease_id(client, headers, property_id) -> str:
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]


async def test_reminder_history_newest_first(client, db_session):
    headers = await landlord_headers(client, "rh@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)

    older = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    newer = datetime.fromisoformat("2026-02-01T00:00:00+00:00")
    db_session.add(
        LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=60, sent_at=older)
    )
    db_session.add(
        LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30, sent_at=newer)
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/leases/{lease_id}/reminders", headers=headers)
    assert response.status_code == 200
    assert [r["threshold_days"] for r in response.json()] == [30, 60]


async def test_reminder_history_cross_org_is_404(client):
    org_a = await landlord_headers(client, "rha@example.com")
    org_b = await landlord_headers(client, "rhb@example.com")
    property_id = await make_property(client, org_a)
    lease_id = await _make_lease_id(client, org_a, property_id)
    response = await client.get(f"/api/v1/leases/{lease_id}/reminders", headers=org_b)
    assert response.status_code == 404


async def test_reminder_history_requires_auth(client):
    headers = await landlord_headers(client, "rhauth@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)
    response = await client.get(f"/api/v1/leases/{lease_id}/reminders")
    assert response.status_code == 401
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && uv run pytest tests/test_reminder_history.py -q`
Expected: FAIL (404 for the history route — it does not exist yet — so the newest-first test fails on status 200).

- [ ] **Step 3: Add the schema**

Edit `backend/app/schemas/tenant.py`. Add `datetime` to the `from datetime import ...` line (it currently imports `date`), so it reads `from datetime import date, datetime`. Then add at the end of the file:

```python
class LeaseReminderInfo(BaseModel):
    threshold_days: int
    sent_at: datetime
```

- [ ] **Step 4: Add the endpoint**

Edit `backend/app/routers/leases.py`.

Add `LeaseReminder` to the `from app.models import (...)` block (keep it alphabetical: after `Lease`), and add `LeaseReminderInfo` to the `from app.schemas.tenant import ...` line.

Append this endpoint at the end of the file (mirrors the existing `list_lease_invitations`):

```python
@router.get("/leases/{lease_id}/reminders", response_model=list[LeaseReminderInfo])
async def list_lease_reminders(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[LeaseReminderInfo]:
    """List expiry reminders sent for the given lease, newest first."""
    await get_owned_lease(lease_id, membership, session)
    result = await session.execute(
        select(LeaseReminder.threshold_days, LeaseReminder.sent_at)
        .where(LeaseReminder.lease_id == lease_id)
        .order_by(LeaseReminder.sent_at.desc())
    )
    return [
        LeaseReminderInfo(threshold_days=threshold, sent_at=sent_at)
        for threshold, sent_at in result.all()
    ]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_reminder_history.py -q`
Expected: PASS (3 tests).

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
git add backend/app/schemas/tenant.py backend/app/routers/leases.py backend/tests/test_reminder_history.py
git commit -m "Add GET /leases/{id}/reminders history endpoint"
git push
```
Then report and wait for approval.

---

### Task 7: Frontend lib client + "Expiry reminders" section

**Files:**
- Modify: `frontend/src/lib/tenants.ts`
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/leases/{id}/reminders` (Task 6).
- Produces: `LeaseReminderInfo { threshold_days: number; sent_at: string }` and `listLeaseReminders(leaseId)` in `@/lib/tenants`.

- [ ] **Step 1: Add the lib client**

Edit `frontend/src/lib/tenants.ts`. Add the interface after `LeaseInvitationInfo`:

```typescript
export interface LeaseReminderInfo {
  threshold_days: number;
  sent_at: string;
}
```

Add the function after `revokeLeaseInvitation`:

```typescript
export function listLeaseReminders(leaseId: string) {
  return apiFetch<LeaseReminderInfo[]>(`/api/v1/leases/${leaseId}/reminders`);
}
```

- [ ] **Step 2: Wire reminders into the lease-detail page**

Edit `frontend/src/app/app/leases/[leaseId]/page.tsx`.

Add `LeaseReminderInfo`, `listLeaseReminders` to the existing import from `@/lib/tenants`:

```tsx
import {
  inviteTenant,
  listLeaseInvitations,
  listLeaseReminders,
  listLeaseTenants,
  revokeLeaseInvitation,
  type LeaseInvitationInfo,
  type LeaseReminderInfo,
  type LeaseTenantInfo,
} from "@/lib/tenants";
```

Add reminder state next to `pending`:

```tsx
  const [reminders, setReminders] = useState<LeaseReminderInfo[]>([]);
```

In the `useEffect`, add a fetch alongside the existing `listLeaseInvitations` block (respecting the `active` guard):

```tsx
    listLeaseReminders(leaseId)
      .then((r) => {
        if (active) setReminders(r);
      })
      .catch(() => {
        if (active) setReminders([]);
      });
```

- [ ] **Step 3: Render the read-only section**

In the same file, add this `<section>` immediately after the closing `</section>` of the Tenants block (still inside the non-editing `<>...</>`):

```tsx
          <section className="mt-8">
            <h2 className="mb-2 font-semibold">Expiry reminders</h2>
            {reminders.length === 0 ? (
              <p className="text-sm text-gray-500">No reminders sent yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-gray-700">
                {reminders.map((r, i) => (
                  <li key={i}>
                    {r.threshold_days}-day reminder - sent{" "}
                    {new Date(r.sent_at).toLocaleDateString()}
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
git add frontend/src/lib/tenants.ts "frontend/src/app/app/leases/[leaseId]/page.tsx"
git commit -m "Show expiry-reminder history on the lease detail page"
git push
```
Then report and wait for approval.

---

### Task 8: e2e — empty-state section renders

**Files:**
- Modify: `frontend/e2e/tenant-invite.spec.ts`

**Interfaces:**
- Consumes: the "Expiry reminders" section (Task 7); the history endpoint (Task 6).

- [ ] **Step 1: Restart the local backend (new endpoint)**

```bash
lsof -ti tcp:8000 | xargs kill
cd backend && uv run uvicorn app.main:app --port 8000
```
(Leave it running in a second shell for the e2e run.)

- [ ] **Step 2: Add the assertions**

Edit `frontend/e2e/tenant-invite.spec.ts`. At the end of the existing test (after the Revoke/Invite assertions, before the closing `});`), add:

```typescript
  // A fresh lease has no reminders yet — the read-only section shows its empty state.
  await expect(page.getByRole("heading", { name: "Expiry reminders" })).toBeVisible();
  await expect(page.getByText("No reminders sent yet.")).toBeVisible();
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
git commit -m "Assert expiry-reminder empty-state renders on lease detail"
git push
gh run watch --exit-status
```
Expected: all three CI jobs (backend, frontend, e2e) green.

- [ ] **Step 7: Report — Milestone 3.4 complete**

Report: expiry reminders now send to landlords/PMs + tenant roster at 60/30/7-day thresholds (dedup by `UNIQUE(lease_id, threshold_days)`), driven by APScheduler in the app lifespan with a `uv run python -m app.jobs.expiry_reminders` CLI, and managers see the reminder history on the lease detail page. Wait for direction (Milestone 4: rent charges + payments + dashboard stats).

---

## Self-Review

**Spec coverage:**
- Recipients (managers + roster) -> Task 3 `_manager_emails` + `_roster_emails`, verified in `test_sends_to_managers_and_roster`. ✓
- Thresholds 60/30/7 + bucketing (>=0 guard, missed-day robustness) -> Task 2 `_bucket` + Task 3 window, verified in `test_bucket` + `test_bucket_advances_over_time` + `test_window_excludes_far` + `test_window_excludes_ended` + `test_sends_on_expiry_day`. ✓
- Dedup table + UNIQUE + CASCADE -> Task 1 model/migration, verified in `test_unique_lease_threshold` + `test_delete_lease_cascades_reminders` + `test_dedup_runs_twice_sends_once`. ✓
- Email-failure safety -> Task 3 `_safe_send`, verified in `test_email_failure_still_records`. ✓
- APScheduler + lifespan + `reminders_enabled` -> Task 4. ✓
- CLI -> Task 5. ✓
- History endpoint + schema -> Task 6. ✓
- Frontend section + lib -> Task 7; e2e empty-state -> Task 8. ✓
- Settings (`reminders_enabled`, `reminder_thresholds`, `reminder_hour`) -> Task 1. ✓
- Out of scope (per-org config, payments/rent-tracking, tenant-overview page) -> not planned. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the only `<rev>` is the Alembic-generated revision id (a real convention). ✓

**Type consistency:** `run_expiry_reminders(session, today) -> int`, `_bucket(days_left, thresholds) -> int | None`, `LeaseReminder(lease_id, threshold_days, sent_at)`, `LeaseReminderInfo(threshold_days, sent_at)` used identically across backend tasks; frontend `LeaseReminderInfo { threshold_days: number; sent_at: string }` and `listLeaseReminders(leaseId)` match the endpoint. Monkeypatch target `app.services.reminders.send_email` matches the module-bound import. ✓
