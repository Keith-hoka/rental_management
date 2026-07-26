# Compliance Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit leases against NSW tenancy law via lease-compliance-service, show findings on the lease detail page, enrol audited leases in change monitoring, and turn detected changes into notifications.

**Architecture:** One HTTP boundary module (`app/services/compliance.py`) carries the client, the chain mapper, and the queue/poll service functions. Create/renew enqueue an outbox row in the lease's transaction; an APScheduler interval job drains it; a daily job polls `audit-changes` into `lease_audits` + notifications. The compliance service gains one list endpoint first (cross-repo Task 1).

**Tech Stack:** Existing app stack (FastAPI, async SQLAlchemy, Alembic, APScheduler, httpx; Next.js 16 + Playwright). No new dependencies.

## Global Constraints

- Two repos: Task 1 runs in `/Users/keithho/LLMProjects/lease-compliance-service`; Tasks 2-9 in `/Users/keithho/LLMProjects/rental_management_app` (backend work under `backend/`).
- Every task ends with its own repo's verification: service repo `uv run pytest -q` + ruff sequence (`format` -> `check --fix` -> `check` -> `format --check`); backend `cd backend && uv run pytest -q` + same ruff sequence; frontend `npm run lint`. Then commit -> push -> CI green -> report -> WAIT for approval.
- `uv` only, never `python3`/`pip`. No emojis anywhere. Docstrings over comments.
- Feature flag: `compliance_api_url` and `compliance_api_key` both non-empty means enabled; empty (default) disables button/section, enqueue and jobs.
- App tests never call the real compliance service: fake `create_audit`/`get_audit`/`list_changes` at the function boundary with monkeypatch.
- Findings copy always includes "General information, not legal advice."
- `client_ref` is always `str(lease.id)`.

## File Structure

| Path | Responsibility |
|---|---|
| service repo `app/routers/audits.py` + `tests/test_api.py` | Task 1: list endpoint |
| `backend/app/core/config.py` | 5 new settings |
| `backend/app/services/compliance.py` | client, mapper, enqueue, drain, poll, cursor |
| `backend/app/models/compliance.py` | `LeaseAudit`, `ComplianceAuditQueue`, `ComplianceSyncState` |
| `backend/app/models/__init__.py` | exports |
| `backend/alembic/versions/<gen>_add_compliance_tables.py` | migration |
| `backend/app/schemas/compliance.py` | `ComplianceAuditInfo`, `ComplianceAuditState` |
| `backend/app/routers/compliance.py` | POST/GET `/api/v1/leases/{id}/compliance-audit` |
| `backend/app/routers/leases.py` | enqueue in create/renew |
| `backend/app/core/scheduler.py` | drain + poll jobs |
| `backend/app/compliance_backfill.py` | backfill CLI |
| `backend/app/main.py` | mount router |
| `backend/tests/test_compliance_mapper.py`, `test_compliance_endpoints.py`, `test_compliance_jobs.py` | backend tests |
| `frontend/src/lib/compliance.ts`, `frontend/src/app/app/leases/ComplianceSection.tsx`, `[leaseId]/page.tsx` | UI |
| `frontend/e2e/compliance.spec.ts` | env-gated e2e |

---

### Task 1: Service list endpoint (repo: lease-compliance-service)

**Files:** Modify `app/routers/audits.py`, `tests/test_api.py`.

**Interfaces:** Produces `GET /v1/audits?client_ref=<required>&limit=20` — tenant-scoped, `created_at` desc, `list[AuditInfo]`.

- [ ] **Step 1: Failing tests** — append to `tests/test_api.py`:

```python
async def test_list_audits_by_client_ref(client, seeded):
    for _ in range(2):
        await client.post(
            "/v1/audits", json=dict(AUDIT_BODY, client_ref="lease-9"), headers=KEY
        )
    await client.post("/v1/audits", json=AUDIT_BODY, headers=KEY)

    listed = await client.get("/v1/audits", params={"client_ref": "lease-9"}, headers=KEY)
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 2
    assert all(item["client_ref"] == "lease-9" for item in body)
    assert body[0]["created_at"] >= body[1]["created_at"]


async def test_list_audits_is_tenant_scoped(client, seeded):
    await client.post("/v1/audits", json=dict(AUDIT_BODY, client_ref="lease-9"), headers=KEY)
    other = await client.get("/v1/audits", params={"client_ref": "lease-9"}, headers=OTHER)
    assert other.json() == []


async def test_list_audits_requires_client_ref(client):
    assert (await client.get("/v1/audits", headers=KEY)).status_code == 422
```

- [ ] **Step 2: Run -> fail.** `uv run pytest tests/test_api.py -q` — the two list tests 404/405.

- [ ] **Step 3: Implement** — append to `app/routers/audits.py` (add `select` to the sqlalchemy imports):

```python
@router.get("/audits", response_model=list[AuditInfo])
async def list_audits(
    client_ref: str, client_id: ClientDep, session: SessionDep, limit: int = 20
) -> list[AuditInfo]:
    query = (
        select(Audit)
        .where(Audit.client_id == client_id, Audit.client_ref == client_ref)
        .order_by(Audit.created_at.desc(), Audit.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(query)).scalars().all()
    return [
        AuditInfo(
            id=row.id,
            jurisdiction=row.jurisdiction,
            as_at=row.as_at,
            engine_version=row.engine_version,
            client_ref=row.client_ref,
            findings=row.findings,
            created_at=row.created_at,
        )
        for row in rows
    ]
```

Route ordering note: FastAPI matches `/audits` before `/audits/{audit_id}` regardless of declaration order because the path shapes differ; still declare `list_audits` after `get_audit` to keep the file grouped by verb.

- [ ] **Step 4: Run -> pass; full suite; ruff; commit** (`Add the audit list endpoint`); push; CI green. Report and WAIT.

---

### Task 2: Settings and the compliance client (repo: rental_management_app from here on)

**Files:** Modify `backend/app/core/config.py`; create `backend/app/services/compliance.py`, `backend/tests/test_compliance_mapper.py` (client tests only this task).

**Interfaces:** Produces `enabled() -> bool`; `async create_audit(payload: dict) -> dict` (POST `{url}/v1/audits`, `X-API-Key`, raises `httpx.HTTPStatusError` on non-201); `async get_audit(audit_id: str) -> dict`; `async list_changes(since: str | None, limit: int = 100) -> list[dict]`. Later tasks monkeypatch these three names.

- [ ] **Step 1: Settings** — append to the `Settings` class in `backend/app/core/config.py`:

```python
    # Lease compliance service: both values set enables audits, monitoring
    # enrolment and the queue/poll jobs; empty disables the whole feature.
    compliance_api_url: str = ""
    compliance_api_key: str = ""
    compliance_queue_interval_minutes: int = 2
    compliance_poll_hour: int = 7
    compliance_queue_max_attempts: int = 10
```

- [ ] **Step 2: Failing tests** — `backend/tests/test_compliance_mapper.py`:

```python
import pytest

from app.core.config import settings
from app.services.compliance import enabled


def test_disabled_by_default():
    assert enabled() is False


def test_enabled_needs_both_values(monkeypatch):
    monkeypatch.setattr(settings, "compliance_api_url", "http://localhost:8100")
    assert enabled() is False
    monkeypatch.setattr(settings, "compliance_api_key", "dev-key")
    assert enabled() is True
```

- [ ] **Step 3: Run -> fail** (ModuleNotFoundError). `cd backend && uv run pytest tests/test_compliance_mapper.py -q`

- [ ] **Step 4: Implement** — `backend/app/services/compliance.py`:

```python
"""Client, mapper and jobs for the lease-compliance-service integration."""

import httpx

from app.core.config import settings

TIMEOUT = 10.0


def enabled() -> bool:
    """True when the compliance integration is configured."""
    return bool(settings.compliance_api_url and settings.compliance_api_key)


def _headers() -> dict:
    return {"X-API-Key": settings.compliance_api_key}


async def create_audit(payload: dict) -> dict:
    """POST an audit to the compliance service and return its body."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{settings.compliance_api_url}/v1/audits", json=payload, headers=_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_audit(audit_id: str) -> dict:
    """Fetch one audit by the compliance service's audit id."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{settings.compliance_api_url}/v1/audits/{audit_id}", headers=_headers()
        )
        response.raise_for_status()
        return response.json()


async def list_changes(since: str | None, limit: int = 100) -> list[dict]:
    """One page of the tenant's audit-changes feed, ascending."""
    params: dict = {"limit": limit}
    if since is not None:
        params["since"] = since
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{settings.compliance_api_url}/v1/audit-changes",
            params=params,
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 5: Run -> pass; backend full suite; ruff; commit** (`Add compliance settings and client`); push; CI green. Report and WAIT.

---

### Task 3: Compliance tables

**Files:** Create `backend/app/models/compliance.py`, migration; modify `backend/app/models/__init__.py`; test in `backend/tests/test_compliance_mapper.py`.

**Interfaces:** Produces `LeaseAudit(id, lease_id, organization_id, audit_id unique, as_at, findings, created_at)`, `ComplianceAuditQueue(id, lease_id unique, attempts, last_error, created_at)`, `ComplianceSyncState(key pk, value)` exported from `app.models`.

- [ ] **Step 1: Failing test** — append to `backend/tests/test_compliance_mapper.py`:

```python
import uuid as uuid_mod
from datetime import date

from sqlalchemy import select

from app.models import ComplianceAuditQueue, ComplianceSyncState, Lease, LeaseAudit


async def test_compliance_tables_round_trip(db_session):
    from tests.test_lease_model import make_lease_row

    lease = await make_lease_row(db_session)
    audit = LeaseAudit(
        lease_id=lease.id,
        organization_id=lease.organization_id,
        audit_id=uuid_mod.uuid4(),
        as_at=date(2026, 7, 27),
        findings=[{"rule_id": "nsw.bond_max_4_weeks", "verdict": "green"}],
    )
    queue_row = ComplianceAuditQueue(lease_id=lease.id)
    db_session.add_all([audit, queue_row, ComplianceSyncState(key="cursor", value="x")])
    await db_session.commit()
    stored = (await db_session.execute(select(LeaseAudit))).scalar_one()
    assert stored.findings[0]["verdict"] == "green"
    assert (await db_session.execute(select(ComplianceAuditQueue))).scalar_one().attempts == 0
```

If `tests/test_lease_model.py` has no `make_lease_row` helper, add one there (org + property + lease rows via the models, returning the lease); reuse its existing organization/property construction style.

- [ ] **Step 2: Run -> fail** (ImportError).

- [ ] **Step 3: Implement** — `backend/app/models/compliance.py`:

```python
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LeaseAudit(Base):
    __tablename__ = "lease_audits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lease_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leases.id"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    audit_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    as_at: Mapped[date] = mapped_column(Date)
    findings: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComplianceAuditQueue(Base):
    __tablename__ = "compliance_audit_queue"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lease_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leases.id"), unique=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComplianceSyncState(Base):
    __tablename__ = "compliance_sync_state"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(100))
```

Add the three names to `backend/app/models/__init__.py` imports and `__all__`.

- [ ] **Step 4: Migration** — `cd backend && uv run alembic revision -m "add compliance tables"`; write `upgrade` creating the three tables exactly as above (`sa.Uuid()`, unique constraints on `lease_audits.audit_id` and `compliance_audit_queue.lease_id`, indexes on `lease_audits.lease_id`/`organization_id`), `downgrade` dropping them in reverse. Verify `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`.

- [ ] **Step 5: Run -> pass; backend full suite; ruff; commit** (`Add the compliance tables`); push; CI green. Report and WAIT.

---

### Task 4: Chain mapper (this milestone's eval)

**Files:** Modify `backend/app/services/compliance.py`, `backend/tests/test_compliance_mapper.py`.

**Interfaces:** Produces `async load_chain(session, lease) -> list[Lease]` (oldest -> newest, ending at the given lease) and `chain_to_audit_payload(chain: list[Lease]) -> dict` (pure). Payload: `{"jurisdiction": "NSW", "client_ref": str(newest.id), "lease": {...}}` with `start_date` from the chain root, `end_date`/`rent_amount`/`rent_frequency`/`bond_amount` from the newest, `rent_increases` only when synthesis is non-empty.

- [ ] **Step 1: Failing tests** — append (build leases in memory; no DB needed for the pure function):

```python
from datetime import date as date_mod
from decimal import Decimal

from app.models import Lease, LeaseFrequency
from app.services.compliance import chain_to_audit_payload


def _lease(start, end, rent, bond=None, prev=None):
    lease = Lease(
        id=uuid_mod.uuid4(),
        organization_id=uuid_mod.uuid4(),
        property_id=uuid_mod.uuid4(),
        tenant_name="T",
        tenant_email="t@example.com",
        co_tenants=[],
        rent_amount=Decimal(rent),
        rent_frequency=LeaseFrequency.weekly,
        bond_amount=Decimal(bond) if bond is not None else None,
        start_date=date_mod.fromisoformat(start),
        end_date=date_mod.fromisoformat(end),
        renewed_from_id=prev.id if prev is not None else None,
    )
    return lease


def test_payload_single_lease_no_increases():
    lease = _lease("2026-01-01", "2026-12-31", 600, bond=2400)
    payload = chain_to_audit_payload([lease])
    assert payload["jurisdiction"] == "NSW"
    assert payload["client_ref"] == str(lease.id)
    body = payload["lease"]
    assert body["start_date"] == "2026-01-01"
    assert body["end_date"] == "2026-12-31"
    assert body["rent_amount"] == "600"
    assert body["rent_frequency"] == "weekly"
    assert body["bond_amount"] == "2400"
    assert "rent_increases" not in body


def test_payload_chain_synthesises_increases_from_root():
    first = _lease("2024-01-01", "2024-12-31", 600)
    second = _lease("2025-01-01", "2025-12-31", 650, prev=first)
    third = _lease("2026-01-01", "2026-12-31", 650, prev=second)
    payload = chain_to_audit_payload([first, second, third])
    body = payload["lease"]
    assert payload["client_ref"] == str(third.id)
    assert body["start_date"] == "2024-01-01"
    assert body["end_date"] == "2026-12-31"
    assert body["rent_increases"] == [
        {"effective_on": "2025-01-01", "new_amount": "650"}
    ]


def test_payload_decrease_emits_nothing():
    first = _lease("2024-01-01", "2024-12-31", 700)
    second = _lease("2025-01-01", "2025-12-31", 650, prev=first)
    payload = chain_to_audit_payload([first, second])
    assert "rent_increases" not in payload["lease"]


def test_payload_omits_missing_bond():
    lease = _lease("2026-01-01", "2026-12-31", 600)
    assert "bond_amount" not in chain_to_audit_payload([lease])["lease"]
```

- [ ] **Step 2: Run -> fail.**

- [ ] **Step 3: Implement** — append to `backend/app/services/compliance.py` (new imports at top: `from itertools import pairwise`, `from sqlalchemy import select`, `from sqlalchemy.ext.asyncio import AsyncSession`, `from app.models import Lease`):

```python
async def load_chain(session: AsyncSession, lease: Lease) -> list[Lease]:
    """The renewal chain ending at this lease, oldest first."""
    chain = [lease]
    current = lease
    while current.renewed_from_id is not None:
        current = (
            await session.execute(select(Lease).where(Lease.id == current.renewed_from_id))
        ).scalar_one()
        chain.append(current)
    return list(reversed(chain))


def chain_to_audit_payload(chain: list[Lease]) -> dict:
    """The compliance audit request for a renewal chain.

    start_date is the tenancy start (chain root): the 12-month first-increase
    rule measures from the tenancy, and successive agreements are continuous.
    An empty synthesis omits rent_increases entirely (None, not []): in-place
    rent edits are invisible here, so an empty list would falsely assert that
    the rent never increased.
    """
    newest = chain[-1]
    lease_body: dict = {
        "rent_amount": str(newest.rent_amount),
        "rent_frequency": newest.rent_frequency.value,
        "start_date": chain[0].start_date.isoformat(),
        "end_date": newest.end_date.isoformat(),
    }
    if newest.bond_amount is not None:
        lease_body["bond_amount"] = str(newest.bond_amount)
    increases = [
        {"effective_on": later.start_date.isoformat(), "new_amount": str(later.rent_amount)}
        for earlier, later in pairwise(chain)
        if later.rent_amount > earlier.rent_amount
    ]
    if increases:
        lease_body["rent_increases"] = increases
    return {"jurisdiction": "NSW", "client_ref": str(newest.id), "lease": lease_body}
```

- [ ] **Step 4: Run -> pass; backend full suite; ruff; commit** (`Add the compliance chain mapper`); push; CI green. Report and WAIT.

---

### Task 5: Audit endpoints and enqueue on create/renew

**Files:** Create `backend/app/schemas/compliance.py`, `backend/app/routers/compliance.py`, `backend/tests/test_compliance_endpoints.py`; modify `backend/app/services/compliance.py`, `backend/app/routers/leases.py`, `backend/app/main.py`.

**Interfaces:** Produces `async run_lease_audit(session, lease) -> LeaseAudit` (chain -> payload -> `create_audit` -> stored row; caller commits) and `async enqueue_audit(session, lease_id) -> None` (INSERT, duplicate-safe); routes `POST`/`GET /api/v1/leases/{lease_id}/compliance-audit`. GET returns `ComplianceAuditState {enabled: bool, audit: ComplianceAuditInfo | None}`; POST returns `ComplianceAuditInfo`, 503 when disabled, 502 when the service call fails.

- [ ] **Step 1: Failing tests** — `backend/tests/test_compliance_endpoints.py`:

```python
import uuid

import pytest

from app.core.config import settings
from app.models import ComplianceAuditQueue, LeaseAudit
from sqlalchemy import select

from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers

FAKE_AUDIT = {
    "id": str(uuid.uuid4()),
    "jurisdiction": "NSW",
    "as_at": "2026-07-27",
    "engine_version": "1.0.0",
    "client_ref": None,
    "findings": [
        {
            "rule_id": "nsw.bond_max_4_weeks",
            "verdict": "green",
            "summary": "Bond ok.",
            "evidence": {},
            "citations": [],
            "skip_reason": None,
        }
    ],
    "created_at": "2026-07-27T00:00:00Z",
}


@pytest.fixture
def compliance_on(monkeypatch):
    monkeypatch.setattr(settings, "compliance_api_url", "http://localhost:8100")
    monkeypatch.setattr(settings, "compliance_api_key", "dev-key")


@pytest.fixture
def fake_create(monkeypatch):
    async def _fake(payload):
        body = dict(FAKE_AUDIT)
        body["client_ref"] = payload["client_ref"]
        return body

    monkeypatch.setattr("app.services.compliance.create_audit", _fake)


async def _make_lease(client, headers):
    property_id = await make_property(client, headers, "1 Compliance St")
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    return created


async def test_post_runs_audit_and_stores(client, db_session, compliance_on, fake_create):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["findings"][0]["verdict"] == "green"
    stored = (await db_session.execute(select(LeaseAudit))).scalar_one()
    assert str(stored.lease_id) == lease["id"]


async def test_post_disabled_is_503(client):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers
    )
    assert response.status_code == 503


async def test_get_returns_enabled_flag_and_latest(client, compliance_on, fake_create):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    empty = await client.get(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    assert empty.json() == {"enabled": True, "audit": None}
    await client.post(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    state = (
        await client.get(f"/api/v1/leases/{lease['id']}/compliance-audit", headers=headers)
    ).json()
    assert state["audit"]["findings"][0]["rule_id"] == "nsw.bond_max_4_weeks"


async def test_create_and_renew_enqueue_when_enabled(client, db_session, compliance_on):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    queued = (await db_session.execute(select(ComplianceAuditQueue))).scalars().all()
    assert [str(q.lease_id) for q in queued] == [lease["id"]]
    renewed = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew", json={"end_date": "2027-12-31"}, headers=headers
        )
    ).json()
    queued = (await db_session.execute(select(ComplianceAuditQueue))).scalars().all()
    assert {str(q.lease_id) for q in queued} == {lease["id"], renewed["id"]}


async def test_create_does_not_enqueue_when_disabled(client, db_session):
    headers = await landlord_headers(client)
    await _make_lease(client, headers)
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None


async def test_cross_org_lease_is_404(client, compliance_on, fake_create):
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    outsider = await landlord_headers(client, email="other-org@example.com")
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/compliance-audit", headers=outsider
    )
    assert response.status_code == 404
```

(`landlord_headers` accepts an email override in this repo's test helpers; if its signature differs, follow its actual parameters to create a second organization's landlord.)
```

- [ ] **Step 2: Run -> fail** (404 route; enqueue tests find no rows).

- [ ] **Step 3: Implement service pieces** — append to `backend/app/services/compliance.py` (imports: `uuid`, `from sqlalchemy.dialects.postgresql import insert as pg_insert`, `from app.models import ComplianceAuditQueue, LeaseAudit`):

```python
async def run_lease_audit(session: AsyncSession, lease: Lease) -> LeaseAudit:
    """Audit one lease now and store the result. The caller commits."""
    chain = await load_chain(session, lease)
    body = await create_audit(chain_to_audit_payload(chain))
    audit = LeaseAudit(
        lease_id=lease.id,
        organization_id=lease.organization_id,
        audit_id=uuid.UUID(body["id"]),
        as_at=date.fromisoformat(body["as_at"]),
        findings=body["findings"],
    )
    session.add(audit)
    await session.flush()
    return audit


async def enqueue_audit(session: AsyncSession, lease_id) -> None:
    """Queue a lease for auditing; a pending duplicate is a no-op."""
    statement = (
        pg_insert(ComplianceAuditQueue)
        .values(lease_id=lease_id)
        .on_conflict_do_nothing(index_elements=["lease_id"])
    )
    await session.execute(statement)
```

(`from datetime import date` goes at the top.)

- [ ] **Step 4: Schemas and router** — `backend/app/schemas/compliance.py`:

```python
import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ComplianceAuditInfo(BaseModel):
    id: uuid.UUID
    audit_id: uuid.UUID
    as_at: date
    findings: list
    created_at: datetime


class ComplianceAuditState(BaseModel):
    enabled: bool
    audit: ComplianceAuditInfo | None = None
```

`backend/app/routers/compliance.py`:

```python
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import LeaseAudit, Membership, Role
from app.routers.leases import get_owned_lease
from app.schemas.compliance import ComplianceAuditInfo, ComplianceAuditState
from app.services import compliance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["compliance"])

manager = require_roles(Role.landlord, Role.property_manager)


def _info(audit: LeaseAudit) -> ComplianceAuditInfo:
    return ComplianceAuditInfo(
        id=audit.id,
        audit_id=audit.audit_id,
        as_at=audit.as_at,
        findings=audit.findings,
        created_at=audit.created_at,
    )


@router.post("/leases/{lease_id}/compliance-audit", response_model=ComplianceAuditInfo)
async def run_audit_now(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> ComplianceAuditInfo:
    """Audit the lease synchronously and store the result."""
    if not compliance.enabled():
        raise HTTPException(status_code=503, detail="Compliance integration is not configured")
    lease = await get_owned_lease(lease_id, membership, session)
    try:
        audit = await compliance.run_lease_audit(session, lease)
    except httpx.HTTPError as exc:
        logger.warning("Compliance audit failed for lease %s: %s", lease_id, exc)
        raise HTTPException(status_code=502, detail="Compliance service unavailable") from exc
    await session.commit()
    return _info(audit)


@router.get("/leases/{lease_id}/compliance-audit", response_model=ComplianceAuditState)
async def latest_audit(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> ComplianceAuditState:
    """The newest stored audit for the lease, plus the feature flag."""
    lease = await get_owned_lease(lease_id, membership, session)
    row = (
        await session.execute(
            select(LeaseAudit)
            .where(LeaseAudit.lease_id == lease.id)
            .order_by(LeaseAudit.created_at.desc(), LeaseAudit.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return ComplianceAuditState(
        enabled=compliance.enabled(), audit=_info(row) if row is not None else None
    )
```

Mount in `backend/app/main.py` next to the other routers: `from app.routers.compliance import router as compliance_router` + `app.include_router(compliance_router)`.

- [ ] **Step 5: Enqueue in create/renew** — in `backend/app/routers/leases.py` add `from app.services.compliance import enabled as compliance_enabled, enqueue_audit`. In `create_lease`, replace `session.add(lease)` / `await session.commit()` with:

```python
    session.add(lease)
    await session.flush()
    if compliance_enabled():
        await enqueue_audit(session, lease.id)
    await session.commit()
```

In `renew_lease`, immediately before `await session.commit()`:

```python
    if compliance_enabled():
        await enqueue_audit(session, renewal.id)
```

- [ ] **Step 6: Run -> pass; backend full suite; ruff; commit** (`Add compliance audit endpoints and enqueue`); push; CI green. Report and WAIT.

---

### Task 6: Queue drain job

**Files:** Modify `backend/app/services/compliance.py`, `backend/app/core/scheduler.py`; create `backend/tests/test_compliance_jobs.py`.

**Interfaces:** Produces `async drain_audit_queue(session) -> int` (audits performed; commits per row) registered as an interval job when `enabled()`.

- [ ] **Step 1: Failing tests** — `backend/tests/test_compliance_jobs.py`:

```python
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import ComplianceAuditQueue, LeaseAudit
from app.services.compliance import drain_audit_queue, enqueue_audit
from tests.test_compliance_endpoints import FAKE_AUDIT, _make_lease, compliance_on, fake_create  # noqa: F401
from tests.test_properties_crud import landlord_headers


async def test_drain_success_stores_and_deletes(client, db_session, compliance_on, fake_create):  # noqa: F811
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    count = await drain_audit_queue(db_session)
    assert count == 1
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None
    stored = (await db_session.execute(select(LeaseAudit))).scalar_one()
    assert str(stored.lease_id) == lease["id"]


async def test_drain_failure_keeps_row_with_attempts(client, db_session, compliance_on, monkeypatch):  # noqa: F811
    async def _boom(payload):
        raise RuntimeError("service down")

    monkeypatch.setattr("app.services.compliance.create_audit", _boom)
    headers = await landlord_headers(client)
    await _make_lease(client, headers)
    count = await drain_audit_queue(db_session)
    assert count == 0
    row = (await db_session.execute(select(ComplianceAuditQueue))).scalar_one()
    assert row.attempts == 1
    assert "service down" in row.last_error


async def test_drain_skips_rows_at_max_attempts(client, db_session, compliance_on, fake_create):  # noqa: F811
    headers = await landlord_headers(client)
    await _make_lease(client, headers)
    row = (await db_session.execute(select(ComplianceAuditQueue))).scalar_one()
    row.attempts = settings.compliance_queue_max_attempts
    await db_session.commit()
    assert await drain_audit_queue(db_session) == 0
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is not None
```

- [ ] **Step 2: Run -> fail** (ImportError: `drain_audit_queue`).

- [ ] **Step 3: Implement** — append to `backend/app/services/compliance.py` (imports: `import logging`; `logger = logging.getLogger(__name__)` at module level):

```python
async def drain_audit_queue(session: AsyncSession) -> int:
    """Audit every queued lease; delete rows on success, count attempts on failure."""
    rows = (
        (
            await session.execute(
                select(ComplianceAuditQueue)
                .where(ComplianceAuditQueue.attempts < settings.compliance_queue_max_attempts)
                .order_by(ComplianceAuditQueue.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    done = 0
    for row in rows:
        lease = (
            await session.execute(select(Lease).where(Lease.id == row.lease_id))
        ).scalar_one()
        try:
            await run_lease_audit(session, lease)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the drain
            row.attempts += 1
            row.last_error = str(exc)
            await session.commit()
            continue
        await session.delete(row)
        await session.commit()
        done += 1
    return done
```

- [ ] **Step 4: Scheduler** — in `backend/app/core/scheduler.py` add imports `from apscheduler.triggers.interval import IntervalTrigger`, `from app.services.compliance import drain_audit_queue, enabled as compliance_enabled`, the job function, and registration inside `start_scheduler()` guarded by the flag:

```python
async def _compliance_drain_job() -> None:
    """Open a session and drain the compliance audit queue."""
    async with SessionLocal() as session:
        count = await drain_audit_queue(session)
    if count:
        logger.info("compliance queue: audited %s", count)
```

```python
    if compliance_enabled():
        scheduler.add_job(
            _compliance_drain_job,
            IntervalTrigger(minutes=settings.compliance_queue_interval_minutes),
            id="compliance_drain",
            replace_existing=True,
        )
```

- [ ] **Step 5: Run -> pass; backend full suite; ruff; commit** (`Add the compliance queue drain job`); push; CI green. Report and WAIT.

---

### Task 7: Change poll job and notifications

**Files:** Modify `backend/app/services/compliance.py`, `backend/app/core/scheduler.py`, `backend/tests/test_compliance_jobs.py`.

**Interfaces:** Produces `async poll_audit_changes(session) -> int` (changes applied; commits) registered as a daily cron job when `enabled()`. Cursor key `audit_changes_cursor` in `ComplianceSyncState`.

- [ ] **Step 1: Failing tests** — append to `backend/tests/test_compliance_jobs.py`:

```python
from datetime import UTC, datetime, timedelta

from app.models import ComplianceSyncState, Notification
from app.services.compliance import poll_audit_changes


def _change(client_ref, new_audit_id, created_at):
    return {
        "id": str(uuid.uuid4()),
        "client_ref": client_ref,
        "old_audit_id": str(uuid.uuid4()),
        "new_audit_id": new_audit_id,
        "changes": {"nsw.bond_max_4_weeks": {"from": "green", "to": "red"}},
        "created_at": created_at,
    }


@pytest.fixture
def fake_feed(monkeypatch):
    """One change for the given client_ref; get_audit returns FAKE_AUDIT with that id."""

    def install(client_ref, new_audit_id=None):
        new_audit_id = new_audit_id or str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        calls = {"count": 0}

        async def _changes(since, limit=100):
            calls["count"] += 1
            if calls["count"] > 1:
                return []
            return [_change(client_ref, new_audit_id, now)]

        async def _get(audit_id):
            body = dict(FAKE_AUDIT)
            body["id"] = audit_id
            body["client_ref"] = client_ref
            return body

        monkeypatch.setattr("app.services.compliance.list_changes", _changes)
        monkeypatch.setattr("app.services.compliance.get_audit", _get)
        return new_audit_id

    return install


async def test_poll_stores_and_notifies_active_lease(client, db_session, compliance_on, fake_feed):  # noqa: F811
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    new_audit_id = fake_feed(lease["id"])
    count = await poll_audit_changes(db_session)
    assert count == 1
    stored = (await db_session.execute(select(LeaseAudit))).scalar_one()
    assert str(stored.audit_id) == new_audit_id
    notes = (await db_session.execute(select(Notification))).scalars().all()
    assert any(n.category == "compliance" for n in notes)
    cursor = (
        await db_session.execute(
            select(ComplianceSyncState).where(ComplianceSyncState.key == "audit_changes_cursor")
        )
    ).scalar_one()
    assert cursor.value


async def test_poll_skips_superseded_and_unknown(client, db_session, compliance_on, fake_feed):  # noqa: F811
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    await client.post(
        f"/api/v1/leases/{lease['id']}/renew", json={"end_date": "2027-12-31"}, headers=headers
    )
    fake_feed(lease["id"])
    assert await poll_audit_changes(db_session) == 0
    assert (await db_session.execute(select(LeaseAudit))).first() is None

    fake_feed(str(uuid.uuid4()))
    assert await poll_audit_changes(db_session) == 0


async def test_poll_skips_ended_lease(client, db_session, compliance_on, fake_feed):  # noqa: F811
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers, "9 Ended St")
    ended = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(start_date="2025-01-01", end_date="2025-12-31"),
            headers=headers,
        )
    ).json()
    fake_feed(ended["id"])
    assert await poll_audit_changes(db_session) == 0
    assert (await db_session.execute(select(LeaseAudit))).first() is None
```

(add `make_property` and `lease_body` to this file's imports from `tests.test_leases`.)


async def test_poll_rerun_is_idempotent(client, db_session, compliance_on, fake_feed):  # noqa: F811
    headers = await landlord_headers(client)
    lease = await _make_lease(client, headers)
    audit_id = fake_feed(lease["id"])
    await poll_audit_changes(db_session)
    fake_feed(lease["id"], new_audit_id=audit_id)
    assert await poll_audit_changes(db_session) == 0
    assert len((await db_session.execute(select(LeaseAudit))).scalars().all()) == 1
```

Note the renew in the superseded test: `lease_body()` ends 2026-12-31, so the source lease is superseded by the renewal and its change must be skipped.

- [ ] **Step 2: Run -> fail** (ImportError: `poll_audit_changes`).

- [ ] **Step 3: Implement** — append to `backend/app/services/compliance.py` (imports: `from datetime import UTC, datetime`, `from app.models import ComplianceSyncState`, `from app.services.notify import manager_emails, manager_user_ids, notify_users, safe_send`):

```python
CURSOR_KEY = "audit_changes_cursor"


async def _cursor(session: AsyncSession) -> ComplianceSyncState | None:
    return (
        await session.execute(
            select(ComplianceSyncState).where(ComplianceSyncState.key == CURSOR_KEY)
        )
    ).scalar_one_or_none()


def _delta_lines(changes: dict) -> str:
    return "; ".join(
        f"{rule}: {t['from']} -> {t['to']}" for rule, t in sorted(changes.items())
    )


async def _lease_for_change(session: AsyncSession, client_ref: str) -> Lease | None:
    """The active lease a change applies to, or None when it should be skipped."""
    try:
        lease_id = uuid.UUID(client_ref)
    except ValueError:
        return None
    lease = (
        await session.execute(select(Lease).where(Lease.id == lease_id))
    ).scalar_one_or_none()
    if lease is None or lease.end_date < datetime.now(UTC).date():
        return None
    superseded = (
        await session.execute(select(Lease.id).where(Lease.renewed_from_id == lease.id))
    ).first()
    return None if superseded else lease


async def poll_audit_changes(session: AsyncSession) -> int:
    """Apply the service's audit-changes feed: store new audits and notify."""
    state = await _cursor(session)
    since = state.value if state else None
    applied = 0
    while True:
        batch = await list_changes(since)
        for change in batch:
            since = change["created_at"]
            lease = await _lease_for_change(session, change["client_ref"])
            if lease is None:
                logger.info("compliance poll: skipping change for %s", change["client_ref"])
                continue
            audit_id = uuid.UUID(change["new_audit_id"])
            existing = (
                await session.execute(
                    select(LeaseAudit).where(LeaseAudit.audit_id == audit_id)
                )
            ).first()
            if existing is not None:
                continue
            body = await get_audit(change["new_audit_id"])
            session.add(
                LeaseAudit(
                    lease_id=lease.id,
                    organization_id=lease.organization_id,
                    audit_id=audit_id,
                    as_at=date.fromisoformat(body["as_at"]),
                    findings=body["findings"],
                )
            )
            delta = _delta_lines(change["changes"])
            body_text = (
                f"The lease for {lease.tenant_name} changed under updated law or rules: "
                f"{delta}. General information, not legal advice."
            )
            await notify_users(
                session,
                await manager_user_ids(session, lease.organization_id),
                lease.organization_id,
                "compliance",
                "Lease compliance status changed",
                body_text,
                f"/app/leases/{lease.id}",
            )
            subject = f"Lease compliance status changed - {lease.tenant_name}"
            html = f"<p>{body_text}</p>"
            for email in await manager_emails(session, lease.organization_id):
                await safe_send(email, subject, html)
            applied += 1
        if len(batch) < 100:
            break
    if since is not None:
        if state is None:
            session.add(ComplianceSyncState(key=CURSOR_KEY, value=since))
        else:
            state.value = since
    await session.commit()
    return applied
```

- [ ] **Step 4: Scheduler** — in `start_scheduler()`, inside the same `if compliance_enabled():` block:

```python
        scheduler.add_job(
            _compliance_poll_job,
            CronTrigger(hour=settings.compliance_poll_hour),
            id="compliance_poll",
            replace_existing=True,
        )
```

with the job function (import `poll_audit_changes` alongside the drain import):

```python
async def _compliance_poll_job() -> None:
    """Open a session and apply the compliance change feed."""
    async with SessionLocal() as session:
        count = await poll_audit_changes(session)
    logger.info("compliance changes: applied %s", count)
```

- [ ] **Step 5: Run -> pass; backend full suite; ruff; commit** (`Add the compliance change poll and notifications`); push; CI green. Report and WAIT.

---

### Task 8: Backfill CLI

**Files:** Create `backend/app/compliance_backfill.py`; extend `backend/tests/test_compliance_jobs.py`.

**Interfaces:** Produces `async backfill(session) -> int` (leases enqueued) and the CLI `uv run python -m app.compliance_backfill`.

- [ ] **Step 1: Failing test** — append:

```python
from app.compliance_backfill import backfill


async def test_backfill_enqueues_only_active_unaudited(client, db_session, compliance_on, fake_create):  # noqa: F811
    headers = await landlord_headers(client)
    audited = await _make_lease(client, headers)
    plain = await _make_lease(client, headers)
    renewed = await _make_lease(client, headers)
    await client.post(
        f"/api/v1/leases/{renewed['id']}/renew", json={"end_date": "2027-12-31"}, headers=headers
    )
    await db_session.execute(ComplianceAuditQueue.__table__.delete())
    await db_session.commit()
    await client.post(f"/api/v1/leases/{audited['id']}/compliance-audit", headers=headers)

    count = await backfill(db_session)
    queued = {
        str(row.lease_id)
        for row in (await db_session.execute(select(ComplianceAuditQueue))).scalars().all()
    }
    assert audited["id"] not in queued
    assert renewed["id"] not in queued
    assert plain["id"] in queued
    assert count == len(queued)
```

Each `_make_lease` call creates a distinct property; the renewal successor itself stays queued — that is correct (it is active and unaudited).

- [ ] **Step 2: Run -> fail.**

- [ ] **Step 3: Implement** — `backend/app/compliance_backfill.py`:

```python
"""Enqueue every active, never-audited lease for a compliance audit.

Usage: uv run python -m app.compliance_backfill
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.db import SessionLocal
from app.models import Lease, LeaseAudit
from app.services.compliance import enqueue_audit


async def backfill(session: AsyncSession) -> int:
    """Enqueue leases with no audit that are neither ended nor superseded."""
    successor = aliased(Lease)
    result = await session.execute(
        select(Lease.id).where(
            Lease.end_date >= datetime.now(UTC).date(),
            ~select(successor.id).where(successor.renewed_from_id == Lease.id).exists(),
            ~select(LeaseAudit.id).where(LeaseAudit.lease_id == Lease.id).exists(),
        )
    )
    count = 0
    for (lease_id,) in result.all():
        await enqueue_audit(session, lease_id)
        count += 1
    await session.commit()
    return count


async def main() -> None:
    async with SessionLocal() as session:
        count = await backfill(session)
    print(f"backfill: enqueued {count} leases")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run -> pass; backend full suite; ruff; commit** (`Add the compliance backfill CLI`); push; CI green. Report and WAIT.

---

### Task 9: Frontend section and e2e

**Files:** Create `frontend/src/lib/compliance.ts`, `frontend/src/app/app/leases/ComplianceSection.tsx`, `frontend/e2e/compliance.spec.ts`; modify `frontend/src/app/app/leases/[leaseId]/page.tsx`.

**Interfaces:** Consumes `GET`/`POST /api/v1/leases/{id}/compliance-audit`. Read `node_modules/next/dist/docs/` guidance per `frontend/AGENTS.md` before writing components.

- [ ] **Step 1: API lib** — `frontend/src/lib/compliance.ts`:

```typescript
import { apiFetch } from "@/lib/api";

export type ComplianceVerdict = "red" | "green" | "skipped";

export interface ComplianceCitation {
  act: string;
  section_no: string;
}

export interface ComplianceFinding {
  rule_id: string;
  verdict: ComplianceVerdict;
  summary: string;
  citations: ComplianceCitation[];
  skip_reason: string | null;
}

export interface ComplianceAudit {
  id: string;
  audit_id: string;
  as_at: string;
  findings: ComplianceFinding[];
  created_at: string;
}

export interface ComplianceAuditState {
  enabled: boolean;
  audit: ComplianceAudit | null;
}

export function getComplianceAudit(leaseId: string): Promise<ComplianceAuditState> {
  return apiFetch<ComplianceAuditState>(`/api/v1/leases/${leaseId}/compliance-audit`);
}

export function runComplianceAudit(leaseId: string): Promise<ComplianceAudit> {
  return apiFetch<ComplianceAudit>(`/api/v1/leases/${leaseId}/compliance-audit`, {
    method: "POST",
  });
}
```

- [ ] **Step 2: Component** — `frontend/src/app/app/leases/ComplianceSection.tsx` (client component; follow the detail page's `Card`/`Badge`/`Button` usage from `@/components/ui`):

```typescript
"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import {
  getComplianceAudit,
  runComplianceAudit,
  type ComplianceAuditState,
} from "@/lib/compliance";

const VERDICT_TONE: Record<string, string> = {
  red: "bg-red-100 text-red-800",
  green: "bg-green-100 text-green-800",
  skipped: "bg-gray-100 text-gray-600",
};

export function ComplianceSection({ leaseId }: { leaseId: string }) {
  const [state, setState] = useState<ComplianceAuditState | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getComplianceAudit(leaseId).then(setState).catch(() => setState(null));
  }, [leaseId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!state?.enabled) return null;
  const audit = state.audit;
  const counts = { red: 0, green: 0, skipped: 0 };
  audit?.findings.forEach((f) => {
    counts[f.verdict] += 1;
  });

  async function check() {
    setRunning(true);
    setError(null);
    try {
      await runComplianceAudit(leaseId);
      load();
    } catch {
      setError("Compliance check failed. Try again later.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <Card data-testid="compliance-section">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">NSW compliance</h2>
        <Button onClick={check} disabled={running}>
          {running ? "Checking..." : "Check now"}
        </Button>
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {audit ? (
        <div className="mt-3 space-y-2">
          <div className="flex gap-2">
            <Badge className={VERDICT_TONE.red}>{counts.red} issues</Badge>
            <Badge className={VERDICT_TONE.green}>{counts.green} compliant</Badge>
            <Badge className={VERDICT_TONE.skipped}>{counts.skipped} skipped</Badge>
            <span className="text-sm text-gray-500">as at {audit.as_at}</span>
          </div>
          <ul className="divide-y">
            {audit.findings.map((f) => (
              <li key={f.rule_id} className="flex items-start gap-2 py-2 text-sm">
                <Badge className={VERDICT_TONE[f.verdict]}>{f.verdict}</Badge>
                <span>
                  {f.summary}
                  {f.citations[0] && (
                    <span className="text-gray-500"> (s{f.citations[0].section_no})</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-3 text-sm text-gray-500">No compliance check has run yet.</p>
      )}
      <p className="mt-3 text-xs text-gray-400">General information, not legal advice.</p>
    </Card>
  );
}
```

Adjust `Badge`/`Card`/`Button` props to the actual `@/components/ui` signatures (check the file; e.g. if `Badge` has a `tone` prop instead of `className`, use it).

- [ ] **Step 3: Mount** — in `frontend/src/app/app/leases/[leaseId]/page.tsx` import `{ ComplianceSection } from "@/app/app/leases/ComplianceSection"` and render `<ComplianceSection leaseId={leaseId} />` after the existing detail cards (locate the main column of cards and append it as the last card).

- [ ] **Step 4: e2e** — `frontend/e2e/compliance.spec.ts` (env-gated: the button flow needs the real compliance service running locally with the backend configured against it; without the env it verifies the hidden state):

```typescript
import { expect, test } from "@playwright/test";

const LIVE = !!process.env.COMPLIANCE_E2E;

test("compliance section hidden when integration is disabled", async ({ page }) => {
  test.skip(LIVE, "backend is configured with compliance enabled");
  // Reuse the existing e2e login + lease creation helpers used by other specs
  // (see e2e/inspections.spec.ts for the pattern), then:
  // await expect(page.getByTestId("compliance-section")).toHaveCount(0);
});

test("check now renders findings and the disclaimer", async ({ page }) => {
  test.skip(!LIVE, "requires the local compliance service (set COMPLIANCE_E2E=1)");
  // Login, create a lease, open its detail page (existing helper pattern), then:
  // await page.getByRole("button", { name: "Check now" }).click();
  // await expect(page.getByTestId("compliance-section")).toContainText("compliant");
  // await expect(page.getByTestId("compliance-section")).toContainText(
  //   "General information, not legal advice."
  // );
});
```

Replace the commented sketches with the repo's real e2e helpers when writing the spec (open `e2e/inspections.spec.ts`, copy its login/create-lease setup verbatim).

- [ ] **Step 5: Verify** — `cd frontend && npm run lint`; run the disabled-state e2e locally (`npx playwright test e2e/compliance.spec.ts`); for the live path, start the compliance service (`API_KEYS=dev-key:rentalapp uv run uvicorn app.main:app --port 8100` in its repo), set backend `.env` `compliance_api_url=http://localhost:8100` / `compliance_api_key=dev-key`, and run with `COMPLIANCE_E2E=1`. Record both outputs in the report.

- [ ] **Step 6: Full backend suite still green (`cd backend && uv run pytest -q`); ruff; commit** (`Add the compliance section to the lease page`); push; CI green. Report and WAIT — integration complete.
