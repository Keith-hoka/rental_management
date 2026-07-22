# Milestone 6.1: Messages Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every user gets an in-app inbox at `/app/messages` with unread markers and mark-as-read, fed first by the existing lease-expiry reminder.

**Architecture:** A `Notification` row is one message for one recipient user, written alongside the email that already goes out. The email plumbing hidden in `services/reminders.py` moves into a shared `services/notify.py`, which also resolves recipient user ids and writes notification rows — M6.2's sources will reuse it.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js. No new dependencies.

## Global Constraints

- Package manager: `uv` only (`uv run ...`, `uv add ...`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before EVERY push, from `backend/`, in order:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- **Ruff gotcha:** test files keep ALL imports at the top (E402). `ruff check --fix` auto-removes unused imports but NOT unused module-level assignments (e.g. a stale `logger = ...`).
- Each task ends with: full test run -> ruff sequence -> commit -> `git push` (CI) -> report -> WAIT for approval.
- Migration is enum-free; verify upgrade -> downgrade -> upgrade. Current head: `405a20d32df6`.
- `category` is a plain string (M6.2 adds values without a migration). M6.1 writes only `lease_expiry`.
- In-app messages go only to users with accounts; email keeps going to roster addresses.
- The dev `.env` holds a live Resend key: running the reminder job locally sends real email.
- Backend tests: `cd backend && uv run pytest -q`. Frontend: `npm run lint`, `npm run build`, e2e `npx playwright test` from `frontend/`.
- Restart the e2e backend after new endpoints: `lsof -ti tcp:8000 | xargs kill` then `uv run uvicorn app.main:app --port 8000`.

---

## Task Overview

1. `Notification` model + migration
2. `services/notify.py` + refactor `reminders.py` onto it (no behavior change)
3. Lease-expiry reminders write notifications
4. Schemas + notifications API
5. Frontend lib + Messages page + dashboard nav badge
6. e2e + CI green

---

### Task 1: `Notification` model + migration

**Files:**
- Create: `backend/app/models/notification.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_notifications.py`
- Test: `backend/tests/test_notification_model.py`

**Interfaces:**
- Produces: `Notification(id, organization_id, user_id, category, title, body, link, created_at, read_at)` importable from `app.models`.

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/test_notification_model.py`:

```python
from sqlalchemy import select

from app.models import Membership, Notification, User
from tests.test_properties_crud import landlord_headers


async def _user_and_org(db_session, email):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    org_id = (
        await db_session.execute(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        )
    ).scalar_one()
    return user, org_id


async def test_insert_and_read(client, db_session):
    email = "nmodel@example.com"
    await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)

    db_session.add(
        Notification(
            organization_id=org_id,
            user_id=user.id,
            category="lease_expiry",
            title="Lease expiring in 7 days",
            body="The lease at 1 Main St expires soon.",
            link="/app/leases/abc",
        )
    )
    await db_session.commit()

    rows = (
        (await db_session.execute(select(Notification).where(Notification.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].category == "lease_expiry"
    assert rows[0].link == "/app/leases/abc"
    assert rows[0].read_at is None
    assert rows[0].created_at is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_notification_model.py -q`
Expected: FAIL with `ImportError: cannot import name 'Notification' from 'app.models'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/notification.py`:

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

- [ ] **Step 4: Register the model**

Edit `backend/app/models/__init__.py`: add `from app.models.notification import Notification`
and `"Notification",` to `__all__` (keep alphabetical placement).

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_notification_model.py -q`
Expected: PASS.

- [ ] **Step 6: Generate and verify the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add notifications"
```

Confirm the generated file creates `notifications` with the columns and the three indexes
(`organization_id`, `user_id`, `created_at`), that `down_revision = "405a20d32df6"`, and that
`downgrade()` drops the indexes then the table. No enums are involved. Verify the round-trip:

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
git add backend/app/models/notification.py backend/app/models/__init__.py \
        backend/alembic/versions backend/tests/test_notification_model.py
git commit -m "Add Notification model and migration"
git push
```
Then report and wait for approval.

---

### Task 2: `services/notify.py` + refactor `reminders.py`

**Files:**
- Create: `backend/app/services/notify.py`
- Modify: `backend/app/services/reminders.py`
- Modify: `backend/tests/test_reminders.py` (monkeypatch target)
- Test: `backend/tests/test_notify_service.py`

**Interfaces:**
- Consumes: `Notification` (Task 1); `send_email`; models `Lease`, `LeaseTenant`, `Membership`, `Role`, `User`.
- Produces: in `app.services.notify` — `safe_send(to, subject, html)`, `manager_emails(session, organization_id) -> list[str]`, `roster_emails(lease) -> list[str]`, `manager_user_ids(session, organization_id) -> list[uuid.UUID]`, `lease_tenant_user_ids(session, lease_id) -> list[uuid.UUID]`, `notify_users(session, user_ids, organization_id, category, title, body, link=None)` (adds rows, does **not** commit).

- [ ] **Step 1: Write the failing tests for the new helpers**

Create `backend/tests/test_notify_service.py`:

```python
import uuid

from sqlalchemy import select

from app.models import Membership, Notification, User
from app.services.notify import lease_tenant_user_ids, manager_user_ids, notify_users
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _org_id(db_session, email):
    return (
        await db_session.execute(
            select(Membership.organization_id)
            .join(User, User.id == Membership.user_id)
            .where(User.email == email)
        )
    ).scalar_one()


async def test_manager_user_ids(client, db_session):
    email = "nmu@example.com"
    await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)

    ids = await manager_user_ids(db_session, org_id)
    assert len(ids) == 1


async def test_lease_tenant_user_ids(client, db_session):
    headers = await landlord_headers(client, "nlt@example.com")
    lease_id = await make_lease(client, headers, "Notify St")
    await onboard_tenant(client, db_session, headers, lease_id, "nlt-t@example.com")

    ids = await lease_tenant_user_ids(db_session, uuid.UUID(lease_id))
    assert len(ids) == 1


async def test_notify_users_writes_one_row_each(client, db_session):
    email = "nnu@example.com"
    await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    ids = await manager_user_ids(db_session, org_id)

    await notify_users(db_session, ids, org_id, "lease_expiry", "Title", "Body", "/app/leases/x")
    await db_session.commit()

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert len(rows) == len(ids) == 1
    assert rows[0].category == "lease_expiry"
    assert rows[0].title == "Title"
    assert rows[0].link == "/app/leases/x"
    assert rows[0].read_at is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_notify_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.notify'`.

- [ ] **Step 3: Create `notify.py`**

Create `backend/app/services/notify.py`:

```python
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.models import Lease, LeaseTenant, Membership, Notification, Role, User

logger = logging.getLogger(__name__)


async def safe_send(to: str, subject: str, html: str) -> None:
    """Send one email; a failure is logged and swallowed, never aborting the caller."""
    try:
        await send_email(to, subject, html)
    except Exception:  # noqa: BLE001 - a failed email must not abort the caller
        logger.exception("Failed to send notification email to %s", to)


async def manager_emails(session: AsyncSession, organization_id) -> list[str]:
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


def roster_emails(lease: Lease) -> list[str]:
    """The tenant contact emails on the lease (main tenant plus co-tenants)."""
    return [lease.tenant_email] + [c["email"] for c in lease.co_tenants]


async def manager_user_ids(session: AsyncSession, organization_id) -> list[uuid.UUID]:
    """User ids of the landlords and property managers in the organization."""
    result = await session.execute(
        select(Membership.user_id).where(
            Membership.organization_id == organization_id,
            Membership.role.in_([Role.landlord, Role.property_manager]),
        )
    )
    return [user_id for (user_id,) in result.all()]


async def lease_tenant_user_ids(session: AsyncSession, lease_id) -> list[uuid.UUID]:
    """User ids of the tenants who have joined the lease."""
    result = await session.execute(
        select(LeaseTenant.user_id).where(LeaseTenant.lease_id == lease_id)
    )
    return [user_id for (user_id,) in result.all()]


async def notify_users(
    session: AsyncSession,
    user_ids,
    organization_id,
    category: str,
    title: str,
    body: str,
    link: str | None = None,
) -> None:
    """Queue one in-app notification per recipient user. The caller commits."""
    for user_id in user_ids:
        session.add(
            Notification(
                organization_id=organization_id,
                user_id=user_id,
                category=category,
                title=title,
                body=body,
                link=link,
            )
        )
```

- [ ] **Step 4: Run the new tests**

Run: `cd backend && uv run pytest tests/test_notify_service.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Refactor `reminders.py` onto the shared module**

Edit `backend/app/services/reminders.py`:

1. Delete the functions `_manager_emails`, `_roster_emails`, and `_safe_send` entirely.
2. Delete the line `logger = logging.getLogger(__name__)` **by hand** (ruff will not remove it) and
   the now-unused `import logging`.
3. Add `from app.services.notify import manager_emails, roster_emails, safe_send`.
4. Replace the three call sites inside `run_expiry_reminders`:
   - `for email in await _manager_emails(session, lease.organization_id):` ->
     `for email in await manager_emails(session, lease.organization_id):`
   - `await _safe_send(email, manager_subject, manager_html)` ->
     `await safe_send(email, manager_subject, manager_html)`
   - `for email in _roster_emails(lease):` -> `for email in roster_emails(lease):`
   - `await _safe_send(email, tenant_subject, tenant_html)` ->
     `await safe_send(email, tenant_subject, tenant_html)`
5. `ruff check --fix` will drop the now-unused `send_email`, `Membership`, `Role`, `User` imports,
   leaving `from app.models import Lease, LeaseReminder, Property`.

`_bucket`, `_expiring_leases`, `_already_sent`, and the rest of `run_expiry_reminders` are unchanged.

- [ ] **Step 6: Retarget the reminder tests' monkeypatch (REQUIRED)**

Edit `backend/tests/test_reminders.py`. `reminders.py` no longer references `send_email`, so both
monkeypatch targets must move to the shared module:

- in the `captured` fixture: `monkeypatch.setattr("app.services.reminders.send_email", fake_send)`
  -> `monkeypatch.setattr("app.services.notify.send_email", fake_send)`
- in `test_email_failure_still_records`: `monkeypatch.setattr("app.services.reminders.send_email", boom)`
  -> `monkeypatch.setattr("app.services.notify.send_email", boom)`

- [ ] **Step 7: Verify the refactor changed nothing**

```bash
cd backend && uv run pytest tests/test_reminders.py tests/test_notify_service.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: the M3.4 reminder tests still pass unchanged in behavior; full suite passes; ruff clean.

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/services/notify.py backend/app/services/reminders.py \
        backend/tests/test_reminders.py backend/tests/test_notify_service.py
git commit -m "Extract shared notification plumbing into notify service"
git push
```
Then report and wait for approval.

---

### Task 3: Lease-expiry reminders write notifications

**Files:**
- Modify: `backend/app/services/reminders.py`
- Test: `backend/tests/test_expiry_notifications.py`

**Interfaces:**
- Consumes: `manager_user_ids`, `lease_tenant_user_ids`, `notify_users` (Task 2); `Notification` (Task 1).
- Produces: a `lease_expiry` notification per recipient user each time a reminder bucket fires.

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_expiry_notifications.py`:

```python
from datetime import date, timedelta

from sqlalchemy import select

from app.models import Notification
from app.services.reminders import run_expiry_reminders
from tests.test_leases import lease_body, make_property
from tests.test_portal import onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _lease_ending_in(client, headers, address, days):
    property_id = await make_property(client, headers, address)
    today = date.today()
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=days)),
            ),
            headers=headers,
        )
    ).json()["id"]


async def test_expiry_reminder_writes_notifications(client, db_session):
    headers = await landlord_headers(client, "exn@example.com")
    lease_id = await _lease_ending_in(client, headers, "Notify Way", 7)
    await onboard_tenant(client, db_session, headers, lease_id, "exn-t@example.com")

    sent = await run_expiry_reminders(db_session, date.today())
    assert sent == 1

    rows = (await db_session.execute(select(Notification))).scalars().all()
    # One for the landlord user, one for the joined tenant user.
    assert len(rows) == 2
    assert {r.category for r in rows} == {"lease_expiry"}
    assert all(r.link == f"/app/leases/{lease_id}" for r in rows)
    assert all(r.read_at is None for r in rows)


async def test_rerunning_adds_no_duplicate_notifications(client, db_session):
    headers = await landlord_headers(client, "exn2@example.com")
    lease_id = await _lease_ending_in(client, headers, "Dedup Way", 7)
    await onboard_tenant(client, db_session, headers, lease_id, "exn2-t@example.com")

    await run_expiry_reminders(db_session, date.today())
    assert await run_expiry_reminders(db_session, date.today()) == 0

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert len(rows) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_expiry_notifications.py -q`
Expected: FAIL — no `Notification` rows are written yet (`assert len(rows) == 2` sees 0).

- [ ] **Step 3: Write the notifications in `run_expiry_reminders`**

Edit `backend/app/services/reminders.py`. Extend the notify import to
`from app.services.notify import (lease_tenant_user_ids, manager_emails, manager_user_ids, notify_users, roster_emails, safe_send)`.

Then, inside `run_expiry_reminders`, after the tenant email loop and immediately **before**
`session.add(LeaseReminder(...))`, insert:

```python
        recipients = await manager_user_ids(session, lease.organization_id)
        recipients += await lease_tenant_user_ids(session, lease.id)
        await notify_users(
            session,
            recipients,
            lease.organization_id,
            "lease_expiry",
            f"Lease expiring in {days_left} days",
            f"The lease for {lease.tenant_name} at {address} expires on {lease.end_date}.",
            f"/app/leases/{lease.id}",
        )
```

The existing `await session.commit()` on the next lines persists both the `LeaseReminder` and the
notifications, so the existing dedup keeps notifications from being written twice.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_expiry_notifications.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 6: Commit and push**

```bash
git add backend/app/services/reminders.py backend/tests/test_expiry_notifications.py
git commit -m "Write in-app notifications when lease-expiry reminders fire"
git push
```
Then report and wait for approval.

---

### Task 4: Schemas + notifications API

**Files:**
- Create: `backend/app/schemas/notification.py`
- Create: `backend/app/routers/notifications.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_notifications_api.py`

**Interfaces:**
- Consumes: `Notification` (Task 1); `get_current_user`.
- Produces: `NotificationInfo`, `UnreadCount`; `GET /api/v1/me/notifications`, `GET /api/v1/me/notifications/unread_count`, `POST /api/v1/me/notifications/{id}/read`, `POST /api/v1/me/notifications/read_all`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_notifications_api.py`:

```python
from sqlalchemy import select

from app.models import Membership, Notification, User
from tests.test_properties_crud import landlord_headers


async def _user_and_org(db_session, email):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    org_id = (
        await db_session.execute(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        )
    ).scalar_one()
    return user, org_id


async def _add(db_session, user, org_id, title):
    db_session.add(
        Notification(
            organization_id=org_id,
            user_id=user.id,
            category="lease_expiry",
            title=title,
            body="body",
            link="/app",
        )
    )
    await db_session.commit()


async def test_lists_own_notifications(client, db_session):
    email = "napi@example.com"
    headers = await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)
    await _add(db_session, user, org_id, "First")

    body = (await client.get("/api/v1/me/notifications", headers=headers)).json()
    assert len(body) == 1
    assert body[0]["title"] == "First"
    assert body[0]["read_at"] is None


async def test_unread_filter_and_count(client, db_session):
    email = "nunread@example.com"
    headers = await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)
    await _add(db_session, user, org_id, "One")

    assert (await client.get("/api/v1/me/notifications/unread_count", headers=headers)).json()[
        "count"
    ] == 1
    unread = (
        await client.get("/api/v1/me/notifications?unread=true", headers=headers)
    ).json()
    assert len(unread) == 1


async def test_mark_read_and_read_all(client, db_session):
    email = "nread@example.com"
    headers = await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)
    await _add(db_session, user, org_id, "One")
    await _add(db_session, user, org_id, "Two")

    listed = (await client.get("/api/v1/me/notifications", headers=headers)).json()
    marked = await client.post(
        f"/api/v1/me/notifications/{listed[0]['id']}/read", headers=headers
    )
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None
    assert (await client.get("/api/v1/me/notifications/unread_count", headers=headers)).json()[
        "count"
    ] == 1

    cleared = await client.post("/api/v1/me/notifications/read_all", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["count"] == 0
    assert (await client.get("/api/v1/me/notifications/unread_count", headers=headers)).json()[
        "count"
    ] == 0


async def test_cannot_read_another_users_notification(client, db_session):
    owner_email = "nown@example.com"
    await landlord_headers(client, owner_email)
    owner, org_id = await _user_and_org(db_session, owner_email)
    await _add(db_session, owner, org_id, "Theirs")
    row = (await db_session.execute(select(Notification))).scalars().first()

    other = await landlord_headers(client, "nother@example.com")
    resp = await client.post(f"/api/v1/me/notifications/{row.id}/read", headers=other)
    assert resp.status_code == 404


async def test_requires_auth(client):
    assert (await client.get("/api/v1/me/notifications")).status_code == 401
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_notifications_api.py -q`
Expected: FAIL — routes missing (404s where 200/401 expected).

- [ ] **Step 3: Add the schemas**

Create `backend/app/schemas/notification.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


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

- [ ] **Step 4: Create the router**

Create `backend/app/routers/notifications.py`:

```python
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models import Notification, User
from app.schemas.notification import NotificationInfo, UnreadCount

router = APIRouter(prefix="/api/v1", tags=["notifications"])


def _to_info(notification: Notification) -> NotificationInfo:
    return NotificationInfo(
        id=notification.id,
        category=notification.category,
        title=notification.title,
        body=notification.body,
        link=notification.link,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


@router.get("/me/notifications", response_model=list[NotificationInfo])
async def list_notifications(
    unread: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[NotificationInfo]:
    """The caller's notifications, newest first (latest 100)."""
    query = select(Notification).where(Notification.user_id == user.id)
    if unread:
        query = query.where(Notification.read_at.is_(None))
    result = await session.execute(query.order_by(Notification.created_at.desc()).limit(100))
    return [_to_info(n) for n in result.scalars().all()]


@router.get("/me/notifications/unread_count", response_model=UnreadCount)
async def unread_count(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UnreadCount:
    """How many of the caller's notifications are unread."""
    count = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
    ).scalar_one()
    return UnreadCount(count=count)


@router.post("/me/notifications/{notification_id}/read", response_model=NotificationInfo)
async def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationInfo:
    """Mark one of the caller's notifications as read."""
    notification = (
        await session.execute(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(notification)
    return _to_info(notification)


@router.post("/me/notifications/read_all", response_model=UnreadCount)
async def mark_all_read(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UnreadCount:
    """Mark every unread notification of the caller as read."""
    result = await session.execute(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    )
    now = datetime.now(UTC)
    for notification in result.scalars().all():
        notification.read_at = now
    await session.commit()
    return UnreadCount(count=0)
```

- [ ] **Step 5: Mount the router**

Edit `backend/app/main.py`: add
`from app.routers.notifications import router as notifications_router` with the other router
imports, and `app.include_router(notifications_router)` after them.

- [ ] **Step 6: Run tests + full suite + ruff**

```bash
cd backend && uv run pytest tests/test_notifications_api.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/schemas/notification.py backend/app/routers/notifications.py \
        backend/app/main.py backend/tests/test_notifications_api.py
git commit -m "Add notifications inbox API"
git push
```
Then report and wait for approval.

---

### Task 5: Frontend lib + Messages page + dashboard badge

**Files:**
- Create: `frontend/src/lib/notifications.ts`
- Create: `frontend/src/app/app/messages/page.tsx`
- Modify: `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: the notifications API (Task 4).
- Produces: `@/lib/notifications` client; the `/app/messages` page; a Messages nav link in both dashboard branches.

Per `frontend/AGENTS.md`, this Next.js version may differ from training data — skim the relevant
guide in `frontend/node_modules/next/dist/docs/` before writing the page, and follow the existing
`src/app/app/maintenance/page.tsx` client-page pattern.

- [ ] **Step 1: Create the lib**

Create `frontend/src/lib/notifications.ts`:

```typescript
import { apiFetch } from "@/lib/api";

export interface NotificationInfo {
  id: string;
  category: string;
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  read_at: string | null;
}

export interface UnreadCount {
  count: number;
}

export function listNotifications(unreadOnly?: boolean) {
  const query = unreadOnly ? "?unread=true" : "";
  return apiFetch<NotificationInfo[]>(`/api/v1/me/notifications${query}`);
}

export function getUnreadCount() {
  return apiFetch<UnreadCount>("/api/v1/me/notifications/unread_count");
}

export function markRead(id: string) {
  return apiFetch<NotificationInfo>(`/api/v1/me/notifications/${id}/read`, { method: "POST" });
}

export function markAllRead() {
  return apiFetch<UnreadCount>("/api/v1/me/notifications/read_all", { method: "POST" });
}
```

- [ ] **Step 2: Create the Messages page**

Create `frontend/src/app/app/messages/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken } from "@/lib/auth";
import {
  listNotifications,
  markAllRead,
  markRead,
  type NotificationInfo,
} from "@/lib/notifications";

const FILTERS = [
  { label: "All", value: "" },
  { label: "Lease", value: "lease" },
  { label: "Rent", value: "rent" },
  { label: "Maintenance", value: "maintenance" },
];

export default function MessagesPage() {
  const router = useRouter();
  const [items, setItems] = useState<NotificationInfo[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    listNotifications()
      .then((n) => {
        if (active) setItems(n);
      })
      .catch(() => {
        if (active) setItems([]);
      });
    return () => {
      active = false;
    };
  }, [router]);

  async function refresh() {
    setItems(await listNotifications());
  }

  const shown = filter ? items.filter((n) => n.category.startsWith(filter)) : items;
  const unread = items.filter((n) => n.read_at === null).length;

  return (
    <main className="mx-auto max-w-2xl p-8">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Messages</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">{unread} unread</span>
          <select
            aria-label="Filter category"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded border px-2 py-1 text-sm"
          >
            {FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <button
            onClick={async () => {
              await markAllRead();
              await refresh();
            }}
            className="rounded border px-3 py-1 text-sm text-blue-600"
          >
            Mark all read
          </button>
        </div>
      </div>
      <ul className="space-y-2">
        {shown.map((n) => (
          <li key={n.id} className="rounded border p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className={n.read_at === null ? "font-semibold text-gray-900" : "text-gray-700"}>
                {n.read_at === null && (
                  <span className="mr-2 inline-block h-2 w-2 rounded-full bg-blue-600" />
                )}
                {n.title}
              </span>
              <span className="text-xs text-gray-500">
                {new Date(n.created_at).toLocaleDateString()}
              </span>
            </div>
            <p className="text-gray-600">{n.body}</p>
            <div className="mt-1 flex items-center gap-3">
              {n.link && (
                <Link href={n.link} className="text-xs text-blue-600">
                  View
                </Link>
              )}
              {n.read_at === null && (
                <button
                  onClick={async () => {
                    await markRead(n.id);
                    await refresh();
                  }}
                  className="text-xs text-blue-600"
                >
                  Mark read
                </button>
              )}
            </div>
          </li>
        ))}
        {shown.length === 0 && <li className="text-gray-500">No messages yet.</li>}
      </ul>
      <p className="mt-6">
        <Link href="/app" className="text-blue-600">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
```

- [ ] **Step 3: Add the dashboard Messages link with the unread count**

Edit `frontend/src/app/app/page.tsx`.

Add the import:

```tsx
import { getUnreadCount } from "@/lib/notifications";
```

Add state next to the other dashboard state:

```tsx
  const [unread, setUnread] = useState(0);
```

In the effect, right after `setMe(m);` (so it runs for every role), add its own guarded fetch that
cannot trigger the auth-failure logout:

```tsx
        getUnreadCount()
          .then((u) => {
            if (active) setUnread(u.count);
          })
          .catch(() => {
            if (active) setUnread(0);
          });
```

Add this link to **both** link rows — the tenant branch's `<div className="mt-6 flex gap-3">` and
the manager branch's `<div className="mt-4 flex gap-3">`:

```tsx
        <Link href="/app/messages" className="rounded border px-3 py-1 text-blue-600">
          Messages{unread > 0 ? ` (${unread})` : ""}
        </Link>
```

- [ ] **Step 4: Lint + build**

Run from `frontend/`: `npm run lint` then `npm run build`.
Expected: lint clean; build succeeds.

- [ ] **Step 5: Ruff (backend, keeps CI green) + commit**

```bash
cd backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add frontend/src/lib/notifications.ts "frontend/src/app/app/messages/page.tsx" frontend/src/app/app/page.tsx
git commit -m "Add messages inbox page and dashboard unread badge"
git push
```
Then report and wait for approval.

---

### Task 6: e2e + CI green

**Files:**
- Create: `frontend/e2e/messages.spec.ts`

**Interfaces:**
- Consumes: the Messages page (Task 5) and the notifications API (Task 4).

- [ ] **Step 1: Restart the local backend (new endpoints)**

```bash
lsof -ti tcp:8000 | xargs kill
cd backend && uv run uvicorn app.main:app --port 8000
```
(Leave running in a second shell for the e2e run.)

- [ ] **Step 2: Write the spec**

Create `frontend/e2e/messages.spec.ts`:

```typescript
import { expect, test } from "@playwright/test";

const landlord = `messages-${Date.now()}@example.com`;

test("landlord opens the messages inbox from the dashboard", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Msg Landlord");
  await page.getByPlaceholder("Organization name").fill("Msg Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Messages" }).click();
  await expect(page).toHaveURL(/\/app\/messages$/);
  await expect(page.getByRole("heading", { name: "Messages" })).toBeVisible();
  await expect(page.getByText("No messages yet.")).toBeVisible();
});
```

- [ ] **Step 3: Run the e2e suite (serial, CI-safe)**

Run from `frontend/`: `npx playwright test --workers=1`
Expected: all specs pass, including `messages`.

- [ ] **Step 4: Lint + build + ruff**

```bash
cd frontend && npm run lint && npm run build
cd ../backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: clean.

- [ ] **Step 5: Commit, push, watch CI green**

```bash
git add "frontend/e2e/messages.spec.ts"
git commit -m "Add messages inbox e2e"
git push
gh run watch --exit-status
```
Expected: all three CI jobs (backend, frontend, e2e) green.

- [ ] **Step 6: Report — Milestone 6.1 complete**

Report: every user now has an in-app inbox at `/app/messages` with unread markers, per-item and
bulk mark-as-read, and a dashboard badge; lease-expiry reminders write to it as the first source,
and `services/notify.py` is the shared plumbing M6.2 will reuse. Wait for approval to plan
**Milestone 6.2** (rent reminders + maintenance notifications, both writing to this inbox).

---

## Self-Review

**Spec coverage:**
- `Notification` model (string category, indexes, no cascade) + migration -> Task 1. ✓
- Shared `notify.py` (safe_send / manager_emails / roster_emails / manager_user_ids /
  lease_tenant_user_ids / notify_users, no commit) + `reminders.py` refactor -> Task 2. ✓
- The flagged monkeypatch retarget in `tests/test_reminders.py` -> Task 2, Step 6. ✓
- Lease-expiry as the first source, deduped by the existing `LeaseReminder` -> Task 3. ✓
- Endpoints (list, `?unread`, unread_count, mark one, read_all, 404 on another user's row, 401)
  -> Task 4. ✓
- Frontend lib, Messages page (unread styling, client-side category filter, mark read / mark all,
  link, empty state) and the badge in **both** dashboard branches -> Task 5. ✓
- e2e empty state -> Task 6. ✓
- Out of scope (rent/maintenance sources, push, SMS, preferences, pagination) -> not planned. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the only `<rev>` is the
Alembic revision id. ✓

**Type consistency:** `NotificationInfo` fields (`id`, `category`, `title`, `body`, `link`,
`created_at`, `read_at`) and `UnreadCount{count}` are identical across the schema, `_to_info`, and
the frontend types; `notify_users(session, user_ids, organization_id, category, title, body, link)`
is called with exactly that signature in Task 3; `manager_user_ids` / `lease_tenant_user_ids`
return `list[uuid.UUID]` and are concatenated with `+` in Task 3; frontend
`listNotifications`/`getUnreadCount`/`markRead`/`markAllRead` match the four endpoint paths and
methods. ✓
