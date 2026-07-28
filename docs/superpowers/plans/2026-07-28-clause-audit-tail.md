# Clause Audit Tail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send stored lease PDFs to the compliance service's async clause-audit API, track jobs to completion, notify managers, and render clause findings and field discrepancies on the lease page.

**Architecture:** A `lease_clause_audits` table mirrors the existing compliance integration; a new `services/clause_audit.py` module owns the multipart client, submit and poll; one POST + one GET endpoint drive a `ClauseAuditSection` on the lease page; an APScheduler interval job polls in-flight jobs and notifies on completion. No service-side changes.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0 + Alembic + PostgreSQL, httpx, APScheduler; Next.js 16 + React 19 + Tailwind 4; Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-07-28-clause-audit-tail-design.md`

## Global Constraints

- Backend from `backend/`: `uv run ...` only; frontend from `frontend/`: `npm`/`npx`.
- Every task ends: backend full suite (`uv run pytest`) -> ruff sequence from `backend/` (`uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`) -> commit -> push -> CI green. Frontend tasks additionally `npx tsc --noEmit`.
- Button-only trigger; audits the document's **latest version**; payload always carries the lease's money/date fields.
- Errors (exact): compliance disabled -> 503; document not on the lease -> 404; category not `lease` -> 422; latest version not `application/pdf` -> 422; duplicate in-flight audit for the document -> 409; service 429 passes through as 429; other `httpx.HTTPError` -> 502.
- Poll interval setting `clause_poll_interval_minutes` default 1; frontend refetch every 10 s only while an audit is in flight.
- Always notify managers on terminal status (in-app + email): success summary `Clause audit finished: {reds} red, {yellows} yellow, {mismatches} field mismatch` or `Clause audit finished: all green`; failure `Clause audit failed`. Notification body ends with "General information, not legal advice."
- Frontend copy includes the footer line exactly: `General information, not legal advice.`
- All lease-side FKs carry `ondelete="CASCADE"`. No emojis anywhere.
- e2e gated by `CLAUSE_AUDIT_E2E`; never in regular CI.

---

### Task 1: Model, migration, schemas

**Files:**
- Create: `backend/app/models/clause_audit.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/b7d31f8c4e21_lease_clause_audits.py`
- Create: `backend/app/schemas/clause_audit.py`
- Test: `backend/tests/test_clause_audit_service.py` (new)

**Interfaces:**
- Consumes: `Base` from `app.core.db`; existing `Document`, `DocumentVersion`, `Lease` models.
- Produces: ORM `LeaseClauseAudit` (tablename `lease_clause_audits`; columns as below); Pydantic `ClauseAuditInfo` and `ClauseAuditListState` — later tasks import these names verbatim. Test helpers `_org_and_user(db_session, email)` and `_seed_document(db_session, org_id, lease_id, user_id, stored_name="stored.pdf")` are reused by Task 4's test file.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_clause_audit_service.py`:

```python
import uuid

from sqlalchemy import select

from app.models import (
    Document,
    DocumentCategory,
    DocumentVersion,
    LeaseClauseAudit,
    Membership,
    User,
)
from tests.test_portal import make_lease
from tests.test_properties_crud import landlord_headers


async def _org_and_user(db_session, email):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    org_id = (
        await db_session.execute(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        )
    ).scalar_one()
    return org_id, user.id


async def _seed_document(db_session, org_id, lease_id, user_id, stored_name="stored.pdf"):
    document = Document(
        organization_id=org_id,
        lease_id=lease_id,
        title="Signed Lease",
        category=DocumentCategory.lease,
        created_by=user_id,
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        DocumentVersion(
            document_id=document.id,
            version_number=1,
            stored_name=stored_name,
            original_filename="lease.pdf",
            content_type="application/pdf",
            size_bytes=16,
            uploaded_by=user_id,
        )
    )
    await db_session.commit()
    return document


async def test_lease_clause_audit_round_trip(client, db_session):
    email = "clausemodel@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, "1 Clause St"))
    document = await _seed_document(db_session, org_id, lease_id, user_id)
    version_id = (
        await db_session.execute(
            select(DocumentVersion.id).where(DocumentVersion.document_id == document.id)
        )
    ).scalar_one()

    row = LeaseClauseAudit(
        organization_id=org_id,
        lease_id=lease_id,
        document_id=document.id,
        document_version_id=version_id,
        job_id=str(uuid.uuid4()),
        status="pending",
        model="claude-opus-4-8",
        engine_version="1.1.1",
    )
    db_session.add(row)
    await db_session.commit()

    stored = (await db_session.execute(select(LeaseClauseAudit))).scalar_one()
    assert stored.status == "pending"
    assert stored.findings == [] and stored.discrepancies == []
    assert stored.completed_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_clause_audit_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'LeaseClauseAudit'`.

- [ ] **Step 3: Implement**

`backend/app/models/clause_audit.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LeaseClauseAudit(Base):
    """One clause-audit job for a document version; history is never overwritten."""

    __tablename__ = "lease_clause_audits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    lease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    job_id: Mapped[str] = mapped_column(String(36), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending")
    findings: Mapped[list] = mapped_column(JSON, default=list)
    discrepancies: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(50))
    engine_version: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

In `backend/app/models/__init__.py`, add `LeaseClauseAudit` to the imports (from `app.models.clause_audit`) and to `__all__`, keeping the file's alphabetical style.

`backend/alembic/versions/b7d31f8c4e21_lease_clause_audits.py`:

```python
"""lease_clause_audits

Revision ID: b7d31f8c4e21
Revises: a96ec8fc1f5c
Create Date: 2026-07-28

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d31f8c4e21"
down_revision: str | Sequence[str] | None = "a96ec8fc1f5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the lease_clause_audits table."""
    op.create_table(
        "lease_clause_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "lease_id",
            sa.Uuid(),
            sa.ForeignKey("leases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.Uuid(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_id", sa.String(36), nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("discrepancies", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("engine_version", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_lease_clause_audits_organization_id", "lease_clause_audits", ["organization_id"]
    )
    op.create_index("ix_lease_clause_audits_lease_id", "lease_clause_audits", ["lease_id"])
    op.create_index("ix_lease_clause_audits_document_id", "lease_clause_audits", ["document_id"])


def downgrade() -> None:
    """Drop the lease_clause_audits table."""
    op.drop_index("ix_lease_clause_audits_document_id", "lease_clause_audits")
    op.drop_index("ix_lease_clause_audits_lease_id", "lease_clause_audits")
    op.drop_index("ix_lease_clause_audits_organization_id", "lease_clause_audits")
    op.drop_table("lease_clause_audits")
```

`backend/app/schemas/clause_audit.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class ClauseAuditInfo(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    job_id: str
    status: str
    findings: list
    discrepancies: list
    model: str
    engine_version: str
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ClauseAuditListState(BaseModel):
    enabled: bool
    audits: list[ClauseAuditInfo] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_clause_audit_service.py -v`
Expected: PASS.

- [ ] **Step 5: Apply the migration**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade a96ec8fc1f5c -> b7d31f8c4e21`.

- [ ] **Step 6: Full suite, ruff sequence, commit, push, CI**

```bash
cd backend && uv run pytest
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add -A && git commit -m "Add the lease clause audit table and schemas" && git push origin main
```

Watch CI to green (`gh run watch`).

---

### Task 2: Client, lease fields, submit

**Files:**
- Create: `backend/app/services/clause_audit.py`
- Test: `backend/tests/test_clause_audit_service.py` (append)

**Interfaces:**
- Consumes: `settings.compliance_api_url` / `settings.compliance_api_key` / `settings.documents_dir`; `LeaseClauseAudit`; `Document`, `DocumentVersion`, `Lease`.
- Produces (later tasks import verbatim): `UPLOAD_TIMEOUT = 30.0`; `IN_FLIGHT = ("pending", "running")`; `create_clause_audit(filename, content, content_type, payload) -> dict`; `get_clause_audit(job_id) -> dict`; `lease_fields(lease) -> dict`; `latest_version(session, document_id) -> DocumentVersion | None`; `submit_document_audit(session, lease, document) -> LeaseClauseAudit` (flushes; the caller commits). Test constant `FAKE_JOB` is reused by Task 4's test file.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_clause_audit_service.py`:

```python
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.config import settings
from app.models import Lease
from app.models.lease import RentFrequency
from app.services import clause_audit

FAKE_JOB = {
    "id": "11111111-1111-1111-1111-111111111111",
    "status": "pending",
    "jurisdiction": "NSW",
    "as_at": "2026-07-28",
    "engine_version": "1.1.1",
    "model": "claude-opus-4-8",
    "client_ref": None,
    "findings": [],
    "discrepancies": [],
    "error": None,
    "created_at": "2026-07-28T00:00:00Z",
    "completed_at": None,
}


def test_lease_fields_subset_and_none_omission():
    lease = Lease(
        rent_amount=Decimal(560),
        rent_frequency=RentFrequency.weekly,
        start_date=date(2026, 2, 1),
        end_date=date(2027, 1, 31),
        bond_amount=Decimal(2240),
    )
    fields = clause_audit.lease_fields(lease)
    assert fields["rent_amount"] == "560"
    assert fields["rent_frequency"] == "weekly"
    assert fields["start_date"] == "2026-02-01"
    assert fields["end_date"] == "2027-01-31"
    assert fields["bond_amount"] == "2240"
    assert "holding_deposit_amount" not in fields


async def test_submit_document_audit_posts_latest_version(client, db_session, tmp_path, monkeypatch):
    email = "clausesubmit@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, "2 Submit St"))
    document = await _seed_document(db_session, org_id, lease_id, user_id)
    db_session.add(
        DocumentVersion(
            document_id=document.id,
            version_number=2,
            stored_name="v2.pdf",
            original_filename="lease-v2.pdf",
            content_type="application/pdf",
            size_bytes=20,
            uploaded_by=user_id,
        )
    )
    await db_session.commit()
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    Path(tmp_path, "v2.pdf").write_bytes(b"%PDF-1.4 v2 bytes")

    captured = {}

    async def fake_create(filename, content, content_type, payload):
        captured.update(
            filename=filename, content=content, content_type=content_type, payload=payload
        )
        return FAKE_JOB

    monkeypatch.setattr("app.services.clause_audit.create_clause_audit", fake_create)
    lease = (await db_session.execute(select(Lease).where(Lease.id == lease_id))).scalar_one()

    row = await clause_audit.submit_document_audit(db_session, lease, document)
    await db_session.commit()

    assert captured["filename"] == "lease-v2.pdf"
    assert captured["content"] == b"%PDF-1.4 v2 bytes"
    assert captured["content_type"] == "application/pdf"
    assert captured["payload"]["jurisdiction"] == "NSW"
    assert captured["payload"]["client_ref"] == str(lease_id)
    assert captured["payload"]["lease"]["rent_amount"]
    assert row.job_id == FAKE_JOB["id"]
    assert row.status == "pending"
    assert row.model == "claude-opus-4-8" and row.engine_version == "1.1.1"
    version_2 = (
        await db_session.execute(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_number == 2,
            )
        )
    ).scalar_one()
    assert row.document_version_id == version_2
```

(If `RentFrequency` lives elsewhere, check `backend/app/models/lease.py` for the enum's
actual name and import path and use that; the assertion values stay the same.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_clause_audit_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.clause_audit'`.

- [ ] **Step 3: Implement**

`backend/app/services/clause_audit.py`:

```python
"""Client and jobs for the compliance service's async clause-audit API."""

import json
import logging
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, DocumentVersion, Lease, LeaseClauseAudit

logger = logging.getLogger(__name__)

UPLOAD_TIMEOUT = 30.0
IN_FLIGHT = ("pending", "running")

MONEY_FIELDS = (
    "bond_amount",
    "rent_in_advance_amount",
    "holding_deposit_amount",
    "other_security_amount",
    "break_fee_amount",
)


def _headers() -> dict:
    return {"X-API-Key": settings.compliance_api_key}


async def create_clause_audit(
    filename: str, content: bytes, content_type: str, payload: dict
) -> dict:
    """POST a clause-audit job with the document file and return its body."""
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        response = await client.post(
            f"{settings.compliance_api_url}/v1/clause-audits",
            files={"file": (filename, content, content_type)},
            data={"payload": json.dumps(payload)},
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()


async def get_clause_audit(job_id: str) -> dict:
    """Fetch one clause-audit job by the service's job id."""
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        response = await client.get(
            f"{settings.compliance_api_url}/v1/clause-audits/{job_id}", headers=_headers()
        )
        response.raise_for_status()
        return response.json()


def lease_fields(lease: Lease) -> dict:
    """The field cross-check subset: money and dates, None omitted."""
    fields = {
        "rent_amount": str(lease.rent_amount),
        "rent_frequency": lease.rent_frequency.value,
        "start_date": lease.start_date.isoformat(),
        "end_date": lease.end_date.isoformat(),
    }
    for name in MONEY_FIELDS:
        value = getattr(lease, name)
        if value is not None:
            fields[name] = str(value)
    return fields


async def latest_version(session: AsyncSession, document_id) -> DocumentVersion | None:
    return (
        await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def submit_document_audit(
    session: AsyncSession, lease: Lease, document: Document
) -> LeaseClauseAudit:
    """Send the document's latest version for a clause audit. The caller commits."""
    version = await latest_version(session, document.id)
    content = Path(settings.documents_dir, version.stored_name).read_bytes()
    payload = {
        "jurisdiction": "NSW",
        "client_ref": str(lease.id),
        "lease": lease_fields(lease),
    }
    body = await create_clause_audit(
        version.original_filename, content, version.content_type, payload
    )
    row = LeaseClauseAudit(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        document_id=document.id,
        document_version_id=version.id,
        job_id=body["id"],
        status=body["status"],
        model=body["model"],
        engine_version=body["engine_version"],
    )
    session.add(row)
    await session.flush()
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_clause_audit_service.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite, ruff sequence, commit, push, CI**

```bash
cd backend && uv run pytest
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add -A && git commit -m "Add the clause audit client and submit" && git push origin main
```

---

### Task 3: Poll and notifications

**Files:**
- Modify: `backend/app/services/clause_audit.py`
- Test: `backend/tests/test_clause_audit_service.py` (append)

**Interfaces:**
- Consumes: `get_clause_audit`, `IN_FLIGHT`, `LeaseClauseAudit`; `manager_emails`, `manager_user_ids`, `notify_users`, `safe_send` from `app.services.notify`.
- Produces: `poll_clause_audits(session) -> int` — updates terminal rows, notifies, returns the count updated; `_summary(row) -> str` (exact wording in Global Constraints).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_clause_audit_service.py`:

```python
from app.models import Notification


def _terminal_job(job_id, status="succeeded", findings=None, discrepancies=None, error=None):
    body = dict(FAKE_JOB)
    body.update(
        id=job_id,
        status=status,
        findings=findings or [],
        discrepancies=discrepancies or [],
        error=error,
        completed_at="2026-07-28T01:00:00Z",
    )
    return body


RED_FINDING = {
    "rule_id": "nsw.clause.carpet_cleaning",
    "verdict": "red",
    "summary": "Found",
    "evidence": {},
    "citations": [],
    "skip_reason": None,
    "clause_quote": "carpet professionally cleaned",
}


async def _seed_in_flight(client, db_session, email, address):
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, address))
    document = await _seed_document(db_session, org_id, lease_id, user_id)
    version_id = (
        await db_session.execute(
            select(DocumentVersion.id).where(DocumentVersion.document_id == document.id)
        )
    ).scalar_one()
    row = LeaseClauseAudit(
        organization_id=org_id,
        lease_id=lease_id,
        document_id=document.id,
        document_version_id=version_id,
        job_id=str(uuid.uuid4()),
        status="pending",
        model="claude-opus-4-8",
        engine_version="1.1.1",
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def test_poll_writes_results_and_notifies(client, db_session, monkeypatch):
    row = await _seed_in_flight(client, db_session, "clausepoll@example.com", "3 Poll St")

    async def fake_get(job_id):
        return _terminal_job(
            job_id,
            findings=[RED_FINDING],
            discrepancies=[
                {"field": "rent_amount", "document_value": "$520", "submitted_value": "560"}
            ],
        )

    sent = []

    async def fake_send(to, subject, html):
        sent.append((to, subject))

    monkeypatch.setattr("app.services.clause_audit.get_clause_audit", fake_get)
    monkeypatch.setattr("app.services.clause_audit.safe_send", fake_send)

    updated = await clause_audit.poll_clause_audits(db_session)

    assert updated == 1
    await db_session.refresh(row)
    assert row.status == "succeeded"
    assert row.findings[0]["verdict"] == "red"
    assert row.discrepancies[0]["field"] == "rent_amount"
    assert row.completed_at is not None
    notifications = (
        (
            await db_session.execute(
                select(Notification).where(Notification.organization_id == row.organization_id)
            )
        )
        .scalars()
        .all()
    )
    assert any("1 red, 0 yellow, 1 field mismatch" in n.body for n in notifications)
    assert sent and "Clause audit finished" in sent[0][1]


async def test_poll_isolates_one_bad_row(client, db_session, monkeypatch):
    bad = await _seed_in_flight(client, db_session, "clausebad@example.com", "4 Bad St")
    good = await _seed_in_flight(client, db_session, "clausegood@example.com", "5 Good St")

    async def fake_get(job_id):
        if job_id == bad.job_id:
            raise RuntimeError("service hiccup")
        return _terminal_job(job_id)

    async def fake_send(to, subject, html):
        pass

    monkeypatch.setattr("app.services.clause_audit.get_clause_audit", fake_get)
    monkeypatch.setattr("app.services.clause_audit.safe_send", fake_send)

    updated = await clause_audit.poll_clause_audits(db_session)

    assert updated == 1
    await db_session.refresh(bad)
    await db_session.refresh(good)
    assert bad.status == "pending"
    assert good.status == "succeeded"


async def test_poll_failure_status_notifies_failure(client, db_session, monkeypatch):
    row = await _seed_in_flight(client, db_session, "clausefail@example.com", "6 Fail St")

    async def fake_get(job_id):
        return _terminal_job(job_id, status="failed", error="model declined the request")

    sent = []

    async def fake_send(to, subject, html):
        sent.append(subject)

    monkeypatch.setattr("app.services.clause_audit.get_clause_audit", fake_get)
    monkeypatch.setattr("app.services.clause_audit.safe_send", fake_send)

    updated = await clause_audit.poll_clause_audits(db_session)

    assert updated == 1
    await db_session.refresh(row)
    assert row.status == "failed"
    assert row.error == "model declined the request"
    assert sent and "Clause audit failed" in sent[0]
```

(If the in-app notification model's text column is not named `body`, check
`backend/app/models` for the `Notification` model's actual column and adjust the one
assertion; everything else stays.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_clause_audit_service.py -v`
Expected: FAIL with `AttributeError: module 'app.services.clause_audit' has no attribute 'poll_clause_audits'`.

- [ ] **Step 3: Implement**

Extend the imports at the top of `backend/app/services/clause_audit.py` with
`from datetime import UTC, datetime` and
`from app.services.notify import manager_emails, manager_user_ids, notify_users, safe_send`,
then append:

```python
def _summary(row: LeaseClauseAudit) -> str:
    if row.status == "failed":
        return "Clause audit failed"
    reds = sum(1 for f in row.findings if f["verdict"] == "red")
    yellows = sum(1 for f in row.findings if f["verdict"] == "yellow")
    mismatches = len(row.discrepancies)
    if not (reds or yellows or mismatches):
        return "Clause audit finished: all green"
    return f"Clause audit finished: {reds} red, {yellows} yellow, {mismatches} field mismatch"


async def _notify_completion(session: AsyncSession, row: LeaseClauseAudit) -> list[tuple]:
    """Queue in-app notifications; return (to, subject, html) emails for after commit."""
    lease = (await session.execute(select(Lease).where(Lease.id == row.lease_id))).scalar_one()
    document = (
        await session.execute(select(Document).where(Document.id == row.document_id))
    ).scalar_one()
    summary = _summary(row)
    title = "Clause audit failed" if row.status == "failed" else "Clause audit finished"
    body_text = f"{document.title}: {summary}. General information, not legal advice."
    await notify_users(
        session,
        await manager_user_ids(session, row.organization_id),
        row.organization_id,
        "compliance",
        title,
        body_text,
        f"/app/leases/{lease.id}",
    )
    subject = f"{title} - {lease.tenant_name}"
    html = f"<p>{body_text}</p>"
    return [(email, subject, html) for email in await manager_emails(session, row.organization_id)]


async def poll_clause_audits(session: AsyncSession) -> int:
    """Advance every in-flight clause audit; one bad row never blocks the rest."""
    rows = (
        (
            await session.execute(
                select(LeaseClauseAudit)
                .where(LeaseClauseAudit.status.in_(IN_FLIGHT))
                .order_by(LeaseClauseAudit.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    updated = 0
    for row in rows:
        try:
            body = await get_clause_audit(row.job_id)
            if body["status"] not in ("succeeded", "failed"):
                if body["status"] != row.status:
                    row.status = body["status"]
                    await session.commit()
                continue
            row.status = body["status"]
            row.findings = body["findings"]
            row.discrepancies = body["discrepancies"]
            row.error = body["error"]
            row.completed_at = datetime.now(UTC)
            emails = await _notify_completion(session, row)
            await session.commit()
            updated += 1
            for to, subject, html in emails:
                await safe_send(to, subject, html)
        except Exception:  # noqa: BLE001 - keep polling the other rows
            logger.exception("clause audit poll: failed on job %s", row.job_id)
            await session.rollback()
            continue
    return updated
```

(Check `notify_users`'s exact signature in `backend/app/services/notify.py` before
writing the call — the compliance module's `_apply_change` shows the working argument
order; mirror it exactly.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_clause_audit_service.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite, ruff sequence, commit, push, CI**

```bash
cd backend && uv run pytest
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add -A && git commit -m "Poll clause audit jobs and notify managers" && git push origin main
```

---

### Task 4: Endpoints, scheduler, settings

**Files:**
- Create: `backend/app/routers/clause_audits.py`
- Modify: `backend/app/main.py` (router registration block, after `compliance_router`)
- Modify: `backend/app/core/scheduler.py`
- Modify: `backend/app/core/config.py` (after `compliance_queue_max_attempts`)
- Test: `backend/tests/test_clause_audit_endpoints.py` (new)

**Interfaces:**
- Consumes: `submit_document_audit`, `latest_version`, `poll_clause_audits`, `IN_FLIGHT`; `ClauseAuditInfo`, `ClauseAuditListState`; `compliance.enabled`; `get_owned_lease`, `require_roles`; the `compliance_on` fixture; Task 1/2 test helpers (`FAKE_JOB`, `_org_and_user`, `_seed_document`).
- Produces: `POST /api/v1/leases/{lease_id}/documents/{document_id}/clause-audit` (202) and `GET /api/v1/leases/{lease_id}/clause-audits`; scheduler job id `clause_poll`; setting `clause_poll_interval_minutes: int = 1`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_clause_audit_endpoints.py`:

```python
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.models import DocumentCategory, DocumentVersion, LeaseClauseAudit
from tests.test_clause_audit_service import FAKE_JOB, _org_and_user, _seed_document
from tests.test_portal import make_lease
from tests.test_properties_crud import landlord_headers


async def _setup(client, db_session, email, address, tmp_path, monkeypatch):
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, address))
    document = await _seed_document(db_session, org_id, lease_id, user_id)
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    Path(tmp_path, "stored.pdf").write_bytes(b"%PDF-1.4 stored")
    return headers, lease_id, document


def _fake_create(monkeypatch):
    async def _fake(filename, content, content_type, payload):
        body = dict(FAKE_JOB)
        body["id"] = str(uuid.uuid4())
        return body

    monkeypatch.setattr("app.services.clause_audit.create_clause_audit", _fake)


async def test_post_disabled_is_503(client, db_session, tmp_path, monkeypatch):
    headers, lease_id, document = await _setup(
        client, db_session, "cl503@example.com", "10 Off St", tmp_path, monkeypatch
    )
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 503


async def test_post_creates_job_row(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cl202@example.com", "11 Run St", tmp_path, monkeypatch
    )
    _fake_create(monkeypatch)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["document_id"] == str(document.id)
    stored = (await db_session.execute(select(LeaseClauseAudit))).scalar_one()
    assert stored.job_id == body["job_id"]


async def test_post_foreign_document_is_404(
    client, db_session, tmp_path, monkeypatch, compliance_on
):
    headers, lease_id, _ = await _setup(
        client, db_session, "cl404@example.com", "12 Foreign St", tmp_path, monkeypatch
    )
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{uuid.uuid4()}/clause-audit", headers=headers
    )
    assert response.status_code == 404


async def test_post_wrong_category_is_422(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cl422a@example.com", "13 Cat St", tmp_path, monkeypatch
    )
    document.category = DocumentCategory.report
    await db_session.commit()
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 422


async def test_post_non_pdf_is_422(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cl422b@example.com", "14 Png St", tmp_path, monkeypatch
    )
    version = (
        await db_session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
    ).scalar_one()
    version.content_type = "image/png"
    await db_session.commit()
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 422


async def test_post_duplicate_in_flight_is_409(
    client, db_session, tmp_path, monkeypatch, compliance_on
):
    headers, lease_id, document = await _setup(
        client, db_session, "cl409@example.com", "15 Twice St", tmp_path, monkeypatch
    )
    _fake_create(monkeypatch)
    first = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert first.status_code == 202
    second = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert second.status_code == 409


async def test_post_service_429_passes_through(
    client, db_session, tmp_path, monkeypatch, compliance_on
):
    headers, lease_id, document = await _setup(
        client, db_session, "cl429@example.com", "16 Full St", tmp_path, monkeypatch
    )

    async def _full(filename, content, content_type, payload):
        request = httpx.Request("POST", "http://service/v1/clause-audits")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("too many", request=request, response=response)

    monkeypatch.setattr("app.services.clause_audit.create_clause_audit", _full)
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 429


async def test_list_shape_and_scoping(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "cllist@example.com", "17 List St", tmp_path, monkeypatch
    )
    _fake_create(monkeypatch)
    await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    listed = await client.get(f"/api/v1/leases/{lease_id}/clause-audits", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["enabled"] is True
    assert len(body["audits"]) == 1

    other_headers = await landlord_headers(client, "clother@example.com")
    foreign = await client.get(f"/api/v1/leases/{lease_id}/clause-audits", headers=other_headers)
    assert foreign.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_clause_audit_endpoints.py -v`
Expected: FAIL (404s — router not registered yet).

- [ ] **Step 3: Implement**

`backend/app/routers/clause_audits.py`:

```python
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Document, DocumentCategory, LeaseClauseAudit, Membership, Role
from app.routers.leases import get_owned_lease
from app.schemas.clause_audit import ClauseAuditInfo, ClauseAuditListState
from app.services import clause_audit, compliance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["clause-audits"])

manager = require_roles(Role.landlord, Role.property_manager)


def _info(row: LeaseClauseAudit) -> ClauseAuditInfo:
    return ClauseAuditInfo(
        id=row.id,
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        job_id=row.job_id,
        status=row.status,
        findings=row.findings,
        discrepancies=row.discrepancies,
        model=row.model,
        engine_version=row.engine_version,
        error=row.error,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.post(
    "/leases/{lease_id}/documents/{document_id}/clause-audit",
    status_code=202,
    response_model=ClauseAuditInfo,
)
async def run_clause_audit(
    lease_id: uuid.UUID,
    document_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> ClauseAuditInfo:
    """Send the document's latest version for an async clause audit."""
    if not compliance.enabled():
        raise HTTPException(status_code=503, detail="Compliance integration is not configured")
    lease = await get_owned_lease(lease_id, membership, session)
    document = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.lease_id == lease.id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.category != DocumentCategory.lease:
        raise HTTPException(status_code=422, detail="Only lease documents can be audited")
    version = await clause_audit.latest_version(session, document.id)
    if version is None:
        raise HTTPException(status_code=404, detail="Document has no versions")
    if version.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="Only PDF documents can be audited")
    in_flight = (
        await session.execute(
            select(LeaseClauseAudit.id).where(
                LeaseClauseAudit.document_id == document.id,
                LeaseClauseAudit.status.in_(clause_audit.IN_FLIGHT),
            )
        )
    ).first()
    if in_flight is not None:
        raise HTTPException(status_code=409, detail="A clause audit is already in flight")
    try:
        row = await clause_audit.submit_document_audit(session, lease, document)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise HTTPException(
                status_code=429, detail="Clause audit queue is full, try again later"
            ) from exc
        logger.warning("Clause audit submit failed for document %s: %s", document_id, exc)
        raise HTTPException(status_code=502, detail="Compliance service unavailable") from exc
    except httpx.HTTPError as exc:
        logger.warning("Clause audit submit failed for document %s: %s", document_id, exc)
        raise HTTPException(status_code=502, detail="Compliance service unavailable") from exc
    await session.commit()
    await session.refresh(row)
    return _info(row)


@router.get("/leases/{lease_id}/clause-audits", response_model=ClauseAuditListState)
async def list_clause_audits(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> ClauseAuditListState:
    """The lease's clause audits, newest first, plus the feature flag."""
    lease = await get_owned_lease(lease_id, membership, session)
    rows = (
        (
            await session.execute(
                select(LeaseClauseAudit)
                .where(LeaseClauseAudit.lease_id == lease.id)
                .order_by(LeaseClauseAudit.created_at.desc(), LeaseClauseAudit.id.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return ClauseAuditListState(enabled=compliance.enabled(), audits=[_info(row) for row in rows])
```

In `backend/app/main.py`: add `from app.routers.clause_audits import router as clause_audits_router` with the other router imports and `app.include_router(clause_audits_router)` right after the `compliance_router` line.

In `backend/app/core/config.py`, after `compliance_queue_max_attempts: int = 10`:

```python
    clause_poll_interval_minutes: int = 1
```

In `backend/app/core/scheduler.py`: add `from app.services.clause_audit import poll_clause_audits` below the compliance imports, add the job function:

```python
async def _clause_poll_job() -> None:
    """Open a session and advance in-flight clause audits."""
    async with SessionLocal() as session:
        count = await poll_clause_audits(session)
    if count:
        logger.info("clause audits: completed %s", count)
```

and register it inside the existing `if compliance_enabled():` block:

```python
        scheduler.add_job(
            _clause_poll_job,
            IntervalTrigger(minutes=settings.clause_poll_interval_minutes),
            id="clause_poll",
            replace_existing=True,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_clause_audit_endpoints.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite, ruff sequence, commit, push, CI**

```bash
cd backend && uv run pytest
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add -A && git commit -m "Add the clause audit endpoints and poll job" && git push origin main
```

---

### Task 5: Frontend lib, section, page mount

**Files:**
- Create: `frontend/src/lib/clauseAudit.ts`
- Create: `frontend/src/app/app/leases/ClauseAuditSection.tsx`
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx` (import next to the `ComplianceSection` import at line ~38; mount right after `<ComplianceSection leaseId={leaseId} />` at line ~827)

**Interfaces:**
- Consumes: `apiFetch` from `@/lib/api`; `listLeaseDocuments`, `DocumentInfo` from `@/lib/documents`; `Badge`, `Button`, `Card` from `@/components/ui` (Badge tones: `neutral | brand | success | warning | danger`).
- Produces: `listClauseAudits(leaseId)`, `runClauseAudit(leaseId, documentId)`, types `ClauseAudit`, `ClauseFinding`, `ClauseDiscrepancy`, `ClauseAuditListState`; component `ClauseAuditSection({ leaseId })`.

- [ ] **Step 1: Write the lib**

`frontend/src/lib/clauseAudit.ts`:

```typescript
import { apiFetch } from "@/lib/api";

export type ClauseVerdict = "red" | "green" | "yellow" | "skipped";
export type ClauseAuditStatus = "pending" | "running" | "succeeded" | "failed";

export interface ClauseCitation {
  act: string;
  section_no: string;
  as_at: string;
}

export interface ClauseFinding {
  rule_id: string;
  verdict: ClauseVerdict;
  summary: string;
  clause_quote: string | null;
  citations: ClauseCitation[];
  skip_reason: string | null;
}

export interface ClauseDiscrepancy {
  field: string;
  document_value: string;
  submitted_value: string;
}

export interface ClauseAudit {
  id: string;
  document_id: string;
  document_version_id: string;
  job_id: string;
  status: ClauseAuditStatus;
  findings: ClauseFinding[];
  discrepancies: ClauseDiscrepancy[];
  model: string;
  engine_version: string;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ClauseAuditListState {
  enabled: boolean;
  audits: ClauseAudit[];
}

export function listClauseAudits(leaseId: string): Promise<ClauseAuditListState> {
  return apiFetch<ClauseAuditListState>(`/api/v1/leases/${leaseId}/clause-audits`);
}

export function runClauseAudit(leaseId: string, documentId: string): Promise<ClauseAudit> {
  return apiFetch<ClauseAudit>(`/api/v1/leases/${leaseId}/documents/${documentId}/clause-audit`, {
    method: "POST",
  });
}
```

- [ ] **Step 2: Write the section component**

`frontend/src/app/app/leases/ClauseAuditSection.tsx`:

```typescript
"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card } from "@/components/ui";
import {
  listClauseAudits,
  runClauseAudit,
  type ClauseAudit,
  type ClauseFinding,
  type ClauseVerdict,
} from "@/lib/clauseAudit";
import { listLeaseDocuments, type DocumentInfo } from "@/lib/documents";

const VERDICT_TONE: Record<ClauseVerdict, "danger" | "success" | "warning" | "neutral"> = {
  red: "danger",
  green: "success",
  yellow: "warning",
  skipped: "neutral",
};

const CLAUSE_RULE_LABELS: Record<string, string> = {
  "nsw.clause.carpet_cleaning": "Prohibited term: professional carpet cleaning (s 19)",
  "nsw.clause.fumigation": "Prohibited term: fumigation at end of tenancy (s 19)",
  "nsw.clause.specified_insurance": "Prohibited term: tenant must take out insurance (s 19)",
  "nsw.clause.landlord_liability_exemption": "Prohibited term: landlord liability exemption (s 19)",
  "nsw.clause.breach_penalty": "Prohibited term: breach penalty or remaining rent (s 19)",
  "nsw.clause.no_breach_rent_inducement": "Prohibited term: conditional rent inducement (s 19)",
  "nsw.clause.specified_contractor": "Prohibited term: specified contractor (s 19)",
  "nsw.clause.specified_contractor_reg":
    "Prohibited term: specified contractor (Reg cl 5, pre-2025)",
  "nsw.clause.utility_provider": "Prohibited term: specific utility provider (Reg cl 5)",
  "nsw.clause.states_rent_payment": "Required term: rent and payment (s 33)",
  "nsw.clause.quiet_enjoyment_term": "Required term: quiet enjoyment (s 50)",
  "nsw.clause.tenant_use_term": "Required term: use of premises (s 51)",
  "nsw.clause.habitability_term": "Required term: clean and habitable (s 52)",
  "nsw.clause.repairs_term": "Required term: repairs (s 63)",
  "nsw.clause.locks_security_term": "Required term: locks and security (s 70)",
};

const FIELD_LABELS: Record<string, string> = {
  rent_amount: "Rent",
  rent_frequency: "Rent frequency",
  start_date: "Start date",
  end_date: "End date",
  bond_amount: "Bond",
  rent_in_advance_amount: "Rent in advance",
  holding_deposit_amount: "Holding fee",
  other_security_amount: "Other security",
  break_fee_amount: "Break fee",
};

const VERDICT_ORDER: Record<ClauseVerdict, number> = { red: 0, yellow: 1, green: 2, skipped: 3 };

function label(finding: ClauseFinding): string {
  return CLAUSE_RULE_LABELS[finding.rule_id] ?? finding.rule_id;
}

function StatusChip({ audit }: { audit: ClauseAudit }) {
  if (audit.status === "pending") return <Badge tone="neutral">Queued</Badge>;
  if (audit.status === "running") return <Badge tone="brand">Running...</Badge>;
  if (audit.status === "failed") return <Badge tone="danger">Failed</Badge>;
  return (
    <Badge tone="success">
      Completed {audit.completed_at ? new Date(audit.completed_at).toLocaleString() : ""}
    </Badge>
  );
}

function FindingRow({ finding }: { finding: ClauseFinding }) {
  const citation = finding.citations[0];
  if (finding.verdict === "green" || finding.verdict === "skipped") {
    return (
      <li className="text-sm text-muted">
        <Badge tone={VERDICT_TONE[finding.verdict]}>{finding.verdict}</Badge>{" "}
        <span className="font-medium">{label(finding)}</span>
        {finding.verdict === "skipped" && finding.skip_reason ? ` - ${finding.skip_reason}` : null}
      </li>
    );
  }
  return (
    <li className="space-y-1 text-sm">
      <div>
        <Badge tone={VERDICT_TONE[finding.verdict]}>{finding.verdict}</Badge>{" "}
        <span className="font-medium">{label(finding)}</span>
      </div>
      <p className="text-muted">{finding.summary}</p>
      {finding.clause_quote ? (
        <blockquote className="border-l-2 pl-2 italic text-muted">
          {finding.clause_quote}
        </blockquote>
      ) : null}
      {citation ? (
        <p className="text-xs text-muted">
          {citation.act}, s {citation.section_no} - as at {citation.as_at}
        </p>
      ) : null}
    </li>
  );
}

function ResultPanel({ audit }: { audit: ClauseAudit }) {
  const ordered = [...audit.findings].sort(
    (a, b) => VERDICT_ORDER[a.verdict] - VERDICT_ORDER[b.verdict],
  );
  return (
    <div className="space-y-3">
      {audit.discrepancies.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted">
              <th className="py-1">Field</th>
              <th className="py-1">Document says</th>
              <th className="py-1">Form says</th>
            </tr>
          </thead>
          <tbody>
            {audit.discrepancies.map((d) => (
              <tr key={d.field}>
                <td className="py-1 font-medium">{FIELD_LABELS[d.field] ?? d.field}</td>
                <td className="py-1">{d.document_value}</td>
                <td className="py-1">{d.submitted_value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <ul className="space-y-2">
        {ordered.map((finding) => (
          <FindingRow key={finding.rule_id} finding={finding} />
        ))}
      </ul>
    </div>
  );
}

export function ClauseAuditSection({ leaseId }: { leaseId: string }) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [state, setState] = useState<{ enabled: boolean; audits: ClauseAudit[] } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const [docs, audits] = await Promise.all([
        listLeaseDocuments(leaseId),
        listClauseAudits(leaseId),
      ]);
      setDocuments(docs.filter((d) => d.category === "lease"));
      setState(audits);
    } catch {
      setState(null);
    }
  }, [leaseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const inFlight = (state?.audits ?? []).some(
    (a) => a.status === "pending" || a.status === "running",
  );

  useEffect(() => {
    if (!inFlight) return;
    const timer = setInterval(() => void load(), 10_000);
    return () => clearInterval(timer);
  }, [inFlight, load]);

  if (!state?.enabled || documents.length === 0) return null;

  const byDocument = new Map<string, ClauseAudit[]>();
  for (const audit of state.audits) {
    const list = byDocument.get(audit.document_id) ?? [];
    list.push(audit);
    byDocument.set(audit.document_id, list);
  }

  async function run(documentId: string) {
    setErrors((prev) => ({ ...prev, [documentId]: "" }));
    try {
      await runClauseAudit(leaseId, documentId);
      await load();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Clause audit failed to start";
      setErrors((prev) => ({ ...prev, [documentId]: message }));
    }
  }

  return (
    <Card>
      <h2 className="text-lg font-semibold">Clause audit</h2>
      <div className="mt-3 space-y-4">
        {documents.map((document) => {
          const audits = byDocument.get(document.id) ?? [];
          const latest = audits[0];
          const latestDone = audits.find((a) => a.status === "succeeded");
          const older = audits.filter((a) => a !== latestDone && a.status === "succeeded");
          const isPdf = document.current_version.content_type === "application/pdf";
          const running = latest?.status === "pending" || latest?.status === "running";
          return (
            <div key={document.id} className="space-y-2 border-b pb-3 last:border-b-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{document.title}</span>
                {latest ? <StatusChip audit={latest} /> : null}
                <Button disabled={!isPdf || running} onClick={() => void run(document.id)}>
                  Run clause audit
                </Button>
              </div>
              {!isPdf ? (
                <p className="text-xs text-muted">Only PDF documents can be audited.</p>
              ) : null}
              {errors[document.id] ? (
                <p className="text-xs text-danger">{errors[document.id]}</p>
              ) : null}
              {latest?.status === "failed" && latest.error ? (
                <p className="text-xs text-danger">{latest.error}</p>
              ) : null}
              {latestDone ? <ResultPanel audit={latestDone} /> : null}
              {older.length > 0 ? (
                <p className="text-xs text-muted">
                  Previous audits:{" "}
                  {older
                    .map(
                      (a) =>
                        `${new Date(a.created_at).toLocaleDateString()} (` +
                        `${a.findings.filter((f) => f.verdict === "red").length} red, ` +
                        `${a.findings.filter((f) => f.verdict === "yellow").length} yellow)`,
                    )
                    .join("; ")}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-muted">General information, not legal advice.</p>
    </Card>
  );
}
```

Match the `Button` usage (variant prop, if any) and the muted/danger text utility class
names to what `ComplianceSection.tsx` in the same directory already uses — copy its
conventions rather than inventing new ones.

- [ ] **Step 3: Mount on the lease page**

In `frontend/src/app/app/leases/[leaseId]/page.tsx`: add
`import { ClauseAuditSection } from "@/app/app/leases/ClauseAuditSection";` next to the
`ComplianceSection` import (line ~38), and render
`<ClauseAuditSection leaseId={leaseId} />` immediately after
`<ComplianceSection leaseId={leaseId} />` (line ~827).

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Full backend suite (unchanged), ruff, commit, push, CI**

```bash
cd backend && uv run pytest
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add -A && git commit -m "Render clause audits on the lease page" && git push origin main
```

---

### Task 6: Env-gated e2e

**Files:**
- Create: `frontend/e2e/clause-audit.spec.ts`

**Interfaces:**
- Consumes: the signup/property/lease flow used by `frontend/e2e/compliance.spec.ts` (same selectors); the lease page's Documents upload UI; a backend configured with the compliance service.

- [ ] **Step 1: Write the spec**

`frontend/e2e/clause-audit.spec.ts`:

```typescript
import { expect, test } from "@playwright/test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const LIVE = !!process.env.CLAUSE_AUDIT_E2E;
const landlord = `clause-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

async function openLeaseDetail(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Clause Owner");
  await page.getByPlaceholder("Organization name").fill("Clause Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("31 Clause Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "31 Clause Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Cleo Clause");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent", { exact: true }).fill("600");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(364));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page).toHaveURL(/\/app\/leases$/);

  await page.getByRole("link", { name: "31 Clause Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
}

test("run clause audit queues a job for an uploaded lease PDF", async ({ page }) => {
  test.skip(!LIVE, "requires the local compliance service (set CLAUSE_AUDIT_E2E=1)");
  await openLeaseDetail(page);

  const dir = mkdtempSync(join(tmpdir(), "clause-e2e-"));
  const pdfPath = join(dir, "lease.pdf");
  writeFileSync(
    pdfPath,
    "%PDF-1.4\nRESIDENTIAL TENANCY AGREEMENT. The tenant must have the carpet " +
      "professionally cleaned at the end of the tenancy.\n%%EOF",
  );

  await expect(page.getByRole("heading", { name: "Documents", exact: true })).toBeVisible();
  await page.setInputFiles('input[type="file"]', pdfPath);
  await expect(page.getByText("Signed", { exact: false }).first()).toBeVisible();

  await expect(page.getByRole("heading", { name: "Clause audit" })).toBeVisible();
  await page.getByRole("button", { name: "Run clause audit" }).first().click();
  await expect(page.getByText("Queued").or(page.getByText("Running..."))).toBeVisible();
  await expect(page.getByText("General information, not legal advice.").first()).toBeVisible();
});
```

Before finalising, open the lease page's Documents section markup and align the upload
interaction (file input selector, any title/category fields, submit button, and the
post-upload assertion) with how that UI actually uploads. The required shape of the test
stays: upload a PDF, click "Run clause audit", assert the Queued/Running chip and the
disclaimer line.

- [ ] **Step 2: Verify the spec is skipped without the flag**

Run: `cd frontend && npx playwright test e2e/clause-audit.spec.ts`
Expected: 1 skipped.

- [ ] **Step 3: Full backend suite, ruff, commit, push, CI**

```bash
cd backend && uv run pytest
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add -A && git commit -m "Add the env-gated clause audit e2e" && git push origin main
```

Manual live run (optional; costs about US$1 and 1-3 minutes):

```bash
CLAUSE_AUDIT_E2E=1 npx playwright test e2e/clause-audit.spec.ts
```

---

## Acceptance (manual, after Task 6)

With the service running (`ANTHROPIC_API_KEY` set) and the SaaS configured
(`COMPLIANCE_API_URL`, `COMPLIANCE_API_KEY`): open a lease, upload a lease
PDF, press "Run clause audit", watch the chip go Queued -> Running ->
Completed within a few minutes (scheduler poll), and check the findings,
discrepancy table, notification bell and email. On the service DB,
`select document from clause_audit_jobs` returns NULL for the finished job.
