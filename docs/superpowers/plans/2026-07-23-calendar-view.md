# Calendar View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An organization-wide calendar for the management side that overlays lease starts/ends, rent due dates, and maintenance onto a month grid, and lets managers add, edit, and delete their own timed events.

**Architecture:** A new `CalendarEvent` table with CRUD endpoints, plus one read `GET /api/v1/calendar` feed that aggregates four derived kinds (from existing Lease/Charge/MaintenanceRequest rows) with the custom events, all org-scoped. The frontend is a hand-built month grid that fetches the feed for the visible range.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js 16, Playwright. No new dependency (the month grid is plain date math + CSS grid).

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Migration is a plain table (no enum). Current head: `591d2d4c3249`. Create it with `uv run alembic revision -m "add calendar_events"` to get a fresh revision id, then fill the body by hand (do not `--autogenerate`). Verify upgrade -> downgrade -> upgrade.
- Management side only: endpoints require `require_roles(landlord, property_manager)`; the page lives in the manager `AppShell` (tenants use `PortalShell`, so they never see it). No tenant/`/me` calendar this milestone.
- Timezone rule: derived records are calendar dates — send them as `date` (`"YYYY-MM-DD"`), never midnight-UTC datetimes, so they never shift a day. Custom events are instants — tz-aware `start_at`/`end_at`.
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- Backend commands run from `backend/`, frontend from `frontend/`. The shell keeps its cwd between commands — always `cd` explicitly.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/calendar_event.py` | `CalendarEvent` model |
| `backend/app/models/__init__.py` | register it |
| `backend/alembic/versions/<rev>_add_calendar_events.py` | table, reversible |
| `backend/app/schemas/calendar.py` | `CalendarEventCreate/Update/Info`, `CalendarEntry` |
| `backend/app/routers/calendar.py` | CRUD + aggregation feed |
| `backend/app/main.py` | mount the router |
| `backend/tests/test_calendar.py` | the whole feature |
| `frontend/src/lib/calendar.ts` | API client + types |
| `frontend/src/app/app/calendar/page.tsx` | month-grid page + dialogs |
| `frontend/src/components/app-shell.tsx` | nav entry "Calendar" |
| `frontend/e2e/calendar.spec.ts` | end-to-end |

---

### Task 1: CalendarEvent model, register, migration

**Files:**
- Create: `backend/app/models/calendar_event.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_calendar_events.py`
- Test: `backend/tests/test_calendar.py`

**Interfaces:**
- Produces: `CalendarEvent(id, organization_id, title, description, start_at, end_at, property_id, created_by, created_at)`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_calendar.py`:

```python
import uuid
from datetime import datetime, timedelta, UTC

from sqlalchemy import select

from app.models import CalendarEvent, Membership, User
from tests.test_properties_crud import landlord_headers


async def _org_and_user(db_session, email):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    org_id = (
        await db_session.execute(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        )
    ).scalar_one()
    return org_id, user.id


async def test_calendar_event_round_trip(client, db_session):
    email = "calmodel@example.com"
    await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)

    start = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    event = CalendarEvent(
        organization_id=org_id,
        title="Inspection",
        start_at=start,
        end_at=start + timedelta(hours=1),
        created_by=user_id,
    )
    db_session.add(event)
    await db_session.commit()

    stored = (
        await db_session.execute(select(CalendarEvent).where(CalendarEvent.id == event.id))
    ).scalar_one()
    assert stored.title == "Inspection"
    assert stored.property_id is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_calendar.py -q`
Expected: FAIL with `ImportError: cannot import name 'CalendarEvent'`.

- [ ] **Step 3: Write the model**

Create `backend/app/models/calendar_event.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Add to `backend/app/models/__init__.py`: import `CalendarEvent` from `.calendar_event` and add it to `__all__`.

- [ ] **Step 4: Create and fill the migration**

Run: `cd backend && uv run alembic revision -m "add calendar_events"` (this prints the new file path with a fresh revision id; do not use `--autogenerate`). Fill its body:

```python
def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_calendar_events_organization_id"), "calendar_events", ["organization_id"]
    )
    op.create_index(
        op.f("ix_calendar_events_property_id"), "calendar_events", ["property_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_calendar_events_property_id"), table_name="calendar_events")
    op.drop_index(op.f("ix_calendar_events_organization_id"), table_name="calendar_events")
    op.drop_table("calendar_events")
```

Confirm `down_revision = "591d2d4c3249"` (the revision command sets it to the current head automatically).

- [ ] **Step 5: Verify the migration round-trips, then run the test**

```bash
cd backend
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run pytest tests/test_calendar.py -q
```
Expected: migrations clean both ways; test passes.

- [ ] **Step 6: Full test run, ruff, commit, push**

```bash
cd backend && uv run pytest
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add backend/app/models/calendar_event.py backend/app/models/__init__.py backend/alembic/versions backend/tests/test_calendar.py
git commit -m "Add the CalendarEvent model and migration"
git push origin main
```
Then report and wait for approval.

---

### Task 2: Event schemas + CRUD endpoints

**Files:**
- Create: `backend/app/schemas/calendar.py`
- Create: `backend/app/routers/calendar.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_calendar.py`

**Interfaces:**
- Consumes: `CalendarEvent`; `manager = require_roles(landlord, property_manager)` and `get_owned_lease`-style org scoping (mirror `app/routers/documents.py`).
- Produces: `POST /api/v1/calendar/events`, `PATCH /api/v1/calendar/events/{id}`, `DELETE /api/v1/calendar/events/{id}`; `CalendarEventInfo`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_calendar.py` (top-level imports already present):

```python
def _event_body(start="2026-08-01T09:00:00Z", end="2026-08-01T10:00:00Z", **kw):
    return {"title": "Viewing", "start_at": start, "end_at": end, **kw}


async def test_create_event(client):
    headers = await landlord_headers(client, "calcreate@example.com")
    r = await client.post("/api/v1/calendar/events", json=_event_body(), headers=headers)
    assert r.status_code == 201
    assert r.json()["title"] == "Viewing"


async def test_create_event_rejects_end_before_start(client):
    headers = await landlord_headers(client, "calbad@example.com")
    body = _event_body(start="2026-08-01T10:00:00Z", end="2026-08-01T09:00:00Z")
    r = await client.post("/api/v1/calendar/events", json=body, headers=headers)
    assert r.status_code == 400


async def test_cross_org_event_is_404(client):
    owner = await landlord_headers(client, "calowner@example.com")
    event_id = (
        await client.post("/api/v1/calendar/events", json=_event_body(), headers=owner)
    ).json()["id"]
    stranger = await landlord_headers(client, "calthief@example.com")
    assert (
        await client.patch(
            f"/api/v1/calendar/events/{event_id}", json={"title": "x"}, headers=stranger
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/calendar/events/{event_id}", headers=stranger)
    ).status_code == 404


async def test_update_and_delete_event(client):
    headers = await landlord_headers(client, "caledit@example.com")
    event_id = (
        await client.post("/api/v1/calendar/events", json=_event_body(), headers=headers)
    ).json()["id"]
    patched = await client.patch(
        f"/api/v1/calendar/events/{event_id}", json={"title": "Renamed"}, headers=headers
    )
    assert patched.json()["title"] == "Renamed"
    assert (
        await client.delete(f"/api/v1/calendar/events/{event_id}", headers=headers)
    ).status_code == 204
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_calendar.py -q`
Expected: FAIL (404 for the POST route — router not mounted yet).

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/calendar.py`:

```python
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CalendarEventCreate(BaseModel):
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime
    property_id: uuid.UUID | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    property_id: uuid.UUID | None = None


class CalendarEventInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    start_at: datetime
    end_at: datetime
    property_id: uuid.UUID | None
    created_at: datetime


class CalendarEntry(BaseModel):
    kind: str
    title: str
    all_day: bool
    date: date | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    link: str | None = None
    event_id: uuid.UUID | None = None
```

- [ ] **Step 4: Write the CRUD endpoints**

Create `backend/app/routers/calendar.py` (feed added in Task 3):

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import CalendarEvent, Membership, Property
from app.routers.leases import manager
from app.schemas.calendar import CalendarEventCreate, CalendarEventInfo, CalendarEventUpdate

router = APIRouter(prefix="/api/v1", tags=["calendar"])


async def _owned_event(event_id, membership, session) -> CalendarEvent:
    event = (
        await session.execute(
            select(CalendarEvent).where(
                CalendarEvent.id == event_id,
                CalendarEvent.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


async def _check_property(property_id, membership, session) -> None:
    if property_id is None:
        return
    owned = (
        await session.execute(
            select(Property.id).where(
                Property.id == property_id,
                Property.organization_id == membership.organization_id,
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=400, detail="Unknown property")


@router.post("/calendar/events", status_code=201, response_model=CalendarEventInfo)
async def create_event(
    body: CalendarEventCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> CalendarEvent:
    if body.end_at < body.start_at:
        raise HTTPException(status_code=400, detail="end_at must not precede start_at")
    await _check_property(body.property_id, membership, session)
    event = CalendarEvent(
        organization_id=membership.organization_id,
        title=body.title,
        description=body.description,
        start_at=body.start_at,
        end_at=body.end_at,
        property_id=body.property_id,
        created_by=membership.user_id,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.patch("/calendar/events/{event_id}", response_model=CalendarEventInfo)
async def update_event(
    event_id: uuid.UUID,
    body: CalendarEventUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> CalendarEvent:
    event = await _owned_event(event_id, membership, session)
    data = body.model_dump(exclude_unset=True)
    if "property_id" in data:
        await _check_property(data["property_id"], membership, session)
    for field, value in data.items():
        setattr(event, field, value)
    if event.end_at < event.start_at:
        raise HTTPException(status_code=400, detail="end_at must not precede start_at")
    await session.commit()
    await session.refresh(event)
    return event


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_event(
    event_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    event = await _owned_event(event_id, membership, session)
    await session.delete(event)
    await session.commit()
    return Response(status_code=204)
```

Mount in `backend/app/main.py`: `from app.routers.calendar import router as calendar_router` and `app.include_router(calendar_router)` (next to the others).

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/test_calendar.py -q`
Expected: PASS.

- [ ] **Step 6: Full test run, ruff, commit, push** (same sequence as Task 1; commit message `Add calendar event create, update and delete`). Report and wait.

---

### Task 3: Aggregation feed

**Files:**
- Modify: `backend/app/routers/calendar.py`
- Test: `backend/tests/test_calendar.py`

**Interfaces:**
- Consumes: `Lease`, `Property`, `Charge`, `MaintenanceRequest`, `CalendarEvent`.
- Produces: `GET /api/v1/calendar?start=&end=` -> `list[CalendarEntry]`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_calendar.py`. Reuse `make_lease` (from `tests.test_portal`) which creates a lease starting yesterday and ending +30 days; seed a charge and a maintenance request, and one custom event; assert one entry per kind:

```python
from datetime import date, timedelta

from tests.test_portal import make_lease


async def test_feed_returns_derived_and_custom_entries(client, db_session):
    headers = await landlord_headers(client, "calfeed@example.com")
    lease_id = await make_lease(client, headers, "1 Calendar Way")
    # A custom event today.
    today = date.today()
    await client.post(
        "/api/v1/calendar/events",
        json=_event_body(
            start=f"{today}T09:00:00Z", end=f"{today}T10:00:00Z", title="Site visit"
        ),
        headers=headers,
    )

    start = today - timedelta(days=40)
    end = today + timedelta(days=40)
    body = (
        await client.get(f"/api/v1/calendar?start={start}&end={end}", headers=headers)
    ).json()

    kinds = {e["kind"] for e in body}
    assert "lease_start" in kinds
    assert "lease_end" in kinds
    assert "event" in kinds
    event = next(e for e in body if e["kind"] == "event")
    assert event["all_day"] is False
    assert event["event_id"]
    lease_end = next(e for e in body if e["kind"] == "lease_end")
    assert lease_end["all_day"] is True
    assert lease_end["link"] == f"/app/leases/{lease_id}"


async def test_feed_is_org_scoped(client, db_session):
    owner = await landlord_headers(client, "calfeedowner@example.com")
    await make_lease(client, owner, "2 Private Way")
    stranger = await landlord_headers(client, "calfeedthief@example.com")
    today = date.today()
    body = (
        await client.get(
            f"/api/v1/calendar?start={today - timedelta(days=40)}&end={today + timedelta(days=40)}",
            headers=stranger,
        )
    ).json()
    assert body == []
```

(If the seeded lease produces rent charges automatically, also assert `"rent_due" in kinds`; otherwise seed a `Charge` directly like `tests/test_rent_reminders._charge`. Verify which when the test first runs — do not leave it guessed.)

- [ ] **Step 2: Run to verify it fails** — `GET /api/v1/calendar` 404 (no feed route).

- [ ] **Step 3: Implement the feed**

Add to `backend/app/routers/calendar.py`:

```python
from datetime import date

from app.models import Charge, Lease, MaintenanceRequest
from app.schemas.calendar import CalendarEntry


@router.get("/calendar", response_model=list[CalendarEntry])
async def calendar_feed(
    start: date,
    end: date,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[CalendarEntry]:
    """Every dated record in [start, end] for the org: derived kinds plus events."""
    org = membership.organization_id
    entries: list[CalendarEntry] = []

    leases = (
        await session.execute(
            select(Lease, Property.address)
            .join(Property, Property.id == Lease.property_id)
            .where(Lease.organization_id == org)
        )
    ).all()
    for lease, address in leases:
        if start <= lease.start_date <= end:
            entries.append(
                CalendarEntry(
                    kind="lease_start",
                    title=f"Lease starts: {address}",
                    all_day=True,
                    date=lease.start_date,
                    link=f"/app/leases/{lease.id}",
                )
            )
        if start <= lease.end_date <= end:
            entries.append(
                CalendarEntry(
                    kind="lease_end",
                    title=f"Lease ends: {address}",
                    all_day=True,
                    date=lease.end_date,
                    link=f"/app/leases/{lease.id}",
                )
            )

    charges = (
        (
            await session.execute(
                select(Charge).where(
                    Charge.organization_id == org,
                    Charge.due_date >= start,
                    Charge.due_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    entries += [
        CalendarEntry(
            kind="rent_due",
            title=f"Rent due ${c.amount_due}",
            all_day=True,
            date=c.due_date,
            link=f"/app/leases/{c.lease_id}",
        )
        for c in charges
    ]

    requests = (
        (
            await session.execute(
                select(MaintenanceRequest).where(MaintenanceRequest.organization_id == org)
            )
        )
        .scalars()
        .all()
    )
    for r in requests:
        created = r.created_at.date()
        if start <= created <= end:
            entries.append(
                CalendarEntry(
                    kind="maintenance",
                    title=r.title,
                    all_day=True,
                    date=created,
                    link="/app/maintenance",
                )
            )

    events = (
        (await session.execute(select(CalendarEvent).where(CalendarEvent.organization_id == org)))
        .scalars()
        .all()
    )
    for e in events:
        if e.start_at.date() <= end and e.end_at.date() >= start:
            entries.append(
                CalendarEntry(
                    kind="event",
                    title=e.title,
                    all_day=False,
                    start_at=e.start_at,
                    end_at=e.end_at,
                    event_id=e.id,
                )
            )
    return entries
```

- [ ] **Step 4: Run the tests** — PASS. Confirm the rent-charge assertion decision from Step 1.

- [ ] **Step 5: Full test run, ruff, commit, push** (`Add the calendar aggregation feed`). Report and wait.

---

### Task 4: Frontend client + month-grid page + nav

**Files:**
- Create: `frontend/src/lib/calendar.ts`
- Create: `frontend/src/app/app/calendar/page.tsx`
- Modify: `frontend/src/components/app-shell.tsx`

**Interfaces:**
- Consumes: `apiFetch` (`@/lib/api`); existing UI (`Card`, `Button`, `AppShell`, `useShell`).
- Produces: `listCalendar(start, end)`, `createEvent`, `updateEvent`, `deleteEvent`; the `/app/calendar` route; the accessible name `Calendar`.

- [ ] **Step 1: Add the API client**

Create `frontend/src/lib/calendar.ts`:

```ts
import { apiFetch } from "@/lib/api";

export type CalendarKind = "lease_start" | "lease_end" | "rent_due" | "maintenance" | "event";

export interface CalendarEntry {
  kind: CalendarKind;
  title: string;
  all_day: boolean;
  date: string | null;
  start_at: string | null;
  end_at: string | null;
  link: string | null;
  event_id: string | null;
}

export interface CalendarEventInput {
  title: string;
  description?: string | null;
  start_at: string;
  end_at: string;
  property_id?: string | null;
}

export interface CalendarEventInfo extends CalendarEventInput {
  id: string;
  created_at: string;
}

export function listCalendar(start: string, end: string) {
  return apiFetch<CalendarEntry[]>(`/api/v1/calendar?start=${start}&end=${end}`);
}

export function createEvent(body: CalendarEventInput) {
  return apiFetch<CalendarEventInfo>("/api/v1/calendar/events", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateEvent(id: string, body: Partial<CalendarEventInput>) {
  return apiFetch<CalendarEventInfo>(`/api/v1/calendar/events/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteEvent(id: string) {
  return apiFetch<void>(`/api/v1/calendar/events/${id}`, { method: "DELETE" });
}
```

(Confirm `apiFetch` sets the JSON `Content-Type` for a string body — mirror how `@/lib/leases` posts. If it does not, follow the existing pattern there.)

- [ ] **Step 2: Add the month-grid page (render only)**

Create `frontend/src/app/app/calendar/page.tsx`. Compute a fixed 6x7 grid; fetch the feed for the visible range; render chips. Date helpers:

```tsx
function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function gridDays(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - first.getDay()); // back up to Sunday
  return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
}
```

Chip color by kind (Tailwind tokens already in the design system): `lease_end` -> danger, `rent_due` -> warning, `lease_start` -> brand, `maintenance` -> muted/neutral, `event` -> brand accent. Group entries by their day key: derived by `entry.date`, custom by `ymd(new Date(entry.start_at))`. Render each day cell with its chips; greyed cells for days outside the current month. Provide Prev / Today / Next controls that change `year`/`month` state and refetch `listCalendar(ymd(days[0]), ymd(days[41]))`.

Wrap the page in `AppShell` with `useShell()` (mirror `frontend/src/app/app/maintenance/page.tsx`).

- [ ] **Step 3: Add the nav entry**

In `frontend/src/components/app-shell.tsx`, add a nav link to `/app/calendar` labelled `Calendar` alongside the existing manager nav items (Dashboard, Properties, Leases, Maintenance, Messages, Team). Match the existing link markup exactly.

- [ ] **Step 4: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both clean.

- [ ] **Step 5: Commit and push** (`Add the calendar page and month grid`). Report and wait.

---

### Task 5: Add / edit / delete custom events

**Files:**
- Modify: `frontend/src/app/app/calendar/page.tsx`

**Interfaces:**
- Consumes: `createEvent`, `updateEvent`, `deleteEvent`; `ConfirmDialog` (`@/components/ui`).

- [ ] **Step 1: Add the event dialog and handlers**

Add state for a dialog holding the editing event (or a new one pre-filled with a clicked day) with fields title / description / start / end (two `datetime-local` inputs) / optional property `<Select>` (fetch properties via `listProperties` from `@/lib/properties`). Convert on submit: `new Date(localValue).toISOString()`; convert `start_at` back with `toLocaleString()` for the chip label. Handlers:

```tsx
async function onSaveEvent() {
  const body = {
    title,
    description,
    start_at: new Date(startLocal).toISOString(),
    end_at: new Date(endLocal).toISOString(),
    property_id: propertyId || null,
  };
  if (editingId) await updateEvent(editingId, body);
  else await createEvent(body);
  setDialogOpen(false);
  await refresh();
}

async function onDeleteEvent() {
  if (editingId) await deleteEvent(editingId);
  setConfirmOpen(false);
  setDialogOpen(false);
  await refresh();
}
```

- [ ] **Step 2: Wire interactions**

- Click an empty day cell -> open the dialog with `startLocal`/`endLocal` pre-filled to that day 09:00/10:00, `editingId = null`.
- Click a custom-event chip (`entry.event_id`) -> open the dialog pre-filled from that event, `editingId = entry.event_id`, with a Delete button that opens a `ConfirmDialog` (`label="Delete event"`, `confirmLabel="Yes, delete"`, message "Delete this event? This cannot be undone.").
- Click a derived chip (`entry.link`) -> `router.push(entry.link)`.

Reuse the modal/dialog markup pattern from `frontend/src/app/app/leases/[leaseId]/page.tsx` and the existing `ConfirmDialog`.

- [ ] **Step 3: Lint and build** — clean.

- [ ] **Step 4: Commit and push** (`Add create, edit and delete for calendar events`). Report and wait.

---

### Task 6: End-to-end + CI

**Files:**
- Create: `frontend/e2e/calendar.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-5.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/calendar.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const landlord = `cal-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("a manager sees derived entries and manages a custom event", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Cal Owner");
  await page.getByPlaceholder("Organization name").fill("Cal Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // A lease whose end date is inside this month's grid.
  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("7 Cal Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "7 Cal Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Casey Cal");
  await page.getByPlaceholder("Tenant email").fill(`cal-t-${Date.now()}@example.com`);
  await page.getByLabel("Rent").fill("500");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(10));
  await page.getByRole("button", { name: "Add lease" }).click();

  await page.getByRole("link", { name: "Calendar" }).click();
  await expect(page).toHaveURL(/\/app\/calendar$/);
  await expect(page.getByText(/Lease ends/)).toBeVisible();

  // Add a custom event on some day, then confirm, edit, delete it.
  // (Finalise the exact day-cell and dialog selectors against the real markup
  //  when the test first runs; assert the event title becomes visible, the
  //  edited title replaces it, and it is gone after "Yes, delete".)
});
```

Finalise the add/edit/delete selectors against the real page markup when the test first runs (do not leave them guessed — the plan author for this task fills them in against the built page).

- [ ] **Step 2: Run the new spec** — `cd frontend && npx playwright test calendar` -> 1 passed.
- [ ] **Step 3: Run the whole e2e suite** — `npx playwright test --workers=1` -> all pass.
- [ ] **Step 4: Full backend run + ruff** (from `backend/`).
- [ ] **Step 5: Commit and push** (`Add calendar view e2e`).
- [ ] **Step 6: Confirm CI is green** — `gh run list --limit 3`; read the log on any failure before changing anything. Report and wait.
