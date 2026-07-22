# Milestone 8.1: Contractor Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A manager keeps a directory of contractors, assigns one to a maintenance request, the contractor gets a work order by email, and the tenant sees who is coming and how to reach them.

**Architecture:** A new `contractors` table per organization, plus a nullable `MaintenanceRequest.contractor_id`. Assignment lives on its own `POST`/`DELETE .../assign` routes rather than the existing maintenance `PATCH`, because `MaintenanceUpdate` treats `None` as "not supplied" and so cannot express unassigning. The work order reuses `safe_send`, which logs and swallows failures so a mistyped address cannot fail the assignment.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js 16 App Router, Tailwind v4, Playwright. No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- This migration adds **no enum**: a new table plus one nullable FK column, both reversed in `downgrade`. Verify upgrade -> downgrade -> upgrade. Current head: `0e4536ea7e9a`.
- Accessible names introduced: `Contractors`, `Add contractor`, `Trade`, `Contractor`. The manager maintenance page already uses `aria-label="Status"`, `aria-label="Set priority"` and `aria-label="Filter status"`; `Contractor` does not collide with any of them. **The spec also reserved `Assign` and `Unassign`; this plan does not create them** — a single `Contractor` select does both jobs (pick a name to assign, pick "Unassigned" to clear), and adding two dead buttons purely to honour a name list would be worse than dropping the names.
- Backend commands run from `backend/`, frontend commands from `frontend/`. The shell keeps its working directory between commands — always `cd` explicitly.
- **Correction to the spec:** the spec places the tenant-visibility test in `tests/test_maintenance.py`. No such file exists. The maintenance tests are split into `test_maintenance_tenant.py`, `test_maintenance_manager.py`, `test_maintenance_model.py` and `test_maintenance_notify.py`; that test belongs in **`tests/test_maintenance_tenant.py`**.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/contractor.py` | the `Contractor` model |
| `backend/app/models/__init__.py` | register and export `Contractor` |
| `backend/app/models/maintenance.py` | add `contractor_id` |
| `backend/alembic/versions/<rev>_add_contractors.py` | table + column, reversible |
| `backend/app/schemas/contractor.py` | create/update/info + `AssignContractor` |
| `backend/app/schemas/maintenance.py` | three contractor fields on `MaintenanceInfo` |
| `backend/app/routers/contractors.py` | directory CRUD |
| `backend/app/routers/maintenance.py` | assign / unassign; `_to_info` resolves the contractor |
| `backend/app/services/maintenance_notify.py` | `notify_assigned` (work order + tenant notification) |
| `backend/tests/test_contractors.py` | directory CRUD and assignment |
| `backend/tests/test_maintenance_tenant.py` | tenant sees the contractor |
| `backend/tests/test_maintenance_notify.py` | work order and assignment notification |
| `frontend/src/lib/contractors.ts` | directory API client |
| `frontend/src/lib/maintenance.ts` | assign / unassign + the new fields |
| `frontend/src/app/app/contractors/page.tsx` | the directory page |
| `frontend/src/components/app-shell.tsx` | `Contractors` nav link |
| `frontend/src/app/app/maintenance/page.tsx` | picker, Assign, Unassign |
| `frontend/src/app/app/page.tsx` | tenant branch shows the assigned contractor |
| `frontend/e2e/contractor-assignment.spec.ts` | cross-role end-to-end |

---

### Task 1: Contractor model, `contractor_id` column, migration

**Files:**
- Create: `backend/app/models/contractor.py`
- Modify: `backend/app/models/__init__.py`, `backend/app/models/maintenance.py`
- Create: `backend/alembic/versions/<rev>_add_contractors.py`
- Test: `backend/tests/test_contractors.py`

**Interfaces:**
- Produces: `Contractor` with `id`, `organization_id`, `name`, `trade`, `phone`, `email`, `created_at`; `MaintenanceRequest.contractor_id: uuid.UUID | None`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_contractors.py`:

```python
import uuid

from sqlalchemy import select

from app.models import Contractor, MaintenanceRequest
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers

REQ = {"title": "Broken heater", "description": "No hot water", "priority": "urgent"}


async def test_contractor_row_round_trips(client, db_session):
    await landlord_headers(client, "cmodel@example.com")
    org_id = (await db_session.execute(select(Contractor.organization_id))).scalars().first()
    assert org_id is None, "no contractors exist yet"

    from app.models import Organization

    organization = (await db_session.execute(select(Organization))).scalars().first()
    contractor = Contractor(
        organization_id=organization.id,
        name="Bob's Plumbing",
        trade="Plumber",
        phone="0400 123 456",
        email="bob@example.com",
    )
    db_session.add(contractor)
    await db_session.commit()

    stored = (
        await db_session.execute(select(Contractor).where(Contractor.id == contractor.id))
    ).scalar_one()
    assert stored.name == "Bob's Plumbing"
    assert stored.trade == "Plumber"
    assert stored.created_at is not None


async def test_request_contractor_id_defaults_to_none(client, db_session):
    headers = await landlord_headers(client, "cnull@example.com")
    lease_id = await make_lease(client, headers, "Null Contractor St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "cnull-t@example.com")
    rid = (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]

    request = (
        await db_session.execute(
            select(MaintenanceRequest).where(MaintenanceRequest.id == uuid.UUID(rid))
        )
    ).scalar_one()
    assert request.contractor_id is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_contractors.py -v`
Expected: FAIL with `ImportError: cannot import name 'Contractor' from 'app.models'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/contractor.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Contractor(Base):
    """A trade the organization hires, reusable across maintenance requests."""

    __tablename__ = "contractors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    trade: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    # Optional: a phone-only contractor must still be recordable. With no email
    # on file, assignment sends no work order.
    email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Register it**

In `backend/app/models/__init__.py`, add the import after the `charge_reminder` line:

```python
from app.models.contractor import Contractor
```

and `"Contractor",` to `__all__`, keeping the list alphabetical (after `"ChargeReminder",`).

- [ ] **Step 5: Add the request column**

In `backend/app/models/maintenance.py`, after the `image_urls` line, add:

```python
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contractors.id"), index=True
    )
```

- [ ] **Step 6: Generate the migration**

Run: `cd backend && uv run alembic revision -m "add contractors"`

Replace the generated `upgrade`/`downgrade` with this, keeping the generated `revision` value (`down_revision` must be `0e4536ea7e9a`):

```python
def upgrade() -> None:
    op.create_table(
        "contractors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("trade", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contractors_organization_id", "contractors", ["organization_id"])
    op.add_column("maintenance_requests", sa.Column("contractor_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_maintenance_requests_contractor_id_contractors",
        "maintenance_requests",
        "contractors",
        ["contractor_id"],
        ["id"],
    )
    op.create_index(
        "ix_maintenance_requests_contractor_id", "maintenance_requests", ["contractor_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_maintenance_requests_contractor_id", table_name="maintenance_requests")
    op.drop_constraint(
        "fk_maintenance_requests_contractor_id_contractors",
        "maintenance_requests",
        type_="foreignkey",
    )
    op.drop_column("maintenance_requests", "contractor_id")
    op.drop_index("ix_contractors_organization_id", table_name="contractors")
    op.drop_table("contractors")
```

`downgrade` drops the column before the table: the FK points from `maintenance_requests` to `contractors`, so dropping the table first would fail.

Do not use `--autogenerate`. Hand-written migrations are the practice in this project.

- [ ] **Step 7: Verify the migration round-trips**

```bash
cd backend
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all three succeed. The middle step proves `downgrade` works rather than merely existing.

- [ ] **Step 8: Run the test**

Run: `cd backend && uv run pytest tests/test_contractors.py -v`
Expected: 2 passed.

- [ ] **Step 9: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 10: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 11: Commit and push**

```bash
git add backend/app/models backend/alembic/versions backend/tests/test_contractors.py
git commit -m "Add the Contractor model and maintenance contractor_id"
git push origin main
```

Then report and wait for approval.

---

### Task 2: Contractor schemas and directory CRUD

**Files:**
- Create: `backend/app/schemas/contractor.py`, `backend/app/routers/contractors.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_contractors.py`

**Interfaces:**
- Consumes: `Contractor` (Task 1).
- Produces: `ContractorCreate`, `ContractorUpdate`, `ContractorInfo`, `AssignContractor`; routes `POST /api/v1/contractors`, `GET /api/v1/contractors`, `PATCH /api/v1/contractors/{contractor_id}`, `DELETE /api/v1/contractors/{contractor_id}`; helper `get_owned_contractor(contractor_id, membership, session) -> Contractor`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_contractors.py`:

```python
CONTRACTOR = {
    "name": "Bob's Plumbing",
    "trade": "Plumber",
    "phone": "0400 123 456",
    "email": "bob@example.com",
}


async def test_create_and_list_contractors(client):
    headers = await landlord_headers(client, "ccrud@example.com")
    created = await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    assert created.status_code == 201
    assert created.json()["name"] == "Bob's Plumbing"

    listed = (await client.get("/api/v1/contractors", headers=headers)).json()
    assert [c["name"] for c in listed] == ["Bob's Plumbing"]


async def test_contractor_list_is_org_scoped(client):
    mine = await landlord_headers(client, "cmine@example.com")
    await client.post("/api/v1/contractors", json=CONTRACTOR, headers=mine)
    stranger = await landlord_headers(client, "cstranger@example.com")

    assert (await client.get("/api/v1/contractors", headers=stranger)).json() == []


async def test_update_contractor(client):
    headers = await landlord_headers(client, "cupd@example.com")
    cid = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    ).json()["id"]

    updated = await client.patch(
        f"/api/v1/contractors/{cid}", json={"phone": "0400 999 000"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "0400 999 000"
    assert updated.json()["name"] == "Bob's Plumbing"


async def test_delete_contractor(client):
    headers = await landlord_headers(client, "cdel@example.com")
    cid = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    ).json()["id"]

    assert (await client.delete(f"/api/v1/contractors/{cid}", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/contractors", headers=headers)).json() == []


async def test_other_orgs_contractor_is_404(client):
    owner = await landlord_headers(client, "cowner@example.com")
    cid = (await client.post("/api/v1/contractors", json=CONTRACTOR, headers=owner)).json()["id"]
    stranger = await landlord_headers(client, "cthief@example.com")

    patched = await client.patch(
        f"/api/v1/contractors/{cid}", json={"name": "Mine now"}, headers=stranger
    )
    assert patched.status_code == 404
    assert patched.json()["detail"] == "Contractor not found"
    assert (
        await client.delete(f"/api/v1/contractors/{cid}", headers=stranger)
    ).status_code == 404
```

The 404 test asserts the detail message as well as the status. A missing route also returns 404, so the status alone would pass against no isolation at all.

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_contractors.py -v`
Expected: the five new tests FAIL with 404 (no such route).

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/contractor.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class ContractorCreate(BaseModel):
    name: str
    trade: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class ContractorUpdate(BaseModel):
    name: str | None = None
    trade: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class ContractorInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    trade: str | None
    phone: str | None
    email: EmailStr | None
    created_at: datetime


class AssignContractor(BaseModel):
    contractor_id: uuid.UUID
```

- [ ] **Step 4: Write the router**

Create `backend/app/routers/contractors.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Contractor, MaintenanceRequest, Membership, Role
from app.schemas.contractor import ContractorCreate, ContractorInfo, ContractorUpdate

router = APIRouter(prefix="/api/v1/contractors", tags=["contractors"])

manager = require_roles(Role.landlord, Role.property_manager)


async def get_owned_contractor(
    contractor_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Contractor:
    """Fetch a contractor in the caller's organization, or raise 404."""
    contractor = (
        await session.execute(
            select(Contractor).where(
                Contractor.id == contractor_id,
                Contractor.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if contractor is None:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return contractor


@router.post("", status_code=201, response_model=ContractorInfo)
async def create_contractor(
    body: ContractorCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Contractor:
    """Add a contractor to the caller's organization directory."""
    contractor = Contractor(
        organization_id=membership.organization_id, **body.model_dump()
    )
    session.add(contractor)
    await session.commit()
    await session.refresh(contractor)
    return contractor


@router.get("", response_model=list[ContractorInfo])
async def list_contractors(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Contractor]:
    """The organization's contractors, by name."""
    result = await session.execute(
        select(Contractor)
        .where(Contractor.organization_id == membership.organization_id)
        .order_by(Contractor.name)
    )
    return list(result.scalars().all())


@router.patch("/{contractor_id}", response_model=ContractorInfo)
async def update_contractor(
    contractor_id: uuid.UUID,
    body: ContractorUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Contractor:
    """Update a contractor's details."""
    contractor = await get_owned_contractor(contractor_id, membership, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contractor, field, value)
    await session.commit()
    await session.refresh(contractor)
    return contractor


@router.delete("/{contractor_id}", status_code=204)
async def delete_contractor(
    contractor_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a contractor, unless requests still point at them."""
    contractor = await get_owned_contractor(contractor_id, membership, session)
    assigned = (
        await session.execute(
            select(func.count())
            .select_from(MaintenanceRequest)
            .where(MaintenanceRequest.contractor_id == contractor_id)
        )
    ).scalar_one()
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=f"Contractor is assigned to {assigned} maintenance requests",
        )
    await session.delete(contractor)
    await session.commit()
    return Response(status_code=204)
```

Refusing the delete beats silently unassigning the jobs, and beats surfacing a raw foreign-key error.

- [ ] **Step 5: Mount the router**

In `backend/app/main.py`, add the import next to the others (alphabetical, after `auth_router`):

```python
from app.routers.contractors import router as contractors_router
```

and the mount after `app.include_router(auth_router)`:

```python
app.include_router(contractors_router)
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && uv run pytest tests/test_contractors.py -v`
Expected: 7 passed.

- [ ] **Step 7: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 8: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 9: Commit and push**

```bash
git add backend/app/schemas/contractor.py backend/app/routers/contractors.py backend/app/main.py backend/tests/test_contractors.py
git commit -m "Add the contractor directory endpoints"
git push origin main
```

Then report and wait for approval.

---

### Task 3: Assign and unassign

**Files:**
- Modify: `backend/app/schemas/maintenance.py`, `backend/app/routers/maintenance.py`
- Test: `backend/tests/test_contractors.py`

**Interfaces:**
- Consumes: `AssignContractor`, `get_owned_contractor` (Task 2); `get_owned_request`, `_to_info` (existing in `app/routers/maintenance.py`).
- Produces: `POST /api/v1/maintenance/{request_id}/assign`, `DELETE /api/v1/maintenance/{request_id}/assign`; `MaintenanceInfo.contractor_id` / `.contractor_name` / `.contractor_phone`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_contractors.py`:

```python
async def _seed_request(client, db_session, prefix):
    """A landlord, an onboarded tenant, and one open request. Returns (headers, request id)."""
    headers = await landlord_headers(client, f"{prefix}@example.com")
    lease_id = await make_lease(client, headers, f"{prefix} Street")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, f"{prefix}-t@example.com")
    rid = (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]
    return headers, rid


async def test_assign_sets_the_contractor(client, db_session):
    headers, rid = await _seed_request(client, db_session, "asg")
    cid = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    ).json()["id"]

    response = await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["contractor_id"] == cid
    assert body["contractor_name"] == "Bob's Plumbing"
    assert body["contractor_phone"] == "0400 123 456"
    # Assignment records who does the work; it must not touch the status.
    assert body["status"] == "open"


async def test_unassign_clears_the_contractor(client, db_session):
    headers, rid = await _seed_request(client, db_session, "unasg")
    cid = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    ).json()["id"]
    await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )

    response = await client.delete(f"/api/v1/maintenance/{rid}/assign", headers=headers)
    assert response.status_code == 200
    assert response.json()["contractor_id"] is None
    assert response.json()["contractor_name"] is None


async def test_assigning_another_orgs_contractor_is_404(client, db_session):
    headers, rid = await _seed_request(client, db_session, "xorg")
    stranger = await landlord_headers(client, "xorg-other@example.com")
    foreign = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=stranger)
    ).json()["id"]

    response = await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": foreign}, headers=headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Contractor not found"


async def test_delete_assigned_contractor_is_refused(client, db_session):
    headers, rid = await _seed_request(client, db_session, "delasg")
    cid = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    ).json()["id"]
    await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )

    response = await client.delete(f"/api/v1/contractors/{cid}", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Contractor is assigned to 1 maintenance requests"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_contractors.py -k "assign or delete_assigned" -v`
Expected: FAIL — the assign route does not exist, so the first three 404, and the delete is not yet refused.

- [ ] **Step 3: Add the schema fields**

In `backend/app/schemas/maintenance.py`, add to `MaintenanceInfo` after `created_at`:

```python
    contractor_id: uuid.UUID | None = None
    contractor_name: str | None = None
    contractor_phone: str | None = None
```

One schema serves both roles: name and phone are exactly what a tenant may see.

- [ ] **Step 4: Resolve the contractor in `_to_info`**

In `backend/app/routers/maintenance.py`, add `Contractor` to the `app.models` import list, and replace `_to_info` with:

```python
async def _to_info(session: AsyncSession, request: MaintenanceRequest) -> MaintenanceInfo:
    """Build the response, resolving the property address, reporter and contractor."""
    address = (
        await session.execute(select(Property.address).where(Property.id == request.property_id))
    ).scalar_one()
    reporter = (
        await session.execute(select(User.name).where(User.id == request.created_by))
    ).scalar_one_or_none()
    contractor = (
        (
            await session.execute(
                select(Contractor).where(Contractor.id == request.contractor_id)
            )
        ).scalar_one_or_none()
        if request.contractor_id
        else None
    )
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
        contractor_id=request.contractor_id,
        contractor_name=contractor.name if contractor else None,
        contractor_phone=contractor.phone if contractor else None,
    )
```

- [ ] **Step 5: Add the two routes**

In `backend/app/routers/maintenance.py`, add these imports:

```python
from app.routers.contractors import get_owned_contractor
from app.schemas.contractor import AssignContractor
```

and append the routes at the end of the file:

```python
@router.post("/maintenance/{request_id}/assign", response_model=MaintenanceInfo)
async def assign_contractor(
    request_id: uuid.UUID,
    body: AssignContractor,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """Assign a contractor to a request. Does not change the request's status."""
    request = await get_owned_request(request_id, membership, session)
    contractor = await get_owned_contractor(body.contractor_id, membership, session)
    request.contractor_id = contractor.id
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)


@router.delete("/maintenance/{request_id}/assign", response_model=MaintenanceInfo)
async def unassign_contractor(
    request_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """Clear a request's contractor. Sends nothing."""
    request = await get_owned_request(request_id, membership, session)
    request.contractor_id = None
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)
```

`get_owned_contractor` is what makes cross-organization assignment a 404: it checks the contractor's `organization_id`, not merely that the id exists.

- [ ] **Step 6: Run the tests**

Run: `cd backend && uv run pytest tests/test_contractors.py -v`
Expected: 11 passed.

- [ ] **Step 7: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass. Watch `tests/test_maintenance_manager.py` and `tests/test_maintenance_tenant.py` in particular — `_to_info` changed and every maintenance response flows through it.

- [ ] **Step 8: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 9: Commit and push**

```bash
git add backend/app/schemas/maintenance.py backend/app/routers/maintenance.py backend/tests/test_contractors.py
git commit -m "Add contractor assign and unassign endpoints"
git push origin main
```

Then report and wait for approval.

---

### Task 4: Work order email and tenant notification

**Files:**
- Modify: `backend/app/services/maintenance_notify.py`, `backend/app/routers/maintenance.py`
- Test: `backend/tests/test_maintenance_notify.py`, `backend/tests/test_maintenance_tenant.py`

**Interfaces:**
- Consumes: `assign_contractor` (Task 3); `safe_send`, `notify_users`, `manager_emails` from `app/services/notify.py`; `lease_tenant_user_ids` from `app/services/notify.py`.
- Produces: `notify_assigned(session, request, contractor) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_maintenance_notify.py`. Its existing imports at the top already cover `select`, `Notification`, `User`, `make_lease`, `onboard_tenant`, `landlord_headers`; add `import pytest` there if it is not present.

```python
CONTRACTOR = {
    "name": "Bob's Plumbing",
    "trade": "Plumber",
    "phone": "0400 123 456",
    "email": "bob@example.com",
}
REQ_A = {"title": "Broken heater", "description": "No hot water", "priority": "urgent"}


@pytest.fixture
def sent(monkeypatch):
    """Collect (to, subject) for every email the service sends."""
    calls: list[tuple[str, str]] = []

    async def fake_send(to, subject, html):
        calls.append((to, subject))

    monkeypatch.setattr("app.services.notify.send_email", fake_send)
    return calls


async def _seed_for_assign(client, db_session, prefix):
    headers = await landlord_headers(client, f"{prefix}@example.com")
    lease_id = await make_lease(client, headers, f"{prefix} Street")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, f"{prefix}-t@example.com")
    rid = (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ_A, headers=tenant)
    ).json()["id"]
    return headers, tenant, rid


async def test_assign_emails_the_contractor(client, db_session, sent):
    headers, _, rid = await _seed_for_assign(client, db_session, "wo")
    cid = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    ).json()["id"]
    sent.clear()

    await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )

    assert ("bob@example.com", "Maintenance job - wo Street") in sent


async def test_contractor_without_email_gets_no_work_order(client, db_session, sent):
    headers, _, rid = await _seed_for_assign(client, db_session, "noem")
    cid = (
        await client.post(
            "/api/v1/contractors",
            json={"name": "Phone Only", "phone": "0400 000 000"},
            headers=headers,
        )
    ).json()["id"]
    sent.clear()

    response = await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )

    assert response.status_code == 200, "the assignment must succeed without an email address"
    assert sent == []


async def test_assign_notifies_the_tenant(client, db_session, sent):
    headers, _, rid = await _seed_for_assign(client, db_session, "asgn")
    cid = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    ).json()["id"]

    await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )

    tenant_id = await _user_id(db_session, "asgn-t@example.com")
    assert "maintenance_assigned" in await _categories(db_session, tenant_id)


async def test_unassign_sends_nothing(client, db_session, sent):
    headers, _, rid = await _seed_for_assign(client, db_session, "unas")
    cid = (
        await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    ).json()["id"]
    await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )
    sent.clear()

    await client.delete(f"/api/v1/maintenance/{rid}/assign", headers=headers)

    assert sent == []
```

`_user_id` and `_categories` already exist at the top of this file.

Append to `backend/tests/test_maintenance_tenant.py`:

```python
async def test_tenant_sees_the_assigned_contractor(client, db_session):
    headers = await landlord_headers(client, "tsee@example.com")
    lease_id = await make_lease(client, headers, "Tenant Sees St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "tsee-t@example.com")
    rid = (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]
    cid = (
        await client.post(
            "/api/v1/contractors",
            json={"name": "Bob's Plumbing", "phone": "0400 123 456"},
            headers=headers,
        )
    ).json()["id"]
    await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )

    mine = (
        await client.get(f"/api/v1/me/leases/{lease_id}/maintenance", headers=tenant)
    ).json()
    assert mine[0]["contractor_name"] == "Bob's Plumbing"
    assert mine[0]["contractor_phone"] == "0400 123 456"
```

Add `from tests.test_portal import make_lease, onboard_tenant` and
`from tests.test_properties_crud import landlord_headers` to the top of that file if they are not already there.

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_maintenance_notify.py tests/test_maintenance_tenant.py -v`
Expected: the four new notify tests fail (no email, no `maintenance_assigned` category). `test_tenant_sees_the_assigned_contractor` should already **pass** — Task 3 made `_to_info` resolve the contractor for every caller, tenants included. If it fails, stop: it means the tenant path does not share `_to_info` and the design's "one schema serves both roles" claim is wrong.

- [ ] **Step 3: Add the notifier**

In `backend/app/services/maintenance_notify.py`, add `Contractor` to the `app.models` import, and `lease_tenant_user_ids` to the `app.services.notify` import. Append:

```python
async def notify_assigned(
    session: AsyncSession, request: MaintenanceRequest, contractor: Contractor
) -> None:
    """Send the contractor their work order and tell the tenants who is coming.

    The work order deliberately omits the tenant's phone number: sharing a
    contractor's details with a tenant is the manager's own supplier to share,
    while the tenant never agreed to have their number sent to an outside party.
    """
    address = await _address(session, request)
    if contractor.email:
        managers = await manager_emails(session, request.organization_id)
        reply_to = managers[0] if managers else settings.email_from
        await safe_send(
            contractor.email,
            f"Maintenance job - {address}",
            f"<p>{request.title} at {address} ({request.priority.value} priority).</p>"
            f"<p>{request.description}</p>"
            f"<p>Reply to {reply_to}.</p>",
        )

    tenant_ids = await lease_tenant_user_ids(session, request.lease_id)
    await notify_users(
        session,
        tenant_ids,
        request.organization_id,
        "maintenance_assigned",
        "Contractor assigned",
        f"{contractor.name} has been assigned to {request.title} at {address}.",
        TENANT_LINK,
    )
    await session.commit()
```

- [ ] **Step 4: Call it from the assign route**

In `backend/app/routers/maintenance.py`, add `notify_assigned` to the `app.services.maintenance_notify` import, and add one line to `assign_contractor` before the return:

```python
    await session.refresh(request)
    await notify_assigned(session, request, contractor)
    return await _to_info(session, request)
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/test_maintenance_notify.py tests/test_maintenance_tenant.py -v`
Expected: all pass.

- [ ] **Step 6: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 7: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/services/maintenance_notify.py backend/app/routers/maintenance.py backend/tests/test_maintenance_notify.py backend/tests/test_maintenance_tenant.py
git commit -m "Send the contractor a work order and tell the tenant"
git push origin main
```

Then report and wait for approval.

---

### Task 5: Frontend directory, picker and tenant display

**Files:**
- Create: `frontend/src/lib/contractors.ts`, `frontend/src/app/app/contractors/page.tsx`
- Modify: `frontend/src/lib/maintenance.ts`, `frontend/src/components/app-shell.tsx`, `frontend/src/app/app/maintenance/page.tsx`, `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: the contractor and assignment endpoints (Tasks 2-4).
- Produces: `listContractors`, `createContractor`, `updateContractor`, `deleteContractor`, `assignContractor`, `unassignContractor`; the accessible names `Contractors`, `Add contractor`, `Assign`, `Unassign`, `Trade`, `Contractor`.

- [ ] **Step 1: Add the contractors API client**

Create `frontend/src/lib/contractors.ts`:

```ts
import { apiFetch } from "@/lib/api";

export interface ContractorInfo {
  id: string;
  name: string;
  trade: string | null;
  phone: string | null;
  email: string | null;
  created_at: string;
}

export interface ContractorInput {
  name: string;
  trade?: string | null;
  phone?: string | null;
  email?: string | null;
}

export function listContractors() {
  return apiFetch<ContractorInfo[]>("/api/v1/contractors");
}

export function createContractor(input: ContractorInput) {
  return apiFetch<ContractorInfo>("/api/v1/contractors", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateContractor(id: string, input: Partial<ContractorInput>) {
  return apiFetch<ContractorInfo>(`/api/v1/contractors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteContractor(id: string) {
  return apiFetch<void>(`/api/v1/contractors/${id}`, { method: "DELETE" });
}
```

- [ ] **Step 2: Extend the maintenance client**

In `frontend/src/lib/maintenance.ts`, add three fields to `MaintenanceInfo`:

```ts
  contractor_id: string | null;
  contractor_name: string | null;
  contractor_phone: string | null;
```

and append:

```ts
export function assignContractor(requestId: string, contractorId: string) {
  return apiFetch<MaintenanceInfo>(`/api/v1/maintenance/${requestId}/assign`, {
    method: "POST",
    body: JSON.stringify({ contractor_id: contractorId }),
  });
}

export function unassignContractor(requestId: string) {
  return apiFetch<MaintenanceInfo>(`/api/v1/maintenance/${requestId}/assign`, {
    method: "DELETE",
  });
}
```

- [ ] **Step 3: Create the directory page**

Create `frontend/src/app/app/contractors/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  createContractor,
  deleteContractor,
  listContractors,
  type ContractorInfo,
} from "@/lib/contractors";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import {
  Button,
  Card,
  DataList,
  DataRow,
  EmptyState,
  Field,
  Input,
  PageHeader,
} from "@/components/ui";

export default function ContractorsPage() {
  const { me, unread, logOut } = useShell();
  const [contractors, setContractors] = useState<ContractorInfo[]>([]);
  const [name, setName] = useState("");
  const [trade, setTrade] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listContractors()
      .then((c) => active && setContractors(c))
      .catch(() => active && setContractors([]));
    return () => {
      active = false;
    };
  }, [me]);

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createContractor({
        name,
        trade: trade || null,
        phone: phone || null,
        email: email || null,
      });
      setName("");
      setTrade("");
      setPhone("");
      setEmail("");
      setContractors(await listContractors());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the contractor");
    }
  }

  async function onDelete(id: string) {
    setError(null);
    try {
      await deleteContractor(id);
      setContractors(await listContractors());
    } catch (err) {
      // A contractor still assigned to requests comes back 409 with a count.
      setError(err instanceof ApiError ? err.message : "Could not delete the contractor");
    }
  }

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Contractors" />
      {error && (
        <p className="mb-3 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <Card className="mb-5">
        <form onSubmit={onAdd} className="flex flex-wrap items-end gap-2">
          <div className="min-w-40 flex-1">
            <Field label="Name">
              <Input required value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
          </div>
          <div className="min-w-32 flex-1">
            <Field label="Trade">
              <Input value={trade} onChange={(e) => setTrade(e.target.value)} />
            </Field>
          </div>
          <div className="min-w-32 flex-1">
            <Field label="Phone">
              <Input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </Field>
          </div>
          <div className="min-w-40 flex-1">
            <Field label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
          </div>
          <Button type="submit">Add contractor</Button>
        </form>
      </Card>
      <DataList>
        {contractors.map((c) => (
          <DataRow key={c.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                <span className="font-medium text-text">{c.name}</span>
                {c.trade && <span className="text-muted"> · {c.trade}</span>}
                <span className="block text-muted">
                  {c.phone ?? "no phone"} · {c.email ?? "no email - work orders cannot be sent"}
                </span>
              </span>
              <Button variant="danger" size="sm" onClick={() => onDelete(c.id)}>
                Delete
              </Button>
            </div>
          </DataRow>
        ))}
        {contractors.length === 0 && (
          <DataRow>
            <EmptyState>No contractors yet.</EmptyState>
          </DataRow>
        )}
      </DataList>
    </AppShell>
  );
}
```

- [ ] **Step 4: Add the nav link**

In `frontend/src/components/app-shell.tsx`, add to the `MANAGE` array after the Maintenance entry:

```tsx
  { href: "/app/contractors", label: "Contractors" },
```

- [ ] **Step 5: Add the picker to the maintenance page**

In `frontend/src/app/app/maintenance/page.tsx`, add the imports:

```tsx
import { assignContractor, unassignContractor } from "@/lib/maintenance";
import { listContractors, type ContractorInfo } from "@/lib/contractors";
import { Button } from "@/components/ui";
```

(`Button` joins the existing `@/components/ui` import rather than a second one.)

Add state and a loader alongside the existing ones:

```tsx
  const [contractors, setContractors] = useState<ContractorInfo[]>([]);

  useEffect(() => {
    if (!me) return;
    let active = true;
    listContractors()
      .then((c) => active && setContractors(c))
      .catch(() => active && setContractors([]));
    return () => {
      active = false;
    };
  }, [me]);
```

Add the handler next to `onChange`:

```tsx
  async function onAssign(id: string, contractorId: string) {
    if (contractorId) await assignContractor(id, contractorId);
    else await unassignContractor(id);
    setRequests(await listMaintenance(filter || undefined));
  }
```

Inside the `DataRow`, after the existing status/priority `Select` block, add:

```tsx
              <Select
                aria-label="Contractor"
                value={m.contractor_id ?? ""}
                onChange={(e) => onAssign(m.id, e.target.value)}
                className="w-48"
              >
                <option value="">Unassigned</option>
                {contractors.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
```

and immediately below the `<div className="mt-2 flex gap-2">` block, add the assigned line:

```tsx
            {m.contractor_name && (
              <p className="mt-2 text-xs text-muted">
                Assigned to {m.contractor_name}
                {m.contractor_phone ? ` (${m.contractor_phone})` : ""}
              </p>
            )}
```

A single `Select` handles both directions: choosing a contractor assigns, choosing "Unassigned" clears. That is why the plan adds no separate `Assign` / `Unassign` buttons — the two accessible names reserved for them are not needed, and adding dead controls to satisfy a name list would be worse than dropping the names.

- [ ] **Step 6: Show the contractor in the tenant portal**

In `frontend/src/app/app/page.tsx`, inside the tenant maintenance `DataRow`, after the `<p className="mt-1 text-muted">{m.description}</p>` line, add:

```tsx
                      {m.contractor_name && (
                        <p className="mt-1 text-sm text-text">
                          Contractor: {m.contractor_name}
                          {m.contractor_phone ? ` (${m.contractor_phone})` : ""}
                        </p>
                      )}
```

- [ ] **Step 7: Lint, typecheck and build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: both clean. `npm run build` runs the TypeScript check.

- [ ] **Step 8: Restart the backend with the email key emptied, then check by hand**

The development `.env` holds a working Resend key, and this is the first feature that sends mail from a request handler, so exercising the UI would send for real. Start the backend for verification with `RESEND_API_KEY` empty.

Then: add a contractor, confirm it appears; assign it to a request from `/app/maintenance` and confirm the "Assigned to" line; try deleting the assigned contractor and confirm the 409 message is shown rather than a silent failure.

- [ ] **Step 9: Commit and push**

```bash
git add frontend/src/lib/contractors.ts frontend/src/lib/maintenance.ts frontend/src/app/app/contractors/page.tsx frontend/src/components/app-shell.tsx frontend/src/app/app/maintenance/page.tsx frontend/src/app/app/page.tsx
git commit -m "Add the contractor directory page, picker and tenant display"
git push origin main
```

Then report and wait for approval.

---

### Task 6: End-to-end coverage

**Files:**
- Create: `frontend/e2e/contractor-assignment.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-5.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/contractor-assignment.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { invitationToken } from "./invitation-token";

const stamp = Date.now();
const landlord = `contractor-owner-${stamp}@example.com`;
const tenant = `contractor-tenant-${stamp}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("a landlord assigns a contractor and the tenant sees who is coming", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Contractor Owner");
  await page.getByPlaceholder("Organization name").fill("Contractor Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // A contractor in the directory.
  await page.getByRole("link", { name: "Contractors" }).click();
  await expect(page).toHaveURL(/\/app\/contractors$/);
  await page.getByLabel("Name").fill("Bob's Plumbing");
  await page.getByLabel("Trade").fill("Plumber");
  await page.getByLabel("Phone").fill("0400 123 456");
  await page.getByRole("button", { name: "Add contractor" }).click();
  await expect(page.getByText("Bob's Plumbing")).toBeVisible();

  // A property, a lease, and an onboarded tenant to report the issue.
  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("7 Contractor Close");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "7 Contractor Close (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Tess Tenant");
  await page.getByPlaceholder("Tenant email").fill(tenant);
  await page.getByLabel("Rent").fill("400");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(60));
  await page.getByRole("button", { name: "Add lease" }).click();

  await page.getByRole("link", { name: "7 Contractor Close" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByRole("button", { name: "Invite" }).first().click();
  await expect(page.getByText(`Invitation sent to ${tenant}`)).toBeVisible();

  const token = await invitationToken(tenant);
  await page.goto(`/accept-invite?token=${token}`);
  await page.getByPlaceholder("Your name").fill("Tess Tenant");
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(page).toHaveURL(/\/app$/);

  // The tenant reports an issue, then logs out.
  await page.getByPlaceholder("Issue title").fill("Burst pipe");
  await page.getByPlaceholder("Description").fill("Water under the sink");
  await page.getByRole("button", { name: "Report" }).click();
  await expect(page.getByText("Burst pipe")).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // The landlord assigns the contractor.
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password").fill("secret123");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();
  await page.getByRole("link", { name: "Maintenance" }).click();
  await expect(page.getByText("Burst pipe")).toBeVisible();
  await page.getByLabel("Contractor").selectOption({ label: "Bob's Plumbing" });
  await expect(page.getByText("Assigned to Bob's Plumbing (0400 123 456)")).toBeVisible();

  // The tenant sees who is coming. This is the cross-role rule the whole
  // feature turns on, and the part most likely to break silently.
  await page.getByRole("button", { name: "Log out" }).click();
  // The role radio is required here: the login form defaults to landlord, and
  // signing in with the wrong role is refused (see auth.spec.ts).
  await page.getByRole("radio", { name: "Tenant" }).click();
  await page.getByPlaceholder("Email").fill(tenant);
  await page.getByPlaceholder("Password").fill("secret123");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText("Contractor: Bob's Plumbing (0400 123 456)")).toBeVisible();
});
```

- [ ] **Step 2: Restart the backend with the email key emptied**

Assignment sends a work order. Start the backend used for e2e with `RESEND_API_KEY` empty so the run cannot send real mail. Restarting is also required for the new routes if the server predates Task 2.

- [ ] **Step 3: Run the new spec**

Run: `cd frontend && npx playwright test contractor-assignment`
Expected: 1 passed.

- [ ] **Step 4: Run the whole e2e suite**

Run: `cd frontend && npx playwright test --workers=1`
Expected: all pass (25 existing plus this one). Use `--workers=1` to match CI; the local default runs several workers and the signup bcrypt cost makes parallel runs slower and noisier.

- [ ] **Step 5: Full backend test run and ruff sequence**

```bash
cd backend
uv run pytest
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 6: Commit and push**

```bash
git add frontend/e2e/contractor-assignment.spec.ts
git commit -m "Add contractor assignment e2e"
git push origin main
```

- [ ] **Step 7: Confirm CI is green**

Run: `gh run list --limit 3`
Expected: the newest run for `main` succeeds. If it fails, read the log before changing anything — the failure is evidence, not noise.

Then report and wait for approval.
