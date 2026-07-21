# Milestone 5: Maintenance Requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tenants report maintenance issues on their lease (title, description, priority, photos) and track status; landlords/PMs triage them through a status workflow.

**Architecture:** A `MaintenanceRequest` belongs to a lease (denormalizing property + org), created by the reporting tenant, with priority/status enums and a JSON image list. Tenant `/me` endpoints create/list/cancel/attach-images; manager endpoints list/view/update. The property-image save logic is extracted into a shared `save_image` helper.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js. No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run ...`, `uv add ...`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before EVERY push, from `backend/`, in order:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- **Ruff gotcha:** test files keep ALL imports at the top (E402). `ruff check --fix` auto-removes unused imports.
- Each task ends with: full test run -> ruff sequence -> commit -> `git push` (CI) -> report -> WAIT for approval.
- Migration adds two PG enums: after autogenerate, ADD both enum drops to `downgrade`
  (`sa.Enum(name="maintenancepriority").drop(op.get_bind())` and
  `sa.Enum(name="maintenancestatus").drop(op.get_bind())` after `drop_table`), and verify
  upgrade -> downgrade -> upgrade. Current head: `4f6bf92b0607`.
- Backend tests: `cd backend && uv run pytest -q`. Frontend: `npm run lint`, `npm run build`, e2e `npx playwright test` from `frontend/`.
- Restart the e2e backend after new endpoints: `lsof -ti tcp:8000 | xargs kill` then `uv run uvicorn app.main:app --port 8000`.

---

## Task Overview

1. `MaintenanceRequest` model + enums + migration
2. Schemas + tenant create/list endpoints (+ mount router)
3. Shared `save_image` + properties refactor + tenant image/cancel endpoints
4. Manager list/get/patch endpoints
5. Frontend lib + tenant portal Maintenance section
6. Frontend manager Maintenance page + nav link
7. e2e + CI green

---

### Task 1: `MaintenanceRequest` model + enums + migration

**Files:**
- Create: `backend/app/models/maintenance.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_maintenance_requests.py`
- Test: `backend/tests/test_maintenance_model.py`

**Interfaces:**
- Produces: `MaintenanceRequest(id, organization_id, property_id, lease_id, created_by, title, description, priority, status, image_urls, created_at, updated_at)`, `MaintenancePriority{low,medium,high,urgent}`, `MaintenanceStatus{open,in_progress,resolved,cancelled}` importable from `app.models`.

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/test_maintenance_model.py`:

```python
import uuid

from sqlalchemy import select

from app.models import (
    Lease,
    MaintenancePriority,
    MaintenanceRequest,
    MaintenanceStatus,
    User,
)
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease_and_user(client, db_session, email):
    headers = await landlord_headers(client, email)
    property_id = await make_property(client, headers)
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    return headers, lease, user


def _request(lease, user, **overrides):
    data = {
        "organization_id": lease.organization_id,
        "property_id": lease.property_id,
        "lease_id": lease.id,
        "created_by": user.id,
        "title": "Leaky tap",
        "description": "Kitchen tap drips",
    }
    data.update(overrides)
    return MaintenanceRequest(**data)


async def test_insert_and_read(client, db_session):
    _, lease, user = await _lease_and_user(client, db_session, "mmodel@example.com")
    db_session.add(_request(lease, user, priority=MaintenancePriority.high))
    await db_session.commit()

    rows = (
        (await db_session.execute(select(MaintenanceRequest).where(MaintenanceRequest.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].priority == MaintenancePriority.high
    assert rows[0].status == MaintenanceStatus.open
    assert rows[0].image_urls == []


async def test_delete_lease_cascades(client, db_session):
    headers, lease, user = await _lease_and_user(client, db_session, "mcascade@example.com")
    db_session.add(_request(lease, user))
    await db_session.commit()

    await client.delete(f"/api/v1/leases/{lease.id}", headers=headers)

    rows = (
        (await db_session.execute(select(MaintenanceRequest).where(MaintenanceRequest.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert rows == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_maintenance_model.py -q`
Expected: FAIL with `ImportError: cannot import name 'MaintenanceRequest' from 'app.models'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/maintenance.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MaintenancePriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class MaintenanceStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    cancelled = "cancelled"


class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    lease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[MaintenancePriority] = mapped_column(
        Enum(MaintenancePriority), default=MaintenancePriority.medium
    )
    status: Mapped[MaintenanceStatus] = mapped_column(
        Enum(MaintenanceStatus), default=MaintenanceStatus.open
    )
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Register the model**

Edit `backend/app/models/__init__.py`: add
`from app.models.maintenance import MaintenancePriority, MaintenanceRequest, MaintenanceStatus`
and add `"MaintenancePriority"`, `"MaintenanceRequest"`, `"MaintenanceStatus"` to `__all__`.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_maintenance_model.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Generate and fix the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add maintenance_requests"
```

Open the generated file. `upgrade()` creates `maintenance_requests` with the columns, the `priority`
and `status` `sa.Enum(...)` columns, FKs (`lease_id` `ondelete='CASCADE'`), and indexes. Confirm
`down_revision = "4f6bf92b0607"`. **Fix `downgrade()`** — after `op.drop_table('maintenance_requests')`,
drop both enum types:

```python
def downgrade() -> None:
    op.drop_index(op.f("ix_maintenance_requests_created_by"), table_name="maintenance_requests")
    op.drop_index(op.f("ix_maintenance_requests_lease_id"), table_name="maintenance_requests")
    op.drop_index(op.f("ix_maintenance_requests_property_id"), table_name="maintenance_requests")
    op.drop_index(op.f("ix_maintenance_requests_organization_id"), table_name="maintenance_requests")
    op.drop_table("maintenance_requests")
    sa.Enum(name="maintenancepriority").drop(op.get_bind())
    sa.Enum(name="maintenancestatus").drop(op.get_bind())
```

(Match the autogenerated index names exactly.) Verify the round-trip:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all three succeed. (A 2nd-upgrade "type already exists" error means an enum drop is missing.)

- [ ] **Step 7: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/models/maintenance.py backend/app/models/__init__.py \
        backend/alembic/versions backend/tests/test_maintenance_model.py
git commit -m "Add MaintenanceRequest model, enums, and migration"
git push
```
Then report and wait for approval.

---

### Task 2: Schemas + tenant create/list endpoints

**Files:**
- Create: `backend/app/schemas/maintenance.py`
- Create: `backend/app/routers/maintenance.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_maintenance_tenant.py`

**Interfaces:**
- Consumes: `MaintenanceRequest`, `MaintenancePriority`, `MaintenanceStatus` (Task 1); `get_current_user`; models `Lease`, `LeaseTenant`, `Property`, `User`.
- Produces: `MaintenanceCreate`, `MaintenanceUpdate`, `MaintenanceInfo` in `app.schemas.maintenance`; router with `POST/GET /api/v1/me/leases/{lease_id}/maintenance`; helpers `_to_info`, `_tenant_lease`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_maintenance_tenant.py`:

```python
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers

REQ = {"title": "Leaky tap", "description": "Kitchen tap drips", "priority": "high"}


async def test_tenant_creates_request(client, db_session):
    headers = await landlord_headers(client, "mtc@example.com")
    lease_id = await make_lease(client, headers, "Maint St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mtc-t@example.com")

    resp = await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "open"
    assert body["priority"] == "high"
    assert body["property_address"] == "Maint St"
    assert body["title"] == "Leaky tap"


async def test_create_requires_lease_tenant(client, db_session):
    headers = await landlord_headers(client, "mreq@example.com")
    lease_a = await make_lease(client, headers, "A Maint")
    lease_b = await make_lease(client, headers, "B Maint")
    ta = await onboard_tenant(client, db_session, headers, lease_a, "mreq-a@example.com", "TA")
    await onboard_tenant(client, db_session, headers, lease_b, "mreq-b@example.com", "TB")

    resp = await client.post(f"/api/v1/me/leases/{lease_b}/maintenance", json=REQ, headers=ta)
    assert resp.status_code == 404


async def test_manager_cannot_create(client, db_session):
    headers = await landlord_headers(client, "mmgr@example.com")
    lease_id = await make_lease(client, headers, "Mgr Maint")

    resp = await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=headers)
    assert resp.status_code == 404


async def test_tenant_lists_own_requests(client, db_session):
    headers = await landlord_headers(client, "mlist@example.com")
    lease_id = await make_lease(client, headers, "List Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mlist-t@example.com")
    await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)

    body = (await client.get(f"/api/v1/me/leases/{lease_id}/maintenance", headers=tenant)).json()
    assert len(body) == 1
    assert body[0]["title"] == "Leaky tap"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_maintenance_tenant.py -q`
Expected: FAIL — routes missing (create gets 404 not 201).

- [ ] **Step 3: Add the schemas**

Create `backend/app/schemas/maintenance.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import MaintenancePriority, MaintenanceStatus


class MaintenanceCreate(BaseModel):
    title: str
    description: str
    priority: MaintenancePriority = MaintenancePriority.medium


class MaintenanceUpdate(BaseModel):
    status: MaintenanceStatus | None = None
    priority: MaintenancePriority | None = None


class MaintenanceInfo(BaseModel):
    id: uuid.UUID
    property_address: str
    title: str
    description: str
    priority: MaintenancePriority
    status: MaintenanceStatus
    image_urls: list[str]
    reported_by: str
    created_at: datetime
```

- [ ] **Step 4: Create the router (tenant create/list)**

Create `backend/app/routers/maintenance.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models import Lease, LeaseTenant, MaintenanceRequest, Property, User
from app.schemas.maintenance import MaintenanceCreate, MaintenanceInfo

router = APIRouter(prefix="/api/v1", tags=["maintenance"])


async def _to_info(session: AsyncSession, request: MaintenanceRequest) -> MaintenanceInfo:
    address = (
        await session.execute(select(Property.address).where(Property.id == request.property_id))
    ).scalar_one()
    reporter = (
        await session.execute(select(User.name).where(User.id == request.created_by))
    ).scalar_one_or_none()
    return MaintenanceInfo(
        id=request.id,
        property_address=address,
        title=request.title,
        description=request.description,
        priority=request.priority,
        status=request.status,
        image_urls=request.image_urls,
        reported_by=reporter or "",
        created_at=request.created_at,
    )


async def _tenant_lease(lease_id: uuid.UUID, user: User, session: AsyncSession) -> Lease:
    owned = (
        await session.execute(
            select(LeaseTenant.id).where(
                LeaseTenant.lease_id == lease_id, LeaseTenant.user_id == user.id
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    return (await session.execute(select(Lease).where(Lease.id == lease_id))).scalar_one()


@router.post(
    "/me/leases/{lease_id}/maintenance", status_code=201, response_model=MaintenanceInfo
)
async def create_request(
    lease_id: uuid.UUID,
    body: MaintenanceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """A tenant of the lease reports a maintenance issue."""
    lease = await _tenant_lease(lease_id, user, session)
    request = MaintenanceRequest(
        organization_id=lease.organization_id,
        property_id=lease.property_id,
        lease_id=lease.id,
        created_by=user.id,
        title=body.title,
        description=body.description,
        priority=body.priority,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)


@router.get("/me/leases/{lease_id}/maintenance", response_model=list[MaintenanceInfo])
async def list_my_requests(
    lease_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MaintenanceInfo]:
    """List the caller's maintenance requests for a lease they are a tenant of."""
    await _tenant_lease(lease_id, user, session)
    result = await session.execute(
        select(MaintenanceRequest)
        .where(MaintenanceRequest.lease_id == lease_id)
        .order_by(MaintenanceRequest.created_at.desc())
    )
    return [await _to_info(session, r) for r in result.scalars().all()]
```

- [ ] **Step 5: Mount the router**

Edit `backend/app/main.py`: add `from app.routers.maintenance import router as maintenance_router`
with the other router imports, and `app.include_router(maintenance_router)` after them.

- [ ] **Step 6: Run tests + full suite + ruff**

```bash
cd backend && uv run pytest tests/test_maintenance_tenant.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/schemas/maintenance.py backend/app/routers/maintenance.py \
        backend/app/main.py backend/tests/test_maintenance_tenant.py
git commit -m "Add maintenance schemas and tenant create/list endpoints"
git push
```
Then report and wait for approval.

---

### Task 3: Shared `save_image` + properties refactor + tenant image/cancel

**Files:**
- Create: `backend/app/core/uploads.py`
- Modify: `backend/app/routers/properties.py`
- Modify: `backend/app/routers/maintenance.py`
- Test: `backend/tests/test_maintenance_tenant.py`

**Interfaces:**
- Consumes: `MaintenanceRequest`, `MaintenanceStatus` (Task 1); `_to_info`, `_tenant_lease` are already in the router.
- Produces: `async save_image(file: UploadFile) -> str` in `app.core.uploads`; `POST /api/v1/me/maintenance/{request_id}/images` and `/cancel`; helper `_tenant_request`.

- [ ] **Step 1: Write the failing tests**

Edit the top import block of `backend/tests/test_maintenance_tenant.py` to become:

```python
import uuid

from sqlalchemy import select

from app.models import MaintenanceRequest, MaintenanceStatus
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers
```

Then append:

```python
async def _make_request(client, tenant, lease_id):
    return (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]


async def test_tenant_uploads_image(client, db_session):
    headers = await landlord_headers(client, "mimg@example.com")
    lease_id = await make_lease(client, headers, "Img Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mimg-t@example.com")
    rid = await _make_request(client, tenant, lease_id)

    resp = await client.post(
        f"/api/v1/me/maintenance/{rid}/images",
        files={"file": ("p.png", b"imgbytes", "image/png")},
        headers=tenant,
    )
    assert resp.status_code == 200
    assert len(resp.json()["image_urls"]) == 1


async def test_image_rejects_bad_type(client, db_session):
    headers = await landlord_headers(client, "mbad@example.com")
    lease_id = await make_lease(client, headers, "Bad Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mbad-t@example.com")
    rid = await _make_request(client, tenant, lease_id)

    resp = await client.post(
        f"/api/v1/me/maintenance/{rid}/images",
        files={"file": ("p.txt", b"x", "text/plain")},
        headers=tenant,
    )
    assert resp.status_code == 400


async def test_image_non_owner_404(client, db_session):
    headers = await landlord_headers(client, "mown@example.com")
    lease_a = await make_lease(client, headers, "OwnA")
    lease_b = await make_lease(client, headers, "OwnB")
    ta = await onboard_tenant(client, db_session, headers, lease_a, "mown-a@example.com", "TA")
    tb = await onboard_tenant(client, db_session, headers, lease_b, "mown-b@example.com", "TB")
    rid = await _make_request(client, ta, lease_a)

    resp = await client.post(
        f"/api/v1/me/maintenance/{rid}/images",
        files={"file": ("p.png", b"x", "image/png")},
        headers=tb,
    )
    assert resp.status_code == 404


async def test_tenant_cancels(client, db_session):
    headers = await landlord_headers(client, "mcan@example.com")
    lease_id = await make_lease(client, headers, "Can Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mcan-t@example.com")
    rid = await _make_request(client, tenant, lease_id)

    resp = await client.post(f"/api/v1/me/maintenance/{rid}/cancel", headers=tenant)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_cancel_resolved_conflicts(client, db_session):
    headers = await landlord_headers(client, "mres@example.com")
    lease_id = await make_lease(client, headers, "Res Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mres-t@example.com")
    rid = await _make_request(client, tenant, lease_id)
    request = (
        await db_session.execute(
            select(MaintenanceRequest).where(MaintenanceRequest.id == uuid.UUID(rid))
        )
    ).scalar_one()
    request.status = MaintenanceStatus.resolved
    await db_session.commit()

    resp = await client.post(f"/api/v1/me/maintenance/{rid}/cancel", headers=tenant)
    assert resp.status_code == 409
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_maintenance_tenant.py -q`
Expected: FAIL — image/cancel routes missing (404s / assertion mismatches).

- [ ] **Step 3: Create the shared upload helper**

Create `backend/app/core/uploads.py`:

```python
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import settings

IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


async def save_image(file: UploadFile) -> str:
    """Validate and store an uploaded image; return its /uploads URL."""
    extension = IMAGE_EXTENSIONS.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=400, detail="Unsupported image type")
    name = f"{uuid.uuid4().hex}{extension}"
    directory = Path(settings.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(await file.read())
    return f"/uploads/{name}"
```

- [ ] **Step 4: Refactor the property upload to use it**

Edit `backend/app/routers/properties.py`:
- Add `from app.core.uploads import save_image` to the imports.
- Delete the module-level `IMAGE_EXTENSIONS = { ... }` block.
- Replace the body of `upload_image` between `prop = await get_owned_property(...)` and
  `await session.commit()` with:

```python
    url = await save_image(file)
    prop.image_urls = [*prop.image_urls, url]
```

(This removes the inline extension check + file write.) `ruff check --fix` will drop the now-unused
`Path` / `settings` / `HTTPException` imports if they are no longer used elsewhere in the file —
run it and let it clean up. If `ruff check` still flags an unused import it could not auto-remove,
remove it by hand.

- [ ] **Step 5: Add the image + cancel routes**

Edit `backend/app/routers/maintenance.py`:
- Change the fastapi import to `from fastapi import APIRouter, Depends, File, HTTPException, UploadFile`.
- Add `from app.core.uploads import save_image`.
- Add `MaintenanceStatus` to the models import:
  `from app.models import Lease, LeaseTenant, MaintenanceRequest, MaintenanceStatus, Property, User`.

Add the helper (after `_tenant_lease`):

```python
async def _tenant_request(
    request_id: uuid.UUID, user: User, session: AsyncSession
) -> MaintenanceRequest:
    request = (
        await session.execute(
            select(MaintenanceRequest).where(MaintenanceRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if request is None or request.created_by != user.id:
        raise HTTPException(status_code=404, detail="Request not found")
    return request
```

Append the routes:

```python
@router.post("/me/maintenance/{request_id}/images", response_model=MaintenanceInfo)
async def add_image(
    request_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """Attach an image to the caller's own maintenance request."""
    request = await _tenant_request(request_id, user, session)
    url = await save_image(file)
    request.image_urls = [*request.image_urls, url]
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)


@router.post("/me/maintenance/{request_id}/cancel", response_model=MaintenanceInfo)
async def cancel_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """Cancel the caller's own open/in-progress request."""
    request = await _tenant_request(request_id, user, session)
    if request.status not in (MaintenanceStatus.open, MaintenanceStatus.in_progress):
        raise HTTPException(status_code=409, detail="Request cannot be cancelled")
    request.status = MaintenanceStatus.cancelled
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)
```

- [ ] **Step 6: Run tests + full suite + ruff**

```bash
cd backend && uv run pytest tests/test_maintenance_tenant.py tests/test_properties_crud.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass (property tests still green after the refactor); ruff clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/core/uploads.py backend/app/routers/properties.py \
        backend/app/routers/maintenance.py backend/tests/test_maintenance_tenant.py
git commit -m "Add shared image upload helper and maintenance image/cancel endpoints"
git push
```
Then report and wait for approval.

---

### Task 4: Manager list/get/patch endpoints

**Files:**
- Modify: `backend/app/routers/maintenance.py`
- Test: `backend/tests/test_maintenance_manager.py`

**Interfaces:**
- Consumes: `MaintenanceRequest`, `MaintenanceStatus` (Task 1); `manager` from `app.routers.leases`; `_to_info`.
- Produces: `GET /api/v1/maintenance`, `GET /api/v1/maintenance/{id}`, `PATCH /api/v1/maintenance/{id}`; helper `get_owned_request`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_maintenance_manager.py`:

```python
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers

REQ = {"title": "Broken heater", "description": "No hot water", "priority": "urgent"}


async def _seed(client, db_session, prefix, address):
    headers = await landlord_headers(client, f"{prefix}@example.com")
    lease_id = await make_lease(client, headers, address)
    tenant = await onboard_tenant(client, db_session, headers, lease_id, f"{prefix}-t@example.com")
    rid = (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]
    return headers, tenant, rid


async def test_manager_lists(client, db_session):
    headers, _, _ = await _seed(client, db_session, "mgl", "Mgr List St")
    body = (await client.get("/api/v1/maintenance", headers=headers)).json()
    assert len(body) == 1
    assert body[0]["title"] == "Broken heater"
    assert body[0]["reported_by"]


async def test_manager_filters_by_status(client, db_session):
    headers, _, _ = await _seed(client, db_session, "mgf", "Mgr Filter St")
    assert len((await client.get("/api/v1/maintenance?status=open", headers=headers)).json()) == 1
    assert (await client.get("/api/v1/maintenance?status=resolved", headers=headers)).json() == []


async def test_manager_gets_and_patches(client, db_session):
    headers, _, rid = await _seed(client, db_session, "mgp", "Mgr Patch St")
    assert (await client.get(f"/api/v1/maintenance/{rid}", headers=headers)).status_code == 200
    patched = await client.patch(
        f"/api/v1/maintenance/{rid}",
        json={"status": "in_progress", "priority": "high"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "in_progress"
    assert patched.json()["priority"] == "high"


async def test_manager_cross_org_404(client, db_session):
    _, _, rid = await _seed(client, db_session, "mgx", "Mgr Cross St")
    other = await landlord_headers(client, "mgx-other@example.com")
    assert (await client.get(f"/api/v1/maintenance/{rid}", headers=other)).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/maintenance/{rid}", json={"status": "resolved"}, headers=other
        )
    ).status_code == 404


async def test_tenant_forbidden_on_manager_list(client, db_session):
    _, tenant, _ = await _seed(client, db_session, "mgt", "Mgr Tenant St")
    assert (await client.get("/api/v1/maintenance", headers=tenant)).status_code == 403
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_maintenance_manager.py -q`
Expected: FAIL — manager routes missing (list gets 404; etc.).

- [ ] **Step 3: Add the manager routes**

Edit `backend/app/routers/maintenance.py`:
- Add `Membership` to the models import and `MaintenanceUpdate` to the schemas import:
  `from app.models import Lease, LeaseTenant, MaintenanceRequest, MaintenanceStatus, Membership, Property, User`
  and `from app.schemas.maintenance import MaintenanceCreate, MaintenanceInfo, MaintenanceUpdate`.
- Add `from app.routers.leases import manager`.

Add the helper and routes:

```python
async def get_owned_request(
    request_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> MaintenanceRequest:
    request = (
        await session.execute(
            select(MaintenanceRequest).where(
                MaintenanceRequest.id == request_id,
                MaintenanceRequest.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return request


@router.get("/maintenance", response_model=list[MaintenanceInfo])
async def list_requests(
    status: MaintenanceStatus | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[MaintenanceInfo]:
    """List the organization's maintenance requests, optionally filtered by status."""
    query = select(MaintenanceRequest).where(
        MaintenanceRequest.organization_id == membership.organization_id
    )
    if status is not None:
        query = query.where(MaintenanceRequest.status == status)
    result = await session.execute(query.order_by(MaintenanceRequest.created_at.desc()))
    return [await _to_info(session, r) for r in result.scalars().all()]


@router.get("/maintenance/{request_id}", response_model=MaintenanceInfo)
async def get_request(
    request_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    return await _to_info(session, await get_owned_request(request_id, membership, session))


@router.patch("/maintenance/{request_id}", response_model=MaintenanceInfo)
async def update_request(
    request_id: uuid.UUID,
    body: MaintenanceUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """Update a request's status and/or priority (manager)."""
    request = await get_owned_request(request_id, membership, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(request, field, value)
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)
```

- [ ] **Step 4: Run tests + full suite + ruff**

```bash
cd backend && uv run pytest tests/test_maintenance_manager.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit and push**

```bash
git add backend/app/routers/maintenance.py backend/tests/test_maintenance_manager.py
git commit -m "Add manager maintenance list/get/patch endpoints"
git push
```
Then report and wait for approval.

---

### Task 5: Frontend lib + tenant portal Maintenance section

**Files:**
- Create: `frontend/src/lib/maintenance.ts`
- Modify: `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: tenant maintenance endpoints (Tasks 2-3).
- Produces: `@/lib/maintenance` client.

- [ ] **Step 1: Create the maintenance lib**

Create `frontend/src/lib/maintenance.ts`:

```typescript
import { apiFetch, API_BASE_URL, ApiError } from "@/lib/api";

export type MaintenancePriority = "low" | "medium" | "high" | "urgent";
export type MaintenanceStatus = "open" | "in_progress" | "resolved" | "cancelled";

export interface MaintenanceInfo {
  id: string;
  property_address: string;
  title: string;
  description: string;
  priority: MaintenancePriority;
  status: MaintenanceStatus;
  image_urls: string[];
  reported_by: string;
  created_at: string;
}

export interface MaintenanceCreateBody {
  title: string;
  description: string;
  priority: MaintenancePriority;
}

export function createMaintenance(leaseId: string, body: MaintenanceCreateBody) {
  return apiFetch<MaintenanceInfo>(`/api/v1/me/leases/${leaseId}/maintenance`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listLeaseMaintenance(leaseId: string) {
  return apiFetch<MaintenanceInfo[]>(`/api/v1/me/leases/${leaseId}/maintenance`);
}

export function cancelMaintenance(id: string) {
  return apiFetch<MaintenanceInfo>(`/api/v1/me/maintenance/${id}/cancel`, { method: "POST" });
}

export async function uploadMaintenanceImage(id: string, file: File): Promise<MaintenanceInfo> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/v1/me/maintenance/${id}/images`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? "Upload failed");
  }
  return response.json();
}

export function listMaintenance(status?: MaintenanceStatus) {
  const query = status ? `?status=${status}` : "";
  return apiFetch<MaintenanceInfo[]>(`/api/v1/maintenance${query}`);
}

export function getMaintenance(id: string) {
  return apiFetch<MaintenanceInfo>(`/api/v1/maintenance/${id}`);
}

export function updateMaintenance(
  id: string,
  body: { status?: MaintenanceStatus; priority?: MaintenancePriority },
) {
  return apiFetch<MaintenanceInfo>(`/api/v1/maintenance/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
```

- [ ] **Step 2: Wire the tenant Maintenance section into the dashboard**

Edit `frontend/src/app/app/page.tsx`. Add imports:

```tsx
import {
  createMaintenance,
  listLeaseMaintenance,
  cancelMaintenance,
  uploadMaintenanceImage,
  type MaintenanceInfo,
  type MaintenancePriority,
} from "@/lib/maintenance";
```

Add state (next to `chargesByLease`):

```tsx
  const [maintByLease, setMaintByLease] = useState<Record<string, MaintenanceInfo[]>>({});
  const [issueTitle, setIssueTitle] = useState("");
  const [issueDesc, setIssueDesc] = useState("");
  const [issuePriority, setIssuePriority] = useState<MaintenancePriority>("medium");
```

In the tenant branch of the effect, after building `chargesByLease`, also fetch maintenance:

```tsx
            const maint = await Promise.all(
              l.map((lease) =>
                listLeaseMaintenance(lease.id)
                  .then((m) => [lease.id, m] as const)
                  .catch(() => [lease.id, []] as const),
              ),
            );
            if (active) setMaintByLease(Object.fromEntries(maint));
```

Add handlers (inside `DashboardPage`, before the tenant `return`):

```tsx
  async function refreshMaint(leaseId: string) {
    const m = await listLeaseMaintenance(leaseId);
    setMaintByLease((prev) => ({ ...prev, [leaseId]: m }));
  }

  async function reportIssue(leaseId: string, e: React.FormEvent) {
    e.preventDefault();
    await createMaintenance(leaseId, {
      title: issueTitle,
      description: issueDesc,
      priority: issuePriority,
    });
    setIssueTitle("");
    setIssueDesc("");
    setIssuePriority("medium");
    await refreshMaint(leaseId);
  }
```

- [ ] **Step 3: Render the Maintenance section in each tenant lease card**

Inside the tenant lease `<li>` (after the charges list, before the `</li>`), add:

```tsx
              <div className="mt-3">
                <p className="font-medium text-gray-800">Maintenance</p>
                <form onSubmit={(e) => reportIssue(l.id, e)} className="mt-1 flex flex-wrap gap-2">
                  <input
                    required
                    placeholder="Issue title"
                    value={issueTitle}
                    onChange={(e) => setIssueTitle(e.target.value)}
                    className="w-40 rounded border px-2 py-1 text-sm"
                  />
                  <input
                    required
                    placeholder="Description"
                    value={issueDesc}
                    onChange={(e) => setIssueDesc(e.target.value)}
                    className="flex-1 rounded border px-2 py-1 text-sm"
                  />
                  <select
                    aria-label="Priority"
                    value={issuePriority}
                    onChange={(e) => setIssuePriority(e.target.value as MaintenancePriority)}
                    className="rounded border px-2 py-1 text-sm"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                  <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-sm text-white">
                    Report
                  </button>
                </form>
                <ul className="mt-2 space-y-1 text-sm text-gray-700">
                  {(maintByLease[l.id] ?? []).map((m) => (
                    <li key={m.id} className="rounded border p-2">
                      <span className="font-medium text-gray-800">{m.title}</span>{" "}
                      <span className="text-xs text-gray-500">
                        {m.priority} · {m.status}
                      </span>
                      <p className="text-gray-600">{m.description}</p>
                      {m.image_urls.length > 0 && (
                        <div className="mt-1 flex gap-1">
                          {m.image_urls.map((u) => (
                            <img
                              key={u}
                              src={`${API_BASE_URL}${u}`}
                              alt=""
                              className="h-12 w-12 rounded object-cover"
                            />
                          ))}
                        </div>
                      )}
                      <div className="mt-1 flex items-center gap-3">
                        <label className="cursor-pointer text-xs text-blue-600">
                          Add image
                          <input
                            type="file"
                            accept="image/*"
                            className="hidden"
                            aria-label="Add maintenance image"
                            onChange={async (e) => {
                              const file = e.target.files?.[0];
                              if (file) {
                                await uploadMaintenanceImage(m.id, file);
                                await refreshMaint(l.id);
                              }
                            }}
                          />
                        </label>
                        {(m.status === "open" || m.status === "in_progress") && (
                          <button
                            onClick={async () => {
                              await cancelMaintenance(m.id);
                              await refreshMaint(l.id);
                            }}
                            className="text-xs text-red-600"
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
```

Add `import { API_BASE_URL } from "@/lib/api";` if not already imported (used for image `src`).

- [ ] **Step 4: Lint + build**

Run from `frontend/`: `npm run lint` then `npm run build`. Expected: clean; build succeeds.
(Next's `<img>` may raise an eslint warning; if `npm run lint` errors on `@next/next/no-img-element`,
add `{/* eslint-disable-next-line @next/next/no-img-element */}` above the `<img>` — the property
detail page already uses plain `<img>` for uploaded images, so match that.)

- [ ] **Step 5: Ruff (backend) + commit**

```bash
cd backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add frontend/src/lib/maintenance.ts frontend/src/app/app/page.tsx
git commit -m "Add tenant maintenance reporting to the portal"
git push
```
Then report and wait for approval.

---

### Task 6: Frontend manager Maintenance page + nav link

**Files:**
- Create: `frontend/src/app/app/maintenance/page.tsx`
- Modify: `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: manager maintenance endpoints (Task 4); `@/lib/maintenance`.

- [ ] **Step 1: Create the manager Maintenance page**

Create `frontend/src/app/app/maintenance/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE_URL } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  listMaintenance,
  updateMaintenance,
  type MaintenanceInfo,
  type MaintenancePriority,
  type MaintenanceStatus,
} from "@/lib/maintenance";

const STATUSES: MaintenanceStatus[] = ["open", "in_progress", "resolved", "cancelled"];
const PRIORITIES: MaintenancePriority[] = ["low", "medium", "high", "urgent"];

export default function MaintenancePage() {
  const router = useRouter();
  const [requests, setRequests] = useState<MaintenanceInfo[]>([]);
  const [filter, setFilter] = useState<MaintenanceStatus | "">("");

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    listMaintenance(filter || undefined)
      .then((r) => {
        if (active) setRequests(r);
      })
      .catch(() => {
        if (active) setRequests([]);
      });
    return () => {
      active = false;
    };
  }, [router, filter]);

  async function onChange(
    id: string,
    body: { status?: MaintenanceStatus; priority?: MaintenancePriority },
  ) {
    await updateMaintenance(id, body);
    setRequests(await listMaintenance(filter || undefined));
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Maintenance</h1>
        <select
          aria-label="Filter status"
          value={filter}
          onChange={(e) => setFilter(e.target.value as MaintenanceStatus | "")}
          className="rounded border px-3 py-2"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <ul className="space-y-3">
        {requests.map((m) => (
          <li key={m.id} className="rounded border p-3 text-sm">
            <div className="flex justify-between">
              <span className="font-medium text-gray-800">
                {m.property_address} · {m.title}
              </span>
              <span className="text-xs text-gray-500">by {m.reported_by}</span>
            </div>
            <p className="text-gray-600">{m.description}</p>
            {m.image_urls.length > 0 && (
              <div className="mt-1 flex gap-1">
                {m.image_urls.map((u) => (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img key={u} src={`${API_BASE_URL}${u}`} alt="" className="h-14 w-14 rounded object-cover" />
                ))}
              </div>
            )}
            <div className="mt-2 flex gap-2">
              <select
                aria-label="Status"
                value={m.status}
                onChange={(e) => onChange(m.id, { status: e.target.value as MaintenanceStatus })}
                className="rounded border px-2 py-1"
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <select
                aria-label="Set priority"
                value={m.priority}
                onChange={(e) => onChange(m.id, { priority: e.target.value as MaintenancePriority })}
                className="rounded border px-2 py-1"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </li>
        ))}
        {requests.length === 0 && <li className="text-gray-500">No maintenance requests yet.</li>}
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

- [ ] **Step 2: Add the Maintenance nav link**

Edit `frontend/src/app/app/page.tsx`, in the manager (non-tenant) branch's nav-links `<div>`, add a
link after the "Leases" link:

```tsx
        <Link href="/app/maintenance" className="rounded border px-3 py-1 text-blue-600">
          Maintenance
        </Link>
```

- [ ] **Step 3: Lint + build**

Run from `frontend/`: `npm run lint` then `npm run build`. Expected: clean; build succeeds.

- [ ] **Step 4: Ruff (backend) + commit**

```bash
cd backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add "frontend/src/app/app/maintenance/page.tsx" frontend/src/app/app/page.tsx
git commit -m "Add manager maintenance page and dashboard link"
git push
```
Then report and wait for approval.

---

### Task 7: e2e — manager Maintenance page

**Files:**
- Create: `frontend/e2e/maintenance.spec.ts`

**Interfaces:**
- Consumes: the manager Maintenance page (Task 6); the maintenance endpoints (Tasks 2-4).

- [ ] **Step 1: Restart the local backend (new endpoints)**

```bash
lsof -ti tcp:8000 | xargs kill
cd backend && uv run uvicorn app.main:app --port 8000
```
(Leave running in a second shell for the e2e run.)

- [ ] **Step 2: Write the spec**

Create `frontend/e2e/maintenance.spec.ts`:

```typescript
import { expect, test } from "@playwright/test";

const landlord = `maint-${Date.now()}@example.com`;

test("landlord opens the maintenance page from the dashboard", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Maint Landlord");
  await page.getByPlaceholder("Organization name").fill("Maint Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Maintenance" }).click();
  await expect(page).toHaveURL(/\/app\/maintenance$/);
  await expect(page.getByRole("heading", { name: "Maintenance" })).toBeVisible();
  await expect(page.getByText("No maintenance requests yet.")).toBeVisible();
});
```

- [ ] **Step 3: Run the e2e suite (serial, CI-safe)**

Run from `frontend/`: `npx playwright test`
Expected: all specs pass, including `maintenance`.

- [ ] **Step 4: Lint + build + ruff**

```bash
cd frontend && npm run lint && npm run build
cd ../backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: clean.

- [ ] **Step 5: Commit, push, watch CI green**

```bash
git add "frontend/e2e/maintenance.spec.ts"
git commit -m "Add maintenance page e2e"
git push
gh run watch --exit-status
```
Expected: all three CI jobs (backend, frontend, e2e) green.

- [ ] **Step 6: Report — Milestone 5 complete**

Report: tenants can report maintenance issues (title/description/priority + photos) on their lease
and cancel them; landlords/PMs triage all org requests through open -> in_progress -> resolved with
priority updates. Wait for direction (Notifications milestone would add email on new request /
status change).

---

## Self-Review

**Spec coverage:**
- Model + enums + CASCADE + migration -> Task 1. ✓
- Shared `save_image` + property refactor -> Task 3. ✓
- Tenant create/list -> Task 2; image/cancel -> Task 3; manager list/get/patch -> Task 4. ✓
- Schemas (`MaintenanceCreate`/`MaintenanceUpdate`/`MaintenanceInfo`) -> Task 2. ✓
- Tenant portal reporting UI -> Task 5; manager page + nav -> Task 6. ✓
- e2e (manager page empty state) -> Task 7. ✓
- Product rules: tenant-only create (manager -> 404), priority/status enums, cancel only from
  open/in_progress (409 otherwise), org-scoping + tenant-403 -> covered by tests in Tasks 2-4. ✓
- Out of scope (notifications, AI, contractor, comments, manager upload) -> not planned. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the only `<rev>` is the
Alembic revision id. ✓

**Type consistency:** `MaintenanceInfo` fields (`id`, `property_address`, `title`, `description`,
`priority`, `status`, `image_urls`, `reported_by`, `created_at`) identical across schema, `_to_info`,
and the frontend `MaintenanceInfo`; enum string values (`low/medium/high/urgent`,
`open/in_progress/resolved/cancelled`) consistent across model, schema, and TS; `_to_info`,
`_tenant_lease`, `_tenant_request`, `get_owned_request` signatures used consistently; the frontend
`createMaintenance`/`listLeaseMaintenance`/`cancelMaintenance`/`uploadMaintenanceImage`/
`listMaintenance`/`getMaintenance`/`updateMaintenance` match the endpoint paths/methods. ✓
