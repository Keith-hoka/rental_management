# MVP Milestone 3.2: Lease Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a landlord or property_manager manage leases for a property, and derive each property's `vacant`/`occupied` status from whether an active lease covers today (showing the active lease on the property detail).

**Architecture:** A DB-backed `Lease` (org + property, tenant name/email, rent, dates). Landlord/property_manager CRUD endpoints, organization-scoped. The stored `Property.status` column is dropped; status is computed from an active lease (`start_date <= today <= end_date`) at read time, for both the detail (with an `active_lease` object) and the list (with a status filter). Overlapping leases on one property are rejected.

**Tech Stack:** Existing stack — FastAPI, async SQLAlchemy 2.0, Alembic, pytest + httpx, Next.js 16 (App Router, TypeScript, Tailwind), Postgres.

## Global Constraints

- Python package manager is `uv` only: `uv run`, `uv add` — never `python3` / `pip`.
- No emojis in code, logs, or commit messages.
- Short modules, clear names, docstrings over inline comments. No defensive programming beyond real failure points.
- TDD: every task writes the failing test first.
- **Before every push run the ruff sequence** (Python changes): `uv run ruff format .` → `uv run ruff check --fix .` → `uv run ruff check .` → `uv run ruff format --check .`
- **Per-task user gate:** every task ends with: run full test suite → ruff → commit → `git push` → report to the user (what was done, test results, CI status) → STOP and wait for approval before the next task.
- **Lease management is landlord + property_manager:** all lease endpoints use `require_roles(Role.landlord, Role.property_manager)`. Tenant viewing arrives in M3.3.
- **Organization scoping:** every lease query filters by the caller's `membership.organization_id`; a lease's `organization_id` comes from its property, never the client. Cross-org access returns 404.
- **Two migrations, on purpose:** the spec mentions "one migration"; this plan uses two (create `leases` in Task 1; drop `properties.status` in Task 5) so leases ship and are tested before the property cutover. Both are incremental and green on their own.
- Work on branch `main`. Repo: `https://github.com/Keith-hoka/rental_management`. Local Postgres host port 5433; CI Postgres 5432.

## Existing interfaces this milestone builds on

- `app/models/__init__.py`: re-exports all models (Alembic autogenerate reads it).
- `app/models/property.py`: `Property` (has `status: Mapped[PropertyStatus]` column — removed in Task 5), `PropertyType`, `PropertyStatus` (`vacant`/`occupied`).
- `app/core/db.py`: `Base`, `get_session`, `engine`.
- `app/core/deps.py`: `require_roles(*roles)` → returns the current `Membership`.
- `app/routers/properties.py`: `manager = require_roles(Role.landlord, Role.property_manager)`; `get_owned_property(property_id, membership, session) -> Property` (404 if not in org); endpoints return `PropertyResponse`.
- `app/schemas/property.py`: `PropertyCreate`, `PropertyUpdate`, `PropertyResponse` (all currently carry `status`).
- `app/main.py`: mounts `auth_router`, `properties_router`, `invitations_router`.
- `tests/conftest.py`: fixtures `engine`, `db_session`, `client`, and autouse `disable_real_email`.
- `tests/test_properties_crud.py`: `landlord_headers(client, email="owner@example.com") -> dict` and `NEW_PROPERTY` dict — reused by lease tests.
- Frontend: `frontend/src/lib/api.ts` (`apiFetch<T>`, `API_BASE_URL`, `ApiError`); `frontend/src/lib/properties.ts` (`Property`, `getProperty`, etc.); property detail `frontend/src/app/app/properties/[id]/page.tsx`.

## File Structure

- `backend/app/models/lease.py` — `LeaseFrequency` enum, `Lease` model.
- `backend/app/schemas/lease.py` — `LeaseCreate`, `LeaseUpdate`, `LeaseResponse`.
- `backend/app/routers/leases.py` — lease CRUD + `get_owned_lease`, `overlapping_lease_exists`.
- `backend/app/schemas/property.py` — add `ActiveLease`, add `active_lease` to `PropertyResponse`, drop `status` from create/update (Task 5).
- `backend/app/routers/properties.py` — add `active_leases_by_property`, `build_property_response`; compute status (Task 5).
- `backend/tests/test_lease_model.py`, `test_leases.py`, `test_lease_status.py`.
- `frontend/src/lib/leases.ts` — typed lease API calls + types.
- `frontend/src/app/app/properties/[id]/leases/page.tsx` — lease management page.
- `frontend/e2e/leases.spec.ts` — create-lease-makes-occupied end-to-end.

---

### Task 1: Lease model + LeaseFrequency enum + migration

**Files:**
- Create: `backend/app/models/lease.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_lease_model.py`

**Interfaces:**
- Produces: `Lease(id, organization_id, property_id, tenant_name, tenant_email, rent_amount, rent_frequency, bond_amount, notice_period_days, start_date, end_date, created_at)`; `LeaseFrequency` enum (`weekly`, `fortnightly`, `monthly`). `rent_amount`/`bond_amount` are `Numeric(10, 2)`; `start_date`/`end_date` are `Date`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_lease_model.py`

```python
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models import Lease, LeaseFrequency, Organization, Property, PropertyType


async def test_create_lease(db_session):
    org = Organization(name="Keith Properties", currency="USD")
    db_session.add(org)
    await db_session.flush()

    prop = Property(organization_id=org.id, address="1 Main St", type=PropertyType.house)
    db_session.add(prop)
    await db_session.flush()

    lease = Lease(
        organization_id=org.id,
        property_id=prop.id,
        tenant_name="Tina Tenant",
        tenant_email="tina@example.com",
        rent_amount=Decimal("1500.00"),
        rent_frequency=LeaseFrequency.monthly,
        bond_amount=Decimal("3000.00"),
        notice_period_days=21,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add(lease)
    await db_session.commit()

    found = (
        await db_session.execute(select(Lease).where(Lease.id == lease.id))
    ).scalar_one()
    assert found.property_id == prop.id
    assert found.rent_frequency == LeaseFrequency.monthly
    assert found.rent_amount == Decimal("1500.00")
    assert found.start_date == date(2026, 1, 1)
    assert isinstance(found.id, uuid.UUID)
```

Note: `Property(...)` here omits `status` because Task 5 removes that column; until Task 5 the column still exists but has a Python-side default (`vacant`), so omitting it is fine.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_lease_model.py -v`
Expected: FAIL with `ImportError` (`Lease` not defined).

- [ ] **Step 3: Implement the model** — `backend/app/models/lease.py`

```python
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LeaseFrequency(str, enum.Enum):
    weekly = "weekly"
    fortnightly = "fortnightly"
    monthly = "monthly"


class Lease(Base):
    __tablename__ = "leases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    tenant_name: Mapped[str] = mapped_column(String(255))
    tenant_email: Mapped[str] = mapped_column(String(255))
    rent_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    rent_frequency: Mapped[LeaseFrequency] = mapped_column(Enum(LeaseFrequency))
    bond_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    notice_period_days: Mapped[int | None] = mapped_column()
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Export the model** — `backend/app/models/__init__.py` (replace file)

```python
from app.models.invitation import Invitation, InvitationStatus
from app.models.lease import Lease, LeaseFrequency
from app.models.organization import Membership, Organization, Role
from app.models.property import Property, PropertyStatus, PropertyType
from app.models.user import User

__all__ = [
    "Invitation",
    "InvitationStatus",
    "Lease",
    "LeaseFrequency",
    "Membership",
    "Organization",
    "Property",
    "PropertyStatus",
    "PropertyType",
    "Role",
    "User",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_lease_model.py -v`
Expected: PASS.

- [ ] **Step 6: Generate the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add leases table"
```

Expected: a migration creating `leases` with a new `leasefrequency` enum, FKs to `organizations` and `properties`, and indexes on `organization_id`, `property_id`.

- [ ] **Step 7: Fix the downgrade to drop the new enum type**

`op.drop_table` does not drop the enum type it created (same gotcha as `invitationstatus`). In the generated migration's `downgrade()`, after `op.drop_table("leases")`, add:

```python
    sa.Enum(name="leasefrequency").drop(op.get_bind())
```

(`leasefrequency` is a brand-new type — the `upgrade` create is fine as autogenerated; only the `downgrade` needs this line so an upgrade→downgrade→upgrade cycle is clean.)

- [ ] **Step 8: Apply and round-trip the migration**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic current
```

Expected: upgrade applies; downgrade drops the table and type; re-upgrade succeeds; `current` shows the new head. If re-upgrade errors with `type "leasefrequency" already exists`, Step 7 was missed.

- [ ] **Step 9: Run full suite, ruff, commit, push, report, wait**

```bash
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
git add backend
git commit -m "Add Lease model, frequency enum, and migration"
git push
```
Commit message: `Add Lease model, frequency enum, and migration`

---

### Task 2: Create-lease endpoint (nested) + overlap/date validation

**Files:**
- Create: `backend/app/schemas/lease.py`, `backend/app/routers/leases.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_leases.py`

**Interfaces:**
- Consumes: `get_owned_property` (from `app.routers.properties`), `manager` role dep, `Lease`, `LeaseFrequency`.
- Produces: `POST /api/v1/properties/{property_id}/leases` → 201 `LeaseResponse`. `overlapping_lease_exists(session, property_id, start_date, end_date, exclude_id=None) -> bool`. Router object `router = APIRouter(prefix="/api/v1", tags=["leases"])`. `LeaseCreate` fields: `tenant_name, tenant_email, rent_amount, rent_frequency, bond_amount?, notice_period_days?, start_date, end_date`. `LeaseResponse` adds `id, property_id, created_at`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_leases.py`

```python
from tests.test_properties_crud import landlord_headers


async def make_property(client, headers, address="1 Lease St") -> str:
    """Create a property via the API and return its id."""
    response = await client.post(
        "/api/v1/properties",
        json={"address": address, "type": "house"},
        headers=headers,
    )
    return response.json()["id"]


def lease_body(**overrides) -> dict:
    body = {
        "tenant_name": "Tina Tenant",
        "tenant_email": "tina@example.com",
        "rent_amount": 1500,
        "rent_frequency": "monthly",
        "bond_amount": 3000,
        "notice_period_days": 21,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    }
    body.update(overrides)
    return body


async def test_create_lease_returns_201(client):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tenant_name"] == "Tina Tenant"
    assert body["property_id"] == property_id
    assert float(body["rent_amount"]) == 1500.0
    assert body["id"]


async def test_create_lease_requires_auth(client):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases", json=lease_body()
    )
    assert response.status_code == 401


async def test_create_lease_on_other_org_property_is_404(client):
    org_a = await landlord_headers(client, "a@example.com")
    org_b = await landlord_headers(client, "b@example.com")
    property_id = await make_property(client, org_a)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_b
    )
    assert response.status_code == 404


async def test_create_lease_rejects_start_after_end(client):
    headers = await landlord_headers(client, "order@example.com")
    property_id = await make_property(client, headers)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-12-31", end_date="2026-01-01"),
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_lease_rejects_overlap(client):
    headers = await landlord_headers(client, "overlap@example.com")
    property_id = await make_property(client, headers)
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-01-01", end_date="2026-06-30"),
        headers=headers,
    )
    overlapping = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-06-01", end_date="2026-12-31"),
        headers=headers,
    )
    assert overlapping.status_code == 409


async def test_create_lease_allows_adjacent_ranges(client):
    headers = await landlord_headers(client, "adjacent@example.com")
    property_id = await make_property(client, headers)
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-01-01", end_date="2026-06-30"),
        headers=headers,
    )
    adjacent = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-07-01", end_date="2026-12-31"),
        headers=headers,
    )
    assert adjacent.status_code == 201


# Silence unused-import warnings for helpers reused by later test files.
_ = (date, timedelta)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_leases.py -v`
Expected: FAIL with 404 (route not mounted).

- [ ] **Step 3: Implement schemas** — `backend/app/schemas/lease.py`

```python
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.lease import LeaseFrequency


class LeaseCreate(BaseModel):
    tenant_name: str
    tenant_email: EmailStr
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    bond_amount: Decimal | None = None
    notice_period_days: int | None = None
    start_date: date
    end_date: date


class LeaseUpdate(BaseModel):
    tenant_name: str | None = None
    tenant_email: EmailStr | None = None
    rent_amount: Decimal | None = None
    rent_frequency: LeaseFrequency | None = None
    bond_amount: Decimal | None = None
    notice_period_days: int | None = None
    start_date: date | None = None
    end_date: date | None = None


class LeaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    property_id: uuid.UUID
    tenant_name: str
    tenant_email: EmailStr
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    bond_amount: Decimal | None
    notice_period_days: int | None
    start_date: date
    end_date: date
    created_at: datetime
```

- [ ] **Step 4: Implement the router** — `backend/app/routers/leases.py`

```python
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Lease, Membership, Role
from app.routers.properties import get_owned_property
from app.schemas.lease import LeaseCreate, LeaseResponse

router = APIRouter(prefix="/api/v1", tags=["leases"])

manager = require_roles(Role.landlord, Role.property_manager)


async def overlapping_lease_exists(
    session: AsyncSession,
    property_id: uuid.UUID,
    start_date: date,
    end_date: date,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """True if another lease on the property overlaps the given date range (inclusive)."""
    query = select(Lease.id).where(
        Lease.property_id == property_id,
        Lease.start_date <= end_date,
        start_date <= Lease.end_date,
    )
    if exclude_id is not None:
        query = query.where(Lease.id != exclude_id)
    return (await session.execute(query)).first() is not None


@router.post(
    "/properties/{property_id}/leases", status_code=201, response_model=LeaseResponse
)
async def create_lease(
    property_id: uuid.UUID,
    body: LeaseCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Create a lease for a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    if body.start_date > body.end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if await overlapping_lease_exists(session, property_id, body.start_date, body.end_date):
        raise HTTPException(status_code=409, detail="Lease dates overlap an existing lease")

    lease = Lease(
        organization_id=prop.organization_id, property_id=property_id, **body.model_dump()
    )
    session.add(lease)
    await session.commit()
    await session.refresh(lease)
    return lease
```

- [ ] **Step 5: Mount the router** — `backend/app/main.py`

Add the import alongside the others:

```python
from app.routers.leases import router as leases_router
```

and after `app.include_router(invitations_router)`:

```python
app.include_router(leases_router)
```

- [ ] **Step 6: Run full suite** — `cd backend && uv run pytest -v` — all pass.

- [ ] **Step 7: Ruff, commit, push, report, wait** — commit message: `Add create-lease endpoint with overlap and date validation`

---

### Task 3: List and get one lease (org-scoped)

**Files:**
- Modify: `backend/app/routers/leases.py`
- Test: `backend/tests/test_leases.py` (append)

**Interfaces:**
- Produces: `GET /api/v1/properties/{property_id}/leases` → `list[LeaseResponse]` (that property's leases, newest first). `GET /api/v1/leases/{lease_id}` → `LeaseResponse` (404 cross-org). `get_owned_lease(lease_id, membership, session) -> Lease` helper.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_leases.py`

```python
async def test_list_leases_for_property(client):
    headers = await landlord_headers(client, "list@example.com")
    property_id = await make_property(client, headers)
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-01-01", end_date="2026-06-30"),
        headers=headers,
    )
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-07-01", end_date="2026-12-31"),
        headers=headers,
    )
    response = await client.get(f"/api/v1/properties/{property_id}/leases", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_leases_for_other_org_property_is_404(client):
    org_a = await landlord_headers(client, "la@example.com")
    org_b = await landlord_headers(client, "lb@example.com")
    property_id = await make_property(client, org_a)
    response = await client.get(f"/api/v1/properties/{property_id}/leases", headers=org_b)
    assert response.status_code == 404


async def test_get_lease_returns_it(client):
    headers = await landlord_headers(client, "getlease@example.com")
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    response = await client.get(f"/api/v1/leases/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_lease_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "ga@example.com")
    org_b = await landlord_headers(client, "gb@example.com")
    property_id = await make_property(client, org_a)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_a
        )
    ).json()
    response = await client.get(f"/api/v1/leases/{created['id']}", headers=org_b)
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_leases.py -v`
Expected: FAIL — `GET /leases/{id}` 404 (route not defined) and the list route 405/404.

- [ ] **Step 3: Implement list + get** — append to `backend/app/routers/leases.py`

```python
async def get_owned_lease(
    lease_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Lease:
    """Fetch a lease in the caller's org, or raise 404."""
    lease = (
        await session.execute(
            select(Lease).where(
                Lease.id == lease_id,
                Lease.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if lease is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    return lease


@router.get("/properties/{property_id}/leases", response_model=list[LeaseResponse])
async def list_leases(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Lease]:
    """List a property's leases (newest first). 404 if the property is not in the org."""
    await get_owned_property(property_id, membership, session)
    result = await session.execute(
        select(Lease)
        .where(Lease.property_id == property_id)
        .order_by(Lease.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/leases/{lease_id}", response_model=LeaseResponse)
async def get_lease(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Fetch a single lease in the caller's organization."""
    return await get_owned_lease(lease_id, membership, session)
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add list and get lease endpoints`

---

### Task 4: Update and delete lease

**Files:**
- Modify: `backend/app/routers/leases.py`
- Test: `backend/tests/test_leases.py` (append)

**Interfaces:**
- Consumes: `get_owned_lease`, `overlapping_lease_exists`, `LeaseUpdate`.
- Produces: `PATCH /api/v1/leases/{lease_id}` → `LeaseResponse` (re-validates date order and overlap, excluding itself). `DELETE /api/v1/leases/{lease_id}` → 204. Both 404 cross-org.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_leases.py`

```python
async def test_update_lease_changes_fields(client):
    headers = await landlord_headers(client, "upd@example.com")
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    response = await client.patch(
        f"/api/v1/leases/{created['id']}",
        json={"rent_amount": 1750, "tenant_name": "Ned New"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert float(body["rent_amount"]) == 1750.0
    assert body["tenant_name"] == "Ned New"


async def test_update_lease_rejects_overlap(client):
    headers = await landlord_headers(client, "updover@example.com")
    property_id = await make_property(client, headers)
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-01-01", end_date="2026-03-31"),
        headers=headers,
    )
    second = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(start_date="2026-07-01", end_date="2026-09-30"),
            headers=headers,
        )
    ).json()
    # Pull the second lease back over the first one.
    response = await client.patch(
        f"/api/v1/leases/{second['id']}",
        json={"start_date": "2026-02-01"},
        headers=headers,
    )
    assert response.status_code == 409


async def test_update_lease_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "ua@example.com")
    org_b = await landlord_headers(client, "ub@example.com")
    property_id = await make_property(client, org_a)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_a
        )
    ).json()
    response = await client.patch(
        f"/api/v1/leases/{created['id']}", json={"rent_amount": 1}, headers=org_b
    )
    assert response.status_code == 404


async def test_delete_lease_removes_it(client):
    headers = await landlord_headers(client, "del@example.com")
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    deleted = await client.delete(f"/api/v1/leases/{created['id']}", headers=headers)
    assert deleted.status_code == 204
    listed = await client.get(f"/api/v1/properties/{property_id}/leases", headers=headers)
    assert listed.json() == []


async def test_delete_lease_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "da@example.com")
    org_b = await landlord_headers(client, "db@example.com")
    property_id = await make_property(client, org_a)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_a
        )
    ).json()
    response = await client.delete(f"/api/v1/leases/{created['id']}", headers=org_b)
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_leases.py -v`
Expected: FAIL — `PATCH`/`DELETE /leases/{id}` return 405 (not defined).

- [ ] **Step 3: Implement update + delete** — append to `backend/app/routers/leases.py`

Add `Response` and `LeaseUpdate` to the existing imports:

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from app.schemas.lease import LeaseCreate, LeaseResponse, LeaseUpdate
```

Append the endpoints:

```python
@router.patch("/leases/{lease_id}", response_model=LeaseResponse)
async def update_lease(
    lease_id: uuid.UUID,
    body: LeaseUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Update a lease; re-validate date order and overlap (excluding itself)."""
    lease = await get_owned_lease(lease_id, membership, session)
    data = body.model_dump(exclude_unset=True)
    start = data.get("start_date", lease.start_date)
    end = data.get("end_date", lease.end_date)
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if await overlapping_lease_exists(session, lease.property_id, start, end, exclude_id=lease.id):
        raise HTTPException(status_code=409, detail="Lease dates overlap an existing lease")

    for field, value in data.items():
        setattr(lease, field, value)
    await session.commit()
    await session.refresh(lease)
    return lease


@router.delete("/leases/{lease_id}", status_code=204)
async def delete_lease(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a lease in the caller's organization."""
    lease = await get_owned_lease(lease_id, membership, session)
    await session.delete(lease)
    await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add update and delete lease endpoints`

---

### Task 5: Derive property status from leases (backend cutover)

**Files:**
- Modify: `backend/app/models/property.py`, `backend/app/schemas/property.py`, `backend/app/routers/properties.py`
- Create: `backend/tests/test_lease_status.py`, plus a migration
- Modify tests: `backend/tests/test_property_model.py`, `backend/tests/test_properties_crud.py`, `backend/tests/test_properties_search.py`

**Interfaces:**
- Consumes: `Lease` (Task 1), the lease create endpoint (Task 2).
- Produces: `PropertyResponse.active_lease: ActiveLease | None`; `status` becomes computed. `active_leases_by_property(session, organization_id, property_ids) -> dict[uuid.UUID, Lease]` and `build_property_response(prop, active_lease) -> PropertyResponse` in `app/routers/properties.py`. The stored `properties.status` column is dropped.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_lease_status.py`

```python
from datetime import date, timedelta

from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def add_lease(client, headers, property_id, start, end):
    return await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date=str(start), end_date=str(end)),
        headers=headers,
    )


async def test_property_is_occupied_with_active_lease(client):
    headers = await landlord_headers(client, "occ@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await add_lease(client, headers, property_id, today - timedelta(days=5), today + timedelta(days=30))

    detail = await client.get(f"/api/v1/properties/{property_id}", headers=headers)
    body = detail.json()
    assert body["status"] == "occupied"
    assert body["active_lease"]["tenant_name"] == "Tina Tenant"
    assert body["active_lease"]["start_date"]


async def test_property_is_vacant_without_lease(client):
    headers = await landlord_headers(client, "vac@example.com")
    property_id = await make_property(client, headers)
    detail = await client.get(f"/api/v1/properties/{property_id}", headers=headers)
    body = detail.json()
    assert body["status"] == "vacant"
    assert body["active_lease"] is None


async def test_property_with_future_lease_is_vacant(client):
    headers = await landlord_headers(client, "fut@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await add_lease(client, headers, property_id, today + timedelta(days=10), today + timedelta(days=40))
    detail = await client.get(f"/api/v1/properties/{property_id}", headers=headers)
    assert detail.json()["status"] == "vacant"


async def test_property_with_past_lease_is_vacant(client):
    headers = await landlord_headers(client, "past@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await add_lease(client, headers, property_id, today - timedelta(days=40), today - timedelta(days=10))
    detail = await client.get(f"/api/v1/properties/{property_id}", headers=headers)
    assert detail.json()["status"] == "vacant"


async def test_status_filter_uses_active_lease(client):
    headers = await landlord_headers(client, "sf@example.com")
    vacant_id = await make_property(client, headers, "Vacant Rd")
    occupied_id = await make_property(client, headers, "Occupied Rd")
    today = date.today()
    await add_lease(client, headers, occupied_id, today - timedelta(days=1), today + timedelta(days=10))

    occupied = await client.get("/api/v1/properties?status=occupied", headers=headers)
    assert [p["address"] for p in occupied.json()] == ["Occupied Rd"]
    vacant = await client.get("/api/v1/properties?status=vacant", headers=headers)
    assert [p["address"] for p in vacant.json()] == ["Vacant Rd"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_lease_status.py -v`
Expected: FAIL — `active_lease` is not a key in the property response (KeyError / None), and status is the stored value.

- [ ] **Step 3: Drop the stored status column** — `backend/app/models/property.py`

Remove the `status` column and the now-unused import. The file becomes:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PropertyType(str, enum.Enum):
    apartment = "apartment"
    house = "house"
    condo = "condo"
    townhouse = "townhouse"
    other = "other"


class PropertyStatus(str, enum.Enum):
    vacant = "vacant"
    occupied = "occupied"


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    address: Mapped[str] = mapped_column(String(500))
    type: Mapped[PropertyType] = mapped_column(Enum(PropertyType))
    bedrooms: Mapped[int] = mapped_column(default=0)
    bathrooms: Mapped[int] = mapped_column(default=0)
    parking: Mapped[int] = mapped_column(default=0)
    description: Mapped[str | None] = mapped_column(String(2000))
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

`PropertyStatus` stays — it now types the computed value.

- [ ] **Step 4: Update the schemas** — `backend/app/schemas/property.py` (replace file)

```python
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.lease import LeaseFrequency
from app.models.property import PropertyStatus, PropertyType


class PropertyCreate(BaseModel):
    address: str
    type: PropertyType
    bedrooms: int = 0
    bathrooms: int = 0
    parking: int = 0
    description: str | None = None
    image_urls: list[str] = []


class PropertyUpdate(BaseModel):
    address: str | None = None
    type: PropertyType | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    parking: int | None = None
    description: str | None = None
    image_urls: list[str] | None = None


class ActiveLease(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_name: str
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    start_date: date
    end_date: date


class PropertyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    address: str
    type: PropertyType
    bedrooms: int
    bathrooms: int
    parking: int
    description: str | None
    status: PropertyStatus
    image_urls: list[str]
    active_lease: ActiveLease | None = None
```

- [ ] **Step 5: Compute status in the properties router** — `backend/app/routers/properties.py`

Replace the imports and the create/list/get/patch/upload bodies to build responses with a computed status. New top of file (imports + helpers):

```python
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Lease, Membership, Property, PropertyStatus, PropertyType, Role
from app.schemas.property import ActiveLease, PropertyCreate, PropertyResponse, PropertyUpdate

IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

router = APIRouter(prefix="/api/v1/properties", tags=["properties"])

manager = require_roles(Role.landlord, Role.property_manager)


async def active_leases_by_property(
    session: AsyncSession,
    organization_id: uuid.UUID,
    property_ids: list[uuid.UUID],
) -> dict[uuid.UUID, Lease]:
    """Map each property id to its lease active today (start <= today <= end), if any."""
    if not property_ids:
        return {}
    today = datetime.now(UTC).date()
    result = await session.execute(
        select(Lease).where(
            Lease.organization_id == organization_id,
            Lease.property_id.in_(property_ids),
            Lease.start_date <= today,
            today <= Lease.end_date,
        )
    )
    return {lease.property_id: lease for lease in result.scalars().all()}


def build_property_response(prop: Property, active_lease: Lease | None) -> PropertyResponse:
    """Build a property response with status derived from its active lease."""
    return PropertyResponse(
        id=prop.id,
        organization_id=prop.organization_id,
        address=prop.address,
        type=prop.type,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        parking=prop.parking,
        description=prop.description,
        image_urls=prop.image_urls,
        status=PropertyStatus.occupied if active_lease else PropertyStatus.vacant,
        active_lease=ActiveLease.model_validate(active_lease) if active_lease else None,
    )
```

Now change each endpoint to return built responses. `create_property`:

```python
@router.post("", status_code=201, response_model=PropertyResponse)
async def create_property(
    body: PropertyCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PropertyResponse:
    """Create a property in the caller's organization (new properties are vacant)."""
    prop = Property(organization_id=membership.organization_id, **body.model_dump())
    session.add(prop)
    await session.commit()
    await session.refresh(prop)
    return build_property_response(prop, None)
```

`list_properties` (status filter now lease-based):

```python
@router.get("", response_model=list[PropertyResponse])
async def list_properties(
    search: str | None = None,
    status: PropertyStatus | None = None,
    type: PropertyType | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[PropertyResponse]:
    """List the caller org's properties, optionally searched and filtered."""
    query = select(Property).where(Property.organization_id == membership.organization_id)
    if search:
        query = query.where(Property.address.ilike(f"%{search}%"))
    if type:
        query = query.where(Property.type == type)
    result = await session.execute(query.order_by(Property.created_at.desc()))
    props = list(result.scalars().all())

    active = await active_leases_by_property(
        session, membership.organization_id, [p.id for p in props]
    )
    if status == PropertyStatus.occupied:
        props = [p for p in props if p.id in active]
    elif status == PropertyStatus.vacant:
        props = [p for p in props if p.id not in active]
    return [build_property_response(p, active.get(p.id)) for p in props]
```

`get_owned_property` stays unchanged. `get_property`, `update_property`, and `upload_image` each build a response from the property's active lease. Replace their bodies:

```python
@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PropertyResponse:
    """Fetch a single property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    active = await active_leases_by_property(session, membership.organization_id, [prop.id])
    return build_property_response(prop, active.get(prop.id))


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: uuid.UUID,
    body: PropertyUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PropertyResponse:
    """Update fields of a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    await session.commit()
    await session.refresh(prop)
    active = await active_leases_by_property(session, membership.organization_id, [prop.id])
    return build_property_response(prop, active.get(prop.id))


@router.post("/{property_id}/images", response_model=PropertyResponse)
async def upload_image(
    property_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PropertyResponse:
    """Upload an image for a property and append its URL to the property."""
    prop = await get_owned_property(property_id, membership, session)
    extension = IMAGE_EXTENSIONS.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    name = f"{uuid.uuid4().hex}{extension}"
    directory = Path(settings.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(await file.read())

    prop.image_urls = [*prop.image_urls, f"/uploads/{name}"]
    await session.commit()
    await session.refresh(prop)
    active = await active_leases_by_property(session, membership.organization_id, [prop.id])
    return build_property_response(prop, active.get(prop.id))
```

- [ ] **Step 6: Fix existing property tests that assumed a stored status**

`backend/tests/test_property_model.py` — remove the stored-status usage. Replace the import line and drop the two `status` lines:

```python
from app.models import Organization, Property, PropertyType
```
Delete `status=PropertyStatus.vacant,` from the `Property(...)` constructor and delete `assert found.status == PropertyStatus.vacant`.

`backend/tests/test_properties_crud.py` — `NEW_PROPERTY` no longer sends `status` (harmless but stale). Remove the `"status": "vacant",` line. In `test_update_property_changes_fields`, status can no longer be set via PATCH; change the request and assertions:

```python
async def test_update_property_changes_fields(client):
    headers = await landlord_headers(client)
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)).json()
    response = await client.patch(
        f"/api/v1/properties/{created['id']}",
        json={"bedrooms": 4},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bedrooms"] == 4
    assert body["status"] == "vacant"
    assert body["address"] == NEW_PROPERTY["address"]
```

In `test_update_property_in_other_org_is_404`, change the PATCH body away from `status`:

```python
    response = await client.patch(
        f"/api/v1/properties/{created['id']}", json={"bedrooms": 4}, headers=org_b
    )
```

`backend/tests/test_properties_search.py` — drop `status` from `make_property` and rewrite the status-filter test to use a lease. Replace the whole file:

```python
from datetime import date, timedelta

from tests.test_leases import lease_body
from tests.test_properties_crud import landlord_headers


async def make_property(client, headers, address, ptype="house"):
    return await client.post(
        "/api/v1/properties",
        json={
            "address": address,
            "type": ptype,
            "bedrooms": 2,
            "bathrooms": 1,
            "parking": 0,
            "image_urls": [],
        },
        headers=headers,
    )


async def test_search_by_address_substring(client):
    headers = await landlord_headers(client, "search@example.com")
    await make_property(client, headers, "12 Oak Avenue")
    await make_property(client, headers, "99 Pine Street")

    response = await client.get("/api/v1/properties?search=oak", headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["address"] == "12 Oak Avenue"


async def test_filter_by_status_and_type(client):
    headers = await landlord_headers(client, "filter@example.com")
    await make_property(client, headers, "A", ptype="house")
    occupied = (await make_property(client, headers, "B", ptype="condo")).json()
    today = date.today()
    await client.post(
        f"/api/v1/properties/{occupied['id']}/leases",
        json=lease_body(
            start_date=str(today - timedelta(days=1)),
            end_date=str(today + timedelta(days=10)),
        ),
        headers=headers,
    )

    vacant_list = await client.get("/api/v1/properties?status=vacant", headers=headers)
    assert [p["address"] for p in vacant_list.json()] == ["A"]

    occupied_list = await client.get("/api/v1/properties?status=occupied", headers=headers)
    assert [p["address"] for p in occupied_list.json()] == ["B"]

    condo = await client.get("/api/v1/properties?type=condo", headers=headers)
    assert [p["address"] for p in condo.json()] == ["B"]
```

- [ ] **Step 7: Generate the column-drop migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "drop properties.status"
uv run alembic upgrade head
```

Autogenerate produces `op.drop_column("properties", "status")` on upgrade and `op.add_column(...)` on downgrade.

- [ ] **Step 8: Fix the downgrade (NOT NULL backfill + existing enum type)**

The `properties.status` column is NOT NULL with only a Python-side default, and its `propertystatus` enum type still exists in the DB (we did not drop it). Edit the generated migration's `downgrade()` so re-adding the column backfills and does not recreate the type:

```python
def downgrade() -> None:
    op.add_column(
        "properties",
        sa.Column(
            "status",
            postgresql.ENUM("vacant", "occupied", name="propertystatus", create_type=False),
            nullable=False,
            server_default="vacant",
        ),
    )
    op.alter_column("properties", "status", server_default=None)
```

Add the import at the top of the migration:

```python
from sqlalchemy.dialects import postgresql
```

Leave the autogenerated `upgrade()` (`op.drop_column("properties", "status")`) as-is.

- [ ] **Step 9: Round-trip the migration**

```bash
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic current
```

Expected: downgrade re-adds `status` (backfilled `vacant`), upgrade drops it again, `current` at head. A `type "propertystatus" already exists` error means Step 8's `create_type=False` was missed.

- [ ] **Step 10: Run full suite** — `cd backend && uv run pytest -v` — all pass (lease-status tests now green; updated property tests green).

- [ ] **Step 11: Ruff, commit, push, report, wait** — commit message: `Derive property status from active leases; drop stored status column`

---

### Task 6: Frontend — lease API client + active-lease card on property detail

**Files:**
- Create: `frontend/src/lib/leases.ts`
- Modify: `frontend/src/lib/properties.ts`, `frontend/src/app/app/properties/[id]/page.tsx`, `frontend/src/app/app/properties/new/page.tsx`

**Interfaces:**
- Consumes: `apiFetch`, the property `active_lease` field.
- Produces: `Lease`, `LeaseInput`, `ActiveLease` TS types; `listLeases(propertyId)`, `createLease(propertyId, input)`, `getLease(id)`, `updateLease(id, input)`, `deleteLease(id)`. Property detail shows the active lease and links to lease management.

- [ ] **Step 1: Lease API module** — `frontend/src/lib/leases.ts`

```typescript
import { apiFetch } from "@/lib/api";

export type LeaseFrequency = "weekly" | "fortnightly" | "monthly";

export interface Lease {
  id: string;
  property_id: string;
  tenant_name: string;
  tenant_email: string;
  rent_amount: number;
  rent_frequency: LeaseFrequency;
  bond_amount: number | null;
  notice_period_days: number | null;
  start_date: string;
  end_date: string;
  created_at: string;
}

export interface LeaseInput {
  tenant_name: string;
  tenant_email: string;
  rent_amount: number;
  rent_frequency: LeaseFrequency;
  bond_amount: number | null;
  notice_period_days: number | null;
  start_date: string;
  end_date: string;
}

export function listLeases(propertyId: string) {
  return apiFetch<Lease[]>(`/api/v1/properties/${propertyId}/leases`);
}

export function createLease(propertyId: string, input: LeaseInput) {
  return apiFetch<Lease>(`/api/v1/properties/${propertyId}/leases`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getLease(id: string) {
  return apiFetch<Lease>(`/api/v1/leases/${id}`);
}

export function updateLease(id: string, input: Partial<LeaseInput>) {
  return apiFetch<Lease>(`/api/v1/leases/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteLease(id: string) {
  return apiFetch<void>(`/api/v1/leases/${id}`, { method: "DELETE" });
}
```

- [ ] **Step 2: Update the property types** — `frontend/src/lib/properties.ts`

Add an `ActiveLease` type, add `active_lease` to `Property`, and drop `status` from `PropertyInput` (create no longer sends it). Replace the type block (lines defining `Property` and `PropertyInput`):

```typescript
export type PropertyStatus = "vacant" | "occupied";
export type PropertyType = "apartment" | "house" | "condo" | "townhouse" | "other";

export interface ActiveLease {
  id: string;
  tenant_name: string;
  rent_amount: number;
  rent_frequency: "weekly" | "fortnightly" | "monthly";
  start_date: string;
  end_date: string;
}

export interface Property {
  id: string;
  organization_id: string;
  address: string;
  type: PropertyType;
  bedrooms: number;
  bathrooms: number;
  parking: number;
  description: string | null;
  status: PropertyStatus;
  image_urls: string[];
  active_lease: ActiveLease | null;
}

export interface PropertyInput {
  address: string;
  type: PropertyType;
  bedrooms: number;
  bathrooms: number;
  parking: number;
  description: string;
  image_urls: string[];
}
```

- [ ] **Step 3: Drop `status` from the create form** — `frontend/src/app/app/properties/new/page.tsx`

In the `EMPTY` constant remove the `status: "vacant",` line (the field no longer exists on `PropertyInput`).

- [ ] **Step 4: Show the active lease on the property detail** — `frontend/src/app/app/properties/[id]/page.tsx`

Render an active-lease card plus a "Manage leases" link. Insert this block immediately before the `<form onSubmit={onSave} className="space-y-3">` line (i.e. right after the closing `)}` of the `{error && (...)}` block):

```tsx
      {prop.active_lease ? (
        <div className="mb-4 rounded border border-green-500 bg-green-50 p-3 text-sm">
          <p className="font-semibold text-green-800">Occupied</p>
          <p className="text-gray-700">
            {prop.active_lease.tenant_name} · ${prop.active_lease.rent_amount}/
            {prop.active_lease.rent_frequency}
          </p>
          <p className="text-gray-600">
            {prop.active_lease.start_date} to {prop.active_lease.end_date}
          </p>
        </div>
      ) : (
        <p className="mb-4 text-sm text-gray-600">Vacant — no active lease.</p>
      )}
      <p className="mb-4">
        <Link href={`/app/properties/${id}/leases`} className="text-blue-600">
          Manage leases
        </Link>
      </p>
```

(`Link` and `id` are already in scope in this file.)

- [ ] **Step 5: Verify build** — `cd frontend && npm run lint && npm run build` — clean; `/app/properties/[id]` still builds.

- [ ] **Step 6: Commit, push, report, wait** — commit message: `Add lease API client and active-lease card on property detail`

---

### Task 7: Frontend — lease management page

**Files:**
- Create: `frontend/src/app/app/properties/[id]/leases/page.tsx`

**Interfaces:**
- Consumes: `listLeases`, `createLease`, `updateLease`, `deleteLease`, `LeaseInput`, `getAccessToken`, `ApiError`.
- Produces: a `/app/properties/{id}/leases` page listing leases with a create/edit form and delete, surfacing overlap (409) and date (422) errors.

- [ ] **Step 1: Lease management page** — `frontend/src/app/app/properties/[id]/leases/page.tsx`

```tsx
"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  createLease,
  deleteLease,
  listLeases,
  updateLease,
  type Lease,
  type LeaseInput,
} from "@/lib/leases";

const EMPTY: LeaseInput = {
  tenant_name: "",
  tenant_email: "",
  rent_amount: 0,
  rent_frequency: "monthly",
  bond_amount: null,
  notice_period_days: null,
  start_date: "",
  end_date: "",
};

export default function LeasesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [leases, setLeases] = useState<Lease[]>([]);
  const [form, setForm] = useState<LeaseInput>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    listLeases(id)
      .then(setLeases)
      .catch(() => setLeases([]));
  }, [id, router]);

  function set<K extends keyof LeaseInput>(key: K, value: LeaseInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function refresh() {
    setLeases(await listLeases(id));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (editingId) {
        await updateLease(editingId, form);
      } else {
        await createLease(id, form);
      }
      setForm(EMPTY);
      setEditingId(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  function startEdit(lease: Lease) {
    setEditingId(lease.id);
    setForm({
      tenant_name: lease.tenant_name,
      tenant_email: lease.tenant_email,
      rent_amount: lease.rent_amount,
      rent_frequency: lease.rent_frequency,
      bond_amount: lease.bond_amount,
      notice_period_days: lease.notice_period_days,
      start_date: lease.start_date,
      end_date: lease.end_date,
    });
  }

  async function onDelete(leaseId: string) {
    await deleteLease(leaseId);
    if (editingId === leaseId) {
      setEditingId(null);
      setForm(EMPTY);
    }
    await refresh();
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Leases</h1>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={onSubmit} className="mb-6 space-y-3">
        <input
          required
          placeholder="Tenant name"
          value={form.tenant_name}
          onChange={(e) => set("tenant_name", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <input
          type="email"
          required
          placeholder="Tenant email"
          value={form.tenant_email}
          onChange={(e) => set("tenant_email", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <div className="flex gap-2">
          <label className="flex-1 text-sm text-gray-600">
            Rent
            <input
              type="number"
              min={0}
              value={form.rent_amount}
              onChange={(e) => set("rent_amount", Number(e.target.value))}
              className="mt-1 w-full rounded border px-3 py-2"
            />
          </label>
          <label className="flex-1 text-sm text-gray-600">
            Frequency
            <select
              value={form.rent_frequency}
              onChange={(e) => set("rent_frequency", e.target.value as LeaseInput["rent_frequency"])}
              className="mt-1 w-full rounded border px-3 py-2"
            >
              <option value="weekly">Weekly</option>
              <option value="fortnightly">Fortnightly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
        </div>
        <div className="flex gap-2">
          <label className="flex-1 text-sm text-gray-600">
            Start
            <input
              type="date"
              required
              value={form.start_date}
              onChange={(e) => set("start_date", e.target.value)}
              className="mt-1 w-full rounded border px-3 py-2"
            />
          </label>
          <label className="flex-1 text-sm text-gray-600">
            End
            <input
              type="date"
              required
              value={form.end_date}
              onChange={(e) => set("end_date", e.target.value)}
              className="mt-1 w-full rounded border px-3 py-2"
            />
          </label>
        </div>
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          {editingId ? "Save lease" : "Add lease"}
        </button>
      </form>
      <ul className="space-y-2">
        {leases.map((lease) => (
          <li key={lease.id} className="flex items-center justify-between rounded border p-3">
            <span className="text-sm">
              {lease.tenant_name} · {lease.start_date} to {lease.end_date}
            </span>
            <span className="flex gap-2">
              <button
                onClick={() => startEdit(lease)}
                className="rounded border px-2 py-1 text-sm text-blue-600 transition hover:bg-blue-50"
              >
                Edit
              </button>
              <button
                onClick={() => onDelete(lease.id)}
                className="rounded border border-red-500 px-2 py-1 text-sm text-red-600 transition hover:bg-red-50"
              >
                Delete
              </button>
            </span>
          </li>
        ))}
        {leases.length === 0 && <li className="text-gray-500">No leases yet.</li>}
      </ul>
      <p className="mt-6">
        <Link href={`/app/properties/${id}`} className="text-blue-600">
          Back to property
        </Link>
      </p>
    </main>
  );
}
```

- [ ] **Step 2: Verify build** — `cd frontend && npm run lint && npm run build` — clean; `/app/properties/[id]/leases` appears in the route manifest.

- [ ] **Step 3: Commit, push, report, wait** — commit message: `Add lease management page`

---

### Task 8: Lease end-to-end

**Files:**
- Create: `frontend/e2e/leases.spec.ts`

**Interfaces:**
- Consumes: the full stack from Tasks 1-7, backend running on 8000 with both migrations applied.
- Produces: an e2e proving a lease makes a property occupied and removing it makes it vacant again.

- [ ] **Step 1: Write the e2e** — `frontend/e2e/leases.spec.ts`

```typescript
import { expect, test } from "@playwright/test";

const landlord = `lease-e2e-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("adding a lease makes a property occupied, deleting it makes it vacant", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Lease Landlord");
  await page.getByPlaceholder("Organization name").fill("Lease Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Create a property.
  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("7 Lease Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Open it — starts vacant — and go to lease management.
  await page.getByRole("link", { name: "7 Lease Way" }).click();
  await expect(page.getByText("Vacant — no active lease.")).toBeVisible();
  await page.getByRole("link", { name: "Manage leases" }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+\/leases$/);

  // Add a lease covering today.
  await page.getByPlaceholder("Tenant name").fill("Tina Tenant");
  await page.getByPlaceholder("Tenant email").fill("tina@example.com");
  await page.getByLabel("Rent").fill("1500");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(30));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page.getByText("Tina Tenant", { exact: false })).toBeVisible();

  // Property detail now shows occupied.
  await page.getByRole("link", { name: "Back to property" }).click();
  await expect(page.getByText("Occupied")).toBeVisible();
  await expect(page.getByText("Tina Tenant", { exact: false })).toBeVisible();

  // Delete the lease -> vacant again.
  await page.getByRole("link", { name: "Manage leases" }).click();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("No leases yet.")).toBeVisible();
  await page.getByRole("link", { name: "Back to property" }).click();
  await expect(page.getByText("Vacant — no active lease.")).toBeVisible();
});
```

- [ ] **Step 2: Run locally**

Prereq: Postgres up; backend on 8000 with `uv run alembic upgrade head` applied (both new migrations); frontend startable by Playwright.
Run: `cd frontend && npx playwright test`
Expected: all e2e pass (auth, forgot-password, change-password, properties, property-images, team-invitations, leases).

- [ ] **Step 3: Commit, push, watch all three CI jobs green**

```bash
git add frontend
git commit -m "Add lease end-to-end test"
git push
gh run watch --exit-status
```

- [ ] **Step 4: Report — Milestone 3.2 (lease management) complete; property status now derives from active leases. Wait for approval to plan Milestone 3.3 (tenant invitations + portal + expiry reminders).**

---

## Milestone Roadmap (next, after this plan ships)

- **Milestone 3.3:** Tenant invitations — reuse the `Invitation` mechanism, tied to a specific lease; add `tenant_user_id` to `Lease`; the tenant accepts and joins with role `tenant`, linked to their lease; tenant portal shows their own lease only. Lease-expiry reminders.
- **Milestone 4:** Rent charges (scheduled generation), payment recording, dashboard stats + charts.
