# MVP Milestone 3.1: Team Invitations (property_manager onboarding) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `property_manager` role reachable: a landlord invites a team member by email, the invitee accepts via an emailed link (setting name + password), and joins the landlord's organization as a `property_manager`.

**Architecture:** A DB-backed `Invitation` (org, email, role, token, status, expiry). Landlord-only endpoints create/list/revoke invitations and send the accept link by email; a public accept endpoint creates the user + membership with the invited role. Only `landlord` may manage members. Next.js pages: a Team page for landlords and a public accept-invite page.

**Tech Stack:** Existing stack — FastAPI, async SQLAlchemy 2.0, Alembic, pytest + httpx, Next.js 16 (App Router, TypeScript, Tailwind), Postgres, Resend (email).

## Global Constraints

- Python package manager is `uv` only: `uv run`, `uv add` — never `python3` / `pip`.
- No emojis in code, logs, or commit messages.
- Short modules, clear names, docstrings over inline comments. No defensive programming beyond real failure points (external APIs, user input).
- TDD: every task writes the failing test first.
- **Before every push run the ruff sequence** (Python changes): `uv run ruff format .` → `uv run ruff check --fix .` → `uv run ruff check .` → `uv run ruff format --check .`
- **Per-task user gate:** every task ends with: run full test suite → ruff → commit → `git push` → report to the user (what was done, test results, CI status) → STOP and wait for approval before the next task.
- **Member management is landlord-only:** invitation create/list/revoke endpoints require role `landlord`. `property_manager` and `tenant` receive 403.
- **Organization scoping:** every invitation query filters by `membership.organization_id`. The invited membership's `organization_id` comes from the inviter's membership, never the client.
- **No account enumeration on accept:** accepting with an already-registered email returns 409; invalid/expired/used tokens return 400.
- Work on branch `main`. Repo: `https://github.com/Keith-hoka/rental_management`. Local Postgres host port 5433; CI Postgres 5432 (`DATABASE_URL` / `TEST_DATABASE_URL` env override).

## Existing interfaces this milestone builds on

- `app/models/organization.py`: `Role` enum (`landlord`, `property_manager`, `tenant`), `Organization`, `Membership` (has `organization_id`, `role`, `user_id`).
- `app/models/__init__.py`: re-exports all models (Alembic autogenerate reads this).
- `app/core/deps.py`: `require_roles(*roles)` → dependency returning the current `Membership`; `get_current_membership`; `get_current_user`.
- `app/core/security.py`: `hash_password(pw)`, `verify_password(pw, hashed)`, `create_token`, `decode_token`.
- `app/core/email.py`: `async send_email(to, subject, html)` — Resend when configured, else logs.
- `app/core/config.py`: `settings.frontend_url` (default `http://localhost:3000`).
- `app/routers/auth.py`: `signup` (creates a landlord membership), `issue_tokens(user_id: str) -> TokenPair`.
- `app/models/user.py`: `User(id, email, hashed_password, name, created_at)`.
- `tests/conftest.py`: fixtures `engine`, `db_session`, `client` (the `client` overrides `get_session` against `rental_test`).
- Auth for tests: `POST /api/v1/auth/signup` returns `{access_token, refresh_token, token_type}`; send `Authorization: Bearer <access_token>`.
- Frontend: `frontend/src/lib/api.ts` (`apiFetch<T>`, `API_BASE_URL`, `ApiError`); `frontend/src/lib/auth.ts` (`saveTokens`, `getAccessToken`); dashboard `frontend/src/app/app/page.tsx` (button/link row).

## File Structure

- `backend/app/models/invitation.py` — `InvitationStatus` enum, `Invitation` model.
- `backend/app/schemas/invitation.py` — `InvitationCreate`, `InvitationResponse`, `AcceptInvitationRequest`.
- `backend/app/routers/invitations.py` — landlord-only create/list/revoke + public accept.
- `backend/tests/test_invitations.py` — invitation CRUD, RBAC, scoping.
- `backend/tests/test_invitation_accept.py` — accept flow, role granted, error cases.
- `frontend/src/lib/invitations.ts` — typed invitation API calls + shared types.
- `frontend/src/app/app/team/page.tsx` — landlord team page (invite + list + revoke).
- `frontend/src/app/accept-invite/page.tsx` — public accept-invite page.
- `frontend/e2e/team-invitations.spec.ts` — end-to-end invite → accept → property_manager access.

---

### Task 1: Invitation model + enum + migration

**Files:**
- Create: `backend/app/models/invitation.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_invitation_model.py`

**Interfaces:**
- Produces: `Invitation(id, organization_id, email, role, token, status, created_at, expires_at)`; `InvitationStatus` enum (`pending`, `accepted`, `revoked`). `token` is a unique random URL-safe string. `role` is a `Role`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_invitation_model.py`

```python
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Invitation, InvitationStatus, Organization, Role


async def test_create_invitation(db_session):
    org = Organization(name="Keith Properties", currency="USD")
    db_session.add(org)
    await db_session.flush()

    invite = Invitation(
        organization_id=org.id,
        email="pm@example.com",
        role=Role.property_manager,
        token="tok-123",
        status=InvitationStatus.pending,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(invite)
    await db_session.commit()

    found = (
        await db_session.execute(select(Invitation).where(Invitation.token == "tok-123"))
    ).scalar_one()
    assert found.organization_id == org.id
    assert found.role == Role.property_manager
    assert found.status == InvitationStatus.pending
    assert isinstance(found.id, uuid.UUID)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_invitation_model.py -v`
Expected: FAIL with `ImportError` (`Invitation` not defined).

- [ ] **Step 3: Implement the model** — `backend/app/models/invitation.py`

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.organization import Role


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus), default=InvitationStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Export the model** — `backend/app/models/__init__.py` (replace file)

```python
from app.models.invitation import Invitation, InvitationStatus
from app.models.organization import Membership, Organization, Role
from app.models.property import Property, PropertyStatus, PropertyType
from app.models.user import User

__all__ = [
    "Invitation",
    "InvitationStatus",
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
Expected: all pass (existing 40 + this one).

- [ ] **Step 6: Generate and apply the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add invitations table"
uv run alembic upgrade head
```

Expected: a migration under `backend/alembic/versions/` creating `invitations` with indexes on `organization_id`, `email`, and a unique `token`; upgrade applies cleanly.

- [ ] **Step 7: Ruff, commit, push, report, wait**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
git add backend
git commit -m "Add Invitation model, status enum, and migration"
git push
```

---

### Task 2: Create-invitation endpoint (landlord only) + email

**Files:**
- Create: `backend/app/schemas/invitation.py`, `backend/app/routers/invitations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_invitations.py`

**Interfaces:**
- Consumes: `require_roles(Role.landlord)`, `send_email`, `settings.frontend_url`.
- Produces: `POST /api/v1/invitations` accepting `{email, role}` (role must be `property_manager` — `tenant` invites come with leases later) → 201 `InvitationResponse`. `organization_id` from the inviter's membership. Sends an email with an accept link `{frontend_url}/accept-invite?token={token}`. Router object `router`; `landlord_only = require_roles(Role.landlord)`. `InvitationResponse` fields: `id, email, role, status, expires_at`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_invitations.py`

```python
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


async def test_create_invitation_returns_201(client):
    headers = await landlord_headers(client)
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "pm@example.com", "role": "property_manager"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "pm@example.com"
    assert body["role"] == "property_manager"
    assert body["status"] == "pending"


async def test_create_invitation_requires_auth(client):
    response = await client.post(
        "/api/v1/invitations", json={"email": "pm@example.com", "role": "property_manager"}
    )
    assert response.status_code == 401


async def test_create_invitation_rejects_tenant_role(client):
    headers = await landlord_headers(client)
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "t@example.com", "role": "tenant"},
        headers=headers,
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_invitations.py -v`
Expected: FAIL with 404 (route not mounted).

- [ ] **Step 3: Implement schemas** — `backend/app/schemas/invitation.py`

```python
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.invitation import InvitationStatus
from app.models.organization import Role


class InvitationCreate(BaseModel):
    email: EmailStr
    # Only team members (property_manager) are invited here; tenant invites
    # arrive with leases in a later plan.
    role: Literal["property_manager"]


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: Role
    status: InvitationStatus
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str
    name: str
    password: str
```

- [ ] **Step 4: Implement the router** — `backend/app/routers/invitations.py`

```python
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.deps import require_roles
from app.core.email import send_email
from app.models import Invitation, Membership, Role
from app.schemas.invitation import InvitationCreate, InvitationResponse

router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])

landlord_only = require_roles(Role.landlord)

INVITE_TTL_DAYS = 7


@router.post("", status_code=201, response_model=InvitationResponse)
async def create_invitation(
    body: InvitationCreate,
    membership: Membership = Depends(landlord_only),
    session: AsyncSession = Depends(get_session),
) -> Invitation:
    """Invite a team member (property_manager) to the caller's organization."""
    invite = Invitation(
        organization_id=membership.organization_id,
        email=body.email,
        role=Role(body.role),
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    accept_url = f"{settings.frontend_url}/accept-invite?token={invite.token}"
    html = (
        "<p>You have been invited to join a team on Rental Management.</p>"
        f'<p><a href="{accept_url}">Accept the invitation</a></p>'
        "<p>This link expires in 7 days.</p>"
    )
    try:
        await send_email(invite.email, "You have been invited", html)
    except Exception:  # noqa: BLE001 - email failure must not fail the invite
        import logging

        logging.getLogger(__name__).exception("Failed to send invite email to %s", invite.email)

    return invite
```

- [ ] **Step 5: Mount the router** — `backend/app/main.py`

Add the import alongside the others:

```python
from app.routers.invitations import router as invitations_router
```

and after `app.include_router(properties_router)`:

```python
app.include_router(invitations_router)
```

- [ ] **Step 6: Run full suite** — `cd backend && uv run pytest -v` — all pass. (The `tenant` role is rejected by the `Literal["property_manager"]` schema with 422.)

- [ ] **Step 7: Ruff, commit, push, report, wait** — commit message: `Add create-invitation endpoint for team members`

---

### Task 3: List and revoke invitations (landlord only, org-scoped)

**Files:**
- Modify: `backend/app/routers/invitations.py`
- Test: `backend/tests/test_invitations.py` (append)

**Interfaces:**
- Produces: `GET /api/v1/invitations` → `list[InvitationResponse]` (pending invitations of the caller's org, newest first). `DELETE /api/v1/invitations/{invitation_id}` → 204, sets status to `revoked`; cross-org is 404.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_invitations.py`

```python
async def test_list_invitations_is_org_scoped(client):
    org_a = await landlord_headers(client, "a@example.com")
    org_b = await landlord_headers(client, "b@example.com")
    await client.post(
        "/api/v1/invitations",
        json={"email": "pm@example.com", "role": "property_manager"},
        headers=org_a,
    )

    b_list = await client.get("/api/v1/invitations", headers=org_b)
    assert b_list.status_code == 200
    assert b_list.json() == []

    a_list = await client.get("/api/v1/invitations", headers=org_a)
    assert len(a_list.json()) == 1


async def test_revoke_invitation_removes_it_from_list(client):
    headers = await landlord_headers(client, "revoker@example.com")
    created = (
        await client.post(
            "/api/v1/invitations",
            json={"email": "pm@example.com", "role": "property_manager"},
            headers=headers,
        )
    ).json()

    revoked = await client.delete(f"/api/v1/invitations/{created['id']}", headers=headers)
    assert revoked.status_code == 204

    listed = await client.get("/api/v1/invitations", headers=headers)
    assert listed.json() == []


async def test_revoke_invitation_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "a5@example.com")
    org_b = await landlord_headers(client, "b5@example.com")
    created = (
        await client.post(
            "/api/v1/invitations",
            json={"email": "pm@example.com", "role": "property_manager"},
            headers=org_a,
        )
    ).json()

    response = await client.delete(f"/api/v1/invitations/{created['id']}", headers=org_b)
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_invitations.py -v`
Expected: FAIL — `GET` returns 405 (not defined) and `DELETE` 405.

- [ ] **Step 3: Implement list + revoke** — update `backend/app/routers/invitations.py`

Update the top imports to add `uuid`, `HTTPException`, `Response`, `select`, `InvitationStatus`, `InvitationResponse` (already imported):

```python
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.deps import require_roles
from app.core.email import send_email
from app.models import Invitation, InvitationStatus, Membership, Role
from app.schemas.invitation import InvitationCreate, InvitationResponse
```

Append after `create_invitation`:

```python
@router.get("", response_model=list[InvitationResponse])
async def list_invitations(
    membership: Membership = Depends(landlord_only),
    session: AsyncSession = Depends(get_session),
) -> list[Invitation]:
    """List pending invitations for the caller's organization, newest first."""
    result = await session.execute(
        select(Invitation)
        .where(
            Invitation.organization_id == membership.organization_id,
            Invitation.status == InvitationStatus.pending,
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    membership: Membership = Depends(landlord_only),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Revoke a pending invitation in the caller's organization."""
    invite = (
        await session.execute(
            select(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    invite.status = InvitationStatus.revoked
    await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Run full suite** — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add list and revoke invitation endpoints`

---

### Task 4: Accept-invitation endpoint (public) — creates property_manager

**Files:**
- Modify: `backend/app/routers/invitations.py`
- Test: `backend/tests/test_invitation_accept.py`

**Interfaces:**
- Consumes: `hash_password`, `issue_tokens` (from `app.routers.auth`), `AcceptInvitationRequest`, `Invitation`, `InvitationStatus`, `Membership`, `User`.
- Produces: `POST /api/v1/invitations/accept` accepting `{token, name, password}` → 201 `TokenPair` (the new user is logged in). Creates a `User` (email from the invitation) + `Membership` with the invited role, marks the invitation `accepted`. Errors: 400 for unknown/expired/non-pending token; 409 if the email is already a registered user.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_invitation_accept.py`

```python
from sqlalchemy import select

from app.models import Invitation
from tests.test_invitations import landlord_headers


async def create_invite(client, db_session, headers, email="pm@example.com") -> str:
    """Create an invitation and read its token from the DB (the API never returns it)."""
    await client.post(
        "/api/v1/invitations",
        json={"email": email, "role": "property_manager"},
        headers=headers,
    )
    invite = (
        await db_session.execute(select(Invitation).where(Invitation.email == email))
    ).scalars().first()
    return invite.token


async def test_accept_invitation_creates_property_manager(client, db_session):
    headers = await landlord_headers(client, "inviter@example.com")
    token = await create_invite(client, db_session, headers)

    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "PM", "password": "pmsecret1"},
    )
    assert response.status_code == 201
    assert response.json()["access_token"]

    # The new property_manager can log in and read properties (allowed for the role).
    login = await client.post(
        "/api/v1/auth/login", json={"email": "pm@example.com", "password": "pmsecret1"}
    )
    assert login.status_code == 200
    pm_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await client.get("/api/v1/auth/me", headers=pm_headers)
    assert me.json()["role"] == "property_manager"
    props = await client.get("/api/v1/properties", headers=pm_headers)
    assert props.status_code == 200


async def test_accept_invitation_rejects_unknown_token(client):
    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": "does-not-exist", "name": "X", "password": "secret123"},
    )
    assert response.status_code == 400


async def test_accept_invitation_is_single_use(client, db_session):
    headers = await landlord_headers(client, "inviter2@example.com")
    token = await create_invite(client, db_session, headers, email="pm2@example.com")

    first = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "PM", "password": "pmsecret1"},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "PM", "password": "pmsecret1"},
    )
    assert second.status_code == 400


async def test_accept_invitation_conflicts_when_email_registered(client, db_session):
    headers = await landlord_headers(client, "inviter3@example.com")
    # Register the invitee email first via signup.
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "already@example.com",
            "password": "secret123",
            "name": "Already",
            "organization_name": "Their Org",
        },
    )
    token = await create_invite(client, db_session, headers, email="already@example.com")

    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "Dup", "password": "secret123"},
    )
    assert response.status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_invitation_accept.py -v`
Expected: FAIL with 404 (accept route not defined).

- [ ] **Step 3: Implement accept** — update `backend/app/routers/invitations.py`

Add imports for the accept flow (top of the file):

```python
from app.core.security import hash_password
from app.models import Invitation, InvitationStatus, Membership, Role, User
from app.routers.auth import issue_tokens
from app.schemas.auth import TokenPair
from app.schemas.invitation import AcceptInvitationRequest, InvitationCreate, InvitationResponse
```

Append after `revoke_invitation`:

```python
@router.post("/accept", status_code=201, response_model=TokenPair)
async def accept_invitation(
    body: AcceptInvitationRequest, session: AsyncSession = Depends(get_session)
) -> TokenPair:
    """Accept an invitation: create the user + membership and log them in."""
    invite = (
        await session.execute(select(Invitation).where(Invitation.token == body.token))
    ).scalar_one_or_none()
    if (
        invite is None
        or invite.status != InvitationStatus.pending
        or invite.expires_at < datetime.now(UTC)
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")

    existing = (
        await session.execute(select(User).where(User.email == invite.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=invite.email, hashed_password=hash_password(body.password), name=body.name)
    session.add(user)
    await session.flush()
    session.add(
        Membership(user_id=user.id, organization_id=invite.organization_id, role=invite.role)
    )
    invite.status = InvitationStatus.accepted
    await session.commit()
    return issue_tokens(str(user.id))
```

> Note: the `datetime.now(UTC)` comparison requires timezone-aware `expires_at`; the model stores `DateTime(timezone=True)`, so the comparison is valid.

- [ ] **Step 4: Run full suite** — `cd backend && uv run pytest -v` — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add accept-invitation endpoint creating a property_manager`

---

### Task 5: Frontend — invitation API client + Team page

**Files:**
- Create: `frontend/src/lib/invitations.ts`, `frontend/src/app/app/team/page.tsx`
- Modify: `frontend/src/app/app/page.tsx` (add a Team link)

**Interfaces:**
- Consumes: `apiFetch`, `getAccessToken`.
- Produces: `Invitation` TS type; `listInvitations()`, `createInvitation(email)`, `revokeInvitation(id)`; a `/app/team` page listing pending invitations with an invite form and a revoke button.

- [ ] **Step 1: Invitation API module** — `frontend/src/lib/invitations.ts`

```typescript
import { apiFetch } from "@/lib/api";

export interface Invitation {
  id: string;
  email: string;
  role: "property_manager";
  status: "pending" | "accepted" | "revoked";
  expires_at: string;
}

export function listInvitations() {
  return apiFetch<Invitation[]>("/api/v1/invitations");
}

export function createInvitation(email: string) {
  return apiFetch<Invitation>("/api/v1/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role: "property_manager" }),
  });
}

export function revokeInvitation(id: string) {
  return apiFetch<void>(`/api/v1/invitations/${id}`, { method: "DELETE" });
}
```

- [ ] **Step 2: Team page** — `frontend/src/app/app/team/page.tsx`

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { createInvitation, listInvitations, revokeInvitation, type Invitation } from "@/lib/invitations";

export default function TeamPage() {
  const router = useRouter();
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    listInvitations()
      .then(setInvitations)
      .catch(() => setInvitations([]));
  }, [router]);

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createInvitation(email);
      setEmail("");
      setInvitations(await listInvitations());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Invite failed");
    }
  }

  async function onRevoke(id: string) {
    await revokeInvitation(id);
    setInvitations(await listInvitations());
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Team</h1>
      <p className="mb-4 text-sm text-gray-600">
        Invite a property manager to help manage your organization.
      </p>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={onInvite} className="mb-6 flex gap-2">
        <input
          type="email"
          required
          placeholder="Email to invite"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="flex-1 rounded border px-3 py-2"
        />
        <button type="submit" className="rounded bg-blue-600 px-3 py-2 text-white">
          Invite
        </button>
      </form>
      <h2 className="mb-2 font-semibold">Pending invitations</h2>
      <ul className="space-y-2">
        {invitations.map((inv) => (
          <li key={inv.id} className="flex items-center justify-between rounded border p-3">
            <span>
              {inv.email} <span className="text-sm text-gray-500">({inv.role})</span>
            </span>
            <button
              onClick={() => onRevoke(inv.id)}
              className="rounded border border-red-500 px-2 py-1 text-sm text-red-600 transition hover:bg-red-50"
            >
              Revoke
            </button>
          </li>
        ))}
        {invitations.length === 0 && <li className="text-gray-500">No pending invitations.</li>}
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

- [ ] **Step 3: Link from the dashboard** — in `frontend/src/app/app/page.tsx`, add a Team link in the button/link row (next to Properties):

```tsx
<Link href="/app/team" className="rounded border px-3 py-1 text-blue-600">
  Team
</Link>
```

- [ ] **Step 4: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 5: Commit, push, report, wait** — commit message: `Add team page and invitation API client`

---

### Task 6: Frontend — accept-invite page

**Files:**
- Create: `frontend/src/app/accept-invite/page.tsx`

**Interfaces:**
- Consumes: `apiFetch`, `saveTokens`, `TokenPair` shape.
- Produces: a public `/accept-invite` page reading `?token=` (wrapped in `<Suspense>`), collecting name + password, accepting the invitation, saving tokens, and redirecting to `/app`.

- [ ] **Step 1: Accept-invite page** — `frontend/src/app/accept-invite/page.tsx`

```tsx
"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { saveTokens, type TokenPair } from "@/lib/auth";

function AcceptForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const tokens = await apiFetch<TokenPair>("/api/v1/invitations/accept", {
        method: "POST",
        body: JSON.stringify({ token, name, password }),
      });
      saveTokens(tokens);
      router.push("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Accept failed");
    }
  }

  if (!token) {
    return (
      <p data-testid="missing-token" className="text-sm text-red-600">
        This invitation link is invalid or missing its token.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-sm text-gray-600">Set up your account to join the team.</p>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <input
        required
        placeholder="Your name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <input
        type="password"
        required
        minLength={8}
        placeholder="Password (min 8 chars)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
        Accept invitation
      </button>
    </form>
  );
}

export default function AcceptInvitePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm space-y-4 rounded-lg bg-white p-8 shadow">
        <h1 className="text-2xl font-semibold">Accept invitation</h1>
        <Suspense>
          <AcceptForm />
        </Suspense>
        <p className="text-sm text-gray-600">
          <Link href="/login" className="text-blue-600">
            Back to log in
          </Link>
        </p>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 3: Commit, push, report, wait** — commit message: `Add accept-invite page`

---

### Task 7: Team-invitation e2e

**Files:**
- Create: `frontend/e2e/team-invitations.spec.ts`

**Interfaces:**
- Consumes: the full stack from Tasks 1-6, plus the backend running with the invitations migration applied.
- Produces: an e2e covering the landlord-side flow (invite -> appears in the pending list -> revoke) and the accept page's missing-token guard.

**Why the accept flow is not driven end-to-end here:** the API deliberately never returns the raw invite token (it is only sent by email), and Playwright cannot read the backend database or the dev email log. Adding a token-exposing endpoint just for tests would weaken production security. So the full accept-and-become-property_manager path is verified by the backend tests in Task 4 (which read the token from the DB via the `db_session` fixture), and this e2e verifies the landlord UI plus that the accept page renders its error state without a token.

- [ ] **Step 1: Write the e2e** — `frontend/e2e/team-invitations.spec.ts`

```typescript
import { expect, test } from "@playwright/test";

const landlord = `landlord-${Date.now()}@example.com`;

test("landlord invites a team member, sees it pending, and revokes it", async ({ page }) => {
  // Sign up as a landlord.
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Landlord");
  await page.getByPlaceholder("Organization name").fill("Landlord Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  // Go to Team and invite a property manager.
  await page.getByRole("link", { name: "Team" }).click();
  await expect(page).toHaveURL(/\/app\/team/);
  await page.getByPlaceholder("Email to invite").fill("pm@example.com");
  await page.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByText("pm@example.com")).toBeVisible();

  // Revoke it.
  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("pm@example.com")).toHaveCount(0);
});

test("accept-invite page shows an error without a token", async ({ page }) => {
  await page.goto("/accept-invite");
  await expect(page.getByTestId("missing-token")).toBeVisible();
});
```

- [ ] **Step 2: Run locally**

Prereq: Postgres up, backend on 8000 (with `uv run alembic upgrade head` applied for the invitations table), frontend startable by Playwright.
Run: `cd frontend && npm run test:e2e`
Expected: all e2e pass (auth, forgot-password, change-password, properties, property-images, team-invitations).

- [ ] **Step 3: Commit, push, watch all three CI jobs green**

```bash
git add frontend
git commit -m "Add team-invitation e2e"
git push
gh run watch --exit-status
```

- [ ] **Step 4: Report — Milestone 3.1 (team invitations) complete; the property_manager role is now reachable. Wait for approval to plan Milestone 3.2 (leases).**

---

## Milestone Roadmap (next, after this plan ships)

- **Milestone 3.2:** Lease management — `Lease` model (property + tenant reference, rent, payment cycle, bond, notice period, start/end, status). Landlord/property_manager CRUD. Property `status` becomes driven by whether an active lease exists (occupied when an active lease covers today, else vacant); property detail displays the active lease's start/end.
- **Milestone 3.3:** Tenant invitations — reuse the `Invitation` mechanism, tied to a specific lease; the tenant accepts and joins with role `tenant`, linked to their lease; tenant portal shows their own lease only. Lease expiry reminders.
- **Milestone 4:** Rent charges (APScheduler generation), payment recording, dashboard stats + charts.
