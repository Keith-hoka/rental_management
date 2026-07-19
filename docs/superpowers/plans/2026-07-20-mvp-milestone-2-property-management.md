# MVP Milestone 2: Property Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full property CRUD with search/filter and image URLs, enforcing organization scoping and role-based access control on every endpoint — the first milestone where one organization's data is provably invisible to another.

**Architecture:** A `properties` router whose every route depends on `require_roles(Role.landlord, Role.property_manager)`; that dependency yields the caller's `Membership`, and its `organization_id` scopes every query. Cross-organization access returns 404 (never leak existence). Next.js pages under `/app/properties` call the API through the existing `apiFetch` client.

**Tech Stack:** Existing stack — FastAPI, async SQLAlchemy 2.0, Alembic, pytest + httpx, Next.js 16 (App Router, TypeScript, Tailwind), Postgres.

## Global Constraints

- Python package manager is `uv` only: `uv run`, `uv add` — never `python3` / `pip`.
- No emojis in code, logs, or commit messages.
- Short modules, clear names, docstrings over inline comments. No defensive programming beyond real failure points.
- TDD: every task writes the failing test first.
- **Before every push run the ruff sequence** (Python changes): `uv run ruff format .` → `uv run ruff check --fix .` → `uv run ruff check .` → `uv run ruff format --check .`
- **Per-task user gate:** every task ends with: run full test suite → ruff → commit → `git push` → report to the user (what was done, test results, CI status) → STOP and wait for approval before the next task.
- **Organization scoping (mandatory):** every property query filters by `membership.organization_id`. Create sets `organization_id` from the membership, never from the client.
- **RBAC (mandatory):** every property endpoint requires role `landlord` or `property_manager`. Tenants receive 403. Unauthenticated receive 401.
- **Cross-org access returns 404** (a property in another org is "not found"), not 403 — do not leak existence.
- Work on branch `main`. Repo: `https://github.com/Keith-hoka/rental_management`. Local Postgres on host port 5433; CI Postgres on 5432 (`DATABASE_URL` / `TEST_DATABASE_URL` env override).

## Existing interfaces this milestone builds on

- `app/core/deps.py`: `require_roles(*roles)` → dependency returning the current `Membership`; `get_current_membership`; `get_current_user`.
- `app/models/organization.py`: `Role` enum (`landlord`, `property_manager`, `tenant`), `Organization`, `Membership` (has `organization_id`, `role`).
- `app/models/__init__.py`: re-exports all models (Alembic autogenerate reads this).
- `app/core/db.py`: `Base`, `get_session`.
- `tests/conftest.py`: fixtures `engine`, `db_session`, `client` (the `client` overrides `get_session` against `rental_test`).
- Auth for tests: `POST /api/v1/auth/signup` returns `{access_token, refresh_token, token_type}`; send `Authorization: Bearer <access_token>`.
- Frontend: `frontend/src/lib/api.ts` exports `apiFetch<T>(path, options)` (adds the bearer token) and `ApiError`; `frontend/src/lib/auth.ts` exports `getAccessToken`; dashboard at `frontend/src/app/app/page.tsx`.

## File Structure

- `backend/app/models/property.py` — `PropertyType`, `PropertyStatus` enums, `Property` model.
- `backend/app/schemas/property.py` — `PropertyCreate`, `PropertyUpdate`, `PropertyResponse`.
- `backend/app/routers/properties.py` — the properties router (CRUD + search/filter + the org-scoped lookup helper).
- `backend/tests/test_property_model.py`, `test_properties_crud.py`, `test_properties_scoping.py`, `test_properties_search.py`.
- `frontend/src/lib/properties.ts` — typed property API calls + shared `Property` type.
- `frontend/src/app/app/properties/page.tsx` — list.
- `frontend/src/app/app/properties/new/page.tsx` — create.
- `frontend/src/app/app/properties/[id]/page.tsx` — detail + edit + delete.
- `frontend/e2e/properties.spec.ts` — CRUD e2e.

---

### Task 1: Property model + enums + migration

**Files:**
- Create: `backend/app/models/property.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_property_model.py`

**Interfaces:**
- Produces: `Property(id, organization_id, address, type, bedrooms, bathrooms, parking, description, status, image_urls, created_at)`; `PropertyType` enum (`apartment`, `house`, `condo`, `townhouse`, `other`); `PropertyStatus` enum (`vacant`, `occupied`). `image_urls` is a JSON list of strings defaulting to `[]`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_property_model.py`

```python
import uuid

from sqlalchemy import select

from app.models import Organization, Property, PropertyStatus, PropertyType


async def test_create_property(db_session):
    org = Organization(name="Keith Properties", currency="USD")
    db_session.add(org)
    await db_session.flush()

    prop = Property(
        organization_id=org.id,
        address="1 Main St",
        type=PropertyType.house,
        bedrooms=3,
        bathrooms=2,
        parking=1,
        description="Nice",
        status=PropertyStatus.vacant,
        image_urls=["http://img/1.jpg"],
    )
    db_session.add(prop)
    await db_session.commit()

    found = (
        await db_session.execute(select(Property).where(Property.id == prop.id))
    ).scalar_one()
    assert found.organization_id == org.id
    assert found.type == PropertyType.house
    assert found.status == PropertyStatus.vacant
    assert found.image_urls == ["http://img/1.jpg"]
    assert isinstance(found.id, uuid.UUID)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_property_model.py -v`
Expected: FAIL with `ImportError` (`Property` not defined).

- [ ] **Step 3: Implement the model** — `backend/app/models/property.py`

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
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    address: Mapped[str] = mapped_column(String(500))
    type: Mapped[PropertyType] = mapped_column(Enum(PropertyType))
    bedrooms: Mapped[int] = mapped_column(default=0)
    bathrooms: Mapped[int] = mapped_column(default=0)
    parking: Mapped[int] = mapped_column(default=0)
    description: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[PropertyStatus] = mapped_column(
        Enum(PropertyStatus), default=PropertyStatus.vacant
    )
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Export the model** — `backend/app/models/__init__.py` (replace file)

```python
from app.models.organization import Membership, Organization, Role
from app.models.property import Property, PropertyStatus, PropertyType
from app.models.user import User

__all__ = [
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

Run: `cd backend && uv run pytest -v`
Expected: all pass (existing 24 + this one).

- [ ] **Step 6: Generate and apply the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add properties table"
uv run alembic upgrade head
```

Expected: a migration under `backend/alembic/versions/` creating `properties` + the `ix_properties_organization_id` index; upgrade applies cleanly.

- [ ] **Step 7: Ruff, commit, push, report, wait**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
git add backend
git commit -m "Add Property model, enums, and migration"
git push
```

---

### Task 2: Create-property endpoint (schemas + router + mount)

**Files:**
- Create: `backend/app/schemas/property.py`, `backend/app/routers/properties.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_properties_crud.py`

**Interfaces:**
- Consumes: `require_roles(Role.landlord, Role.property_manager)`.
- Produces: `POST /api/v1/properties` → 201 `PropertyResponse`, `organization_id` taken from the membership. `PropertyCreate` (address, type, bedrooms, bathrooms, parking=0, description=None, status=vacant, image_urls=[]), `PropertyUpdate` (all optional), `PropertyResponse` (adds id, organization_id). Router object `router` and the shared dependency `manager = require_roles(Role.landlord, Role.property_manager)`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_properties_crud.py`

```python
NEW_PROPERTY = {
    "address": "1 Main St",
    "type": "house",
    "bedrooms": 3,
    "bathrooms": 2,
    "parking": 1,
    "description": "Nice house",
    "status": "vacant",
    "image_urls": ["http://img/1.jpg"],
}


async def landlord_headers(client, email: str = "owner@example.com") -> dict:
    tokens = (
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "secret123",
                "name": "Owner",
                "organization_name": "Owner Org",
            },
        )
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_create_property_returns_201(client):
    headers = await landlord_headers(client)
    response = await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["address"] == "1 Main St"
    assert body["type"] == "house"
    assert body["status"] == "vacant"
    assert body["organization_id"]
    assert body["id"]


async def test_create_property_requires_auth(client):
    response = await client.post("/api/v1/properties", json=NEW_PROPERTY)
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_properties_crud.py -v`
Expected: FAIL with 404 (route not mounted).

- [ ] **Step 3: Implement schemas** — `backend/app/schemas/property.py`

```python
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.property import PropertyStatus, PropertyType


class PropertyCreate(BaseModel):
    address: str
    type: PropertyType
    bedrooms: int = 0
    bathrooms: int = 0
    parking: int = 0
    description: str | None = None
    status: PropertyStatus = PropertyStatus.vacant
    image_urls: list[str] = []


class PropertyUpdate(BaseModel):
    address: str | None = None
    type: PropertyType | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    parking: int | None = None
    description: str | None = None
    status: PropertyStatus | None = None
    image_urls: list[str] | None = None


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
```

- [ ] **Step 4: Implement the router** — `backend/app/routers/properties.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Membership, Property, Role
from app.schemas.property import PropertyCreate, PropertyResponse

router = APIRouter(prefix="/api/v1/properties", tags=["properties"])

manager = require_roles(Role.landlord, Role.property_manager)


@router.post("", status_code=201, response_model=PropertyResponse)
async def create_property(
    body: PropertyCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Property:
    """Create a property in the caller's organization."""
    prop = Property(organization_id=membership.organization_id, **body.model_dump())
    session.add(prop)
    await session.commit()
    await session.refresh(prop)
    return prop
```

- [ ] **Step 5: Mount the router** — `backend/app/main.py` (add import + include)

```python
from app.routers.properties import router as properties_router
```

and after `app.include_router(auth_router)`:

```python
app.include_router(properties_router)
```

- [ ] **Step 6: Run full suite** — `cd backend && uv run pytest -v` — all pass.

- [ ] **Step 7: Ruff, commit, push, report, wait**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
git add backend
git commit -m "Add create-property endpoint with org scoping"
git push
```

---

### Task 3: List properties (org-scoped) + cross-org isolation

**Files:**
- Modify: `backend/app/routers/properties.py`
- Test: `backend/tests/test_properties_scoping.py`

**Interfaces:**
- Produces: `GET /api/v1/properties` → `list[PropertyResponse]`, containing only the caller's organization's properties, newest first.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_properties_scoping.py`

```python
from tests.test_properties_crud import NEW_PROPERTY, landlord_headers


async def test_list_only_returns_own_org(client):
    org_a = await landlord_headers(client, "a@example.com")
    org_b = await landlord_headers(client, "b@example.com")

    created = await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)
    assert created.status_code == 201

    b_list = await client.get("/api/v1/properties", headers=org_b)
    assert b_list.status_code == 200
    assert b_list.json() == []

    a_list = await client.get("/api/v1/properties", headers=org_a)
    assert a_list.status_code == 200
    assert len(a_list.json()) == 1


async def test_list_requires_auth(client):
    response = await client.get("/api/v1/properties")
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_properties_scoping.py -v`
Expected: FAIL with 404 (GET route not defined).

- [ ] **Step 3: Implement the list endpoint** — add to `backend/app/routers/properties.py`

Update imports at the top:

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Membership, Property, Role
from app.schemas.property import PropertyCreate, PropertyResponse
```

Add after `create_property`:

```python
@router.get("", response_model=list[PropertyResponse])
async def list_properties(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Property]:
    """List the caller organization's properties, newest first."""
    result = await session.execute(
        select(Property)
        .where(Property.organization_id == membership.organization_id)
        .order_by(Property.created_at.desc())
    )
    return list(result.scalars().all())
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add org-scoped property listing`

---

### Task 4: Get one property (org-scoped, 404 cross-org)

**Files:**
- Modify: `backend/app/routers/properties.py`
- Test: `backend/tests/test_properties_crud.py` (append)

**Interfaces:**
- Produces: `GET /api/v1/properties/{property_id}` → `PropertyResponse` when it belongs to the caller's org, else 404. Shared helper `get_owned_property(property_id, membership, session) -> Property` (raises 404) reused by update and delete.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_properties_crud.py`

```python
async def test_get_property_returns_it(client):
    headers = await landlord_headers(client)
    created = (
        await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)
    ).json()
    response = await client.get(f"/api/v1/properties/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_property_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "a2@example.com")
    org_b = await landlord_headers(client, "b2@example.com")
    created = (
        await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)
    ).json()
    response = await client.get(f"/api/v1/properties/{created['id']}", headers=org_b)
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_properties_crud.py -v`
Expected: FAIL with 404 on the first new test (route not defined) — note the second test would coincidentally pass, but the first proves the route is missing.

- [ ] **Step 3: Implement the helper + get endpoint** — add to `backend/app/routers/properties.py`

Add `uuid` and `HTTPException` imports:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
```

Add after `list_properties`:

```python
async def get_owned_property(
    property_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Property:
    """Fetch a property in the caller's org, or raise 404."""
    prop = (
        await session.execute(
            select(Property).where(
                Property.id == property_id,
                Property.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Property:
    """Fetch a single property in the caller's organization."""
    return await get_owned_property(property_id, membership, session)
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add org-scoped single-property fetch`

---

### Task 5: Update property (org-scoped)

**Files:**
- Modify: `backend/app/routers/properties.py`
- Test: `backend/tests/test_properties_crud.py` (append)

**Interfaces:**
- Consumes: `get_owned_property`, `PropertyUpdate`.
- Produces: `PATCH /api/v1/properties/{property_id}` → updated `PropertyResponse`; only provided fields change; cross-org is 404.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_properties_crud.py`

```python
async def test_update_property_changes_fields(client):
    headers = await landlord_headers(client)
    created = (
        await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)
    ).json()
    response = await client.patch(
        f"/api/v1/properties/{created['id']}",
        json={"status": "occupied", "bedrooms": 4},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "occupied"
    assert body["bedrooms"] == 4
    assert body["address"] == NEW_PROPERTY["address"]


async def test_update_property_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "a3@example.com")
    org_b = await landlord_headers(client, "b3@example.com")
    created = (
        await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)
    ).json()
    response = await client.patch(
        f"/api/v1/properties/{created['id']}", json={"status": "occupied"}, headers=org_b
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_properties_crud.py -v`
Expected: FAIL with 405 (Method Not Allowed) on PATCH.

- [ ] **Step 3: Implement update** — add `PropertyUpdate` to the schema import and append the endpoint

Change the schema import line to:

```python
from app.schemas.property import PropertyCreate, PropertyResponse, PropertyUpdate
```

Add after `get_property`:

```python
@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: uuid.UUID,
    body: PropertyUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Property:
    """Update fields of a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    await session.commit()
    await session.refresh(prop)
    return prop
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add org-scoped property update`

---

### Task 6: Delete property (org-scoped)

**Files:**
- Modify: `backend/app/routers/properties.py`
- Test: `backend/tests/test_properties_crud.py` (append)

**Interfaces:**
- Consumes: `get_owned_property`.
- Produces: `DELETE /api/v1/properties/{property_id}` → 204; cross-org is 404; deleted property no longer listed.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_properties_crud.py`

```python
async def test_delete_property_removes_it(client):
    headers = await landlord_headers(client)
    created = (
        await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)
    ).json()
    response = await client.delete(f"/api/v1/properties/{created['id']}", headers=headers)
    assert response.status_code == 204

    listed = await client.get("/api/v1/properties", headers=headers)
    assert listed.json() == []


async def test_delete_property_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "a4@example.com")
    org_b = await landlord_headers(client, "b4@example.com")
    created = (
        await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)
    ).json()
    response = await client.delete(f"/api/v1/properties/{created['id']}", headers=org_b)
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_properties_crud.py -v`
Expected: FAIL with 405 on DELETE.

- [ ] **Step 3: Implement delete** — add `Response` to the FastAPI import and append the endpoint

Change the FastAPI import line to:

```python
from fastapi import APIRouter, Depends, HTTPException, Response
```

Add after `update_property`:

```python
@router.delete("/{property_id}", status_code=204)
async def delete_property(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    await session.delete(prop)
    await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add org-scoped property deletion`

---

### Task 7: Search and filter

**Files:**
- Modify: `backend/app/routers/properties.py`
- Test: `backend/tests/test_properties_search.py`

**Interfaces:**
- Produces: `GET /api/v1/properties` accepts optional `search` (case-insensitive substring of address), `status` (`vacant`/`occupied`), `type` (PropertyType). Filters combine with AND, all still org-scoped.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_properties_search.py`

```python
from tests.test_properties_crud import landlord_headers


async def make_property(client, headers, address, status="vacant", ptype="house"):
    return await client.post(
        "/api/v1/properties",
        json={
            "address": address,
            "type": ptype,
            "bedrooms": 2,
            "bathrooms": 1,
            "parking": 0,
            "status": status,
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
    await make_property(client, headers, "A", status="vacant", ptype="house")
    await make_property(client, headers, "B", status="occupied", ptype="condo")

    vacant = await client.get("/api/v1/properties?status=vacant", headers=headers)
    assert [p["address"] for p in vacant.json()] == ["A"]

    condo = await client.get("/api/v1/properties?type=condo", headers=headers)
    assert [p["address"] for p in condo.json()] == ["B"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_properties_search.py -v`
Expected: FAIL — the search/filter params are ignored, so `search=oak` returns 2 rows.

- [ ] **Step 3: Implement search/filter** — replace `list_properties` in `backend/app/routers/properties.py`

Add `PropertyStatus`, `PropertyType` to the models import:

```python
from app.models import Membership, Property, PropertyStatus, PropertyType, Role
```

Replace the whole `list_properties` function with:

```python
@router.get("", response_model=list[PropertyResponse])
async def list_properties(
    search: str | None = None,
    status: PropertyStatus | None = None,
    type: PropertyType | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Property]:
    """List the caller org's properties, optionally searched and filtered."""
    query = select(Property).where(Property.organization_id == membership.organization_id)
    if search:
        query = query.where(Property.address.ilike(f"%{search}%"))
    if status:
        query = query.where(Property.status == status)
    if type:
        query = query.where(Property.type == type)
    result = await session.execute(query.order_by(Property.created_at.desc()))
    return list(result.scalars().all())
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add property search and filtering`

---

### Task 8: Frontend — property API client + list page

**Files:**
- Create: `frontend/src/lib/properties.ts`, `frontend/src/app/app/properties/page.tsx`
- Modify: `frontend/src/app/app/page.tsx` (add a link to `/app/properties`)

**Interfaces:**
- Consumes: `apiFetch`, `getAccessToken`, the properties API.
- Produces: `Property` TS type; `listProperties(params)`, `getProperty(id)`, `createProperty(body)`, `updateProperty(id, body)`, `deleteProperty(id)`; a `/app/properties` page listing properties with a search box, a status filter, and a "New property" link.

- [ ] **Step 1: Property API module** — `frontend/src/lib/properties.ts`

```typescript
import { apiFetch } from "@/lib/api";

export type PropertyStatus = "vacant" | "occupied";
export type PropertyType = "apartment" | "house" | "condo" | "townhouse" | "other";

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
}

export interface PropertyInput {
  address: string;
  type: PropertyType;
  bedrooms: number;
  bathrooms: number;
  parking: number;
  description: string;
  status: PropertyStatus;
  image_urls: string[];
}

export function listProperties(params: { search?: string; status?: string } = {}) {
  const q = new URLSearchParams();
  if (params.search) q.set("search", params.search);
  if (params.status) q.set("status", params.status);
  const suffix = q.toString() ? `?${q.toString()}` : "";
  return apiFetch<Property[]>(`/api/v1/properties${suffix}`);
}

export function getProperty(id: string) {
  return apiFetch<Property>(`/api/v1/properties/${id}`);
}

export function createProperty(body: PropertyInput) {
  return apiFetch<Property>("/api/v1/properties", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateProperty(id: string, body: Partial<PropertyInput>) {
  return apiFetch<Property>(`/api/v1/properties/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteProperty(id: string) {
  return apiFetch<void>(`/api/v1/properties/${id}`, { method: "DELETE" });
}
```

- [ ] **Step 2: List page** — `frontend/src/app/app/properties/page.tsx`

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getAccessToken } from "@/lib/auth";
import { listProperties, type Property } from "@/lib/properties";

export default function PropertiesPage() {
  const router = useRouter();
  const [properties, setProperties] = useState<Property[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    setProperties(await listProperties({ search, status }));
  }, [search, status]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    load();
  }, [router, load]);

  return (
    <main className="p-8">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Properties</h1>
        <Link href="/app/properties/new" className="rounded bg-blue-600 px-3 py-2 text-white">
          New property
        </Link>
      </div>
      <div className="mb-4 flex gap-2">
        <input
          placeholder="Search address"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded border px-3 py-2"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded border px-3 py-2"
        >
          <option value="">All statuses</option>
          <option value="vacant">Vacant</option>
          <option value="occupied">Occupied</option>
        </select>
      </div>
      <ul className="space-y-2">
        {properties.map((p) => (
          <li key={p.id} className="rounded border p-3">
            <Link href={`/app/properties/${p.id}`} className="text-blue-600">
              {p.address}
            </Link>
            <span data-testid="status" className="ml-2 text-sm text-gray-600">
              {p.type} - {p.status}
            </span>
          </li>
        ))}
        {properties.length === 0 && <li className="text-gray-500">No properties yet.</li>}
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

- [ ] **Step 3: Link from the dashboard** — in `frontend/src/app/app/page.tsx`, add a Properties link inside the button row (next to "Change password"):

```tsx
<Link href="/app/properties" className="rounded border px-3 py-1 text-blue-600">
  Properties
</Link>
```

- [ ] **Step 4: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 5: Commit, push, report, wait** — commit message: `Add property list page and API client`

---

### Task 9: Frontend — create property form

**Files:**
- Create: `frontend/src/app/app/properties/new/page.tsx`

**Interfaces:**
- Consumes: `createProperty`, `getAccessToken`.
- Produces: `/app/properties/new` form; on submit creates the property and navigates to its detail page.

- [ ] **Step 1: Create form** — `frontend/src/app/app/properties/new/page.tsx`

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { createProperty, type PropertyInput } from "@/lib/properties";

const EMPTY: PropertyInput = {
  address: "",
  type: "house",
  bedrooms: 1,
  bathrooms: 1,
  parking: 0,
  description: "",
  status: "vacant",
  image_urls: [],
};

export default function NewPropertyPage() {
  const router = useRouter();
  const [form, setForm] = useState<PropertyInput>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof PropertyInput>(key: K, value: PropertyInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await createProperty(form);
      router.push(`/app/properties/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create failed");
    }
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">New property</h1>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={onSubmit} className="space-y-3">
        <input
          required
          placeholder="Address"
          value={form.address}
          onChange={(e) => set("address", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <select
          value={form.type}
          onChange={(e) => set("type", e.target.value as PropertyInput["type"])}
          className="w-full rounded border px-3 py-2"
        >
          <option value="house">House</option>
          <option value="apartment">Apartment</option>
          <option value="condo">Condo</option>
          <option value="townhouse">Townhouse</option>
          <option value="other">Other</option>
        </select>
        <div className="flex gap-2">
          <input
            type="number"
            min={0}
            placeholder="Bedrooms"
            value={form.bedrooms}
            onChange={(e) => set("bedrooms", Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            placeholder="Bathrooms"
            value={form.bathrooms}
            onChange={(e) => set("bathrooms", Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            placeholder="Parking"
            value={form.parking}
            onChange={(e) => set("parking", Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
          />
        </div>
        <textarea
          placeholder="Description"
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          Create property
        </button>
      </form>
      <p className="mt-4">
        <Link href="/app/properties" className="text-blue-600">
          Back to properties
        </Link>
      </p>
    </main>
  );
}
```

- [ ] **Step 2: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 3: Commit, push, report, wait** — commit message: `Add create-property form`

---

### Task 10: Frontend — property detail, edit, delete

**Files:**
- Create: `frontend/src/app/app/properties/[id]/page.tsx`

**Interfaces:**
- Consumes: `getProperty`, `updateProperty`, `deleteProperty`, `getAccessToken`.
- Produces: `/app/properties/[id]` showing the property in an editable form; Save persists changes; Delete removes it and returns to the list.

- [ ] **Step 1: Detail/edit/delete page** — `frontend/src/app/app/properties/[id]/page.tsx`

```tsx
"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { deleteProperty, getProperty, updateProperty, type Property } from "@/lib/properties";

export default function PropertyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [prop, setProp] = useState<Property | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    getProperty(id)
      .then(setProp)
      .catch(() => setError("Property not found"));
  }, [id, router]);

  if (error) return <main className="p-8 text-red-600">{error}</main>;
  if (!prop) return null;

  function set<K extends keyof Property>(key: K, value: Property[K]) {
    setProp((p) => (p ? { ...p, [key]: value } : p));
    setSaved(false);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!prop) return;
    setError(null);
    try {
      const updated = await updateProperty(id, {
        address: prop.address,
        type: prop.type,
        bedrooms: prop.bedrooms,
        bathrooms: prop.bathrooms,
        parking: prop.parking,
        description: prop.description ?? "",
        status: prop.status,
      });
      setProp(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  async function onDelete() {
    await deleteProperty(id);
    router.push("/app/properties");
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Edit property</h1>
      {saved && (
        <p data-testid="saved" className="mb-2 text-sm text-green-700">
          Saved.
        </p>
      )}
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={onSave} className="space-y-3">
        <input
          required
          value={prop.address}
          onChange={(e) => set("address", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <select
          value={prop.status}
          onChange={(e) => set("status", e.target.value as Property["status"])}
          className="w-full rounded border px-3 py-2"
        >
          <option value="vacant">Vacant</option>
          <option value="occupied">Occupied</option>
        </select>
        <div className="flex gap-2">
          <input
            type="number"
            min={0}
            value={prop.bedrooms}
            onChange={(e) => set("bedrooms", Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            value={prop.bathrooms}
            onChange={(e) => set("bathrooms", Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
          />
        </div>
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          Save
        </button>
      </form>
      <button
        onClick={onDelete}
        className="mt-3 w-full rounded border border-red-500 py-2 text-red-600"
      >
        Delete property
      </button>
      <p className="mt-4">
        <Link href="/app/properties" className="text-blue-600">
          Back to properties
        </Link>
      </p>
    </main>
  );
}
```

- [ ] **Step 2: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 3: Commit, push, report, wait** — commit message: `Add property detail, edit, and delete page`

---

### Task 11: Property CRUD e2e

**Files:**
- Create: `frontend/e2e/properties.spec.ts`

**Interfaces:**
- Consumes: the full stack from Tasks 1-10.
- Produces: an e2e that signs up, creates a property, sees it listed, edits its status, and deletes it. Runs in the existing e2e CI job (no workflow change).

- [ ] **Step 1: Write the e2e** — `frontend/e2e/properties.spec.ts`

```typescript
import { expect, test } from "@playwright/test";

const email = `prop-e2e-${Date.now()}@example.com`;

test("create, list, edit, and delete a property", async ({ page }) => {
  // Sign up (logs in and lands on the dashboard).
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Prop E2E");
  await page.getByPlaceholder("Organization name").fill("Prop Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Go to properties and create one.
  await page.getByRole("link", { name: "Properties" }).click();
  await expect(page).toHaveURL(/\/app\/properties/);
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address").fill("42 Test Lane");
  await page.getByRole("button", { name: "Create property" }).click();

  // Lands on the detail page; edit the status.
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+/);
  await page.getByRole("combobox").first().selectOption("occupied");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("saved")).toBeVisible();

  // It appears in the list.
  await page.goto("/app/properties");
  await expect(page.getByText("42 Test Lane")).toBeVisible();

  // Delete it.
  await page.getByRole("link", { name: "42 Test Lane" }).click();
  await page.getByRole("button", { name: "Delete property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);
  await expect(page.getByText("42 Test Lane")).toHaveCount(0);
});
```

- [ ] **Step 2: Run locally**

Prereq: Postgres up, backend on 8000 (with the properties migration applied via `uv run alembic upgrade head`), frontend startable by Playwright.
Run: `cd frontend && npm run test:e2e`
Expected: all e2e pass (auth, forgot-password, change-password, properties).

- [ ] **Step 3: Commit, push, watch all three CI jobs green**

```bash
git add frontend
git commit -m "Add property CRUD e2e"
git push
gh run watch --exit-status
```

- [ ] **Step 4: Report — Milestone 2 (Property management) complete. Wait for approval to plan Milestone 3.**

---

## Deferred to a follow-up (not in this plan)

- **Property image upload (local disk):** the model already stores `image_urls`; a later mini-plan adds a `POST /api/v1/properties/{id}/images` upload endpoint (FastAPI `UploadFile` → local volume, served via `StaticFiles`) and a file-picker on the detail page. Deferred to keep this milestone focused on CRUD + multi-tenancy.

## Milestone Roadmap (next)

- **Milestone 3:** Tenant profiles + email invitations (tenant joins a landlord's org with role `tenant`), lease management (lease links a property to a tenant; expiry reminders; renewal). Property `status` starts being driven by whether an active lease exists.
- **Milestone 4:** Rent charges (APScheduler generation), payment recording, dashboard stats + charts.
- **Milestone 5:** Maintenance requests, notifications (in-app + email), Google OAuth.
