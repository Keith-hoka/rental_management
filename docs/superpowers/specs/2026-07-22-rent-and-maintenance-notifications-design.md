# Milestone 6.2: Rent and Maintenance Notifications — Design

**Date:** 2026-07-22
**Status:** Approved (pending spec review)
**Part of:** Milestone 6 (Notifications), sub-project 2 of 2. M6.1 built the `Notification` model,
the shared `services/notify.py` plumbing, and the `/app/messages` inbox.

## Goal

Add the two remaining notification sources: scheduled rent reminders (due soon and overdue) and
event-driven maintenance updates. Both send email and write to the in-app inbox built in M6.1.

## Architecture

Two new services, deliberately not merged into one module — their lifecycles differ:

- **`services/rent_reminders.py`** — a scheduled sweep, shaped like `services/reminders.py`: pure
  bucket helpers, a scan, a dedup ledger, a scheduler job and a CLI entrypoint.
- **`services/maintenance_notify.py`** — event handlers called inline from the maintenance routes
  after their existing commit.

Both reach the outside world only through `services/notify.py`, so recipients and delivery stay in
one place. Rejected alternatives: a single `services/notifications.py` holding both (mixes a cron
sweep with request-time handlers, poor cohesion), and an event-bus/outbox table (YAGNI at this
scale).

## Tech Stack

Backend: FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, APScheduler (all existing). No new
dependencies. No frontend changes.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- Migration is enum-free; verify upgrade -> downgrade -> upgrade. Current head: `0e07c7d866ed`.
- The dev `.env` uses `onboarding@resend.dev`, Resend's shared test sender. Real calls do leave
  localhost, but an unverified domain only delivers to the account owner's own address, so the
  practical blast radius of running a job locally is one address.

---

## Product Rules (confirmed)

1. **Partially paid charges still get overdue reminders**, quoting the remaining balance
   (`amount_due - amount_paid`). This matches `payments.allocate()`, which already flags a charge
   overdue when `due_date < today and amount_paid < amount_due`; excluding partials would contradict
   the overdue totals shown on the dashboard and the tenant portal.
2. **Overdue escalation stops at 30 days.** Three overdue reminders per charge at most. Longer
   arrears are surfaced by the dashboard `overdue` figure and handled by a human, not by an endless
   dunning loop.
3. **Only a real status change notifies the tenant.** A PATCH whose `status` equals the current
   value sends nothing, and a priority-only PATCH sends nothing — priority is internal triage. A
   manager setting the status to `cancelled` is a status change and does notify.
4. **One reminder per charge**, matching the `(charge_id, kind)` dedup key. No per-lease digest: it
   would need a `(lease, date)` key and leave the in-app `link` ambiguous about which charge it
   refers to.

## Data Model

New file `app/models/charge_reminder.py`:

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Register in `app/models/__init__.py`. `kind` is a plain string, consistent with
`Notification.category`, so the four values need no enum migration. One enum-free migration creates
the table; downgrade drops it. Values: `due_soon`, `overdue_7`, `overdue_14`, `overdue_30`.

## Rent reminders (`app/services/rent_reminders.py`)

Two pure helpers, tested directly:

- `_due_soon(days_until: int) -> bool` — true when `0 <= days_until <= 3`, so the reminder fires on
  each of the three days before the due date and on the due date itself.
- `_overdue_kind(days_overdue: int) -> str | None` — the **largest** threshold in `[7, 14, 30]` that
  is `<= days_overdue`, else `None`. Largest-reached rather than smallest-crossed makes the job
  self-healing: if it does not run for a week, a charge 16 days overdue still gets `overdue_14`
  instead of stalling, and the ledger suppresses whatever was already sent. Past 30 days every kind
  has been sent, so nothing further fires.

The two ranges cannot overlap: `_due_soon` requires `due_date >= today`, `_overdue_kind` requires
`due_date < today`.

**Why the scan is per-lease.** Payments attach to the lease, not the charge, so a charge's paid
state only exists after `payments.allocate()` waterfalls the lease's total payments across its
charges oldest-first. The job therefore selects the leases holding at least one charge with
`due_date <= today + 3`, and for each calls `lease_statuses(session, lease_id, today)`. For every
returned `ChargeStatus`:

- skip when `status == "paid"`;
- pick the kind from `_due_soon` / `_overdue_kind`, skip when there is none;
- skip when `(charge_id, kind)` is already in `charge_reminders`;
- otherwise send, then record the ledger row and commit per charge.

The amount quoted is the remaining balance, `charge.amount_due - status.amount_paid`.

Recipients and categories:

| kind | category | Email | In-app |
| --- | --- | --- | --- |
| `due_soon` | `rent_due` | `roster_emails(lease)` | `lease_tenant_user_ids(lease.id)` |
| `overdue_7` / `overdue_14` / `overdue_30` | `rent_overdue` | roster + `manager_emails(org)` | lease tenants + `manager_user_ids(org)` |

`link` is `/app/leases/{lease_id}` for both; that page already lists charges and payments.

Entry point `run_rent_reminders(session, today) -> int`, returning the number of reminders sent,
mirroring `run_expiry_reminders`.

## Maintenance notifications (`app/services/maintenance_notify.py`)

Three handlers called from `app/routers/maintenance.py` after each route's existing commit, so the
row is persisted and has an id before anything is sent:

| Event | Route | Recipients | category | link |
| --- | --- | --- | --- | --- |
| Tenant files a request | `POST /me/leases/{id}/maintenance` | org managers | `maintenance_new` | `/app/maintenance` |
| Manager changes status | `PATCH /maintenance/{id}` | the reporting tenant (`created_by`) | `maintenance_status` | `/app` |
| Tenant cancels | `POST /me/maintenance/{id}/cancel` | org managers | `maintenance_cancelled` | `/app/maintenance` |

`update_request` captures `request.status` before applying the body and calls the handler only when
the new value differs, which is what makes rule 3 hold: no-op status writes and priority-only edits
send nothing.

Emails go through `safe_send`, so an email outage cannot turn a maintenance action into a 500.

## Addition to `app/services/notify.py`

- `async user_emails(session, user_ids) -> list[str]` — the emails of specific users. Needed to
  email one reporting tenant; the existing helpers only resolve managers or a lease roster.

## Scheduler and CLI

- `app/core/scheduler.py`: a third job `rent_reminders` on `CronTrigger(hour=settings.rent_reminder_hour)`,
  registered alongside the existing two inside `start_scheduler()`.
- `app/core/config.py`: `rent_reminder_hour: int = 9`.
- `app/jobs/rent_reminders.py`: the same shape as `app/jobs/expiry_reminders.py` — open a session,
  run the sweep for today, print the count.

## Frontend

**No changes.** The `/app/messages` page renders any category, and its filter already matches the
`rent` and `maintenance` prefixes, so all five new categories group correctly on arrival.

## Testing

**Pure logic:** `_due_soon` parametrized over `-1, 0, 1, 3, 4` expecting
`False, True, True, True, False`; `_overdue_kind` over `0, 6, 7, 13, 14, 29, 30, 45` expecting
`None, None, 7, 7, 14, 14, 30, 30`.

**Rent job:**

- a charge due in 2 days notifies the lease's tenants only — no manager receives it;
- a charge 7 days overdue notifies tenants and managers;
- re-running the job the same day sends nothing more (ledger dedup);
- a partially paid charge is still reminded, and the message quotes the remaining balance;
- a fully paid charge is skipped;
- escalation advances over time: day 7 sends `overdue_7`, day 10 sends nothing, day 14 sends
  `overdue_14`;
- nothing fires after 30 days once all three kinds are recorded;
- each reminder writes `Notification` rows with category `rent_due` / `rent_overdue`.

**Maintenance:** filing a request notifies managers and not the filing tenant; a status change
notifies the reporting tenant; a PATCH setting the same status notifies nobody; a priority-only
PATCH notifies nobody; a tenant cancel notifies managers.

**CLI/scheduler:** the job module runs and prints a count; `start_scheduler()` registers three jobs.

## Out of Scope

- Real-time push/WebSocket, SMS, per-user notification preferences or opt-out, digest emails.
- Dunning beyond 30 days, late fees, or payment-plan tracking.
- Notifying on charge generation itself, or on payments being recorded.
- Any frontend change.

## File Structure

- Create: `backend/app/models/charge_reminder.py`; Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_charge_reminders.py`
- Create: `backend/app/services/rent_reminders.py`
- Create: `backend/app/services/maintenance_notify.py`
- Modify: `backend/app/services/notify.py` (add `user_emails`)
- Modify: `backend/app/routers/maintenance.py` (three event hooks)
- Modify: `backend/app/core/scheduler.py`, `backend/app/core/config.py`
- Create: `backend/app/jobs/rent_reminders.py`
- Create: `backend/tests/test_rent_reminders.py`, `backend/tests/test_maintenance_notify.py`
