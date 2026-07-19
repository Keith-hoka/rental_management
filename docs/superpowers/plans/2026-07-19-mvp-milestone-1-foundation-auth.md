# MVP Milestone 1: Foundation + Auth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Working project skeleton with CI: FastAPI backend on Postgres with email/password auth (JWT, 3-role RBAC, forgot password), Next.js frontend with signup/login, and an e2e smoke test — every task pushed to GitHub with green CI.

**Architecture:** Single FastAPI app (async SQLAlchemy 2.0 + Alembic) with modular routers; Next.js App Router frontend calling the API via a shared fetch client; row-scoped multi-tenancy starts here (every user gets an Organization + Membership at signup).

**Tech Stack:** Python 3.12 / uv / FastAPI / SQLAlchemy 2.0 async / asyncpg / Alembic / PyJWT / pwdlib(argon2) / pytest + httpx — Next.js (TypeScript, Tailwind) — Postgres 16 (Docker Compose) — GitHub Actions — Playwright.

## Global Constraints

- Python package manager is `uv` only: `uv run`, `uv add` — never `python3` / `pip`.
- No emojis in code, logs, or commit messages.
- Short modules, clear names, docstrings over inline comments. No defensive programming.
- TDD: every task writes the failing test first.
- **Per-task user gate:** every task ends with: run full test suite → commit → `git push` → report to the user what was done + test results + CI status → STOP and wait for user approval before the next task.
- Multi-tenancy: every org-owned row carries `organization_id`; queries scope through the authenticated membership (enforced from Milestone 2 onward; models start correct here).
- Work happens on branch `main` (solo project, per-task gates replace PR review).

---

### Task 1: GitHub remote + repo hygiene

**Files:**
- Create: `.gitignore`, `README.md`

**Interfaces:**
- Produces: remote `origin` configured; all commits pushed. `<REPO_URL>` is supplied by the user at execution time (e.g. `https://github.com/Keith-hoka/rental_management_app.git`).

- [ ] **Step 1: Create .gitignore**

```gitignore
# Python
__pycache__/
*.pyc
.venv/
.env

# Node
node_modules/
.next/
frontend/test-results/
frontend/playwright-report/

# OS / editor
.DS_Store
```

- [ ] **Step 2: Create README.md**

```markdown
# Rental Management App

Two-sided rental management SaaS: landlords and property managers run
properties, leases, rent, and maintenance; tenants pay and file requests.

- Backend: FastAPI + PostgreSQL (`backend/`)
- Frontend: Next.js (`frontend/`)
- Docs: `docs/superpowers/specs/` (design), `docs/superpowers/plans/` (plans)

## Development

    docker compose up -d          # Postgres
    cd backend && uv run uvicorn app.main:app --reload
    cd frontend && npm run dev
```

- [ ] **Step 3: Add remote and push**

```bash
git remote add origin <REPO_URL>
git add .gitignore README.md
git commit -m "Add gitignore and README"
git push -u origin main
```

Expected: push succeeds; repo visible on GitHub with docs + README.

- [ ] **Step 4: Report to user and wait for approval**

---

### Task 2: Backend scaffold + health endpoint

**Files:**
- Create: `backend/pyproject.toml` (via uv), `backend/app/__init__.py`, `backend/app/main.py`, `backend/tests/__init__.py`, `backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.main.app` (FastAPI instance) — every later router mounts on it. `GET /health` → `{"status": "ok"}`.

- [ ] **Step 1: Create uv project and add dependencies**

```bash
cd backend  # create dir first: mkdir backend
uv init --name rental-backend --python 3.12
rm main.py  # uv init template file, not needed
uv add fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic pydantic-settings pyjwt "pwdlib[argon2]" "pydantic[email]"
uv add --dev pytest pytest-asyncio httpx ruff
```

- [ ] **Step 2: Configure pytest + ruff in pyproject.toml** (append)

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
```

- [ ] **Step 3: Write the failing test** — `backend/tests/test_health.py`

```python
from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && uv run pytest -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 5: Implement** — `backend/app/main.py` (plus empty `app/__init__.py`, `tests/__init__.py`)

```python
from fastapi import FastAPI

app = FastAPI(title="Rental Management API")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify pass**

Run: `cd backend && uv run pytest -v` and `uv run ruff check .`
Expected: 1 passed; ruff clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend
git commit -m "Scaffold FastAPI backend with health endpoint"
git push
```

- [ ] **Step 8: Report to user and wait for approval**

---

### Task 3: Postgres (Docker Compose) + SQLAlchemy + Alembic

**Files:**
- Create: `docker-compose.yml`, `scripts/init-test-db.sql`, `backend/app/core/__init__.py`, `backend/app/core/config.py`, `backend/app/core/db.py`, `backend/tests/conftest.py`, `backend/tests/test_db.py`
- Create: `backend/alembic.ini`, `backend/alembic/` (via `alembic init`)

**Interfaces:**
- Produces: `settings` (from `app.core.config`), `Base`, `get_session` (FastAPI dependency yielding `AsyncSession`), test fixtures `engine` and `client` in `conftest.py`. Tests run against database `rental_test`.

- [ ] **Step 1: Create docker-compose.yml** (repo root)

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: rental
      POSTGRES_PASSWORD: rental
      POSTGRES_DB: rental
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/init-test-db.sql:/docker-entrypoint-initdb.d/init-test-db.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rental"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
```

`scripts/init-test-db.sql`:

```sql
CREATE DATABASE rental_test;
```

Run: `docker compose up -d` and wait for healthy.

- [ ] **Step 2: Write settings** — `backend/app/core/config.py`

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """App configuration, overridable via environment variables."""

    database_url: str = "postgresql+asyncpg://rental:rental@localhost:5432/rental"
    test_database_url: str = "postgresql+asyncpg://rental:rental@localhost:5432/rental_test"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 30


settings = Settings()
```

- [ ] **Step 3: Write DB module** — `backend/app/core/db.py`

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all models."""


engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session."""
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 4: Write test fixtures** — `backend/tests/conftest.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db import Base, get_session
from app.main import app


@pytest.fixture
async def engine():
    engine = create_async_engine(settings.test_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
async def client(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 5: Write failing test** — `backend/tests/test_db.py`

```python
from sqlalchemy import text


async def test_database_connects(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
```

Run: `cd backend && uv run pytest -v` — expected PASS if Postgres is up (this test validates fixtures + connectivity; failure means compose/env problem).

- [ ] **Step 6: Init Alembic (async template)**

```bash
cd backend
uv run alembic init -t async alembic
```

Edit `backend/alembic/env.py` — replace the config-url and metadata lines:

```python
from app.core.config import settings
from app.core.db import Base

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata
```

- [ ] **Step 7: Run full suite, commit, push**

Run: `cd backend && uv run pytest -v && uv run ruff check .`
Expected: 2 passed.

```bash
git add docker-compose.yml scripts backend
git commit -m "Add Postgres compose, async SQLAlchemy setup, and Alembic"
git push
```

- [ ] **Step 8: Report to user and wait for approval**

---

### Task 4: GitHub Actions CI (backend)

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: CI running ruff + pytest on every push/PR. Frontend job added in Task 10.

- [ ] **Step 1: Write workflow** — `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: rental
          POSTGRES_PASSWORD: rental
          POSTGRES_DB: rental_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U rental"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest -v
```

- [ ] **Step 2: Commit, push, verify CI**

```bash
git add .github
git commit -m "Add GitHub Actions CI for backend"
git push
gh run watch --exit-status
```

Expected: workflow completes green. If it fails, fix before proceeding.

- [ ] **Step 3: Report to user (include CI run link) and wait for approval**

---

### Task 5: Core models — User, Organization, Membership + first migration

**Files:**
- Create: `backend/app/models/__init__.py`, `backend/app/models/user.py`, `backend/app/models/organization.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `User(id, email, hashed_password, name, created_at)`, `Organization(id, name, currency)`, `Membership(id, user_id, organization_id, role)`, `Role` enum (`landlord`, `property_manager`, `tenant`). `app.models` imports all models (needed by Alembic autogenerate and `Base.metadata`).

- [ ] **Step 1: Write failing test** — `backend/tests/test_models.py`

```python
import uuid

from sqlalchemy import select

from app.models import Membership, Organization, Role, User


async def test_create_user_with_org_and_membership(db_session):
    org = Organization(name="Keith Properties", currency="USD")
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", name="Keith")
    db_session.add_all([org, user])
    await db_session.flush()

    membership = Membership(user_id=user.id, organization_id=org.id, role=Role.landlord)
    db_session.add(membership)
    await db_session.commit()

    found = (
        await db_session.execute(select(Membership).where(Membership.user_id == user.id))
    ).scalar_one()
    assert found.role == Role.landlord
    assert found.organization_id == org.id
```

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL with `ImportError` (models do not exist).

- [ ] **Step 2: Implement models** — `backend/app/models/user.py`

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

`backend/app/models/organization.py`:

```python
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Role(str, enum.Enum):
    landlord = "landlord"
    property_manager = "property_manager"
    tenant = "tenant"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), default="USD")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    role: Mapped[Role] = mapped_column(Enum(Role))
```

`backend/app/models/__init__.py`:

```python
from app.models.organization import Membership, Organization, Role
from app.models.user import User

__all__ = ["Membership", "Organization", "Role", "User"]
```

Also add `import app.models  # noqa: F401` after the `target_metadata` imports in `backend/alembic/env.py` so autogenerate sees the tables.

- [ ] **Step 3: Run test to verify pass**

Run: `cd backend && uv run pytest -v`
Expected: all pass.

- [ ] **Step 4: Generate and apply migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "users organizations memberships"
uv run alembic upgrade head
```

Expected: migration file created under `backend/alembic/versions/`; upgrade applies cleanly to the dev database.

- [ ] **Step 5: Commit and push**

```bash
git add backend
git commit -m "Add User, Organization, Membership models and initial migration"
git push
```

- [ ] **Step 6: Report to user and wait for approval**

---

### Task 6: Signup endpoint

**Files:**
- Create: `backend/app/core/security.py`, `backend/app/schemas/__init__.py`, `backend/app/schemas/auth.py`, `backend/app/routers/__init__.py`, `backend/app/routers/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_signup.py`

**Interfaces:**
- Produces: `POST /api/v1/auth/signup` accepting `{email, password, name, organization_name}` → 201 `{access_token, refresh_token, token_type}`; 409 on duplicate email. `hash_password(pw)`, `verify_password(pw, hashed)`, `create_token(subject, token_type, expires_delta)` in `app.core.security`. `TokenPair` schema.

- [ ] **Step 1: Write failing tests** — `backend/tests/test_auth_signup.py`

```python
SIGNUP = {
    "email": "keith@example.com",
    "password": "secret123",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def test_signup_returns_tokens(client):
    response = await client.post("/api/v1/auth/signup", json=SIGNUP)
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_signup_duplicate_email_conflicts(client):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    response = await client.post("/api/v1/auth/signup", json=SIGNUP)
    assert response.status_code == 409
```

Run: `cd backend && uv run pytest tests/test_auth_signup.py -v`
Expected: FAIL with 404 (route not mounted).

- [ ] **Step 2: Implement security helpers** — `backend/app/core/security.py`

```python
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    """Create a signed JWT. token_type is 'access', 'refresh', or 'reset'."""
    payload = {
        "sub": subject,
        "type": token_type,
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on invalid tokens."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
```

- [ ] **Step 3: Implement schemas** — `backend/app/schemas/auth.py`

```python
from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    organization_name: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
```

(`backend/app/schemas/__init__.py` stays empty.)

- [ ] **Step 4: Implement router** — `backend/app/routers/auth.py`

```python
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.security import create_token, hash_password
from app.models import Membership, Organization, Role, User
from app.schemas.auth import SignupRequest, TokenPair

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def issue_tokens(user_id: str) -> TokenPair:
    return TokenPair(
        access_token=create_token(
            user_id, "access", timedelta(minutes=settings.access_token_minutes)
        ),
        refresh_token=create_token(
            user_id, "refresh", timedelta(days=settings.refresh_token_days)
        ),
    )


@router.post("/signup", status_code=201, response_model=TokenPair)
async def signup(body: SignupRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    """Create a landlord account with its organization."""
    existing = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=body.email, hashed_password=hash_password(body.password), name=body.name)
    org = Organization(name=body.organization_name)
    session.add_all([user, org])
    await session.flush()
    session.add(Membership(user_id=user.id, organization_id=org.id, role=Role.landlord))
    await session.commit()
    return issue_tokens(str(user.id))
```

Mount in `backend/app/main.py`:

```python
from fastapi import FastAPI

from app.routers.auth import router as auth_router

app = FastAPI(title="Rental Management API")
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
```

- [ ] **Step 5: Run full suite**

Run: `cd backend && uv run pytest -v && uv run ruff check .`
Expected: all pass.

- [ ] **Step 6: Commit and push**

```bash
git add backend
git commit -m "Add signup endpoint with password hashing and JWT issuance"
git push
```

- [ ] **Step 7: Report to user and wait for approval**

---

### Task 7: Login endpoint

**Files:**
- Modify: `backend/app/routers/auth.py`, `backend/app/schemas/auth.py`
- Test: `backend/tests/test_auth_login.py`

**Interfaces:**
- Produces: `POST /api/v1/auth/login` accepting `{email, password}` → 200 `TokenPair`; 401 on bad credentials.

- [ ] **Step 1: Write failing tests** — `backend/tests/test_auth_login.py`

```python
SIGNUP = {
    "email": "login@example.com",
    "password": "secret123",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def test_login_returns_tokens(client):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    response = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_wrong_password_unauthorized(client):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    response = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": "wrong"}
    )
    assert response.status_code == 401


async def test_login_unknown_email_unauthorized(client):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert response.status_code == 401
```

Run: expected FAIL with 404.

- [ ] **Step 2: Implement** — add to `backend/app/schemas/auth.py`:

```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
```

Add to `backend/app/routers/auth.py` (import `verify_password`, `LoginRequest`):

```python
@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    """Exchange email + password for a token pair."""
    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(
        body.password, user.hashed_password
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return issue_tokens(str(user.id))
```

- [ ] **Step 3: Run full suite** — `uv run pytest -v && uv run ruff check .` — all pass.

- [ ] **Step 4: Commit and push**

```bash
git add backend
git commit -m "Add login endpoint"
git push
```

- [ ] **Step 5: Report to user and wait for approval**

---

### Task 8: Current user, refresh, and RBAC dependencies

**Files:**
- Create: `backend/app/core/deps.py`
- Modify: `backend/app/routers/auth.py`, `backend/app/schemas/auth.py`
- Test: `backend/tests/test_auth_me.py`

**Interfaces:**
- Produces: `get_current_user` dependency (Bearer token → `User`, 401 otherwise); `get_current_membership` (→ `Membership`); `require_roles(*roles)` dependency factory (403 when the membership role is not allowed) — Milestone 2+ routers depend on these. `GET /api/v1/auth/me` → `{id, email, name, role, organization_id}`. `POST /api/v1/auth/refresh` `{refresh_token}` → new `TokenPair`.

- [ ] **Step 1: Write failing tests** — `backend/tests/test_auth_me.py`

```python
SIGNUP = {
    "email": "me@example.com",
    "password": "secret123",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def signup_and_get_tokens(client) -> dict:
    response = await client.post("/api/v1/auth/signup", json=SIGNUP)
    return response.json()


async def test_me_returns_profile(client):
    tokens = await signup_and_get_tokens(client)
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == SIGNUP["email"]
    assert body["role"] == "landlord"
    assert body["organization_id"]


async def test_me_without_token_unauthorized(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_refresh_returns_new_pair(client):
    tokens = await signup_and_get_tokens(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_rejects_access_token(client):
    tokens = await signup_and_get_tokens(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401
```

Run: expected FAIL with 404 / 401 mismatches.

- [ ] **Step 2: Implement dependencies** — `backend/app/core/deps.py`

```python
import uuid

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_token
from app.models import Membership, Role, User

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_current_membership(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Membership:
    membership = (
        await session.execute(select(Membership).where(Membership.user_id == user.id))
    ).scalars().first()
    if membership is None:
        raise HTTPException(status_code=403, detail="No organization membership")
    return membership


def require_roles(*roles: Role):
    """Dependency factory: 403 unless the current membership has one of the roles."""

    async def checker(membership: Membership = Depends(get_current_membership)) -> Membership:
        if membership.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return membership

    return checker
```

- [ ] **Step 3: Implement endpoints** — add to `backend/app/schemas/auth.py`:

```python
import uuid


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    role: str
    organization_id: uuid.UUID
```

Add to `backend/app/routers/auth.py` (import `jwt`, `decode_token`, deps, new schemas):

```python
@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_membership),
) -> MeResponse:
    """Return the authenticated user's profile and role."""
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=membership.role.value,
        organization_id=membership.organization_id,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest) -> TokenPair:
    """Exchange a valid refresh token for a new token pair."""
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return issue_tokens(payload["sub"])
```

- [ ] **Step 4: Run full suite** — all pass, ruff clean.

- [ ] **Step 5: Commit and push**

```bash
git add backend
git commit -m "Add current-user, refresh, and role-based access dependencies"
git push
```

- [ ] **Step 6: Report to user and wait for approval**

---

### Task 9: Forgot / reset password

**Files:**
- Create: `backend/app/core/email.py`
- Modify: `backend/app/routers/auth.py`, `backend/app/schemas/auth.py`
- Test: `backend/tests/test_auth_password_reset.py`

**Interfaces:**
- Produces: `POST /api/v1/auth/forgot-password` `{email}` → always 202 (no account enumeration); sends a reset link containing a 30-minute `reset` JWT via `send_email` (console printer in dev — swapped for a real provider at deploy). `POST /api/v1/auth/reset-password` `{token, new_password}` → 200; 401 on bad/expired token.

- [ ] **Step 1: Write failing tests** — `backend/tests/test_auth_password_reset.py`

```python
from datetime import timedelta

from app.core.security import create_token

SIGNUP = {
    "email": "reset@example.com",
    "password": "oldpassword",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def test_forgot_password_always_accepts(client):
    response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 202


async def test_reset_password_changes_login(client):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    me = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert me.status_code == 200

    token = create_token(SIGNUP["email"], "reset", timedelta(minutes=30))
    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "newpassword1"}
    )
    assert response.status_code == 200

    old = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": "newpassword1"}
    )
    assert new.status_code == 200


async def test_reset_password_rejects_access_token(client):
    tokens = (await client.post("/api/v1/auth/signup", json=SIGNUP)).json()
    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": tokens["access_token"], "new_password": "x" * 10},
    )
    assert response.status_code == 401
```

Run: expected FAIL with 404.

- [ ] **Step 2: Implement email sender** — `backend/app/core/email.py`

```python
import logging

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    """Development email sender: logs instead of sending.

    Replaced by a real provider (e.g. Resend) at deployment.
    """
    logger.info("EMAIL to=%s subject=%s body=%s", to, subject, body)
```

- [ ] **Step 3: Implement endpoints** — add to `backend/app/schemas/auth.py`:

```python
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
```

Add to `backend/app/routers/auth.py`:

```python
@router.post("/forgot-password", status_code=202)
async def forgot_password(
    body: ForgotPasswordRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    """Send a password reset link if the account exists. Always 202."""
    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if user:
        token = create_token(user.email, "reset", timedelta(minutes=30))
        send_email(user.email, "Reset your password", f"Reset token: {token}")
    return {"status": "accepted"}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    """Set a new password given a valid reset token."""
    try:
        payload = decode_token(body.token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "reset":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = (
        await session.execute(select(User).where(User.email == payload["sub"]))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user.hashed_password = hash_password(body.new_password)
    await session.commit()
    return {"status": "ok"}
```

- [ ] **Step 4: Run full suite** — all pass, ruff clean.

- [ ] **Step 5: Commit and push**

```bash
git add backend
git commit -m "Add forgot and reset password endpoints"
git push
```

- [ ] **Step 6: Report to user and wait for approval**

---

### Task 10: Frontend scaffold + frontend CI job

**Files:**
- Create: `frontend/` (via create-next-app)
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: Next.js app (TypeScript, Tailwind, App Router, `src/` dir, `@/*` alias) building cleanly; CI `frontend` job running lint + build on every push.

- [ ] **Step 1: Scaffold** (repo root)

```bash
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --use-npm --no-import-alias --turbopack
```

(Accept defaults on any remaining prompt.)

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run lint && npm run build`
Expected: both succeed.

- [ ] **Step 3: Add CI job** — append to `.github/workflows/ci.yml`:

```yaml
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run build
```

- [ ] **Step 4: Commit, push, verify CI**

```bash
git add frontend .github
git commit -m "Scaffold Next.js frontend and add frontend CI job"
git push
gh run watch --exit-status
```

Expected: both CI jobs green.

- [ ] **Step 5: Report to user and wait for approval**

---

### Task 11: Frontend auth pages (signup / login)

**Files:**
- Create: `frontend/src/lib/api.ts`, `frontend/src/lib/auth.ts`, `frontend/src/app/login/page.tsx`, `frontend/src/app/signup/page.tsx`, `frontend/src/app/app/page.tsx`
- Modify: `frontend/src/app/page.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/auth/signup`, `/login`, `GET /api/v1/auth/me` from Tasks 6-8.
- Produces: `apiFetch(path, options)` client (base URL from `NEXT_PUBLIC_API_URL`, defaults `http://localhost:8000`); token storage in `localStorage` (`saveTokens`, `getAccessToken`, `clearTokens`); `/login`, `/signup` pages; `/app` dashboard placeholder that redirects to `/login` when unauthenticated.

- [ ] **Step 1: API client** — `frontend/src/lib/api.ts`

```typescript
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? "Request failed");
  }
  return response.json();
}
```

- [ ] **Step 2: Token helpers** — `frontend/src/lib/auth.ts`

```typescript
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export function saveTokens(tokens: TokenPair) {
  localStorage.setItem("access_token", tokens.access_token);
  localStorage.setItem("refresh_token", tokens.refresh_token);
}

export function getAccessToken(): string | null {
  return localStorage.getItem("access_token");
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}
```

- [ ] **Step 3: Login page** — `frontend/src/app/login/page.tsx`

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { saveTokens, type TokenPair } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const tokens = await apiFetch<TokenPair>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      saveTokens(tokens);
      router.push("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg bg-white p-8 shadow">
        <h1 className="text-2xl font-semibold">Log in</h1>
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <input
          type="password"
          required
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          Log in
        </button>
        <p className="text-sm text-gray-600">
          No account? <Link href="/signup" className="text-blue-600">Sign up</Link>
        </p>
      </form>
    </main>
  );
}
```

- [ ] **Step 4: Signup page** — `frontend/src/app/signup/page.tsx`

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { saveTokens, type TokenPair } from "@/lib/auth";

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    name: "",
    organization_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);

  function update(field: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [field]: e.target.value });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const tokens = await apiFetch<TokenPair>("/api/v1/auth/signup", {
        method: "POST",
        body: JSON.stringify(form),
      });
      saveTokens(tokens);
      router.push("/app");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Signup failed");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg bg-white p-8 shadow">
        <h1 className="text-2xl font-semibold">Create account</h1>
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        <input required placeholder="Your name" value={form.name} onChange={update("name")}
          className="w-full rounded border px-3 py-2" />
        <input required placeholder="Organization name" value={form.organization_name}
          onChange={update("organization_name")} className="w-full rounded border px-3 py-2" />
        <input type="email" required placeholder="Email" value={form.email}
          onChange={update("email")} className="w-full rounded border px-3 py-2" />
        <input type="password" required minLength={8} placeholder="Password (min 8 chars)"
          value={form.password} onChange={update("password")}
          className="w-full rounded border px-3 py-2" />
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          Sign up
        </button>
        <p className="text-sm text-gray-600">
          Have an account? <Link href="/login" className="text-blue-600">Log in</Link>
        </p>
      </form>
    </main>
  );
}
```

- [ ] **Step 5: Dashboard placeholder** — `frontend/src/app/app/page.tsx`

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";

interface Me {
  email: string;
  name: string;
  role: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    apiFetch<Me>("/api/v1/auth/me")
      .then(setMe)
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
  }, [router]);

  if (!me) return null;

  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <p data-testid="welcome" className="mt-2 text-gray-700">
        Welcome, {me.name} ({me.role})
      </p>
      <button
        onClick={() => {
          clearTokens();
          router.replace("/login");
        }}
        className="mt-4 rounded border px-3 py-1"
      >
        Log out
      </button>
    </main>
  );
}
```

Replace `frontend/src/app/page.tsx` content with a redirect to `/login`:

```tsx
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/login");
}
```

- [ ] **Step 6: Enable CORS on the backend** — modify `backend/app/main.py` (frontend origin):

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 7: Verify manually and via build**

Run: `cd frontend && npm run lint && npm run build` — clean.
Manual check: `docker compose up -d`, `cd backend && uv run uvicorn app.main:app --reload`, `cd frontend && npm run dev`, then sign up at `http://localhost:3000/signup` and confirm redirect to the dashboard.

- [ ] **Step 8: Commit and push**

```bash
git add frontend backend
git commit -m "Add signup and login pages with API client and dashboard placeholder"
git push
```

- [ ] **Step 9: Report to user and wait for approval**

---

### Task 12: Playwright e2e smoke test + e2e CI job

**Files:**
- Create: `frontend/playwright.config.ts`, `frontend/e2e/auth.spec.ts`
- Modify: `frontend/package.json` (add `@playwright/test` dev dep + `test:e2e` script), `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: full stack from Tasks 2-11.
- Produces: `npm run test:e2e` covering signup → dashboard → logout → login; CI `e2e` job running it against real Postgres + uvicorn + Next.js.

- [ ] **Step 1: Install Playwright**

```bash
cd frontend
npm install --save-dev @playwright/test
npx playwright install chromium
```

Add to `frontend/package.json` scripts: `"test:e2e": "playwright test"`.

- [ ] **Step 2: Config** — `frontend/playwright.config.ts`

```typescript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:3000" },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
```

(The backend is started separately — locally via `uv run uvicorn`, in CI as a background step.)

- [ ] **Step 3: Write the e2e test** — `frontend/e2e/auth.spec.ts`

```typescript
import { expect, test } from "@playwright/test";

const email = `e2e-${Date.now()}@example.com`;
const password = "secret123";

test("signup, logout, login round trip", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("E2E User");
  await page.getByPlaceholder("Organization name").fill("E2E Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill(password);
  await page.getByRole("button", { name: "Sign up" }).click();

  await expect(page.getByTestId("welcome")).toContainText("E2E User (landlord)");

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByTestId("welcome")).toContainText("E2E User (landlord)");
});
```

- [ ] **Step 4: Run locally**

Prereq: `docker compose up -d`; `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app` running.
Run: `cd frontend && npm run test:e2e`
Expected: 1 passed.

- [ ] **Step 5: Add e2e CI job** — append to `.github/workflows/ci.yml`:

```yaml
  e2e:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: rental
          POSTGRES_PASSWORD: rental
          POSTGRES_DB: rental
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U rental"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Start backend
        working-directory: backend
        run: |
          uv sync
          uv run alembic upgrade head
          uv run uvicorn app.main:app --port 8000 &
      - name: Install frontend
        working-directory: frontend
        run: |
          npm ci
          npx playwright install --with-deps chromium
      - name: Run e2e tests
        working-directory: frontend
        run: npm run test:e2e
```

- [ ] **Step 6: Commit, push, verify all three CI jobs green**

```bash
git add frontend .github
git commit -m "Add Playwright e2e smoke test for auth flow"
git push
gh run watch --exit-status
```

- [ ] **Step 7: Report to user — Milestone 1 complete. Wait for approval to plan Milestone 2**

---

## Milestone Roadmap (plans written later, each after the previous milestone ships)

- **Milestone 2:** Property CRUD (search/filter, images), tenant profiles + invitations, lease management. First use of `require_roles` + org scoping on every query.
- **Milestone 3:** RentCharge generation (APScheduler), payment recording, overdue/upcoming views, dashboard stats + charts.
- **Milestone 4:** Maintenance requests (photos, status flow), notifications (in-app + email), lease expiry reminders, Google OAuth (requires user-supplied Google Cloud credentials).
