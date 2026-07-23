# Milestone 9.2: Document Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A manager stores a lease's documents as PDFs or images with a version history; manager and tenant preview or download them through an authenticated endpoint, never a public URL.

**Architecture:** A two-layer model (`Document` + `DocumentVersion`) attached to a lease. Files live in a private `documents_dir` that is not statically mounted, and the only path to a file is an authenticated download endpoint that checks per request that the caller manages or is a tenant of the lease. Uploads notify the lease's tenants in-app.

**Tech Stack:** FastAPI (`FileResponse`), async SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js 16, Playwright. No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- The migration adds **one PostgreSQL enum** (`documentcategory`): create it via the model's `Enum`, and in `downgrade` drop the tables then `sa.Enum(name="documentcategory").drop(op.get_bind())`. Verify upgrade -> downgrade -> upgrade. Current head: `a4d0104d02b0`. Do not use `--autogenerate`; hand-write the migration.
- **Files must not go under the `/uploads` static mount.** `documents_dir` is a new setting and is never passed to `app.mount`. Storing a document where `/uploads/<name>` can reach it defeats the whole feature.
- Accessible names introduced: `Documents`, `Add document`, `New version`, `Preview`, `Download`, `Title`, `Category`. Playwright matches names by **substring**; the lease detail page already has `Delete`, `Yes, delete`, `Invite`, `Revoke`, `Edit`, `Save`. `Download` and `Preview` are new and distinct.
- Backend commands run from `backend/`, frontend from `frontend/`. The shell keeps its cwd between commands — always `cd` explicitly.
- Tests set the storage dir per test: `monkeypatch.setattr(settings, "documents_dir", str(tmp_path))`, and upload with `files={"file": (name, data, content_type)}`, matching `tests/test_properties_images.py`.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/document.py` | `DocumentCategory`, `Document`, `DocumentVersion` |
| `backend/app/models/__init__.py` | register the three |
| `backend/alembic/versions/<rev>_add_documents.py` | tables + one enum, reversible |
| `backend/app/core/config.py` | `documents_dir` |
| `backend/app/core/uploads.py` | `save_document`, `delete_document_file` |
| `backend/app/schemas/document.py` | `DocumentInfo`, `DocumentVersionInfo` |
| `backend/app/routers/documents.py` | upload / version / list / delete / tenant list / download |
| `backend/tests/test_documents.py` | the whole feature |
| `frontend/src/lib/documents.ts` | API client incl. authenticated blob fetch |
| `frontend/src/components/document-preview.tsx` | preview modal |
| `frontend/src/app/app/leases/[leaseId]/page.tsx` | Documents card |
| `frontend/src/app/app/page.tsx` | tenant portal read-only Documents card |
| `frontend/e2e/documents.spec.ts` | end-to-end |

---

### Task 1: Models, enum, migration

**Files:**
- Create: `backend/app/models/document.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_documents.py`
- Test: `backend/tests/test_documents.py`

**Interfaces:**
- Produces: `DocumentCategory` (lease/report/receipt/other); `Document(id, organization_id,
  lease_id, title, category, created_by, created_at)`; `DocumentVersion(id, document_id,
  version_number, stored_name, original_filename, content_type, size_bytes, uploaded_by,
  created_at)`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_documents.py`:

```python
import uuid

from sqlalchemy import select

from app.models import Document, DocumentCategory, DocumentVersion, Membership, User
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


async def test_document_and_version_round_trip(client, db_session):
    email = "docmodel@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    lease_id = uuid.UUID(await make_lease(client, headers, "1 Doc St"))

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
            stored_name="abc.pdf",
            original_filename="lease.pdf",
            content_type="application/pdf",
            size_bytes=1234,
            uploaded_by=user_id,
        )
    )
    await db_session.commit()

    stored = (
        await db_session.execute(select(Document).where(Document.id == document.id))
    ).scalar_one()
    assert stored.category == DocumentCategory.lease
    version = (
        await db_session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
    ).scalar_one()
    assert version.version_number == 1
    assert version.original_filename == "lease.pdf"
```

`created_by` and `uploaded_by` are FKs to `users.id`, so the model test resolves the landlord's real
user id via `_org_and_user` rather than passing an organization id.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_documents.py -v`
Expected: FAIL with `ImportError: cannot import name 'Document' from 'app.models'`.

- [ ] **Step 3: Create the models**

Create `backend/app/models/document.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentCategory(str, enum.Enum):
    lease = "lease"
    report = "report"
    receipt = "receipt"
    other = "other"


class Document(Base):
    """A logical document on a lease, e.g. the signed lease agreement."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    lease_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leases.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[DocumentCategory] = mapped_column(Enum(DocumentCategory))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    """One uploaded file for a document; re-uploading adds a version, never replaces."""

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    stored_name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Register the models**

In `backend/app/models/__init__.py`, add after the `contractor` import:

```python
from app.models.document import Document, DocumentCategory, DocumentVersion
```

and add `"Document"`, `"DocumentCategory"`, `"DocumentVersion"` to `__all__`, keeping it alphabetical (after `"Contractor"`).

- [ ] **Step 5: Generate the migration**

Run: `cd backend && uv run alembic revision -m "add documents"`

Replace the generated `upgrade`/`downgrade` with this (keep the generated `revision`; `down_revision` must be `a4d0104d02b0`):

```python
def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "category",
            sa.Enum("lease", "report", "receipt", "other", name="documentcategory"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"])
    op.create_index("ix_documents_lease_id", "documents", ["lease_id"])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_documents_lease_id", table_name="documents")
    op.drop_index("ix_documents_organization_id", table_name="documents")
    op.drop_table("documents")
    sa.Enum(name="documentcategory").drop(op.get_bind())
```

`document_versions` is dropped before `documents` (its FK target), and the enum is dropped last,
after the table that uses it. This is the same order as the maintenance migration.

- [ ] **Step 6: Verify the migration round-trips**

```bash
cd backend
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all three succeed. The middle step proves `downgrade` (and the enum drop) works.

- [ ] **Step 7: Run the model test**

Run: `cd backend && uv run pytest tests/test_documents.py -v`
Expected: PASS.

- [ ] **Step 8: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 9: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 10: Commit and push**

```bash
git add backend/app/models backend/alembic/versions backend/tests/test_documents.py
git commit -m "Add the Document and DocumentVersion models and migration"
git push origin main
```

Then report and wait for approval.

---

### Task 2: Storage, upload and add-version endpoints, tenant notification

**Files:**
- Modify: `backend/app/core/config.py`, `backend/app/core/uploads.py`, `backend/app/main.py`
- Create: `backend/app/schemas/document.py`, `backend/app/routers/documents.py`
- Test: `backend/tests/test_documents.py`

**Interfaces:**
- Consumes: `Document`, `DocumentVersion`, `DocumentCategory` (Task 1); `save_document` (this
  task); `notify_users`, `lease_tenant_user_ids` from `app/services/notify.py`; `get_owned_lease`
  from `app/routers/leases.py`.
- Produces: `save_document(file) -> tuple[str, int]`; `delete_document_file(stored_name)`;
  `DocumentInfo`, `DocumentVersionInfo`; `POST /api/v1/leases/{lease_id}/documents`,
  `POST /api/v1/documents/{document_id}/versions`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_documents.py`. Add these to the top imports (E402 — imports stay at
the top of the file, not inside functions):

```python
from app.core.config import settings
from app.models import Notification
from tests.test_portal import onboard_tenant
```

```python
PDF = b"%PDF-1.4 minimal"


async def _upload(client, headers, lease_id, tmp_path, monkeypatch, title="Signed Lease"):
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    return await client.post(
        f"/api/v1/leases/{lease_id}/documents",
        data={"title": title, "category": "lease"},
        files={"file": ("lease.pdf", PDF, "application/pdf")},
        headers=headers,
    )


async def test_upload_creates_a_document_and_first_version(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docup@example.com")
    lease_id = await make_lease(client, headers, "1 Upload St")

    response = await _upload(client, headers, lease_id, tmp_path, monkeypatch)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Signed Lease"
    assert body["category"] == "lease"
    assert body["version_count"] == 1
    assert body["current_version"]["version_number"] == 1
    assert list(tmp_path.iterdir())  # a file was written to the private dir


async def test_second_upload_is_version_two(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docv2@example.com")
    lease_id = await make_lease(client, headers, "2 Version Rd")
    doc_id = (await _upload(client, headers, lease_id, tmp_path, monkeypatch)).json()["id"]

    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    response = await client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("lease-v2.pdf", PDF, "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["version_count"] == 2
    assert response.json()["current_version"]["version_number"] == 2


async def test_upload_rejects_unsupported_type(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docbad@example.com")
    lease_id = await make_lease(client, headers, "3 Bad St")
    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))

    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents",
        data={"title": "Notes", "category": "other"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=headers,
    )

    assert response.status_code == 400


async def test_upload_notifies_the_tenant(client, db_session, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docnotify@example.com")
    lease_id = await make_lease(client, headers, "4 Notify St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "docnotify-t@example.com")

    await _upload(client, headers, lease_id, tmp_path, monkeypatch)

    tenant_id = (
        await db_session.execute(
            select(Notification.user_id).where(Notification.category == "document_uploaded")
        )
    ).scalars().all()
    assert len(tenant_id) == 1
    # The onboarded tenant, not the manager, is the recipient.
    mine = (await client.get("/api/v1/me/notifications", headers=tenant)).json()
    assert any(n["category"] == "document_uploaded" for n in mine)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_documents.py -v`
Expected: the four new tests FAIL — 404 (no route) or 500 (no `save_document`).

- [ ] **Step 3: Add the setting**

In `backend/app/core/config.py`, after the `upload_dir` line, add:

```python
    # Private document storage, NOT statically served: access is only through
    # the authenticated download endpoint.
    documents_dir: str = "documents"
```

- [ ] **Step 4: Add the storage helpers**

In `backend/app/core/uploads.py`, add after `save_image`:

```python
DOCUMENT_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def save_document(file: UploadFile) -> tuple[str, int]:
    """Validate and store a document in the private documents dir.

    Returns (stored_name, size_bytes). 400 on an unsupported type. The file is
    never placed under the public /uploads mount.
    """
    extension = DOCUMENT_EXTENSIONS.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=400, detail="Unsupported document type")
    data = await file.read()
    name = f"{uuid.uuid4().hex}{extension}"
    directory = Path(settings.documents_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(data)
    return name, len(data)


def delete_document_file(stored_name: str) -> None:
    """Remove a stored document file. A missing file is not an error."""
    Path(settings.documents_dir, stored_name).unlink(missing_ok=True)
```

- [ ] **Step 5: Add the schemas**

Create `backend/app/schemas/document.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import DocumentCategory


class DocumentVersionInfo(BaseModel):
    id: uuid.UUID
    version_number: int
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class DocumentInfo(BaseModel):
    id: uuid.UUID
    title: str
    category: DocumentCategory
    version_count: int
    current_version: DocumentVersionInfo
    created_at: datetime
```

- [ ] **Step 6: Add the router with the two upload endpoints**

Create `backend/app/routers/documents.py`:

```python
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.uploads import save_document
from app.models import Document, DocumentCategory, DocumentVersion, Membership
from app.routers.leases import get_owned_lease, manager
from app.schemas.document import DocumentInfo, DocumentVersionInfo
from app.services.notify import lease_tenant_user_ids, notify_users

router = APIRouter(prefix="/api/v1", tags=["documents"])


def _version_info(version: DocumentVersion) -> DocumentVersionInfo:
    return DocumentVersionInfo(
        id=version.id,
        version_number=version.version_number,
        original_filename=version.original_filename,
        content_type=version.content_type,
        size_bytes=version.size_bytes,
        created_at=version.created_at,
    )


async def _document_info(session: AsyncSession, document: Document) -> DocumentInfo:
    versions = (
        (
            await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document.id)
                .order_by(DocumentVersion.version_number.desc())
            )
        )
        .scalars()
        .all()
    )
    return DocumentInfo(
        id=document.id,
        title=document.title,
        category=document.category,
        version_count=len(versions),
        current_version=_version_info(versions[0]),
        created_at=document.created_at,
    )


async def get_owned_document(
    document_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Document:
    """A document in the caller's organization, or 404."""
    document = (
        await session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def _add_version(
    session: AsyncSession, document: Document, file: UploadFile, uploaded_by: uuid.UUID
) -> DocumentVersion:
    stored_name, size = await save_document(file)
    highest = (
        await session.execute(
            select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                DocumentVersion.document_id == document.id
            )
        )
    ).scalar_one()
    version = DocumentVersion(
        document_id=document.id,
        version_number=highest + 1,
        stored_name=stored_name,
        original_filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        uploaded_by=uploaded_by,
    )
    session.add(version)
    return version


async def _notify_document_upload(
    session: AsyncSession, document: Document, title: str
) -> None:
    tenant_ids = await lease_tenant_user_ids(session, document.lease_id)
    await notify_users(
        session,
        tenant_ids,
        document.organization_id,
        "document_uploaded",
        "Document shared",
        f"{title} was added to your lease.",
        f"/app/leases/{document.lease_id}",
    )


@router.post("/leases/{lease_id}/documents", status_code=201, response_model=DocumentInfo)
async def create_document(
    lease_id: uuid.UUID,
    title: str = Form(...),
    category: DocumentCategory = Form(...),
    file: UploadFile = File(...),
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> DocumentInfo:
    """Create a document on a lease with its first version, and tell the tenant."""
    lease = await get_owned_lease(lease_id, membership, session)
    document = Document(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        title=title,
        category=category,
        created_by=membership.user_id,
    )
    session.add(document)
    await session.flush()
    await _add_version(session, document, file, membership.user_id)
    await _notify_document_upload(session, document, title)
    await session.commit()
    return await _document_info(session, document)


@router.post("/documents/{document_id}/versions", status_code=201, response_model=DocumentInfo)
async def add_version(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> DocumentInfo:
    """Upload a new version of an existing document, and tell the tenant."""
    document = await get_owned_document(document_id, membership, session)
    await _add_version(session, document, file, membership.user_id)
    await _notify_document_upload(session, document, document.title)
    await session.commit()
    return await _document_info(session, document)
```

`membership.user_id` supplies `created_by` / `uploaded_by`. `manager` and `get_owned_lease` are
imported from the leases router, as the maintenance router does.

- [ ] **Step 7: Mount the router**

In `backend/app/main.py`, add the import (alphabetical, after `contractors_router`):

```python
from app.routers.documents import router as documents_router
```

and the mount after `app.include_router(contractors_router)`:

```python
app.include_router(documents_router)
```

- [ ] **Step 8: Run the tests**

Run: `cd backend && uv run pytest tests/test_documents.py -v`
Expected: all pass.

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
git add backend/app/core/config.py backend/app/core/uploads.py backend/app/main.py backend/app/schemas/document.py backend/app/routers/documents.py backend/tests/test_documents.py
git commit -m "Add document upload and versioning with tenant notification"
git push origin main
```

Then report and wait for approval.

---

### Task 3: List, versions, delete, and the tenant list

**Files:**
- Modify: `backend/app/routers/documents.py`
- Test: `backend/tests/test_documents.py`

**Interfaces:**
- Consumes: `get_owned_document`, `_document_info`, `_version_info` (Task 2); `get_owned_lease`
  (leases); `delete_document_file` (Task 2, `app/core/uploads.py`); `get_current_user` and the
  `LeaseTenant` check pattern.
- Produces: `GET /api/v1/leases/{lease_id}/documents`, `GET /api/v1/documents/{document_id}/versions`,
  `DELETE /api/v1/documents/{document_id}`, `GET /api/v1/me/leases/{lease_id}/documents`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_documents.py`. No new imports are needed — these tests use
`select`, `uuid`, `Document`, `DocumentVersion`, the `_upload` helper and `onboard_tenant`, all
already at the top of the file. The delete test checks the filesystem with the `tmp_path` fixture
(`tmp_path.iterdir()`), not `pathlib`.

```python
async def test_list_documents_for_a_lease(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "doclist@example.com")
    lease_id = await make_lease(client, headers, "5 List St")
    await _upload(client, headers, lease_id, tmp_path, monkeypatch, title="Report")

    body = (await client.get(f"/api/v1/leases/{lease_id}/documents", headers=headers)).json()

    assert [d["title"] for d in body] == ["Report"]
    assert body[0]["version_count"] == 1


async def test_other_orgs_document_is_404(client, tmp_path, monkeypatch):
    owner = await landlord_headers(client, "docowner@example.com")
    lease_id = await make_lease(client, owner, "6 Mine St")
    doc_id = (await _upload(client, owner, lease_id, tmp_path, monkeypatch)).json()["id"]

    stranger = await landlord_headers(client, "docthief@example.com")
    assert (
        await client.get(f"/api/v1/documents/{doc_id}/versions", headers=stranger)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/documents/{doc_id}", headers=stranger)
    ).status_code == 404


async def test_delete_removes_document_versions_and_files(client, db_session, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docdel@example.com")
    lease_id = await make_lease(client, headers, "7 Del St")
    doc_id = (await _upload(client, headers, lease_id, tmp_path, monkeypatch)).json()["id"]
    assert list(tmp_path.iterdir())  # the file exists before delete

    assert (await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)).status_code == 204

    gone = (
        await db_session.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
    ).scalar_one_or_none()
    assert gone is None
    versions = (
        await db_session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == uuid.UUID(doc_id))
        )
    ).scalars().all()
    assert versions == []
    assert list(tmp_path.iterdir()) == []  # the file was unlinked


async def test_tenant_lists_own_lease_documents(client, db_session, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "doctenant@example.com")
    lease_id = await make_lease(client, headers, "8 Tenant St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "doctenant-t@example.com")
    await _upload(client, headers, lease_id, tmp_path, monkeypatch, title="Your Lease")

    body = (await client.get(f"/api/v1/me/leases/{lease_id}/documents", headers=tenant)).json()

    assert [d["title"] for d in body] == ["Your Lease"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_documents.py -k "list or other_orgs or delete_removes or tenant_lists" -v`
Expected: FAIL — the routes do not exist.

- [ ] **Step 3: Add the list, versions and delete endpoints**

In `backend/app/routers/documents.py`, extend the imports:

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from app.core.deps import get_current_user
from app.core.uploads import delete_document_file, save_document
from app.models import Document, DocumentCategory, DocumentVersion, Lease, LeaseTenant, Membership, User
```

Append these endpoints:

```python
@router.get("/leases/{lease_id}/documents", response_model=list[DocumentInfo])
async def list_documents(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentInfo]:
    """The documents on a lease in the caller's organization, newest first."""
    await get_owned_lease(lease_id, membership, session)
    documents = (
        (
            await session.execute(
                select(Document)
                .where(Document.lease_id == lease_id)
                .order_by(Document.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _document_info(session, d) for d in documents]


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionInfo])
async def list_versions(
    document_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentVersionInfo]:
    """Every version of a document, newest first."""
    document = await get_owned_document(document_id, membership, session)
    versions = (
        (
            await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document.id)
                .order_by(DocumentVersion.version_number.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_version_info(v) for v in versions]


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a document, all its versions, and their files."""
    document = await get_owned_document(document_id, membership, session)
    versions = (
        (
            await session.execute(
                select(DocumentVersion).where(DocumentVersion.document_id == document.id)
            )
        )
        .scalars()
        .all()
    )
    for version in versions:
        delete_document_file(version.stored_name)
        await session.delete(version)
    await session.delete(document)
    await session.commit()
    return Response(status_code=204)


async def _tenant_lease_or_404(lease_id: uuid.UUID, user: User, session: AsyncSession) -> None:
    """Raise 404 unless the caller is a tenant of the lease."""
    owned = (
        await session.execute(
            select(LeaseTenant.id).where(
                LeaseTenant.lease_id == lease_id, LeaseTenant.user_id == user.id
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="Lease not found")


@router.get("/me/leases/{lease_id}/documents", response_model=list[DocumentInfo])
async def list_my_documents(
    lease_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentInfo]:
    """The documents on a lease the caller is a tenant of."""
    await _tenant_lease_or_404(lease_id, user, session)
    documents = (
        (
            await session.execute(
                select(Document)
                .where(Document.lease_id == lease_id)
                .order_by(Document.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _document_info(session, d) for d in documents]
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/test_documents.py -v`
Expected: all pass.

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 6: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/routers/documents.py backend/tests/test_documents.py
git commit -m "Add document list, versions, delete, and tenant list"
git push origin main
```

Then report and wait for approval.

---

### Task 4: The authenticated download endpoint

**Files:**
- Modify: `backend/app/routers/documents.py`
- Test: `backend/tests/test_documents.py`

**Interfaces:**
- Consumes: everything from Tasks 2-3; `get_current_user`; `Role` for the manager check.
- Produces: `GET /api/v1/documents/versions/{version_id}/download` -> `FileResponse`, gated on the
  caller being a manager of the document's org or a tenant of its lease.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_documents.py`. Add `from tests.test_portal import make_lease,
onboard_tenant` is already imported; add nothing new beyond what is there.

```python
async def test_manager_downloads_the_file(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "docdl@example.com")
    lease_id = await make_lease(client, headers, "9 Download St")
    version_id = (
        await _upload(client, headers, lease_id, tmp_path, monkeypatch)
    ).json()["current_version"]["id"]

    response = await client.get(f"/api/v1/documents/versions/{version_id}/download", headers=headers)

    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"].startswith("application/pdf")


async def test_tenant_of_another_lease_cannot_download(client, db_session, tmp_path, monkeypatch):
    owner = await landlord_headers(client, "dlowner@example.com")
    lease_id = await make_lease(client, owner, "10 Private St")
    version_id = (
        await _upload(client, owner, lease_id, tmp_path, monkeypatch)
    ).json()["current_version"]["id"]

    # A tenant, but of a different lease in a different org.
    other_mgr = await landlord_headers(client, "dlother@example.com")
    other_lease = await make_lease(client, other_mgr, "11 Other St")
    stranger = await onboard_tenant(client, db_session, other_mgr, other_lease, "dlstranger@example.com")

    response = await client.get(
        f"/api/v1/documents/versions/{version_id}/download", headers=stranger
    )
    assert response.status_code == 404


async def test_unauthenticated_download_is_rejected(client, tmp_path, monkeypatch):
    headers = await landlord_headers(client, "dlnoauth@example.com")
    lease_id = await make_lease(client, headers, "12 NoAuth St")
    version_id = (
        await _upload(client, headers, lease_id, tmp_path, monkeypatch)
    ).json()["current_version"]["id"]

    response = await client.get(f"/api/v1/documents/versions/{version_id}/download")
    assert response.status_code == 401
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_documents.py -k download -v`
Expected: FAIL — the route does not exist (404) for the first two, and the unauth one also 404s
rather than 401.

- [ ] **Step 3: Add the download endpoint**

In `backend/app/routers/documents.py`, extend the imports:

```python
from pathlib import Path

from fastapi.responses import FileResponse

from app.core.config import settings
from app.models import (
    Document,
    DocumentCategory,
    DocumentVersion,
    Lease,
    LeaseTenant,
    Membership,
    Role,
    User,
)
```

Append:

```python
async def _can_read_document(session: AsyncSession, document: Document, user: User) -> bool:
    """True if the user manages the document's org or is a tenant of its lease."""
    is_manager = (
        await session.execute(
            select(Membership.id).where(
                Membership.user_id == user.id,
                Membership.organization_id == document.organization_id,
                Membership.role.in_([Role.landlord, Role.property_manager]),
            )
        )
    ).first()
    if is_manager is not None:
        return True
    is_tenant = (
        await session.execute(
            select(LeaseTenant.id).where(
                LeaseTenant.lease_id == document.lease_id, LeaseTenant.user_id == user.id
            )
        )
    ).first()
    return is_tenant is not None


@router.get("/documents/versions/{version_id}/download")
async def download_version(
    version_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Stream a document version's file. The single gated path to any file."""
    version = (
        await session.execute(select(DocumentVersion).where(DocumentVersion.id == version_id))
    ).scalar_one_or_none()
    document = (
        (
            await session.execute(
                select(Document).where(Document.id == version.document_id)
            )
        ).scalar_one_or_none()
        if version is not None
        else None
    )
    if version is None or document is None or not await _can_read_document(session, document, user):
        raise HTTPException(status_code=404, detail="Document not found")

    return FileResponse(
        Path(settings.documents_dir, version.stored_name),
        media_type=version.content_type,
        filename=version.original_filename,
    )
```

A missing version, a missing document, and a caller who is neither manager nor tenant all return
the same 404 — a reader learns nothing about whether the id exists. The unauthenticated case is a
401 from `get_current_user` before this body runs.

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/test_documents.py -v`
Expected: all pass. `test_unauthenticated_download_is_rejected` now gets 401 from the dependency.

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 6: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/routers/documents.py backend/tests/test_documents.py
git commit -m "Add the authenticated document download endpoint"
git push origin main
```

Then report and wait for approval.

---

### Task 5: Frontend — Documents card, upload, versions, preview modal

**Files:**
- Create: `frontend/src/lib/documents.ts`, `frontend/src/components/document-preview.tsx`
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx`, `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: the endpoints from Tasks 2-4; `getAccessToken`, `API_BASE_URL` (existing);
  `downloadBlob` (M9.1), `ConfirmDialog` (existing).
- Produces: the accessible names `Documents`, `Add document`, `New version`, `Preview`,
  `Download`, `Title`, `Category`.

- [ ] **Step 1: Add the API client**

Create `frontend/src/lib/documents.ts`:

```ts
import { apiFetch, API_BASE_URL } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

export type DocumentCategory = "lease" | "report" | "receipt" | "other";

export interface DocumentVersionInfo {
  id: string;
  version_number: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface DocumentInfo {
  id: string;
  title: string;
  category: DocumentCategory;
  version_count: number;
  current_version: DocumentVersionInfo;
  created_at: string;
}

export function listLeaseDocuments(leaseId: string) {
  return apiFetch<DocumentInfo[]>(`/api/v1/leases/${leaseId}/documents`);
}

export function listMyLeaseDocuments(leaseId: string) {
  return apiFetch<DocumentInfo[]>(`/api/v1/me/leases/${leaseId}/documents`);
}

export function listDocumentVersions(documentId: string) {
  return apiFetch<DocumentVersionInfo[]>(`/api/v1/documents/${documentId}/versions`);
}

export function deleteDocument(documentId: string) {
  return apiFetch<void>(`/api/v1/documents/${documentId}`, { method: "DELETE" });
}

async function uploadFile(url: string, form: FormData): Promise<DocumentInfo> {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE_URL}${url}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!response.ok) throw new Error("Upload failed");
  return response.json();
}

export function uploadDocument(
  leaseId: string,
  title: string,
  category: DocumentCategory,
  file: File,
) {
  const form = new FormData();
  form.append("title", title);
  form.append("category", category);
  form.append("file", file);
  return uploadFile(`/api/v1/leases/${leaseId}/documents`, form);
}

export function uploadVersion(documentId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return uploadFile(`/api/v1/documents/${documentId}/versions`, form);
}

export async function fetchDocumentBlob(versionId: string): Promise<Blob> {
  const token = getAccessToken();
  const response = await fetch(
    `${API_BASE_URL}/api/v1/documents/versions/${versionId}/download`,
    { cache: "no-store", headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!response.ok) throw new Error("Download failed");
  return response.blob();
}
```

- [ ] **Step 2: Add the preview modal**

Create `frontend/src/components/document-preview.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { fetchDocumentBlob, type DocumentVersionInfo } from "@/lib/documents";
import { downloadBlob } from "@/lib/download";
import { Button } from "@/components/ui";

/**
 * In-page preview of one document version. A new browser tab is avoided on
 * purpose: window.open after an async fetch is blocked by popup blockers,
 * because the user-gesture context is gone by the time the blob resolves.
 */
export function DocumentPreview({
  version,
  onClose,
}: {
  version: DocumentVersionInfo;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let created: string | null = null;
    fetchDocumentBlob(version.id)
      .then((blob) => {
        if (!active) return;
        created = URL.createObjectURL(blob);
        setUrl(created);
      })
      .catch(() => active && setUrl(null));
    return () => {
      active = false;
      if (created) URL.revokeObjectURL(created);
    };
  }, [version.id]);

  const isImage = version.content_type.startsWith("image/");

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Preview ${version.original_filename}`}
        className="flex h-full w-full max-w-3xl flex-col rounded-xl border border-border bg-surface p-4 shadow-lg"
      >
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="truncate font-medium text-text">{version.original_filename}</span>
          <span className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => downloadBlob(await fetchDocumentBlob(version.id), version.original_filename)}
            >
              Download
            </Button>
            <Button variant="secondary" size="sm" onClick={onClose}>
              Close
            </Button>
          </span>
        </div>
        {url === null ? (
          <p className="text-muted">Loading…</p>
        ) : isImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={version.original_filename} className="min-h-0 flex-1 object-contain" />
        ) : (
          <iframe src={url} title={version.original_filename} className="min-h-0 flex-1 rounded-lg" />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add the Documents card to the lease detail page**

In `frontend/src/app/app/leases/[leaseId]/page.tsx`, this is the manager view. Add the imports:

```tsx
import {
  listLeaseDocuments,
  uploadDocument,
  uploadVersion,
  deleteDocument,
  type DocumentInfo,
  type DocumentCategory,
} from "@/lib/documents";
import { DocumentPreview } from "@/components/document-preview";
```

Add state alongside the existing state hooks:

```tsx
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [docTitle, setDocTitle] = useState("");
  const [docCategory, setDocCategory] = useState<DocumentCategory>("lease");
  const [previewVersion, setPreviewVersion] = useState<DocumentInfo["current_version"] | null>(null);
  const [deletingDoc, setDeletingDoc] = useState<string | null>(null);
```

In the effect that loads the lease's related data (where `listLeaseTenants`, `listLeaseCharges`
etc. are called), add:

```tsx
    listLeaseDocuments(leaseId)
      .then((d) => {
        if (active) setDocuments(d);
      })
      .catch(() => {
        if (active) setDocuments([]);
      });
```

Add handlers near the other `async function`s:

```tsx
  async function refreshDocuments() {
    setDocuments(await listLeaseDocuments(leaseId));
  }

  async function onAddDocument(file: File) {
    await uploadDocument(leaseId, docTitle || file.name, docCategory, file);
    setDocTitle("");
    await refreshDocuments();
  }

  async function onAddVersion(documentId: string, file: File) {
    await uploadVersion(documentId, file);
    await refreshDocuments();
  }

  async function onDeleteDocument(documentId: string) {
    setDeletingDoc(null);
    await deleteDocument(documentId);
    await refreshDocuments();
  }
```

Add a `Documents` card in the render (after the Tenants card is a natural place), using `Card`,
`Field`, `Input`, `Select`, `Button`, `DataList`, `DataRow`, `EmptyState`, `Badge` — all already
imported on this page:

```tsx
      <Card title="Documents" className="mt-5">
        <div className="mb-4 flex flex-wrap items-end gap-2">
          <div className="min-w-40 flex-1">
            <Field label="Title">
              <Input value={docTitle} onChange={(e) => setDocTitle(e.target.value)} />
            </Field>
          </div>
          <Field label="Category">
            <Select
              value={docCategory}
              onChange={(e) => setDocCategory(e.target.value as DocumentCategory)}
            >
              <option value="lease">Lease</option>
              <option value="report">Report</option>
              <option value="receipt">Receipt</option>
              <option value="other">Other</option>
            </Select>
          </Field>
          <label className={`${linkButtonOutline} cursor-pointer`}>
            Add document
            <input
              type="file"
              accept="application/pdf,image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onAddDocument(file);
                e.target.value = "";
              }}
            />
          </label>
        </div>
        <DataList>
          {documents.map((d) => (
            <DataRow key={d.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  <span className="font-medium text-text">{d.title}</span>{" "}
                  <Badge tone="neutral">{d.category}</Badge>{" "}
                  <span className="text-xs text-muted">v{d.current_version.version_number}</span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPreviewVersion(d.current_version)}
                  >
                    Preview
                  </Button>
                  <label className={`${linkButtonOutline} cursor-pointer text-xs`}>
                    New version
                    <input
                      type="file"
                      accept="application/pdf,image/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) onAddVersion(d.id, file);
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <Button variant="danger" size="sm" onClick={() => setDeletingDoc(d.id)}>
                    Delete
                  </Button>
                </span>
              </div>
            </DataRow>
          ))}
          {documents.length === 0 && (
            <DataRow>
              <EmptyState>No documents yet.</EmptyState>
            </DataRow>
          )}
        </DataList>
      </Card>
```

Render the preview modal and the delete confirm near the other dialogs at the end of the component:

```tsx
      {previewVersion && (
        <DocumentPreview version={previewVersion} onClose={() => setPreviewVersion(null)} />
      )}
      <ConfirmDialog
        open={deletingDoc !== null}
        label="Delete document"
        message="Delete this document and all its versions? This cannot be undone."
        confirmLabel="Yes, delete"
        onConfirm={() => deletingDoc && onDeleteDocument(deletingDoc)}
        onCancel={() => setDeletingDoc(null)}
      />
```

`linkButtonOutline` is already imported on the lease detail page (the M7 renewal links use it). If a
check of the import block shows it missing, add it to the `@/components/ui` import.

- [ ] **Step 4: Add the read-only tenant card**

In `frontend/src/app/app/page.tsx` (tenant branch), inside the per-lease block, add a Documents
card. Add the imports:

```tsx
import { listMyLeaseDocuments, type DocumentInfo } from "@/lib/documents";
import { DocumentPreview } from "@/components/document-preview";
```

Add state:

```tsx
  const [docsByLease, setDocsByLease] = useState<Record<string, DocumentInfo[]>>({});
  const [previewVersion, setPreviewVersion] = useState<DocumentInfo["current_version"] | null>(null);
```

Where the tenant branch loads each lease's charges and maintenance, also load documents:

```tsx
            const docs = await Promise.all(
              l.map((lease) =>
                listMyLeaseDocuments(lease.id)
                  .then((d) => [lease.id, d] as const)
                  .catch(() => [lease.id, []] as const),
              ),
            );
            if (active) setDocsByLease(Object.fromEntries(docs));
```

Add a read-only card in the tenant per-lease render:

```tsx
            <Card title="Documents">
              <DataList>
                {(docsByLease[l.id] ?? []).map((d) => (
                  <DataRow key={d.id}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span>
                        <span className="font-medium text-text">{d.title}</span>{" "}
                        <Badge tone="neutral">{d.category}</Badge>
                      </span>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setPreviewVersion(d.current_version)}
                      >
                        Preview
                      </Button>
                    </div>
                  </DataRow>
                ))}
                {(docsByLease[l.id]?.length ?? 0) === 0 && (
                  <DataRow>
                    <EmptyState>No documents yet.</EmptyState>
                  </DataRow>
                )}
              </DataList>
            </Card>
```

and render the modal once, near the end of the tenant branch return:

```tsx
        {previewVersion && (
          <DocumentPreview version={previewVersion} onClose={() => setPreviewVersion(null)} />
        )}
```

- [ ] **Step 5: Lint, typecheck and build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 6: Check by hand**

The backend must be running. As a landlord, open a lease, add a PDF document, confirm it lists with
`v1`, add a new version and confirm `v2`, click Preview and confirm the PDF renders in the modal,
then Delete through the confirmation. Sign in as that lease's tenant and confirm the Documents card
shows the document with Preview only (no upload or delete), and that the Messages badge shows the
upload notification.

- [ ] **Step 7: Commit and push**

```bash
git add frontend/src/lib/documents.ts frontend/src/components/document-preview.tsx "frontend/src/app/app/leases/[leaseId]/page.tsx" frontend/src/app/app/page.tsx
git commit -m "Add the documents UI, preview modal and tenant view"
git push origin main
```

Then report and wait for approval.

---

### Task 6: End-to-end coverage

**Files:**
- Create: `frontend/e2e/documents.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-5.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/documents.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const landlord = `docs-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const PDF = Buffer.from("%PDF-1.4 e2e minimal");

test("a landlord uploads, versions, previews and deletes a document", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Docs Owner");
  await page.getByPlaceholder("Organization name").fill("Docs Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("13 Docs Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "13 Docs Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Dana Docs");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent").fill("600");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(60));
  await page.getByRole("button", { name: "Add lease" }).click();

  await page.getByRole("link", { name: "13 Docs Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: "Documents" })).toBeVisible();

  await page.getByLabel("Title").fill("Signed Lease");
  await page
    .getByText("Add document")
    .locator("input[type=file]")
    .setInputFiles({ name: "lease.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(page.getByText("Signed Lease")).toBeVisible();
  await expect(page.getByText("v1")).toBeVisible();

  // A new version bumps the counter.
  await page
    .getByText("New version")
    .locator("input[type=file]")
    .setInputFiles({ name: "lease-v2.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(page.getByText("v2")).toBeVisible();

  // Preview opens the modal.
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("dialog", { name: /Preview/ })).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();

  // Delete through the confirmation, and the empty state returns.
  await page.getByRole("button", { name: "Delete" }).first().click();
  await expect(page.getByRole("dialog", { name: "Delete document" })).toBeVisible();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(page.getByText("No documents yet.")).toBeVisible();
});
```

If `getByText("Add document").locator("input[type=file]")` does not resolve (the input is a sibling
inside the `<label>`, which it is here), fall back to `page.locator("label", { hasText: "Add
document" }).locator("input")`. Verify which works when the test first runs; do not leave it
guessed.

- [ ] **Step 2: Restart the backend so the new routes are served**

The e2e hits a live backend. If it was started before Task 2, the document routes 404. The e2e
backend also needs a writable `documents_dir` — the default `"documents"` under `backend/` is fine.

- [ ] **Step 3: Run the new spec**

Run: `cd frontend && npx playwright test documents`
Expected: 1 passed.

- [ ] **Step 4: Run the whole e2e suite**

Run: `cd frontend && npx playwright test --workers=1`
Expected: all pass (30 existing plus this one). Use `--workers=1` to match CI.

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
git add frontend/e2e/documents.spec.ts
git commit -m "Add document management e2e"
git push origin main
```

- [ ] **Step 7: Confirm CI is green**

Run: `gh run list --limit 3`
Expected: the newest run for `main` succeeds. If it fails, read the log before changing anything — the failure is evidence, not noise.

Then report and wait for approval.
