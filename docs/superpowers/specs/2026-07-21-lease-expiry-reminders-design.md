# Milestone 3.4: Lease-Expiry Reminders — Design

**Date:** 2026-07-21
**Status:** Approved (pending spec review)

## Goal

A daily scheduled job finds leases approaching their `end_date` and emails both the
managing side (landlord + property managers) and the tenant side (roster emails) at
three lead-time thresholds — **60 / 30 / 7 days** — without ever sending the same
reminder twice. Managers see a read-only history of reminders sent on each lease.

## Architecture

- A pure service function `run_expiry_reminders(session, today)` holds all the logic
  (find expiring leases, compute the threshold bucket, gather recipients, send, record).
  It takes a session and a date so it is fully unit-testable with no scheduler or clock.
- An in-process `AsyncIOScheduler` (APScheduler) started from the FastAPI `lifespan`
  calls that function once a day. A thin CLI wrapper calls the same function for manual
  runs and local testing.
- A `lease_reminders` table with a `UNIQUE(lease_id, threshold_days)` constraint is the
  dedup ledger: one row per (lease, threshold) that has fired. The unique constraint
  makes a double-run — or concurrent workers — idempotent (the second insert is skipped).

## Tech Stack

- Backend: FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL (existing).
- New dependency: `apscheduler` (`uv add apscheduler`).
- Email: existing `app.core.email.send_email(to, subject, html)` (Resend or log-stub).
- Frontend: Next.js lease-detail page gets one read-only section.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Ruff sequence before every push, run from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Each task ends with: full test run -> ruff sequence -> commit -> push -> report -> wait for approval.
- Migration is enum-free; verify upgrade -> downgrade -> upgrade round-trip.

---

## Recipients

For a lease whose reminder fires, two recipient groups, each with its own copy:

- **Managing side:** every `Membership` in the lease's `organization_id` whose role is
  `landlord` or `property_manager` -> that user's `email`.
- **Tenant side:** the roster emails on the lease itself — `lease.tenant_email` plus each
  `co_tenants[].email`. These are the contact emails on file, used regardless of whether
  the tenant has accepted a portal invitation (the reminder is about the lease).

Each recipient is emailed individually via `send_email`. A per-recipient `try/except`
logs and swallows failures — an email failure must never abort the run or block the
dedup record (same pattern as the existing invite flow).

Manager copy (subject / body):
- Subject: `Lease expiring in {days_left} days - {property_address}`
- Body: property address, tenant name, `end_date`, days left, and a link
  `{frontend_url}/app/leases/{lease_id}`.

Tenant copy:
- Subject: `Your lease expires in {days_left} days - {property_address}`
- Body: property address, `end_date`, days left, and a note to contact the landlord about
  renewal, with a link `{frontend_url}/app`.

## Threshold / Bucketing Logic

Thresholds come from settings, default `[60, 30, 7]`. Work with them sorted ascending:
`[7, 30, 60]`; `max_threshold = 60`.

For each candidate lease, `days_left = (end_date - today).days`. Only leases with
`0 <= days_left <= max_threshold` are candidates (window `[today, today + 60d]`).

**Bucket = the smallest threshold `T` such that `days_left <= T`.** If a `lease_reminders`
row for `(lease_id, bucket)` does not already exist, send to all recipients and insert the
row.

Worked examples (thresholds 60/30/7):

| days_left | bucket | action |
|-----------|--------|--------|
| 61 | none (> 60) | outside window, skip |
| 45 | 60 | send "60-day" bucket once |
| 30 | 30 | send "30-day" bucket |
| 8 | 30 (already sent) | nothing |
| 7 | 7 | send "7-day" bucket |
| 0 | 7 | day-of: send if 7-day bucket not yet sent |

Because the bucket is derived from the current `days_left` (not exact-day equality), a
missed run day never skips a bucket, and a lease entered late with only 5 days left sends
only the most urgent applicable bucket (7) — never three emails at once.

No filter on `start_date`: a lease ending within the window but not yet started is a data
oddity, and a reminder is harmless. Ended leases (`end_date < today`) are excluded by the
window.

## Data Model

New file `app/models/lease_reminder.py`, modeled on `lease_tenant.py`:

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

Register `LeaseReminder` in `app/models/__init__.py` (`__all__` + import).

`ondelete="CASCADE"` cleans up reminder rows when a lease is deleted (consistent with
`lease_tenants` / `invitations`). One Alembic migration creates the table; downgrade drops
it. No enums are involved. Verify upgrade -> downgrade -> upgrade round-trip.

## Service Function

New file `app/services/reminders.py`:

```python
async def run_expiry_reminders(session: AsyncSession, today: date) -> int:
    """Send expiry reminders for leases entering a new threshold bucket.

    Returns the number of (lease, bucket) reminders sent this run.
    """
```

Internal helpers (small, focused, testable):

- `_bucket(days_left: int, thresholds: list[int]) -> int | None` — the smallest `T` with
  `days_left <= T` when `days_left >= 0`, else `None` (so a negative `days_left` and a
  `days_left` beyond the largest threshold both return `None`). This guard makes `_bucket`
  the source of truth; the window query is only an optimization to avoid loading every lease.
- `_expiring_leases(session, today, window_end) -> list[tuple[Lease, str]]` — leases with
  `end_date` in `[today, window_end]`, joined to `Property.address`, scoped by nothing
  (all orgs; this is a system job).
- `_manager_emails(session, organization_id) -> list[str]` — `User.email` for memberships
  with role `landlord` or `property_manager` in the org.
- `_already_sent(session, lease_id, bucket) -> bool` — a `lease_reminders` row exists.
- `_roster_emails(lease) -> list[str]` — `[lease.tenant_email] + [c["email"] for c in
  lease.co_tenants]`.

Flow: sort thresholds; `window_end = today + timedelta(days=max_threshold)`; for each
expiring lease compute `days_left` and `bucket`; skip if `bucket is None` or already sent;
otherwise send manager copies and tenant copies (each recipient wrapped in try/except),
then `session.add(LeaseReminder(lease_id=..., threshold_days=bucket))` and
`await session.commit()`. **Record and commit even if individual emails fail**, so the next
day does not re-send. Increment and return the sent count.

## Scheduler

New file `app/core/scheduler.py`:

```python
scheduler = AsyncIOScheduler()

async def _run_job() -> None:
    async with SessionLocal() as session:
        today = datetime.now(UTC).date()
        await run_expiry_reminders(session, today)

def start_scheduler() -> None:
    scheduler.add_job(_run_job, CronTrigger(hour=settings.reminder_hour), id="expiry_reminders")
    scheduler.start()
```

`main.py` gains a `lifespan` context manager. On startup, if `settings.reminders_enabled`,
call `start_scheduler()`; on shutdown, `scheduler.shutdown(wait=False)`. The existing
upload-dir `mkdir` moves into (or stays alongside) the lifespan startup. The scheduler uses
`SessionLocal` directly (not the `get_session` dependency).

Tests are unaffected: conftest builds the client with httpx `ASGITransport`, which does not
run FastAPI lifespan, so the scheduler never starts during pytest. The `reminders_enabled`
flag is a production off-switch.

## CLI

New file `app/jobs/expiry_reminders.py`:

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

Run: `uv run python -m app.jobs.expiry_reminders`.

## Reminder History Endpoint + Frontend

**Endpoint** in `app/routers/leases.py`:
`GET /api/v1/leases/{lease_id}/reminders` (dep `manager`) ->
`list[LeaseReminderInfo]`, ordered by `sent_at` desc. 404 via `get_owned_lease`.

Schema in `app/schemas/tenant.py` (or a small `reminder.py`):

```python
class LeaseReminderInfo(BaseModel):
    threshold_days: int
    sent_at: datetime
```

**Frontend** `frontend/src/lib/tenants.ts`: add
`LeaseReminderInfo { threshold_days: number; sent_at: string }` and
`listLeaseReminders(leaseId)` -> `GET /api/v1/leases/{id}/reminders`.

**Frontend** lease-detail page `app/leases/[leaseId]/page.tsx`: below the Tenants section,
a read-only **"Expiry reminders"** section. Fetched alongside the existing tenant/invitation
loads. Renders each sent reminder as `"{threshold_days}-day reminder - sent {date}"`; empty
state shows `"No reminders sent yet."`.

## Settings

Add to `app/core/config.py`:

- `reminders_enabled: bool = True`
- `reminder_thresholds: list[int] = [60, 30, 7]`
- `reminder_hour: int = 8`

## Testing

**Backend (pytest, primary):**

- `_bucket`: each `days_left` maps to the correct bucket (45->60, 30->30, 8->30, 7->7,
  0->7, 61->None, -1->None).
- Recipients: a lease 7 days out sends to both manager emails (landlord + PM memberships)
  and every roster email (tenant + co-tenants), captured by monkeypatching `send_email`
  to collect `(to, subject)` calls.
- Dedup: running the job twice for the same lease/bucket sends once; a second insert of the
  same `(lease_id, threshold_days)` is prevented by the unique constraint.
- Bucket advance: a lease at 30 days sends the 30 bucket; re-running at 8 days sends nothing;
  at 7 days sends the 7 bucket.
- Window edges: 61 days -> no send; 0 days -> send; already ended (`end_date < today`) -> no
  send.
- CASCADE: deleting a lease removes its `lease_reminders` rows.
- Email failure: `send_email` raising for one recipient still records the reminder and does
  not abort the run.
- History endpoint: `GET /leases/{id}/reminders` returns sent rows newest-first; cross-org
  lease -> 404; unauth -> 401.

**Frontend e2e (light):** on a freshly created lease, the "Expiry reminders" section renders
with its empty state ("No reminders sent yet"). Real sends depend on dates + the scheduler,
so they are covered by backend tests, not e2e.

## Out of Scope (M3.4)

- Per-org configurable thresholds or a settings UI (global default only).
- Payment history, payment status, overdue rent, outstanding balance — these belong to
  **Milestone 4** (rent charges, payment recording, dashboard stats).
- Landlord-facing "all tenants" overview page (not yet on the roadmap).

## File Structure

- Create: `backend/app/models/lease_reminder.py`
- Modify: `backend/app/models/__init__.py` (register `LeaseReminder`)
- Create: `backend/alembic/versions/<rev>_add_lease_reminders.py`
- Create: `backend/app/services/reminders.py`
- Create: `backend/app/core/scheduler.py`
- Create: `backend/app/jobs/expiry_reminders.py` (+ `app/jobs/__init__.py`)
- Modify: `backend/app/main.py` (lifespan starts/stops scheduler)
- Modify: `backend/app/core/config.py` (three settings)
- Modify: `backend/pyproject.toml` (`apscheduler` dependency)
- Modify: `backend/app/schemas/tenant.py` (`LeaseReminderInfo`)
- Modify: `backend/app/routers/leases.py` (`GET /leases/{id}/reminders`)
- Create: `backend/tests/test_reminders.py`
- Create: `backend/tests/test_reminder_history.py` (endpoint)
- Modify: `frontend/src/lib/tenants.ts` (`LeaseReminderInfo`, `listLeaseReminders`)
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx` (Expiry reminders section)
- Modify: `frontend/e2e/tenant-invite.spec.ts` (assert empty-state section) or a new spec
