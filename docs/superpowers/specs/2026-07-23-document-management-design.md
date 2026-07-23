# Milestone 9.2: Document Management — Design

**Date:** 2026-07-23
**Status:** Approved (pending spec review)

**Part of:** Phase 2, sub-project 2 of 6. M9.1 (payment CSV export) is complete. The remaining
Phase 2 pieces are inspections, full-text search, a calendar view, and monthly reports.

## Goal

A manager stores a lease's documents — signed leases, condition reports, receipts — as PDFs or
images, keeps a version history of each, and both manager and tenant can preview or download them.
Files are served only through an authenticated endpoint, never the public uploads path.

## Architecture

- Documents attach to a **lease**, reusing its `LeaseTenant` roster for tenant visibility.
- A **two-layer model**: a `Document` is one logical document ("Signed Lease"); a
  `DocumentVersion` is one uploaded file. Re-uploading produces a new version and retains the old,
  so "which version is in force" stays answerable.
- **Files are stored outside the public `/uploads` mount.** `/uploads` is served by `StaticFiles`
  with no auth, so anything under it is downloadable by URL. A signed lease contains personal data,
  so documents go in a separate `documents_dir` that is **not** statically mounted, and the only
  path to a file is an authenticated download endpoint that checks, per request, that the caller
  manages or is a tenant of the lease. Storing under `/uploads` and adding an endpoint on top would
  leave the file reachable at `/uploads/<name>` regardless — the private directory is the point.
- `save_image` is untouched: property images stay public by design. Documents get their own
  `save_document` helper and their own directory.

## Tech Stack

- Backend: FastAPI (`FileResponse` for streaming), async SQLAlchemy 2.0, Alembic, PostgreSQL. No
  new dependency.
- Frontend: Next.js (existing). Browser-native PDF and image rendering. No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- The migration adds **one PostgreSQL enum** (`documentcategory`). Follow the established
  enum-migration handling: create the type in `upgrade`, drop it in `downgrade` after the tables
  (`sa.Enum(name="documentcategory").drop(op.get_bind())`), and verify upgrade -> downgrade ->
  upgrade. Current head: `a4d0104d02b0`.
- Accessible names introduced: `Documents`, `Add document`, `New version`, `Preview`, `Download`,
  `Title`, `Category`. Playwright matches names by **substring**; check each against what else is
  on the lease detail page (it already has `Delete`, `Yes, delete`, `Invite`, `Revoke`).

---

## Product Rules (confirmed)

- **Documents belong to a lease.** Tenant visibility follows the existing `LeaseTenant` link.
- **Real version history**, not just multiple files. A `Document` has ordered `DocumentVersion`
  rows; the current version is the highest `version_number`.
- **Authenticated download only.** No public URL. Every download resolves the version to its lease
  and checks the caller is a manager of the organization or a tenant of that lease.
- **PDF and images** (`application/pdf` plus the image types `save_image` already allows). Word and
  other types are out.
- **Managers** upload, add versions, list, download, and delete. **Tenants** list and download
  their own lease's documents; they do not upload or delete.
- **Deleting removes the whole document, all versions, and their files.** There is no delete of a
  single version: the point of a version history is that it is kept, and removing a middle version
  defeats it.
- **Uploading notifies the lease's tenants.** Both creating a document and adding a new version
  write an in-app notification (no email) to the lease's `LeaseTenant`s, linking to the lease, so a
  tenant sees when a signed lease or receipt is shared without polling. This reuses
  `notify_users` / `lease_tenant_user_ids` exactly as M7 renewal does.

---

## Data Model

New enum and models in `backend/app/models/document.py`:

```python
class DocumentCategory(str, enum.Enum):
    lease = "lease"
    report = "report"
    receipt = "receipt"
    other = "other"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    lease_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leases.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[DocumentCategory] = mapped_column(Enum(DocumentCategory))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column()
    stored_name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column()
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

`stored_name` is the on-disk filename in `documents_dir`; it is never exposed as a URL. Register
both models and `DocumentCategory` in `app/models/__init__.py`.

## Storage

`backend/app/core/config.py` gains `documents_dir: str = "documents"`. It is **not** passed to
`app.mount(...)` — that is the whole security boundary.

`backend/app/core/uploads.py` gains:

```python
DOCUMENT_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def save_document(file: UploadFile) -> tuple[str, int]:
    """Validate and store a document; return (stored_name, size_bytes). 400 on bad type."""
```

It writes to `settings.documents_dir`, returns the generated `stored_name` and the byte count. A
`delete_document_file(stored_name)` unlinks from the same directory (`missing_ok=True`), mirroring
`delete_image_file`.

---

## Endpoints (`backend/app/routers/documents.py`, mounted in `main.py`)

Manager, `require_roles(landlord, property_manager)`, org-scoped:

| Method | Path | Behaviour |
|---|---|---|
| POST | `/leases/{lease_id}/documents` | multipart `title`, `category`, `file` -> creates `Document` + version 1; notifies the lease's tenants |
| POST | `/documents/{document_id}/versions` | multipart `file` -> next `version_number`; notifies the lease's tenants |
| GET | `/leases/{lease_id}/documents` | list, each with current version + version count |
| GET | `/documents/{document_id}/versions` | all versions, newest first |
| DELETE | `/documents/{document_id}` | delete the document, its versions, and their files |

Tenant, `get_current_user` + `LeaseTenant` check:

| Method | Path | Behaviour |
|---|---|---|
| GET | `/me/leases/{lease_id}/documents` | the caller's own lease's documents |

Download, `get_current_user`, **either role**:

| Method | Path | Behaviour |
|---|---|---|
| GET | `/documents/versions/{version_id}/download` | stream the file with its content type |

The download handler resolves `version -> document -> lease`, then allows the request only if the
user is a manager of `document.organization_id` **or** a `LeaseTenant` of `document.lease_id`; a
404 otherwise. It returns `FileResponse(path, media_type=content_type, filename=original_filename)`.
This is the single choke point for file access, which is why the files live outside `/uploads`.

Schemas (`backend/app/schemas/document.py`): `DocumentInfo` (id, title, category, version_count,
current version's id/filename/created_at), `DocumentVersionInfo` (id, version_number,
original_filename, content_type, size_bytes, created_at).

---

## Frontend

**Lease detail (`/app/leases/[leaseId]`)** gains a `Documents` card:

- An upload form: `Title` input, `Category` select, a file input, `Add document` button.
- A list: each document shows its title, a category badge, the current version (`v3`), the version
  count, and per-row `Preview`, `Download`, `New version` (a file input), `Delete` (through the
  existing `ConfirmDialog`), and an expander for the version history. Each historical version has
  its own `Preview` / `Download`.

**Tenant portal** (dashboard tenant branch): a read-only `Documents` card per lease — list plus
`Preview` / `Download`, no upload or delete.

**Preview is an in-page modal, not a new browser tab.** `window.open(objectUrl)` after an async
fetch is blocked by popup blockers, because the user-gesture context is gone by the time the blob
resolves. Instead, `Preview` fetches the blob (authenticated), and shows it in a modal — a PDF in
an `<iframe>`, an image in an `<img>` — revoking the object URL on close. No popup blocking, and a
self-contained UX.

`frontend/src/lib/documents.ts`: `listLeaseDocuments`, `listMyLeaseDocuments`, `uploadDocument`,
`uploadVersion`, `listVersions`, `deleteDocument`, and `fetchDocumentBlob(versionId)` — the last
being an authenticated fetch returning a `Blob`, reusing the token accessor the CSV export uses.
`downloadBlob` (from M9.1) is reused for the download action.

---

## Testing

Backend (`backend/tests/test_documents.py` unless noted):

1. Migration round-trip: upgrade -> downgrade -> upgrade.
2. Upload creates a `Document` and a version 1; the response carries the title, category and
   version count 1.
3. A second upload to the same document is version 2, and the list reports the current version as
   2 with a version count of 2.
4. Reading, listing, versioning or deleting another organization's document is a 404.
5. A tenant lists their own lease's documents through the `/me` endpoint, and downloads a version
   through the shared download endpoint (there is no `/me` download route — the one download
   endpoint serves both roles and gates on membership).
6. **A tenant of a different lease downloading a version is a 404** — the access-control core.
7. **An unauthenticated download request is a 401**, and no endpoint response exposes a `/uploads`
   URL for a document (the files are private).
8. An unsupported content type (`text/plain`) is rejected with 400.
9. Deleting a document removes it, its versions, and unlinks the files from `documents_dir`.
10. Uploading a document (and adding a version) writes a `document_uploaded` notification for the
    lease's onboarded tenant.

e2e (`frontend/e2e/documents.spec.ts`): a manager uploads a PDF to a lease, sees it listed with
version 1, uploads a second file as a new version and sees `v2`, opens the preview modal, and
deletes the document through the confirmation. The PDF bytes are not asserted — that is tests 2-3's
job; the e2e proves the flow and the modal.

---

## Out of Scope

- Documents attached to a property or the organization rather than a lease.
- Deleting or rolling back a single version.
- Email notification of uploads (in-app only, matching the renewal and maintenance notifications).
- Full-text search inside documents (that is the separate search sub-project, over metadata only).
- Word / `.docx` or other non-PDF, non-image types.
- Signing or e-signature flows.
- Thumbnails or server-side PDF rendering; the browser renders natively.

---

## File Structure

| File | Change |
|---|---|
| `backend/app/models/document.py` | new: `DocumentCategory`, `Document`, `DocumentVersion` |
| `backend/app/models/__init__.py` | register the three |
| `backend/alembic/versions/<rev>_add_documents.py` | new migration (one enum) |
| `backend/app/core/config.py` | add `documents_dir` |
| `backend/app/core/uploads.py` | `save_document`, `delete_document_file` |
| `backend/app/schemas/document.py` | new |
| `backend/app/routers/documents.py` | new, mounted in `main.py` |
| `backend/tests/test_documents.py` | new |
| `frontend/src/lib/documents.ts` | new |
| `frontend/src/app/app/leases/[leaseId]/page.tsx` | the Documents card |
| `frontend/src/components/document-preview.tsx` | the preview modal |
| `frontend/src/app/app/page.tsx` | tenant portal read-only Documents card |
| `frontend/e2e/documents.spec.ts` | new |

## Task Breakdown

- **T1** models + enum + migration + round-trip
- **T2** `save_document` + `documents_dir` + upload / add-version endpoints + tenant notification +
  tests 2, 3, 8, 10
- **T3** list / versions / delete + tenant `/me` list + tests 4, 9 (test 5's cross-lease download
  is in T4 with the download endpoint)
- **T4** authenticated download + access control + tests 6, 7
- **T5** frontend: Documents card, upload, version history, preview modal, tenant read-only
- **T6** e2e + CI green
