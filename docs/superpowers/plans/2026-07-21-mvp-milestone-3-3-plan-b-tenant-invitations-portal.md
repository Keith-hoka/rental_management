# MVP Milestone 3.3 — Plan B: Tenant Invitations + Tenant Portal

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a landlord/property_manager invite tenants (incl. co-tenants) to a lease by email; the invitee accepts via the existing link, joins the org as `tenant` linked to that lease, and sees a read-only tenant portal with their lease(s) and landlord contact.

**Architecture:** A nullable `Invitation.lease_id` marks tenant invites; a `LeaseTenant` join table links accepted tenant users to leases (co-tenants supported). A lease-scoped invite endpoint emails the tenant; the existing accept endpoint additionally creates the `LeaseTenant`. A user-scoped `GET /api/v1/me/leases` returns the tenant's leases with landlord contact; the dashboard branches on role.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, pytest + httpx, Next.js 16 (App Router, TypeScript, Tailwind), Postgres.

## Global Constraints

- Python package manager is `uv` only: `uv run`, `uv add` — never `python3` / `pip`.
- No emojis in code, logs, or commit messages.
- Short modules, clear names, docstrings over inline comments. No defensive programming beyond real failure points (external APIs, user input).
- TDD: every task writes the failing test first.
- **Before every push run the ruff sequence** (all pushes): `uv run ruff format .` → `uv run ruff check --fix .` → `uv run ruff check .` → `uv run ruff format --check .` (from `backend/`).
- **Per-task user gate:** every task ends with: run full test suite → ruff → commit → `git push` → report to the user → STOP and wait for approval before the next task.
- **Plan A is already merged** (lease roster `tenant_name/tenant_email/tenant_phone/co_tenants`, `User.phone`, profile editing). Build on it; do not redo it.
- **Member/tenant management is landlord + property_manager** for the invite and lease-tenants endpoints (`require_roles(Role.landlord, Role.property_manager)` → 403 for tenants). The tenant portal endpoint is user-scoped (any authenticated user; only tenants have data).
- **Lease deletion cascades:** the `lease_id` FKs on `lease_tenants` and `invitations` use `ON DELETE CASCADE`, so deleting a lease removes its tenant links and tenant invitations (this design decision is added here so lease deletion never FK-violates).
- **Email send failures never fail the request** (wrap `send_email` in try/except and log), as in the existing team-invite endpoint.
- Work on branch `main`. Repo: `https://github.com/Keith-hoka/rental_management`. Local Postgres host port 5433; CI 5432. Current migration head: `b5d49658f834`.

## Existing interfaces this plan builds on

- `app/models/invitation.py`: `Invitation(id, organization_id, email, role, token, status, created_at, expires_at)` (imports `ForeignKey`).
- `app/models/organization.py`: `Role` enum (`landlord`, `property_manager`, `tenant`), `Membership(user_id, organization_id, role)`.
- `app/models/user.py`: `User(id, email, hashed_password, name, phone, created_at)`.
- `app/models/lease.py`: `Lease(...)` incl. `tenant_name`, `tenant_email`, `tenant_phone`, `co_tenants`, `rent_amount`, `rent_frequency`, `bond_amount`, `notice_period_days`, `start_date`, `end_date`, `organization_id`, `property_id`.
- `app/models/__init__.py`: re-exports all models (Alembic autogenerate reads it).
- `app/routers/leases.py`: `router = APIRouter(prefix="/api/v1", tags=["leases"])`, `manager = require_roles(Role.landlord, Role.property_manager)`, `get_owned_lease(lease_id, membership, session) -> Lease` (404 cross-org), `_lease_state(lease, today) -> str` (`upcoming`/`ended`/`active`), imports `from app.models import Lease, Membership, Property, Role`, `from datetime import UTC, date, datetime`.
- `app/routers/properties.py`: `get_owned_property`.
- `app/routers/invitations.py`: `create_invitation` (pattern for token + email), `accept_invitation` (creates `User` + `Membership(role=invite.role)`, marks accepted, `issue_tokens`). Imports `hash_password`, `send_email`, `settings`, `secrets`.
- `app/schemas/invitation.py`: `InvitationResponse(id, email, role, status, expires_at)`, `AcceptInvitationRequest(token, name, password)`.
- `app/core/deps.py`: `require_roles(*roles)`, `get_current_user`, `get_current_membership`.
- `app/main.py`: mounts `auth_router`, `properties_router`, `invitations_router`, `leases_router`.
- `tests/conftest.py`: `client`, `db_session`, `engine` (engine uses `Base.metadata.create_all`, so FK `ondelete` from the models is honored in tests), autouse `disable_real_email`.
- `tests/test_properties_crud.py`: `landlord_headers(client, email="owner@example.com")`. `tests/test_leases.py`: `make_property(client, headers, address="1 Lease St")`, `lease_body(**overrides)`. `tests/test_invitation_accept.py`: token-from-DB pattern.
- Frontend `lib/api.ts` (`apiFetch` with `cache: "no-store"`, `ApiError`), `lib/auth.ts` (`getAccessToken`, `clearTokens`), `lib/leases.ts` (`Lease` incl. `tenant_name/tenant_email/co_tenants`, `getLease`), lease detail `app/app/leases/[leaseId]/page.tsx`, dashboard `app/app/page.tsx` (inline `Me {email,name,role}`). `playwright.config.ts` runs `workers: 1` + `retries: 1` in CI.

## File Structure

- `backend/app/models/lease_tenant.py` — `LeaseTenant`.
- `backend/app/models/invitation.py` — add `lease_id`.
- `backend/app/schemas/tenant.py` — `TenantInviteRequest`, `LeaseTenantInfo`, `TenantLease`.
- `backend/app/routers/leases.py` — invite + lease-tenants endpoints.
- `backend/app/routers/invitations.py` — extend accept.
- `backend/app/routers/portal.py` — `GET /api/v1/me/leases`.
- `backend/app/main.py` — mount portal router.
- `backend/tests/test_tenant_invite.py`, `test_portal.py`, plus additions to `test_lease_model.py`.
- `frontend/src/lib/tenants.ts`, `frontend/src/app/app/leases/[leaseId]/page.tsx`, `frontend/src/app/app/page.tsx`, `frontend/e2e/tenant-invite.spec.ts`.

---

### Task 1: Models — Invitation.lease_id + LeaseTenant + migration

**Files:**
- Create: `backend/app/models/lease_tenant.py`
- Modify: `backend/app/models/invitation.py`, `backend/app/models/__init__.py`
- Test: `backend/tests/test_lease_model.py` (append)

**Interfaces:**
- Produces: `LeaseTenant(id, lease_id, user_id)` with `UniqueConstraint(lease_id, user_id)` and `lease_id` FK `ON DELETE CASCADE`; `Invitation.lease_id: uuid | None` (FK `ON DELETE CASCADE`).

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_lease_model.py`

```python
async def test_lease_tenant_link_and_cascade(db_session):
    from app.models import Invitation, InvitationStatus, LeaseTenant, Role, User

    org = Organization(name="Cascade Org", currency="USD")
    db_session.add(org)
    await db_session.flush()
    prop = Property(organization_id=org.id, address="1 Cascade St", type=PropertyType.house)
    db_session.add(prop)
    await db_session.flush()
    lease = Lease(
        organization_id=org.id,
        property_id=prop.id,
        tenant_name="T",
        tenant_email="t@example.com",
        rent_amount=Decimal("1000.00"),
        rent_frequency=LeaseFrequency.monthly,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    user = User(email="tenant@example.com", hashed_password="x", name="Tenant")
    db_session.add_all([lease, user])
    await db_session.flush()

    db_session.add(LeaseTenant(lease_id=lease.id, user_id=user.id))
    db_session.add(
        Invitation(
            organization_id=org.id,
            email="tenant@example.com",
            role=Role.tenant,
            lease_id=lease.id,
            token="cascade-tok",
            status=InvitationStatus.pending,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await db_session.commit()

    # Deleting the lease cascades to its lease_tenants and invitations.
    await db_session.delete(lease)
    await db_session.commit()
    assert (
        await db_session.execute(select(LeaseTenant).where(LeaseTenant.lease_id == lease.id))
    ).first() is None
    assert (
        await db_session.execute(select(Invitation).where(Invitation.lease_id == lease.id))
    ).first() is None
```

Add `from datetime import UTC, timedelta` support: the file currently imports `from datetime import date`. Change that import line to:

```python
from datetime import UTC, date, datetime, timedelta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_lease_model.py::test_lease_tenant_link_and_cascade -v`
Expected: FAIL — `ImportError` (`LeaseTenant` not defined).

- [ ] **Step 3: Create the LeaseTenant model** — `backend/app/models/lease_tenant.py`

```python
import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LeaseTenant(Base):
    __tablename__ = "lease_tenants"
    __table_args__ = (UniqueConstraint("lease_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
```

- [ ] **Step 4: Add lease_id to Invitation** — `backend/app/models/invitation.py`

Add after `organization_id` (the file already imports `ForeignKey`):

```python
    lease_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), nullable=True, index=True
    )
```

- [ ] **Step 5: Register the model** — `backend/app/models/__init__.py`

Add the import and `__all__` entry:

```python
from app.models.lease_tenant import LeaseTenant
```
and add `"LeaseTenant",` to `__all__` (keep it alphabetical-ish, e.g. after `"Lease"`/`"LeaseFrequency"`).

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_lease_model.py -v`
Expected: PASS.

- [ ] **Step 7: Generate the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add invitation lease_id and lease_tenants"
```

Expected: detects `invitations.lease_id` and the `lease_tenants` table (with the FKs and unique constraint). No enum changes.

- [ ] **Step 8: Apply and round-trip the migration**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic current
```

Expected: upgrade adds the column + table; downgrade drops the `lease_tenants` table and the `invitations.lease_id` column; re-upgrade succeeds; `current` at the new head. If the autogenerated `downgrade` ordering errors, ensure it drops `lease_tenants` before dropping `invitations.lease_id` (both reference `leases`, but they are independent; order between them does not matter).

- [ ] **Step 9: Full suite, ruff, commit, push, report, wait**

```bash
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
git add backend
git commit -m "Add invitation lease_id and lease_tenants with cascade"
git push
```

---

### Task 2: Invite-tenant endpoint + tenant schemas

**Files:**
- Create: `backend/app/schemas/tenant.py`
- Modify: `backend/app/routers/leases.py`
- Test: `backend/tests/test_tenant_invite.py`

**Interfaces:**
- Consumes: `get_owned_lease`, `manager`, `LeaseTenant`, `User`, `Invitation`, `Role`, `send_email`, `settings`.
- Produces: `POST /api/v1/leases/{lease_id}/invite` → 201 `InvitationResponse`. `TenantInviteRequest {email}`, `LeaseTenantInfo {name, email}`, `TenantLease {...}` in `app/schemas/tenant.py`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_tenant_invite.py`

```python
from app.models import LeaseTenant, User
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def make_lease(client, headers, property_address="1 Invite St") -> str:
    property_id = await make_property(client, headers, property_address)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    return created["id"]


async def test_invite_tenant_returns_201(client):
    headers = await landlord_headers(client, "inv-owner@example.com")
    lease_id = await make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/invite",
        json={"email": "tenant@example.com"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "tenant@example.com"
    assert body["role"] == "tenant"


async def test_invite_tenant_requires_auth(client):
    headers = await landlord_headers(client, "inv-owner2@example.com")
    lease_id = await make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/invite", json={"email": "t@example.com"}
    )
    assert response.status_code == 401


async def test_invite_tenant_on_other_org_lease_is_404(client):
    org_a = await landlord_headers(client, "inva@example.com")
    org_b = await landlord_headers(client, "invb@example.com")
    lease_id = await make_lease(client, org_a)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/invite", json={"email": "t@example.com"}, headers=org_b
    )
    assert response.status_code == 404


async def test_invite_tenant_already_a_tenant_is_409(client, db_session):
    headers = await landlord_headers(client, "dupe@example.com")
    lease_id = await make_lease(client, headers)
    # Directly link a user to the lease, then invite the same email.
    user = User(email="already@example.com", hashed_password="x", name="Already")
    db_session.add(user)
    await db_session.flush()
    db_session.add(LeaseTenant(lease_id=lease_id, user_id=user.id))
    await db_session.commit()

    response = await client.post(
        f"/api/v1/leases/{lease_id}/invite",
        json={"email": "already@example.com"},
        headers=headers,
    )
    assert response.status_code == 409
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_tenant_invite.py -v`
Expected: FAIL with 404 (route not defined) / ImportError for `TenantInviteRequest` once wired.

- [ ] **Step 3: Create the tenant schemas** — `backend/app/schemas/tenant.py`

```python
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.models.lease import LeaseFrequency


class TenantInviteRequest(BaseModel):
    email: EmailStr


class LeaseTenantInfo(BaseModel):
    name: str
    email: EmailStr


class TenantLease(BaseModel):
    id: uuid.UUID
    property_address: str
    rent_amount: Decimal
    rent_frequency: LeaseFrequency
    start_date: date
    end_date: date
    bond_amount: Decimal | None
    notice_period_days: int | None
    state: Literal["active", "upcoming", "ended"]
    landlord_name: str
    landlord_email: EmailStr
    landlord_phone: str | None
```

- [ ] **Step 4: Add the invite endpoint** — `backend/app/routers/leases.py`

Update the top imports:

```python
import logging
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.deps import require_roles
from app.core.email import send_email
from app.models import Invitation, Lease, LeaseTenant, Membership, Property, Role, User
from app.routers.properties import get_owned_property
from app.schemas.invitation import InvitationResponse
from app.schemas.lease import LeaseCreate, LeaseResponse, LeaseSummary, LeaseUpdate
from app.schemas.tenant import TenantInviteRequest
```

Append this endpoint (after `list_all_leases`):

```python
@router.post("/leases/{lease_id}/invite", status_code=201, response_model=InvitationResponse)
async def invite_tenant(
    lease_id: uuid.UUID,
    body: TenantInviteRequest,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Invitation:
    """Invite a tenant (by email) to a lease in the caller's organization."""
    lease = await get_owned_lease(lease_id, membership, session)
    already = (
        await session.execute(
            select(LeaseTenant.id)
            .join(User, User.id == LeaseTenant.user_id)
            .where(LeaseTenant.lease_id == lease_id, User.email == body.email)
        )
    ).first()
    if already is not None:
        raise HTTPException(status_code=409, detail="Already a tenant of this lease")

    invite = Invitation(
        organization_id=lease.organization_id,
        email=body.email,
        role=Role.tenant,
        lease_id=lease.id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    accept_url = f"{settings.frontend_url}/accept-invite?token={invite.token}"
    html = (
        "<p>You have been invited as a tenant on Rental Management.</p>"
        f'<p><a href="{accept_url}">Accept the invitation</a></p>'
        "<p>This link expires in 7 days.</p>"
    )
    try:
        await send_email(invite.email, "You have been invited", html)
    except Exception:  # noqa: BLE001 - email failure must not fail the invite
        logging.getLogger(__name__).exception("Failed to send invite email to %s", invite.email)

    return invite
```

- [ ] **Step 5: Run full suite** — `cd backend && uv run pytest -v` — all pass.

- [ ] **Step 6: Ruff, commit, push, report, wait** — commit message: `Add invite-tenant endpoint and tenant schemas`

---

### Task 3: Extend accept to link the lease (LeaseTenant) + tenant RBAC

**Files:**
- Modify: `backend/app/routers/invitations.py`
- Test: `backend/tests/test_tenant_invite.py` (append)

**Interfaces:**
- Consumes: `LeaseTenant`, existing `accept_invitation`.
- Produces: accepting a `tenant` invite (with `lease_id`) creates a `LeaseTenant`. Tenants remain barred from management endpoints.

- [ ] **Step 1: Write the failing tests** — in `backend/tests/test_tenant_invite.py`, first update the top imports so they read:

```python
from sqlalchemy import select

from app.models import Invitation, LeaseTenant, User
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers
```

then append:

```python
async def invite_token(client, db_session, headers, lease_id, email) -> str:
    await client.post(f"/api/v1/leases/{lease_id}/invite", json={"email": email}, headers=headers)
    invite = (
        (await db_session.execute(select(Invitation).where(Invitation.email == email)))
        .scalars()
        .first()
    )
    return invite.token


async def accept(client, token, name="Tenant One", password="tenantpw1"):
    return await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": name, "password": password},
    )


async def test_accept_tenant_creates_lease_tenant(client, db_session):
    headers = await landlord_headers(client, "acc-owner@example.com")
    lease_id = await make_lease(client, headers)
    token = await invite_token(client, db_session, headers, lease_id, "tina@example.com")

    response = await accept(client, token)
    assert response.status_code == 201
    tenant_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    me = await client.get("/api/v1/auth/me", headers=tenant_headers)
    assert me.json()["role"] == "tenant"

    links = (
        (await db_session.execute(select(LeaseTenant).where(LeaseTenant.lease_id == lease_id)))
        .scalars()
        .all()
    )
    assert len(links) == 1


async def test_two_co_tenants_join_one_lease(client, db_session):
    headers = await landlord_headers(client, "co-owner@example.com")
    lease_id = await make_lease(client, headers)
    t1 = await invite_token(client, db_session, headers, lease_id, "one@example.com")
    t2 = await invite_token(client, db_session, headers, lease_id, "two@example.com")
    assert (await accept(client, t1, name="One")).status_code == 201
    assert (await accept(client, t2, name="Two")).status_code == 201

    links = (
        (await db_session.execute(select(LeaseTenant).where(LeaseTenant.lease_id == lease_id)))
        .scalars()
        .all()
    )
    assert len(links) == 2


async def test_tenant_cannot_reach_management_endpoints(client, db_session):
    headers = await landlord_headers(client, "rbac-owner@example.com")
    lease_id = await make_lease(client, headers)
    token = await invite_token(client, db_session, headers, lease_id, "rbac-tenant@example.com")
    tenant_headers = {"Authorization": f"Bearer {(await accept(client, token)).json()['access_token']}"}

    assert (await client.get("/api/v1/properties", headers=tenant_headers)).status_code == 403
    assert (await client.get("/api/v1/leases", headers=tenant_headers)).status_code == 403
    invite_as_tenant = await client.post(
        f"/api/v1/leases/{lease_id}/invite",
        json={"email": "someone@example.com"},
        headers=tenant_headers,
    )
    assert invite_as_tenant.status_code == 403
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_tenant_invite.py -k "accept_tenant or co_tenants" -v`
Expected: FAIL — no `LeaseTenant` row is created (the accept endpoint does not link the lease yet), so the `len(links)` assertions fail.

- [ ] **Step 3: Link the lease on accept** — `backend/app/routers/invitations.py`

Add `LeaseTenant` to the models import:

```python
from app.models import Invitation, InvitationStatus, LeaseTenant, Membership, Role, User
```

In `accept_invitation`, after `session.add(Membership(...))` and before `invite.status = InvitationStatus.accepted`, add:

```python
    if invite.lease_id is not None:
        session.add(LeaseTenant(lease_id=invite.lease_id, user_id=user.id))
```

- [ ] **Step 4: Run full suite** — `cd backend && uv run pytest -v` — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Link the lease on tenant invite acceptance`

---

### Task 4: List a lease's joined tenants

**Files:**
- Modify: `backend/app/routers/leases.py`
- Test: `backend/tests/test_tenant_invite.py` (append)

**Interfaces:**
- Produces: `GET /api/v1/leases/{lease_id}/tenants` → `list[LeaseTenantInfo]` (joined tenants' name/email). 404 cross-org.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_tenant_invite.py`

```python
async def test_list_lease_tenants_returns_joined(client, db_session):
    headers = await landlord_headers(client, "list-owner@example.com")
    lease_id = await make_lease(client, headers)
    token = await invite_token(client, db_session, headers, lease_id, "joined@example.com")
    await accept(client, token, name="Joined Tenant")

    response = await client.get(f"/api/v1/leases/{lease_id}/tenants", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [t["email"] for t in body] == ["joined@example.com"]
    assert body[0]["name"] == "Joined Tenant"


async def test_list_lease_tenants_other_org_is_404(client):
    org_a = await landlord_headers(client, "lta@example.com")
    org_b = await landlord_headers(client, "ltb@example.com")
    lease_id = await make_lease(client, org_a)
    response = await client.get(f"/api/v1/leases/{lease_id}/tenants", headers=org_b)
    assert response.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_tenant_invite.py -k "list_lease_tenants" -v`
Expected: FAIL — `GET /leases/{id}/tenants` returns 404 (route not defined).

- [ ] **Step 3: Add the endpoint** — `backend/app/routers/leases.py`

Add `LeaseTenantInfo` to the tenant schemas import:

```python
from app.schemas.tenant import LeaseTenantInfo, TenantInviteRequest
```

Append after `invite_tenant`:

```python
@router.get("/leases/{lease_id}/tenants", response_model=list[LeaseTenantInfo])
async def list_lease_tenants(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[LeaseTenantInfo]:
    """List the tenants who have joined the given lease."""
    await get_owned_lease(lease_id, membership, session)
    result = await session.execute(
        select(User.name, User.email)
        .join(LeaseTenant, LeaseTenant.user_id == User.id)
        .where(LeaseTenant.lease_id == lease_id)
    )
    return [LeaseTenantInfo(name=name, email=email) for name, email in result.all()]
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add list-lease-tenants endpoint`

---

### Task 5: Tenant portal — GET /api/v1/me/leases

**Files:**
- Create: `backend/app/routers/portal.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_portal.py`

**Interfaces:**
- Consumes: `get_current_user`, `LeaseTenant`, `Lease`, `Property`, `Membership`, `User`, `Role`, `_lease_state`, `TenantLease`.
- Produces: `GET /api/v1/me/leases` → `list[TenantLease]` (user-scoped, with landlord contact). Router object `router` (prefix `/api/v1/me`).

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_portal.py`

```python
from sqlalchemy import select

from app.models import Invitation
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def onboard_tenant(client, db_session, headers, lease_id, email, name="Tenant"):
    await client.post(f"/api/v1/leases/{lease_id}/invite", json={"email": email}, headers=headers)
    token = (
        (await db_session.execute(select(Invitation).where(Invitation.email == email)))
        .scalars()
        .first()
    ).token
    tokens = (
        await client.post(
            "/api/v1/invitations/accept",
            json={"token": token, "name": name, "password": "tenantpw1"},
        )
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def make_lease(client, headers, address="1 Portal St") -> str:
    property_id = await make_property(client, headers, address)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    return created["id"]


async def test_my_leases_shows_lease_and_landlord_contact(client, db_session):
    headers = await landlord_headers(client, "ll@example.com")
    await client.patch("/api/v1/auth/me", json={"name": "Larry Landlord", "phone": "555-7777"}, headers=headers)
    lease_id = await make_lease(client, headers)
    tenant_headers = await onboard_tenant(client, db_session, headers, lease_id, "tp@example.com")

    response = await client.get("/api/v1/me/leases", headers=tenant_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["property_address"] == "1 Portal St"
    assert body[0]["landlord_name"] == "Larry Landlord"
    assert body[0]["landlord_phone"] == "555-7777"
    assert body[0]["state"] in {"active", "upcoming", "ended"}


async def test_my_leases_is_isolated_per_tenant(client, db_session):
    headers = await landlord_headers(client, "iso@example.com")
    lease_a = await make_lease(client, headers, "A St")
    lease_b = await make_lease(client, headers, "B St")
    ta = await onboard_tenant(client, db_session, headers, lease_a, "ta@example.com", "TA")
    await onboard_tenant(client, db_session, headers, lease_b, "tb@example.com", "TB")

    a_leases = (await client.get("/api/v1/me/leases", headers=ta)).json()
    assert [l["property_address"] for l in a_leases] == ["A St"]


async def test_my_leases_empty_for_landlord(client):
    headers = await landlord_headers(client, "notenant@example.com")
    response = await client.get("/api/v1/me/leases", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_my_leases_requires_auth(client):
    response = await client.get("/api/v1/me/leases")
    assert response.status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_portal.py -v`
Expected: FAIL with 404 (route not mounted).

- [ ] **Step 3: Create the portal router** — `backend/app/routers/portal.py`

```python
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models import Lease, LeaseTenant, Membership, Property, Role, User
from app.routers.leases import _lease_state
from app.schemas.tenant import TenantLease

router = APIRouter(prefix="/api/v1/me", tags=["portal"])


@router.get("/leases", response_model=list[TenantLease])
async def my_leases(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TenantLease]:
    """List leases the current user is a tenant of, with landlord contact."""
    today = datetime.now(UTC).date()
    result = await session.execute(
        select(Lease, Property.address)
        .join(LeaseTenant, LeaseTenant.lease_id == Lease.id)
        .join(Property, Property.id == Lease.property_id)
        .where(LeaseTenant.user_id == user.id)
        .order_by(Lease.start_date.desc())
    )

    leases: list[TenantLease] = []
    for lease, address in result.all():
        landlord = (
            await session.execute(
                select(User.name, User.email, User.phone)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.organization_id == lease.organization_id,
                    Membership.role == Role.landlord,
                )
            )
        ).first()
        leases.append(
            TenantLease(
                id=lease.id,
                property_address=address,
                rent_amount=lease.rent_amount,
                rent_frequency=lease.rent_frequency,
                start_date=lease.start_date,
                end_date=lease.end_date,
                bond_amount=lease.bond_amount,
                notice_period_days=lease.notice_period_days,
                state=_lease_state(lease, today),
                landlord_name=landlord.name if landlord else "",
                landlord_email=landlord.email if landlord else "",
                landlord_phone=landlord.phone if landlord else None,
            )
        )
    return leases
```

- [ ] **Step 4: Mount the router** — `backend/app/main.py`

Add the import beside the others and include it after `app.include_router(leases_router)`:

```python
from app.routers.portal import router as portal_router
```
```python
app.include_router(portal_router)
```

- [ ] **Step 5: Run full suite** — `cd backend && uv run pytest -v` — all pass.

- [ ] **Step 6: Ruff, commit, push, report, wait** — commit message: `Add tenant portal endpoint for a tenant's own leases`

---

### Task 6: Frontend — tenant API client + lease-detail Tenants section

**Files:**
- Create: `frontend/src/lib/tenants.ts`
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx`

**Interfaces:**
- Consumes: `apiFetch`, `ApiError`, `Lease` (has `tenant_name`, `tenant_email`, `co_tenants`).
- Produces: `inviteTenant(leaseId, email)`, `listLeaseTenants(leaseId)`, `listMyLeases()`; `LeaseTenantInfo`, `TenantLease` types. Lease detail shows a Tenants section (invite roster + joined list).

- [ ] **Step 1: Tenant API module** — `frontend/src/lib/tenants.ts`

```typescript
import { apiFetch } from "@/lib/api";

export interface LeaseTenantInfo {
  name: string;
  email: string;
}

export interface TenantLease {
  id: string;
  property_address: string;
  rent_amount: number;
  rent_frequency: "weekly" | "fortnightly" | "monthly";
  start_date: string;
  end_date: string;
  bond_amount: number | null;
  notice_period_days: number | null;
  state: "active" | "upcoming" | "ended";
  landlord_name: string;
  landlord_email: string;
  landlord_phone: string | null;
}

export function inviteTenant(leaseId: string, email: string) {
  return apiFetch<unknown>(`/api/v1/leases/${leaseId}/invite`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function listLeaseTenants(leaseId: string) {
  return apiFetch<LeaseTenantInfo[]>(`/api/v1/leases/${leaseId}/tenants`);
}

export function listMyLeases() {
  return apiFetch<TenantLease[]>("/api/v1/me/leases");
}
```

- [ ] **Step 2: Add a Tenants section to the lease detail** — `frontend/src/app/app/leases/[leaseId]/page.tsx`

Add the import:

```tsx
import { inviteTenant, listLeaseTenants, type LeaseTenantInfo } from "@/lib/tenants";
```

Add state (next to the existing `useState` hooks):

```tsx
  const [joined, setJoined] = useState<LeaseTenantInfo[]>([]);
  const [inviteStatus, setInviteStatus] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
```

In the existing `useEffect` (which loads the lease), also load joined tenants; add inside the effect body, after `getLease(...)` chain is set up, a second guarded fetch:

```tsx
    listLeaseTenants(leaseId)
      .then((t) => {
        if (active) setJoined(t);
      })
      .catch(() => {
        if (active) setJoined([]);
      });
```

Add the invite handler (next to the other handlers):

```tsx
  async function onInvite(email: string) {
    setInviteError(null);
    setInviteStatus(null);
    try {
      await inviteTenant(leaseId, email);
      setInviteStatus(`Invitation sent to ${email}`);
      setJoined(await listLeaseTenants(leaseId));
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Invite failed");
    }
  }
```

In the read-only (non-editing) view — after the `</dl>` and the Edit/Delete button row, before the "Back to all leases" link — render the Tenants section:

```tsx
      {!editing && (
        <section className="mt-8">
          <h2 className="mb-2 font-semibold">Tenants</h2>
          {inviteStatus && <p className="mb-2 text-sm text-green-700">{inviteStatus}</p>}
          {inviteError && (
            <p className="mb-2 text-sm text-red-600" role="alert">
              {inviteError}
            </p>
          )}
          <ul className="space-y-2">
            {[
              { name: lease.tenant_name, email: lease.tenant_email },
              ...lease.co_tenants.map((c) => ({ name: c.name, email: c.email })),
            ].map((r) => (
              <li
                key={r.email}
                className="flex items-center justify-between rounded border p-2 text-sm"
              >
                <span>
                  {r.name} <span className="text-gray-500">({r.email})</span>
                </span>
                <button
                  onClick={() => onInvite(r.email)}
                  className="rounded border px-2 py-1 text-blue-600 transition hover:bg-blue-50"
                >
                  Invite
                </button>
              </li>
            ))}
          </ul>
          {joined.length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-semibold text-gray-700">Joined</p>
              <ul className="mt-1 space-y-1 text-sm text-gray-700">
                {joined.map((t) => (
                  <li key={t.email}>
                    {t.name} — {t.email}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
```

(`editing`, `lease`, `leaseId`, `ApiError` are already in scope in this file.)

- [ ] **Step 3: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 4: Commit, push, report, wait** — commit message: `Add tenant invite roster to the lease detail page`

---

### Task 7: Frontend — tenant dashboard branching

**Files:**
- Modify: `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: `listMyLeases`, `TenantLease`.
- Produces: for `me.role === "tenant"`, a read-only "Your lease" view with landlord contact; otherwise the existing manager dashboard.

- [ ] **Step 1: Branch the dashboard on role** — `frontend/src/app/app/page.tsx` (replace the file)

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { listMyLeases, type TenantLease } from "@/lib/tenants";

interface Me {
  email: string;
  name: string;
  role: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [myLeases, setMyLeases] = useState<TenantLease[]>([]);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    apiFetch<Me>("/api/v1/auth/me")
      .then((m) => {
        if (!active) return;
        setMe(m);
        if (m.role === "tenant") {
          return listMyLeases().then((l) => {
            if (active) setMyLeases(l);
          });
        }
      })
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!me) return null;

  function logOut() {
    clearTokens();
    router.replace("/login");
  }

  if (me.role === "tenant") {
    return (
      <main className="mx-auto max-w-lg p-8">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p data-testid="welcome" className="mt-2 text-gray-700">
          Welcome, {me.name} ({me.role})
        </p>
        <h2 className="mt-6 mb-2 font-semibold">Your lease</h2>
        <ul className="space-y-3">
          {myLeases.map((l) => (
            <li key={l.id} className="rounded border p-3 text-sm">
              <p className="font-medium text-gray-800">{l.property_address}</p>
              <p className="text-gray-700">
                ${l.rent_amount} / {l.rent_frequency} · {l.start_date} to {l.end_date} · {l.state}
              </p>
              {l.bond_amount != null && <p className="text-gray-600">Bond: ${l.bond_amount}</p>}
              {l.notice_period_days != null && (
                <p className="text-gray-600">Notice period: {l.notice_period_days} days</p>
              )}
              <p className="mt-1 text-gray-700">
                Landlord contact: {l.landlord_name} — {l.landlord_email}
                {l.landlord_phone ? ` — ${l.landlord_phone}` : ""}
              </p>
            </li>
          ))}
          {myLeases.length === 0 && <li className="text-gray-500">No lease yet.</li>}
        </ul>
        <div className="mt-6 flex gap-3">
          <Link href="/app/profile" className="rounded border px-3 py-1 text-blue-600">
            Contact info
          </Link>
          <Link href="/app/change-password" className="rounded border px-3 py-1 text-blue-600">
            Change password
          </Link>
          <button onClick={logOut} className="rounded border px-3 py-1">
            Log out
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <p data-testid="welcome" className="mt-2 text-gray-700">
        Welcome, {me.name} ({me.role})
      </p>
      <div className="mt-4 flex gap-3">
        <Link href="/app/properties" className="rounded border px-3 py-1 text-blue-600">
          Properties
        </Link>
        <Link href="/app/leases" className="rounded border px-3 py-1 text-blue-600">
          Leases
        </Link>
        <Link href="/app/team" className="rounded border px-3 py-1 text-blue-600">
          Team
        </Link>
        <Link href="/app/change-password" className="rounded border px-3 py-1 text-blue-600">
          Change password
        </Link>
        <Link href="/app/profile" className="rounded border px-3 py-1 text-blue-600">
          Contact info
        </Link>
        <button onClick={logOut} className="rounded border px-3 py-1">
          Log out
        </button>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 3: Commit, push, report, wait** — commit message: `Branch the dashboard into a read-only tenant portal`

---

### Task 8: Tenant-invite e2e

**Files:**
- Create: `frontend/e2e/tenant-invite.spec.ts`

**Interfaces:**
- Consumes: the full stack from Tasks 1-7, backend on 8000 with the migration applied.

**Why the accept + portal flow is not driven end-to-end here:** the invite token is emailed only (never returned by the API), so Playwright cannot accept as the tenant — exactly as with the team-invitation e2e. The accept + `LeaseTenant` + portal path is covered by the backend tests (Tasks 3 and 5). This e2e verifies the landlord-side invite UI.

- [ ] **Step 1: Write the e2e** — `frontend/e2e/tenant-invite.spec.ts`

```typescript
import { expect, test } from "@playwright/test";

const landlord = `tenant-invite-${Date.now()}@example.com`;

test("landlord invites a tenant from the lease detail", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Invite Landlord");
  await page.getByPlaceholder("Organization name").fill("Invite Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Create a property.
  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("5 Tenant Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Create a lease with a main tenant from the Leases page.
  await page.goto("/app");
  await page.getByRole("link", { name: "Leases" }).click();
  await page.getByLabel("Property").selectOption({ label: "5 Tenant Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Tessa Tenant");
  await page.getByPlaceholder("Tenant email").fill("tessa@example.com");
  await page.getByLabel("Rent").fill("1400");
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 1);
  const end = new Date(today);
  end.setDate(end.getDate() + 30);
  await page.getByLabel("Start").fill(start.toISOString().slice(0, 10));
  await page.getByLabel("End").fill(end.toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page.getByText("Tessa Tenant", { exact: false })).toBeVisible();

  // Open the lease detail and invite the main tenant.
  await page.getByRole("link", { name: "5 Tenant Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByRole("button", { name: "Invite" }).first().click();
  await expect(page.getByText("Invitation sent to tessa@example.com")).toBeVisible();
});
```

- [ ] **Step 2: Run locally**

Prereq: Postgres up; backend on 8000 with `uv run alembic upgrade head` applied (the new migration); frontend startable by Playwright.
Run: `cd frontend && npx playwright test`
Expected: all e2e pass (auth, forgot-password, change-password, properties, property-images, team-invitations, leases, profile, tenant-invite).

- [ ] **Step 3: Commit, push, watch all three CI jobs green**

```bash
git add frontend
git commit -m "Add tenant-invite e2e"
git push
gh run watch --exit-status
```

- [ ] **Step 4: Report — Milestone 3.3 complete (Plans A + B): tenants can be invited to a lease, join as `tenant`, and see their own lease + landlord contact. Wait for approval to plan Milestone 3.4 (lease-expiry reminders).**

---

## Milestone Roadmap (next)

- **Milestone 3.4:** Lease-expiry reminders — a scheduled job (APScheduler) that finds leases nearing `end_date` and emails the landlord/tenant; configurable lead time.
- **Milestone 4:** Rent charges (scheduled generation), payment recording, dashboard stats + charts.
