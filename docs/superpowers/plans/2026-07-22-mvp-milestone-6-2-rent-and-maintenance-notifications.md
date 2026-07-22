# Milestone 6.2: Rent and Maintenance Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the last two notification sources — scheduled rent reminders (due soon, overdue) and event-driven maintenance updates — each sending email and writing to the M6.1 inbox.

**Architecture:** A scheduled sweep (`services/rent_reminders.py`, shaped like `services/reminders.py`) and event handlers called from the maintenance routes (`services/maintenance_notify.py`). Both reach the outside world only through `services/notify.py`.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, APScheduler. No new dependencies, no frontend changes.

## Global Constraints

- Package manager: `uv` only (`uv run ...`, `uv add ...`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before EVERY push, from `backend/`, in order:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- **Ruff gotcha:** test files keep ALL imports at the top (E402). `ruff check --fix` removes unused imports but NOT unused module-level assignments.
- Each task ends with: full test run -> ruff sequence -> commit -> `git push` (CI) -> report -> WAIT for approval.
- Migration is enum-free; verify upgrade -> downgrade -> upgrade. Current head: `0e07c7d866ed`.
- `kind` and `category` are plain strings, never PG enums.
- Backend tests: `cd backend && uv run pytest -q`.
- Do not run the reminder jobs against the dev database: `EMAIL_FROM=onboarding@resend.dev` reaches Resend for real, and mail addressed to the account owner's own address would be delivered.

## Settled Product Rules

1. Partially paid charges still get overdue reminders, quoting the remaining balance.
2. Overdue escalation stops at 30 days — at most three overdue reminders per charge.
3. Only a real status change notifies the tenant; no-op status writes and priority-only edits send nothing.
4. One reminder per charge, matching the `(charge_id, kind)` dedup key.

---

## Task Overview

1. `ChargeReminder` ledger model + migration
2. `_due_soon` / `_overdue_kind` / `_kind` pure helpers
3. `run_rent_reminders` service
4. Scheduler job + config + CLI
5. Maintenance event notifications

---

### Task 1: `ChargeReminder` ledger model + migration

**Files:**
- Create: `backend/app/models/charge_reminder.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_charge_reminders.py`
- Test: `backend/tests/test_charge_reminder_model.py`

**Interfaces:**
- Produces: `ChargeReminder(id, charge_id, kind, created_at)` importable from `app.models`, with `UNIQUE(charge_id, kind)`.

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/test_charge_reminder_model.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Charge, ChargeReminder, Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease(client, db_session, headers, address):
    property_id = await make_property(client, headers, address)
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    return (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()


async def _charge(db_session, lease):
    charge = Charge(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        due_date=date(2026, 1, 1),
        amount_due=Decimal("1500"),
    )
    db_session.add(charge)
    await db_session.commit()
    return charge


async def test_insert_and_read(client, db_session):
    headers = await landlord_headers(client, "crmodel@example.com")
    charge = await _charge(db_session, await _lease(client, db_session, headers, "Ledger St"))

    db_session.add(ChargeReminder(charge_id=charge.id, kind="overdue_7"))
    await db_session.commit()

    rows = (await db_session.execute(select(ChargeReminder))).scalars().all()
    assert len(rows) == 1
    assert rows[0].kind == "overdue_7"
    assert rows[0].created_at is not None


async def test_same_kind_twice_is_rejected(client, db_session):
    headers = await landlord_headers(client, "crdup@example.com")
    charge = await _charge(db_session, await _lease(client, db_session, headers, "Dup St"))

    db_session.add(ChargeReminder(charge_id=charge.id, kind="due_soon"))
    await db_session.commit()

    db_session.add(ChargeReminder(charge_id=charge.id, kind="due_soon"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_charge_reminder_model.py -q`
Expected: FAIL with `ImportError: cannot import name 'ChargeReminder' from 'app.models'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/charge_reminder.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ChargeReminder(Base):
    __tablename__ = "charge_reminders"
    __table_args__ = (UniqueConstraint("charge_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    charge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("charges.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Register the model**

Edit `backend/app/models/__init__.py`: add `from app.models.charge_reminder import ChargeReminder`
directly after the `Charge` import, and `"ChargeReminder",` after `"Charge",` in `__all__`.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_charge_reminder_model.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Generate and verify the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add charge reminders"
```

Confirm the file creates `charge_reminders` with the unique constraint on `(charge_id, kind)`, the
`charge_id` index, `down_revision = "0e07c7d866ed"`, and a `downgrade()` that drops the index then
the table. No enums are involved. Verify the round-trip:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: all three succeed.

- [ ] **Step 7: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/models/charge_reminder.py backend/app/models/__init__.py \
        backend/alembic/versions backend/tests/test_charge_reminder_model.py
git commit -m "Add ChargeReminder ledger model and migration"
git push
```
Then report and wait for approval.

---

### Task 2: Reminder-kind pure helpers

**Files:**
- Create: `backend/app/services/rent_reminders.py`
- Test: `backend/tests/test_rent_reminder_kinds.py`

**Interfaces:**
- Produces: `DUE_SOON = "due_soon"`, `DUE_SOON_LEAD = 3`, `OVERDUE_THRESHOLDS = [7, 14, 30]`, `_due_soon(days_until) -> bool`, `_overdue_kind(days_overdue) -> str | None`, `_kind(due_date, today) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_rent_reminder_kinds.py`:

```python
from datetime import date, timedelta

import pytest

from app.services.rent_reminders import _due_soon, _kind, _overdue_kind


@pytest.mark.parametrize(
    ("days_until", "expected"),
    [(-1, False), (0, True), (1, True), (3, True), (4, False)],
)
def test_due_soon(days_until, expected):
    assert _due_soon(days_until) is expected


@pytest.mark.parametrize(
    ("days_overdue", "expected"),
    [
        (0, None),
        (6, None),
        (7, "overdue_7"),
        (13, "overdue_7"),
        (14, "overdue_14"),
        (29, "overdue_14"),
        (30, "overdue_30"),
        (45, "overdue_30"),
    ],
)
def test_overdue_kind(days_overdue, expected):
    assert _overdue_kind(days_overdue) == expected


@pytest.mark.parametrize(
    ("offset", "expected"),
    [(4, None), (3, "due_soon"), (0, "due_soon"), (-6, None), (-7, "overdue_7"), (-30, "overdue_30")],
)
def test_kind_from_dates(offset, expected):
    today = date(2026, 6, 15)
    assert _kind(today + timedelta(days=offset), today) == expected
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_rent_reminder_kinds.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.rent_reminders'`.

- [ ] **Step 3: Write the helpers**

Create `backend/app/services/rent_reminders.py`:

```python
from datetime import date

DUE_SOON = "due_soon"
DUE_SOON_LEAD = 3
OVERDUE_THRESHOLDS = [7, 14, 30]


def _due_soon(days_until: int) -> bool:
    """True from DUE_SOON_LEAD days before the due date through the due date itself."""
    return 0 <= days_until <= DUE_SOON_LEAD


def _overdue_kind(days_overdue: int) -> str | None:
    """The largest overdue threshold reached, or None below the first one.

    Largest-reached rather than smallest-crossed keeps the job self-healing: after a
    missed run, a charge 16 days overdue still gets overdue_14 instead of stalling.
    """
    reached = [t for t in OVERDUE_THRESHOLDS if t <= days_overdue]
    return f"overdue_{max(reached)}" if reached else None


def _kind(due_date: date, today: date) -> str | None:
    """The reminder kind a charge qualifies for today, if any."""
    days_until = (due_date - today).days
    if days_until >= 0:
        return DUE_SOON if _due_soon(days_until) else None
    return _overdue_kind(-days_until)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_rent_reminder_kinds.py -q`
Expected: PASS (19 parametrized cases).

- [ ] **Step 5: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 6: Commit and push**

```bash
git add backend/app/services/rent_reminders.py backend/tests/test_rent_reminder_kinds.py
git commit -m "Add rent reminder kind helpers"
git push
```
Then report and wait for approval.

---

### Task 3: `run_rent_reminders` service

**Files:**
- Modify: `backend/app/services/rent_reminders.py`
- Test: `backend/tests/test_rent_reminders.py`

**Interfaces:**
- Consumes: `_kind` (Task 2); `ChargeReminder` (Task 1); `payments.lease_statuses(session, lease_id, today) -> list[ChargeStatus]` where `ChargeStatus` has `.charge`, `.amount_paid`, `.status` (`"unpaid" | "partial" | "paid"`), `.overdue`; from `notify`: `roster_emails`, `manager_emails`, `lease_tenant_user_ids`, `manager_user_ids`, `notify_users`, `safe_send`.
- Produces: `run_rent_reminders(session, today) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_rent_reminders.py`:

```python
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Charge, ChargeReminder, Lease, Notification
from app.services.rent_reminders import run_rent_reminders
from tests.test_leases import lease_body, make_property
from tests.test_portal import onboard_tenant
from tests.test_properties_crud import landlord_headers

TODAY = date.today()


@pytest.fixture
def captured(monkeypatch):
    """Collect (to, subject) for every email the service sends."""
    calls: list[tuple[str, str]] = []

    async def fake_send(to, subject, html):
        calls.append((to, subject))

    monkeypatch.setattr("app.services.notify.send_email", fake_send)
    return calls


async def _lease(client, db_session, headers, address):
    property_id = await make_property(client, headers, address)
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(tenant_email="renter@example.com"),
            headers=headers,
        )
    ).json()["id"]
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    return lease_id, lease


async def _charge(db_session, lease, due_date, amount="1500"):
    charge = Charge(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        period_start=due_date,
        period_end=due_date + timedelta(days=29),
        due_date=due_date,
        amount_due=Decimal(amount),
    )
    db_session.add(charge)
    await db_session.commit()
    return charge


async def _notifications(db_session):
    return (await db_session.execute(select(Notification))).scalars().all()


async def test_due_soon_goes_to_tenants_only(client, db_session, captured):
    headers = await landlord_headers(client, "rrdue@example.com")
    _, lease = await _lease(client, db_session, headers, "Due St")
    await _charge(db_session, lease, TODAY + timedelta(days=2))

    assert await run_rent_reminders(db_session, TODAY) == 1

    recipients = {to for to, _ in captured}
    assert "renter@example.com" in recipients
    assert "rrdue@example.com" not in recipients  # the landlord is not told about upcoming rent
    rows = await _notifications(db_session)
    assert {r.category for r in rows} == {"rent_due"}


async def test_overdue_goes_to_tenants_and_managers(client, db_session, captured):
    headers = await landlord_headers(client, "rrover@example.com")
    _, lease = await _lease(client, db_session, headers, "Late St")
    await _charge(db_session, lease, TODAY - timedelta(days=7))

    assert await run_rent_reminders(db_session, TODAY) == 1

    recipients = {to for to, _ in captured}
    assert "renter@example.com" in recipients
    assert "rrover@example.com" in recipients
    rows = await _notifications(db_session)
    assert {r.category for r in rows} == {"rent_overdue"}


async def test_rerun_sends_nothing_more(client, db_session, captured):
    headers = await landlord_headers(client, "rrdedup@example.com")
    _, lease = await _lease(client, db_session, headers, "Dedup St")
    await _charge(db_session, lease, TODAY - timedelta(days=7))

    assert await run_rent_reminders(db_session, TODAY) == 1
    assert await run_rent_reminders(db_session, TODAY) == 0
    assert len(await _notifications(db_session)) == 1


async def test_partial_payment_still_reminded_with_remaining_balance(client, db_session, captured):
    headers = await landlord_headers(client, "rrpart@example.com")
    lease_id, lease = await _lease(client, db_session, headers, "Part St")
    await _charge(db_session, lease, TODAY - timedelta(days=7))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 500, "paid_on": str(TODAY), "method": "cash"},
        headers=headers,
    )

    assert await run_rent_reminders(db_session, TODAY) == 1

    body = (await _notifications(db_session))[0].body
    assert "1000" in body  # 1500 due minus 500 paid


async def test_paid_charge_is_skipped(client, db_session, captured):
    headers = await landlord_headers(client, "rrpaid@example.com")
    lease_id, lease = await _lease(client, db_session, headers, "Paid St")
    await _charge(db_session, lease, TODAY - timedelta(days=7))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 1500, "paid_on": str(TODAY), "method": "cash"},
        headers=headers,
    )

    assert await run_rent_reminders(db_session, TODAY) == 0
    assert await _notifications(db_session) == []


async def test_escalation_advances_over_time(client, db_session, captured):
    headers = await landlord_headers(client, "rresc@example.com")
    _, lease = await _lease(client, db_session, headers, "Esc St")
    due = TODAY - timedelta(days=7)
    charge = await _charge(db_session, lease, due)

    assert await run_rent_reminders(db_session, TODAY) == 1  # overdue_7
    assert await run_rent_reminders(db_session, due + timedelta(days=10)) == 0  # still overdue_7
    assert await run_rent_reminders(db_session, due + timedelta(days=14)) == 1  # overdue_14
    assert await run_rent_reminders(db_session, due + timedelta(days=30)) == 1  # overdue_30
    assert await run_rent_reminders(db_session, due + timedelta(days=60)) == 0  # capped

    kinds = (
        (await db_session.execute(select(ChargeReminder.kind).where(ChargeReminder.charge_id == charge.id)))
        .scalars()
        .all()
    )
    assert set(kinds) == {"overdue_7", "overdue_14", "overdue_30"}


async def test_joined_tenant_gets_an_inbox_notification(client, db_session, captured):
    headers = await landlord_headers(client, "rrinbox@example.com")
    lease_id, lease = await _lease(client, db_session, headers, "Inbox St")
    await onboard_tenant(client, db_session, headers, lease_id, "rrinbox-t@example.com")
    await _charge(db_session, lease, TODAY + timedelta(days=2))

    await run_rent_reminders(db_session, TODAY)

    rows = await _notifications(db_session)
    assert len(rows) == 1  # tenants only for due_soon
    assert rows[0].link == f"/app/leases/{lease_id}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_rent_reminders.py -q`
Expected: FAIL with `ImportError: cannot import name 'run_rent_reminders'`.

- [ ] **Step 3: Add the imports and the copy builder**

Edit `backend/app/services/rent_reminders.py`. Replace the single `from datetime import date` line
with the full import block, and append the copy builder after `_kind`:

```python
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Charge, ChargeReminder, Lease, Property
from app.services.notify import (
    lease_tenant_user_ids,
    manager_emails,
    manager_user_ids,
    notify_users,
    roster_emails,
    safe_send,
)
from app.services.payments import ChargeStatus, lease_statuses
```

```python
@dataclass
class _Copy:
    subject: str
    html: str
    category: str
    title: str
    body: str


def _copy_for(kind: str, address: str, charge: Charge, owed: Decimal, url: str, today: date) -> _Copy:
    """The email and in-app wording for one reminder kind."""
    if kind == DUE_SOON:
        return _Copy(
            subject=f"Rent due {charge.due_date} - {address}",
            html=(
                f"<p>Rent of ${owed} for {address} is due on {charge.due_date}.</p>"
                f'<p><a href="{url}">View your lease</a></p>'
            ),
            category="rent_due",
            title=f"Rent due {charge.due_date}",
            body=f"${owed} for {address} is due on {charge.due_date}.",
        )
    days = (today - charge.due_date).days
    return _Copy(
        subject=f"Rent overdue by {days} days - {address}",
        html=(
            f"<p>Rent of ${owed} for {address} was due on {charge.due_date} "
            f"({days} days ago).</p>"
            f'<p><a href="{url}">View the lease</a></p>'
        ),
        category="rent_overdue",
        title=f"Rent overdue by {days} days",
        body=f"${owed} for {address} was due on {charge.due_date}.",
    )
```

- [ ] **Step 4: Add the query and dedup helpers**

Append to `backend/app/services/rent_reminders.py`:

```python
async def _leases_with_due_charges(
    session: AsyncSession, today: date
) -> list[tuple[Lease, str]]:
    """Leases (with property address) holding a charge due on or before the lead horizon."""
    horizon = today + timedelta(days=DUE_SOON_LEAD)
    result = await session.execute(
        select(Lease, Property.address)
        .join(Property, Property.id == Lease.property_id)
        .where(
            Lease.id.in_(select(Charge.lease_id).where(Charge.due_date <= horizon))
        )
    )
    return list(result.all())


async def _already_sent(session: AsyncSession, charge_id, kind: str) -> bool:
    result = await session.execute(
        select(ChargeReminder.id).where(
            ChargeReminder.charge_id == charge_id, ChargeReminder.kind == kind
        )
    )
    return result.first() is not None
```

- [ ] **Step 5: Add the sender and the entry point**

Append to `backend/app/services/rent_reminders.py`:

```python
async def _send(
    session: AsyncSession,
    lease: Lease,
    address: str,
    status: ChargeStatus,
    kind: str,
    today: date,
) -> None:
    """Email the recipients for this kind and post the matching in-app notifications."""
    charge = status.charge
    owed = charge.amount_due - status.amount_paid
    link = f"/app/leases/{lease.id}"
    copy = _copy_for(kind, address, charge, owed, f"{settings.frontend_url}{link}", today)

    emails = roster_emails(lease)
    user_ids = await lease_tenant_user_ids(session, lease.id)
    if kind != DUE_SOON:
        emails += await manager_emails(session, lease.organization_id)
        user_ids += await manager_user_ids(session, lease.organization_id)

    for email in emails:
        await safe_send(email, copy.subject, copy.html)
    await notify_users(
        session, user_ids, lease.organization_id, copy.category, copy.title, copy.body, link
    )


async def run_rent_reminders(session: AsyncSession, today: date) -> int:
    """Remind tenants of rent due soon, and tenants plus managers of overdue rent.

    Returns the number of (charge, kind) reminders sent this run.
    """
    sent = 0
    for lease, address in await _leases_with_due_charges(session, today):
        for status in await lease_statuses(session, lease.id, today):
            kind = _kind(status.charge.due_date, today)
            if kind is None or status.status == "paid":
                continue
            if await _already_sent(session, status.charge.id, kind):
                continue

            await _send(session, lease, address, status, kind, today)
            session.add(ChargeReminder(charge_id=status.charge.id, kind=kind))
            await session.commit()
            sent += 1
    return sent
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_rent_reminders.py -q`
Expected: PASS (7 tests).

- [ ] **Step 7: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/services/rent_reminders.py backend/tests/test_rent_reminders.py
git commit -m "Add rent due and overdue reminder sweep"
git push
```
Then report and wait for approval.

---

### Task 4: Scheduler job + config + CLI

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/scheduler.py`
- Create: `backend/app/jobs/rent_reminders.py`
- Modify: `backend/tests/test_scheduler.py`
- Test: `backend/tests/test_rent_reminders_cli.py`

**Interfaces:**
- Consumes: `run_rent_reminders(session, today) -> int` (Task 3).
- Produces: `settings.rent_reminder_hour`; a scheduler job with id `rent_reminders`; `python -m app.jobs.rent_reminders`.

- [ ] **Step 1: Update the scheduler test to expect three jobs**

Edit `backend/tests/test_scheduler.py` — rename the test and add the third assertion block:

```python
from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler


async def test_start_scheduler_registers_all_daily_jobs():
    try:
        start_scheduler()

        reminders = scheduler.get_job("expiry_reminders")
        assert reminders is not None
        assert f"hour='{settings.reminder_hour}'" in str(reminders.trigger)

        charges = scheduler.get_job("generate_charges")
        assert charges is not None
        assert f"hour='{settings.charge_generation_hour}'" in str(charges.trigger)

        rent = scheduler.get_job("rent_reminders")
        assert rent is not None
        assert f"hour='{settings.rent_reminder_hour}'" in str(rent.trigger)
    finally:
        scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Write the failing CLI test**

Create `backend/tests/test_rent_reminders_cli.py`:

```python
from contextlib import asynccontextmanager

from app.jobs import rent_reminders as cli


async def test_main_prints_count(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    async def fake_run(session, today):
        return 4

    monkeypatch.setattr(cli, "SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr(cli, "run_rent_reminders", fake_run)

    await cli._main()

    assert "rent reminders: sent 4" in capsys.readouterr().out
```

- [ ] **Step 3: Run both to verify they fail**

Run: `cd backend && uv run pytest tests/test_scheduler.py tests/test_rent_reminders_cli.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'rent_reminder_hour'` and
`ModuleNotFoundError: No module named 'app.jobs.rent_reminders'`.

- [ ] **Step 4: Add the setting**

Edit `backend/app/core/config.py`, directly below the `charge_generation_hour` line:

```python
    # Rent reminders: daily job run hour (due-soon lead and overdue thresholds live in the service).
    rent_reminder_hour: int = 9
```

- [ ] **Step 5: Register the third job**

Edit `backend/app/core/scheduler.py`. Add the import
`from app.services.rent_reminders import run_rent_reminders`, add the job function after
`_charges_job`:

```python
async def _rent_job() -> None:
    """Open a session and send rent due-soon and overdue reminders for today."""
    async with SessionLocal() as session:
        count = await run_rent_reminders(session, datetime.now(UTC).date())
    logger.info("rent reminders: sent %s", count)
```

and register it inside `start_scheduler()`, before `scheduler.start()`:

```python
    scheduler.add_job(
        _rent_job,
        CronTrigger(hour=settings.rent_reminder_hour),
        id="rent_reminders",
        replace_existing=True,
    )
```

- [ ] **Step 6: Add the CLI entrypoint**

Create `backend/app/jobs/rent_reminders.py`:

```python
import asyncio
from datetime import UTC, datetime

from app.core.db import SessionLocal
from app.services.rent_reminders import run_rent_reminders


async def _main() -> None:
    async with SessionLocal() as session:
        count = await run_rent_reminders(session, datetime.now(UTC).date())
    print(f"rent reminders: sent {count}")


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 7: Run to verify they pass**

Run: `cd backend && uv run pytest tests/test_scheduler.py tests/test_rent_reminders_cli.py -q`
Expected: PASS (2 tests). Do NOT run the CLI against the dev database — it would reach Resend.

- [ ] **Step 8: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 9: Commit and push**

```bash
git add backend/app/core/config.py backend/app/core/scheduler.py \
        backend/app/jobs/rent_reminders.py backend/tests/test_scheduler.py \
        backend/tests/test_rent_reminders_cli.py
git commit -m "Schedule the rent reminder job and add its CLI"
git push
```
Then report and wait for approval.

---

### Task 5: Maintenance event notifications

**Files:**
- Modify: `backend/app/services/notify.py`
- Create: `backend/app/services/maintenance_notify.py`
- Modify: `backend/app/routers/maintenance.py`
- Test: `backend/tests/test_maintenance_notify.py`

**Interfaces:**
- Consumes: `manager_emails`, `manager_user_ids`, `notify_users`, `safe_send` from `notify`; `MaintenanceRequest`, `MaintenanceStatus`.
- Produces: `notify.user_emails(session, user_ids) -> list[str]`; `notify_new_request(session, request)`, `notify_status_change(session, request)`, `notify_cancelled(session, request)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_maintenance_notify.py`:

```python
from sqlalchemy import select

from app.models import Membership, Notification, User
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _user_id(db_session, email):
    return (
        await db_session.execute(select(User.id).where(User.email == email))
    ).scalar_one()


async def _categories(db_session, user_id):
    rows = (
        await db_session.execute(
            select(Notification.category).where(Notification.user_id == user_id)
        )
    ).scalars().all()
    return sorted(rows)


async def _setup(client, db_session, prefix):
    headers = await landlord_headers(client, f"{prefix}@example.com")
    lease_id = await make_lease(client, headers, f"{prefix} St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, f"{prefix}-t@example.com")
    request_id = (
        await client.post(
            f"/api/v1/me/leases/{lease_id}/maintenance",
            json={"title": "Leaking tap", "description": "Kitchen", "priority": "medium"},
            headers=tenant,
        )
    ).json()["id"]
    return headers, tenant, request_id


async def test_new_request_notifies_managers_only(client, db_session):
    headers, tenant, _ = await _setup(client, db_session, "mnnew")
    landlord_id = await _user_id(db_session, "mnnew@example.com")
    tenant_id = await _user_id(db_session, "mnnew-t@example.com")

    assert await _categories(db_session, landlord_id) == ["maintenance_new"]
    assert await _categories(db_session, tenant_id) == []


async def test_status_change_notifies_the_reporting_tenant(client, db_session):
    headers, tenant, request_id = await _setup(client, db_session, "mnstat")
    tenant_id = await _user_id(db_session, "mnstat-t@example.com")

    await client.patch(
        f"/api/v1/maintenance/{request_id}", json={"status": "in_progress"}, headers=headers
    )

    assert await _categories(db_session, tenant_id) == ["maintenance_status"]


async def test_same_status_notifies_nobody(client, db_session):
    headers, tenant, request_id = await _setup(client, db_session, "mnsame")
    tenant_id = await _user_id(db_session, "mnsame-t@example.com")

    await client.patch(
        f"/api/v1/maintenance/{request_id}", json={"status": "open"}, headers=headers
    )

    assert await _categories(db_session, tenant_id) == []


async def test_priority_only_change_notifies_nobody(client, db_session):
    headers, tenant, request_id = await _setup(client, db_session, "mnprio")
    tenant_id = await _user_id(db_session, "mnprio-t@example.com")

    await client.patch(
        f"/api/v1/maintenance/{request_id}", json={"priority": "urgent"}, headers=headers
    )

    assert await _categories(db_session, tenant_id) == []


async def test_tenant_cancel_notifies_managers(client, db_session):
    headers, tenant, request_id = await _setup(client, db_session, "mncan")
    landlord_id = await _user_id(db_session, "mncan@example.com")

    await client.post(f"/api/v1/me/maintenance/{request_id}/cancel", headers=tenant)

    assert await _categories(db_session, landlord_id) == [
        "maintenance_cancelled",
        "maintenance_new",
    ]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_maintenance_notify.py -q`
Expected: FAIL — no notifications are written, so the first, second and last tests see `[]`.
(`test_same_status_notifies_nobody` and `test_priority_only_change_notifies_nobody` pass
vacuously at this point; they are the regression guards for Step 5.)

- [ ] **Step 3: Add `user_emails` to notify.py**

Append to `backend/app/services/notify.py`:

```python
async def user_emails(session: AsyncSession, user_ids) -> list[str]:
    """The emails of specific users."""
    result = await session.execute(select(User.email).where(User.id.in_(user_ids)))
    return [email for (email,) in result.all()]
```

- [ ] **Step 4: Create the maintenance notification service**

Create `backend/app/services/maintenance_notify.py`:

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import MaintenanceRequest, Property
from app.services.notify import (
    manager_emails,
    manager_user_ids,
    notify_users,
    safe_send,
    user_emails,
)

MANAGER_LINK = "/app/maintenance"
TENANT_LINK = "/app"


async def _address(session: AsyncSession, request: MaintenanceRequest) -> str:
    return (
        await session.execute(select(Property.address).where(Property.id == request.property_id))
    ).scalar_one()


async def _managers(session: AsyncSession, organization_id) -> tuple[list[str], list[uuid.UUID]]:
    """The organization's manager emails and user ids."""
    return (
        await manager_emails(session, organization_id),
        await manager_user_ids(session, organization_id),
    )


async def _deliver(
    session: AsyncSession,
    request: MaintenanceRequest,
    emails: list[str],
    user_ids: list[uuid.UUID],
    category: str,
    subject: str,
    title: str,
    body: str,
    link: str,
) -> None:
    """Email the recipients, post the in-app notifications, and commit them."""
    html = f'<p>{body}</p><p><a href="{settings.frontend_url}{link}">Open the request</a></p>'
    for email in emails:
        await safe_send(email, subject, html)
    await notify_users(session, user_ids, request.organization_id, category, title, body, link)
    await session.commit()


async def notify_new_request(session: AsyncSession, request: MaintenanceRequest) -> None:
    """Tell the organization's managers that a tenant filed a request."""
    address = await _address(session, request)
    emails, user_ids = await _managers(session, request.organization_id)
    await _deliver(
        session,
        request,
        emails,
        user_ids,
        "maintenance_new",
        f"New maintenance request - {address}",
        "New maintenance request",
        f"{request.title} was reported at {address} ({request.priority.value} priority).",
        MANAGER_LINK,
    )


async def notify_status_change(session: AsyncSession, request: MaintenanceRequest) -> None:
    """Tell the reporting tenant that a manager changed the request's status."""
    address = await _address(session, request)
    await _deliver(
        session,
        request,
        await user_emails(session, [request.created_by]),
        [request.created_by],
        "maintenance_status",
        f"Maintenance update - {address}",
        f"Maintenance request {request.status.value}",
        f"{request.title} at {address} is now {request.status.value}.",
        TENANT_LINK,
    )


async def notify_cancelled(session: AsyncSession, request: MaintenanceRequest) -> None:
    """Tell the organization's managers that the tenant cancelled a request."""
    address = await _address(session, request)
    emails, user_ids = await _managers(session, request.organization_id)
    await _deliver(
        session,
        request,
        emails,
        user_ids,
        "maintenance_cancelled",
        f"Maintenance request cancelled - {address}",
        "Maintenance request cancelled",
        f"{request.title} at {address} was cancelled by the tenant.",
        MANAGER_LINK,
    )
```

- [ ] **Step 5: Hook the three routes**

Edit `backend/app/routers/maintenance.py`. Add the import:

```python
from app.services.maintenance_notify import (
    notify_cancelled,
    notify_new_request,
    notify_status_change,
)
```

In `create_request`, after `await session.refresh(request)` and before the return:

```python
    await notify_new_request(session, request)
```

In `cancel_request`, after `await session.refresh(request)` and before the return:

```python
    await notify_cancelled(session, request)
```

In `update_request`, capture the status before applying the body and notify only on a real change:

```python
    request = await get_owned_request(request_id, membership, session)
    previous_status = request.status
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(request, field, value)
    await session.commit()
    await session.refresh(request)
    if request.status != previous_status:
        await notify_status_change(session, request)
    return await _to_info(session, request)
```

- [ ] **Step 6: Run to verify they pass**

Run: `cd backend && uv run pytest tests/test_maintenance_notify.py -q`
Expected: PASS (5 tests).

- [ ] **Step 7: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass — including the existing `tests/test_maintenance_tenant.py` and
`tests/test_maintenance_manager.py`, which must be unaffected; ruff clean.

- [ ] **Step 8: Commit, push, confirm CI green, report**

```bash
git add backend/app/services/notify.py backend/app/services/maintenance_notify.py \
        backend/app/routers/maintenance.py backend/tests/test_maintenance_notify.py
git commit -m "Notify managers and tenants on maintenance events"
git push
gh run watch --exit-status
```

Report: Milestone 6 is complete — lease expiry, rent due/overdue, and maintenance events all send
email and post to the in-app inbox, with `ChargeReminder` and `LeaseReminder` preventing repeats.

---

## Self-Review

**Spec coverage:**
- `ChargeReminder` ledger, string `kind`, enum-free migration -> Task 1. ✓
- `_due_soon` 0..3 inclusive, `_overdue_kind` largest-reached over 7/14/30 -> Task 2. ✓
- Per-lease scan through `lease_statuses` because payments attach to the lease -> Task 3, Step 5. ✓
- Rule 1 (partial still reminded, remaining balance quoted) -> Task 3 test
  `test_partial_payment_still_reminded_with_remaining_balance`. ✓
- Rule 2 (stops at 30) -> Task 3 test `test_escalation_advances_over_time`, final assertion. ✓
- Rule 4 (one per charge) -> `(charge_id, kind)` unique + `_already_sent`. ✓
- due_soon to tenants only, overdue to tenants plus managers; categories `rent_due` /
  `rent_overdue`; link `/app/leases/{id}` -> Task 3. ✓
- Third scheduler job, `rent_reminder_hour`, CLI -> Task 4. ✓
- Rule 3 (only real status changes; priority-only sends nothing) -> Task 5, Step 5 plus two
  dedicated tests. ✓
- `user_emails` addition -> Task 5, Step 3. ✓
- Three maintenance events with their categories and links -> Task 5. ✓
- No frontend work -> no task, as specified. ✓

**Placeholder scan:** No TBD/TODO; every code step carries complete code; the only `<rev>` is the
Alembic revision id. ✓

**Type consistency:** `_kind` returns the same strings the ledger stores and `_copy_for` branches on
(`due_soon`, `overdue_7|14|30`); `_send` takes the `ChargeStatus` from `lease_statuses` and reads
`.charge`, `.amount_paid`, `.status`, matching `app/services/payments.py`; `notify_users(session,
user_ids, organization_id, category, title, body, link)` is called with that exact signature in both
new services; `_deliver` passes `request.organization_id` for the org, so `MaintenanceRequest` is the
only model the maintenance service needs beyond `Property`. ✓
