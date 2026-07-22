# Milestone 6.1: Messages Center — Design

**Date:** 2026-07-22
**Status:** Approved (pending spec review)
**Part of:** Milestone 6 (Notifications), sub-project 1 of 2. M6.2 adds the rent-reminder and
maintenance notification sources.

## Goal

Every user gets an in-app inbox at `/app/messages` listing the notifications addressed to them,
with unread markers and mark-as-read. The existing lease-expiry reminder becomes its first
source, proving the whole path end to end.

## Architecture

- A `Notification` row is **one message for one recipient user**, written alongside the email that
  already goes out. Emails and in-app messages deliberately have different audiences: email goes to
  roster addresses (which may not have accounts), in-app messages go to real user accounts.
- The email plumbing currently hidden in `services/reminders.py` is extracted into a shared
  `services/notify.py`, which also gains the helpers that resolve recipient **user ids** and write
  notification rows. M6.2's sources will reuse the same module.
- Read state lives on the row (`read_at`), so the inbox and the nav badge are plain queries.

## Tech Stack

Backend: FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL (existing). Frontend: Next.js
(existing). No new dependencies.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- Migration is enum-free; verify upgrade -> downgrade -> upgrade. Current head: `405a20d32df6`.
- The dev `.env` holds a live Resend key: running the reminder job locally sends real email.

---

## Product Rules (confirmed)

- **`category` is a string, not a PG enum** — M6.2 adds categories without another enum migration.
  Values used across M6: `lease_expiry`, `rent_due`, `rent_overdue`, `maintenance_new`,
  `maintenance_status`, `maintenance_cancelled`. M6.1 only writes `lease_expiry`.
- **In-app messages go only to users with accounts**: the org's `landlord`/`property_manager`
  members, and the lease's joined tenants (`LeaseTenant`). Email keeps going to roster addresses.
- **Read state:** unread markers, mark one as read, and mark all as read.
- **No pagination:** the inbox returns the newest 100 notifications.

## Data Model

New file `app/models/notification.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Register `Notification` in `app/models/__init__.py`. One enum-free migration creates the table;
downgrade drops it. Notifications are deliberately **not** cascade-deleted with the lease or
charge they reference — the inbox is a historical record; a stale `link` simply 404s.

## Shared notification plumbing

New file `app/services/notify.py`, holding what `services/reminders.py` currently keeps private
plus the new user-targeting helpers:

- `async safe_send(to: str, subject: str, html: str) -> None` — send one email; log and swallow
  failures (moved verbatim from `reminders._safe_send`).
- `async manager_emails(session, organization_id) -> list[str]` (moved from `reminders`).
- `roster_emails(lease) -> list[str]` (moved from `reminders`).
- `async manager_user_ids(session, organization_id) -> list[uuid.UUID]` — users with a
  `landlord`/`property_manager` membership in the org.
- `async lease_tenant_user_ids(session, lease_id) -> list[uuid.UUID]` — users joined to the lease
  via `LeaseTenant`.
- `async notify_users(session, user_ids, organization_id, category, title, body, link=None) -> None`
  — `session.add` one `Notification` per user id. **It does not commit**; the caller's existing
  commit persists them.

`services/reminders.py` is refactored to import these instead of defining its own.

**Test impact (must be handled):** `tests/test_reminders.py` monkeypatches
`app.services.reminders.send_email`. After the refactor `reminders.py` no longer references
`send_email` directly, so that monkeypatch target must change to
`app.services.notify.send_email`.

## First source: lease-expiry reminders

In `run_expiry_reminders`, after sending the bucket's emails and before the existing commit, also
write in-app notifications for that lease:

- recipients: `manager_user_ids(org)` + `lease_tenant_user_ids(lease.id)`
- `category="lease_expiry"`, `title=f"Lease expiring in {days_left} days"`,
  `body` naming the property, tenant, and end date, `link=f"/app/leases/{lease.id}"`

Dedup is unchanged — the existing `LeaseReminder` unique constraint already prevents a bucket from
firing twice, so notifications are written exactly once per (lease, bucket).

## Schemas

New file `app/schemas/notification.py`:

```python
class NotificationInfo(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    body: str
    link: str | None
    created_at: datetime
    read_at: datetime | None


class UnreadCount(BaseModel):
    count: int
```

## Endpoints (`app/routers/notifications.py`, mounted in `main.py`)

All use `get_current_user` — every role has an inbox, and each user only ever sees their own rows.

- `GET /api/v1/me/notifications` (optional `?unread=true`) -> `list[NotificationInfo]`, newest
  first, limited to 100.
- `GET /api/v1/me/notifications/unread_count` -> `UnreadCount` (for the nav badge).
- `POST /api/v1/me/notifications/{notification_id}/read` -> `NotificationInfo`; 404 if the row is
  not the caller's. Setting read on an already-read row is a no-op.
- `POST /api/v1/me/notifications/read_all` -> `UnreadCount` (always `{count: 0}` after the update).

## Frontend

- `frontend/src/lib/notifications.ts`: `NotificationInfo` type; `listNotifications(unreadOnly?)`,
  `getUnreadCount()`, `markRead(id)`, `markAllRead()`.
- **`frontend/src/app/app/messages/page.tsx`**: auth guard; header "Messages" with the unread count
  and a **Mark all read** button; a **client-side** category filter (All / lease / rent /
  maintenance — matching on the category prefix so M6.2's categories group correctly; the API
  takes no category parameter, the page filters the fetched list); a list, newest first, where unread rows
  are visually marked (bold title + dot) and each row shows title, body, relative date, a **Mark
  read** action, and — when `link` is set — a link through to the related page. Empty state:
  "No messages yet." Back-to-dashboard link.
- **Dashboard** (`app/page.tsx`): fetch `getUnreadCount()` for every role after `/auth/me`, and add
  a **Messages** nav link showing the count (e.g. `Messages (3)`) to **both** the tenant branch and
  the manager branch.

## Testing

**Backend (pytest):**

- Model: insert and read back; `read_at` defaults to `None`.
- `notify_users` writes one row per user id, with the given category/title/link.
- `manager_user_ids` returns the org's landlord/PM users; `lease_tenant_user_ids` returns joined
  tenants only.
- Lease-expiry integration: after `run_expiry_reminders`, the manager user and the joined tenant
  user each have one `lease_expiry` notification; running the job again writes no duplicates
  (existing `LeaseReminder` dedup).
- Endpoints: list returns only the caller's rows, newest first; `?unread=true` filters; unread
  count is correct; marking one read sets `read_at` and drops the count; marking another user's
  row -> 404; `read_all` zeroes the count; unauthenticated -> 401.
- The existing M3.4 reminder tests still pass with the monkeypatch retargeted to
  `app.services.notify.send_email`.

**Frontend e2e (light):** a landlord logs in, clicks **Messages** in the dashboard nav, and sees
the page with its empty state ("No messages yet.").

## Out of Scope (M6.2 / later)

- Rent reminders and maintenance notifications as sources — **Milestone 6.2**.
- Real-time push/WebSocket, SMS, per-user notification preferences or opt-out, digest emails,
  pagination beyond the newest 100, deleting notifications.

## File Structure

- Create: `backend/app/models/notification.py`; Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_notifications.py`
- Create: `backend/app/services/notify.py`; Modify: `backend/app/services/reminders.py`
- Modify: `backend/tests/test_reminders.py` (monkeypatch target)
- Create: `backend/app/schemas/notification.py`
- Create: `backend/app/routers/notifications.py`; Modify: `backend/app/main.py`
- Create: `backend/tests/test_notification_model.py`, `test_notify_service.py`,
  `test_notifications_api.py`
- Create: `frontend/src/lib/notifications.ts`
- Create: `frontend/src/app/app/messages/page.tsx`
- Modify: `frontend/src/app/app/page.tsx` (Messages nav link + unread count, both branches)
- Create: `frontend/e2e/messages.spec.ts`
