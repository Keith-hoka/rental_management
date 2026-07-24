# Property Inspections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Managers schedule/complete property inspections with a per-area condition checklist and photos; tenants read their lease's inspections.

**Architecture:** `Inspection` + child `InspectionItem` tables. Manager CRUD treats items as a whole array (replace); photos reuse the maintenance `save_image` pipeline. A tenant `/me` endpoint returns their lease's inspections. Two new frontend surfaces (manager page, tenant card).

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js 16, Playwright. No new dependency.

## Global Constraints

- Package manager: `uv` only; never `python3` / `pip`.
- No emojis in code/logs. Short modules/functions; docstrings over comments; do not program defensively.
- Ruff sequence before every push, from `backend/`: `format` -> `check --fix` -> `check` -> `format --check`.
- Test files keep imports at top (E402).
- Migration adds **three PG enums** (`inspectiontype`, `inspectionstatus`, `inspectioncondition`) and **two tables**. Hand-write it (no `--autogenerate`); `downgrade` drops `inspection_items` then `inspections`, then the three enums via `sa.Enum(name=...).drop(op.get_bind())`. Current head: `697ac076b56e`. Verify upgrade -> downgrade -> upgrade.
- Managers only for `/api/v1/inspections*` (`require_roles(landlord, property_manager)`), org-scoped, cross-org 404. Tenants use the `/me` endpoint.
- Photos: `save_image` (from `app/core/uploads.py`) returns `/uploads/<name>`; append to `image_urls`, exactly like `app/routers/maintenance.py`.
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- Backend from `backend/`, frontend from `frontend/`; always `cd` explicitly.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/inspection.py` | 3 enums, `Inspection`, `InspectionItem` |
| `backend/app/models/__init__.py` | register them |
| `backend/alembic/versions/<rev>_add_inspections.py` | 2 tables + 3 enums, reversible |
| `backend/app/schemas/inspection.py` | item + inspection schemas |
| `backend/app/routers/inspections.py` | manager CRUD + images + tenant list |
| `backend/app/main.py` | mount router |
| `backend/tests/test_inspections.py` | the feature |
| `frontend/src/lib/inspections.ts` | client |
| `frontend/src/app/app/inspections/page.tsx` | manager page |
| `frontend/src/components/app-shell.tsx` | nav entry |
| `frontend/src/app/app/page.tsx` | tenant card |
| `frontend/e2e/inspections.spec.ts` | end-to-end |

---

### Task I-T1: Models, enums, migration

**Files:** Create `backend/app/models/inspection.py`; Modify `backend/app/models/__init__.py`; Create migration; Test `backend/tests/test_inspections.py`.

**Interfaces:** Produces `InspectionType` (move_in/move_out/routine), `InspectionStatus` (scheduled/completed), `InspectionCondition` (good/fair/poor); `Inspection(id, organization_id, property_id, lease_id, type, status, scheduled_for, note, image_urls, created_by, created_at, updated_at)`; `InspectionItem(id, inspection_id, position, area, condition, note)`.

- [ ] **Step 1: Failing test** — `backend/tests/test_inspections.py`:

```python
import uuid
from datetime import date

from sqlalchemy import select

from app.models import Inspection, InspectionCondition, InspectionItem, InspectionStatus, InspectionType
from tests.test_calendar import _org_and_user
from tests.test_leases import make_property
from tests.test_properties_crud import landlord_headers


async def test_inspection_round_trip(client, db_session):
    email = "inspmodel@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    property_id = await make_property(client, headers, "1 Inspect St")
    inspection = Inspection(
        organization_id=org_id,
        property_id=uuid.UUID(property_id),
        type=InspectionType.move_in,
        status=InspectionStatus.scheduled,
        scheduled_for=date(2026, 8, 1),
        created_by=user_id,
    )
    db_session.add(inspection)
    await db_session.flush()
    db_session.add(
        InspectionItem(
            inspection_id=inspection.id, position=0, area="Kitchen", condition=InspectionCondition.good
        )
    )
    await db_session.commit()

    stored = (
        await db_session.execute(select(Inspection).where(Inspection.id == inspection.id))
    ).scalar_one()
    assert stored.status == InspectionStatus.scheduled
    assert stored.image_urls == []
    item = (
        await db_session.execute(
            select(InspectionItem).where(InspectionItem.inspection_id == inspection.id)
        )
    ).scalar_one()
    assert item.area == "Kitchen"
    assert item.condition == InspectionCondition.good
```

- [ ] **Step 2: Run -> fail** (`ImportError`). `cd backend && uv run pytest tests/test_inspections.py -q`.

- [ ] **Step 3: Models** — `backend/app/models/inspection.py`:

```python
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class InspectionType(str, enum.Enum):
    move_in = "move_in"
    move_out = "move_out"
    routine = "routine"


class InspectionStatus(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"


class InspectionCondition(str, enum.Enum):
    good = "good"
    fair = "fair"
    poor = "poor"


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    lease_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[InspectionType] = mapped_column(Enum(InspectionType))
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus), default=InspectionStatus.scheduled
    )
    scheduled_for: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InspectionItem(Base):
    __tablename__ = "inspection_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    area: Mapped[str] = mapped_column(String(100))
    condition: Mapped[InspectionCondition] = mapped_column(Enum(InspectionCondition))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Register all five names in `backend/app/models/__init__.py` (import + `__all__`).

- [ ] **Step 4: Migration** — `cd backend && uv run alembic revision -m "add inspections"`. Fill `upgrade` with two `op.create_table` (inspections carries the `inspectiontype` + `inspectionstatus` `sa.Enum`s; inspection_items carries `inspectioncondition`), plus indexes on the FKs. `downgrade`:

```python
def downgrade() -> None:
    op.drop_index(op.f("ix_inspection_items_inspection_id"), table_name="inspection_items")
    op.drop_table("inspection_items")
    op.drop_index(op.f("ix_inspections_lease_id"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_property_id"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_organization_id"), table_name="inspections")
    op.drop_table("inspections")
    sa.Enum(name="inspectioncondition").drop(op.get_bind())
    sa.Enum(name="inspectiontype").drop(op.get_bind())
    sa.Enum(name="inspectionstatus").drop(op.get_bind())
```

Confirm `down_revision == "697ac076b56e"`.

- [ ] **Step 5: Round-trip + test** — `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run pytest tests/test_inspections.py -q`.

- [ ] **Step 6: Full run, ruff, commit, push** (`Add the Inspection models and migration`). Report and wait.

---

### Task I-T2: Schemas + manager CRUD (nested items)

**Files:** Create `backend/app/schemas/inspection.py`, `backend/app/routers/inspections.py`; Modify `backend/app/main.py`; Test `backend/tests/test_inspections.py`.

**Interfaces:** Produces `POST/GET/PATCH/DELETE /api/v1/inspections`; `InspectionInfo` with nested `items`.

- [ ] **Step 1: Failing tests** — append endpoint tests: create with items (assert items in order + status), foreign property 400, foreign lease 400, list (+ property filter), patch status scheduled->completed, patch items replaces, patch without items keeps them, delete 204, cross-org 404. Use `make_property` and a helper `_body(property_id, **kw)`.

- [ ] **Step 2: Run -> fail** (404).

- [ ] **Step 3: Schemas** — `backend/app/schemas/inspection.py`:

```python
import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models import InspectionCondition, InspectionStatus, InspectionType


class InspectionItemIn(BaseModel):
    area: str
    condition: InspectionCondition
    note: str | None = None


class InspectionItemInfo(BaseModel):
    id: uuid.UUID
    area: str
    condition: InspectionCondition
    note: str | None


class InspectionCreate(BaseModel):
    property_id: uuid.UUID
    lease_id: uuid.UUID | None = None
    type: InspectionType
    status: InspectionStatus = InspectionStatus.scheduled
    scheduled_for: date
    note: str | None = None
    items: list[InspectionItemIn] = []


class InspectionUpdate(BaseModel):
    status: InspectionStatus | None = None
    note: str | None = None
    scheduled_for: date | None = None
    items: list[InspectionItemIn] | None = None


class InspectionInfo(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    lease_id: uuid.UUID | None
    type: InspectionType
    status: InspectionStatus
    scheduled_for: date
    note: str | None
    image_urls: list[str]
    items: list[InspectionItemInfo]
    created_at: datetime
```

- [ ] **Step 4: Router** — `backend/app/routers/inspections.py` with helpers and endpoints:

```python
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Inspection, InspectionItem, Lease, Membership, Property
from app.routers.leases import manager
from app.schemas.inspection import (
    InspectionCreate,
    InspectionInfo,
    InspectionItemInfo,
    InspectionUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["inspections"])


async def _owned(inspection_id, membership, session) -> Inspection:
    inspection = (
        await session.execute(
            select(Inspection).where(
                Inspection.id == inspection_id,
                Inspection.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


async def _check_in_org(model, obj_id, membership, session, detail) -> None:
    if obj_id is None:
        return
    found = (
        await session.execute(
            select(model.id).where(
                model.id == obj_id, model.organization_id == membership.organization_id
            )
        )
    ).first()
    if found is None:
        raise HTTPException(status_code=400, detail=detail)


async def _set_items(session, inspection_id, items) -> None:
    existing = (
        (
            await session.execute(
                select(InspectionItem).where(InspectionItem.inspection_id == inspection_id)
            )
        )
        .scalars()
        .all()
    )
    for it in existing:
        await session.delete(it)
    await session.flush()
    for i, item in enumerate(items):
        session.add(
            InspectionItem(
                inspection_id=inspection_id,
                position=i,
                area=item.area,
                condition=item.condition,
                note=item.note,
            )
        )


async def _info(session, inspection) -> InspectionInfo:
    items = (
        (
            await session.execute(
                select(InspectionItem)
                .where(InspectionItem.inspection_id == inspection.id)
                .order_by(InspectionItem.position)
            )
        )
        .scalars()
        .all()
    )
    return InspectionInfo(
        id=inspection.id,
        property_id=inspection.property_id,
        lease_id=inspection.lease_id,
        type=inspection.type,
        status=inspection.status,
        scheduled_for=inspection.scheduled_for,
        note=inspection.note,
        image_urls=inspection.image_urls,
        items=[
            InspectionItemInfo(id=it.id, area=it.area, condition=it.condition, note=it.note)
            for it in items
        ],
        created_at=inspection.created_at,
    )


@router.post("/inspections", status_code=201, response_model=InspectionInfo)
async def create_inspection(
    body: InspectionCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> InspectionInfo:
    await _check_in_org(Property, body.property_id, membership, session, "Unknown property")
    await _check_in_org(Lease, body.lease_id, membership, session, "Unknown lease")
    inspection = Inspection(
        organization_id=membership.organization_id,
        property_id=body.property_id,
        lease_id=body.lease_id,
        type=body.type,
        status=body.status,
        scheduled_for=body.scheduled_for,
        note=body.note,
        created_by=membership.user_id,
    )
    session.add(inspection)
    await session.flush()
    await _set_items(session, inspection.id, body.items)
    await session.commit()
    await session.refresh(inspection)
    return await _info(session, inspection)


@router.get("/inspections", response_model=list[InspectionInfo])
async def list_inspections(
    property_id: uuid.UUID | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[InspectionInfo]:
    query = select(Inspection).where(Inspection.organization_id == membership.organization_id)
    if property_id is not None:
        query = query.where(Inspection.property_id == property_id)
    inspections = (
        (await session.execute(query.order_by(Inspection.scheduled_for.desc()))).scalars().all()
    )
    return [await _info(session, i) for i in inspections]


@router.patch("/inspections/{inspection_id}", response_model=InspectionInfo)
async def update_inspection(
    inspection_id: uuid.UUID,
    body: InspectionUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> InspectionInfo:
    inspection = await _owned(inspection_id, membership, session)
    data = body.model_dump(exclude_unset=True)
    for field in ("status", "note", "scheduled_for"):
        if field in data:
            setattr(inspection, field, data[field])
    if "items" in data:
        await _set_items(session, inspection.id, body.items or [])
    await session.commit()
    await session.refresh(inspection)
    return await _info(session, inspection)


@router.delete("/inspections/{inspection_id}", status_code=204)
async def delete_inspection(
    inspection_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    inspection = await _owned(inspection_id, membership, session)
    await session.delete(inspection)
    await session.commit()
    return Response(status_code=204)
```

Mount `inspections_router` in `main.py`.

- [ ] **Step 5: Run tests -> pass.**
- [ ] **Step 6: Full run, ruff, commit, push** (`Add inspection create, list, update and delete`). Report and wait.

---

### Task I-T3: Photo upload + tenant list

**Files:** Modify `backend/app/routers/inspections.py`; Test `backend/tests/test_inspections.py`.

**Interfaces:** Produces `POST /api/v1/inspections/{id}/images`; `GET /api/v1/me/leases/{lease_id}/inspections`.

- [ ] **Step 1: Failing tests** — image upload appends a URL (assert `image_urls` length 1, starts with `/uploads/`); tenant `/me` lists own lease's inspections (create an inspection with `lease_id`, onboard a tenant, assert they see it); a tenant of another lease gets 404. Use `onboard_tenant` from `tests.test_portal`; set `monkeypatch.setattr(settings, "upload_dir", str(tmp_path))` for the upload test and post `files={"file": ("x.jpg", b"...", "image/jpeg")}`.

- [ ] **Step 2: Run -> fail.**

- [ ] **Step 3: Implement** — add to `inspections.py`:

```python
from fastapi import File, UploadFile

from app.core.uploads import save_image
from app.models import User
from app.routers.documents import _tenant_lease_or_404
from app.core.deps import get_current_user


@router.post("/inspections/{inspection_id}/images", response_model=InspectionInfo)
async def add_image(
    inspection_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> InspectionInfo:
    inspection = await _owned(inspection_id, membership, session)
    url = await save_image(file)
    inspection.image_urls = [*inspection.image_urls, url]
    await session.commit()
    await session.refresh(inspection)
    return await _info(session, inspection)


@router.get("/me/leases/{lease_id}/inspections", response_model=list[InspectionInfo])
async def list_my_inspections(
    lease_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[InspectionInfo]:
    await _tenant_lease_or_404(lease_id, user, session)
    inspections = (
        (
            await session.execute(
                select(Inspection)
                .where(Inspection.lease_id == lease_id)
                .order_by(Inspection.scheduled_for.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _info(session, i) for i in inspections]
```

- [ ] **Step 4: Run tests -> pass.**
- [ ] **Step 5: Full run, ruff, commit, push** (`Add inspection photos and the tenant list endpoint`). Report and wait.

---

### Task I-T4: Frontend manager page

**Files:** Create `frontend/src/lib/inspections.ts`, `frontend/src/app/app/inspections/page.tsx`; Modify `frontend/src/components/app-shell.tsx`.

- [ ] **Step 1: Client** — `inspections.ts`: `InspectionType`/`InspectionStatus`/`InspectionCondition` unions, `InspectionItemIn`, `InspectionItemInfo`, `InspectionInfo`, `InspectionInput`; `listInspections()`, `createInspection(body)`, `updateInspection(id, body)`, `deleteInspection(id)`, `uploadInspectionImage(id, file)` (FormData + `getAccessToken`, like `uploadDocument`), and re-export `API_BASE_URL` use for images.

- [ ] **Step 2: Page** — `/app/inspections` (`AppShell` + `useShell`): a create `Card` with property `Select` (`listProperties`), optional lease `Select`, type `Select`, date `Input`, note `Input`, and a **dynamic item editor** (state `items: {area, condition, note}[]`; each row = area `Input` + condition `Select` (good/fair/poor) + note `Input` + a remove `Button`; an "Add item" `Button` appends a blank row). Submit calls `createInspection`. Below, a list of inspections; each row shows `type` · a status `Badge` (scheduled=brand, completed=success) · `scheduled_for` · property address · its items (area — condition badge — note), with: **Edit** (inline or dialog: status `Select`, note, date, item editor -> `updateInspection`), a hidden **file input** "Add photo" -> `uploadInspectionImage` rendering `<img src={API_BASE_URL + url}>` thumbnails, and **Delete** via `ConfirmDialog`.

- [ ] **Step 3: Nav** — add `{ href: "/app/inspections", label: "Inspections" }` to `MANAGE` (near Maintenance).

- [ ] **Step 4: Lint + build** -> clean; `/app/inspections` in the route list.
- [ ] **Step 5: Commit and push** (`Add the inspections page`). Report and wait.

---

### Task I-T5: Tenant portal card

**Files:** Modify `frontend/src/lib/inspections.ts` (add `listMyInspections(leaseId)`), `frontend/src/app/app/page.tsx`.

- [ ] **Step 1** — add `listMyInspections(leaseId)` to the client.
- [ ] **Step 2** — in the tenant branch of `page.tsx`, load inspections per lease (mirror the Documents card fetch) into `inspectionsByLease`, and render a read-only "Inspections" `Card` per lease block: for each inspection show type · date · status `Badge` · note · items (area — condition — note) · photo thumbnails (`<img src={API_BASE_URL + url}>`). Empty state "No inspections yet."
- [ ] **Step 3: Lint + build** -> clean.
- [ ] **Step 4: Commit and push** (`Show inspections in the tenant portal`). Report and wait.

---

### Task I-T6: End-to-end + CI

**Files:** Create `frontend/e2e/inspections.spec.ts`.

- [ ] **Step 1: Spec** — manager signs up, creates a property; opens `/app/inspections`; schedules an inspection (pick the property, type move_in, a date, add one checklist item area "Kitchen" condition good); asserts it lists with a "scheduled" badge and the item; edits it to `completed`; asserts the badge shows "completed". Finalise selectors against the built page when the test first runs (do not leave guessed).

- [ ] **Step 2: Run the new spec** — `cd frontend && npx playwright test inspections` -> 1 passed.
- [ ] **Step 3: Whole e2e suite** — `npx playwright test --workers=1` -> all pass.
- [ ] **Step 4: Full backend run + ruff** (from `backend/`).
- [ ] **Step 5: Commit and push** (`Add inspections e2e`).
- [ ] **Step 6: Confirm CI green** — `gh run list --limit 3`; read logs on failure. Report and wait.
