# Milestone 5: Maintenance Requests — Design

**Date:** 2026-07-22
**Status:** Approved (pending spec review)

## Goal

Tenants report maintenance issues on their lease — with a title, description, priority, and
photos — and track status; landlords/PMs triage and work them through a status workflow.

## Architecture

- A `MaintenanceRequest` row belongs to a lease (and denormalizes the property + organization),
  created by the reporting tenant. Priority and status are enums; photos are stored via the
  existing image-upload mechanism (a JSON list of `/uploads/...` URLs).
- Tenant endpoints (under `/me`) let a lease's tenant create, list, attach images to, and cancel
  their own requests. Manager endpoints (org-scoped) list, view, and update (status/priority) all
  of the organization's requests.
- The property-image save logic is extracted into a shared `save_image` helper reused by both
  property and maintenance uploads.

## Tech Stack

- Backend: FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL (existing). No new dependency.
- Frontend: Next.js (existing). No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- Migration adds two PostgreSQL enums: follow the established enum-migration handling — create the
  enum types, drop them in `downgrade` (`sa.Enum(name=...).drop(op.get_bind())` after
  `drop_table`), and verify upgrade -> downgrade -> upgrade. Current head: `4f6bf92b0607`.

---

## Product Rules (confirmed)

- **Who creates:** only a tenant of the lease (a `LeaseTenant` of that lease). Managers triage but
  do not create requests.
- **Priority:** `low` / `medium` / `high` / `urgent`, chosen by the tenant at creation
  (default `medium`); a manager can change it.
- **Status:** `open` / `in_progress` / `resolved` / `cancelled`. A manager advances
  `open -> in_progress -> resolved`. Cancelling (`-> cancelled`) is allowed for the reporting
  tenant or a manager, only from `open` or `in_progress`.
- **Images:** the reporting tenant uploads photos to their own request (reusing the existing
  upload mechanism); managers view them. Manager image upload is out of scope for v1.
- **Notifications** (email on new request / status change) are **out of scope** — deferred to a
  later Notifications milestone.

## Data Model

New file `app/models/maintenance.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MaintenancePriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class MaintenanceStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    cancelled = "cancelled"


class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"), index=True)
    lease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[MaintenancePriority] = mapped_column(
        Enum(MaintenancePriority), default=MaintenancePriority.medium
    )
    status: Mapped[MaintenanceStatus] = mapped_column(
        Enum(MaintenanceStatus), default=MaintenanceStatus.open
    )
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

Register `MaintenanceRequest`, `MaintenancePriority`, `MaintenanceStatus` in
`app/models/__init__.py`. `lease_id` `ondelete=CASCADE` (consistent with the other lease children).
One migration creates the table and the two enums; downgrade drops the table then both enum types.

## Shared upload helper

New file `app/core/uploads.py`: `async def save_image(file: UploadFile) -> str` — validates the
content type (the existing `IMAGE_EXTENSIONS` map), writes the bytes to `settings.upload_dir`, and
returns `/uploads/{name}`. Refactor `app/routers/properties.py`'s `upload_image` to call it (the
property-images tests/e2e cover the refactor).

## Schemas

New file `app/schemas/maintenance.py`:

```python
class MaintenanceCreate(BaseModel):
    title: str
    description: str
    priority: MaintenancePriority = MaintenancePriority.medium


class MaintenanceUpdate(BaseModel):
    status: MaintenanceStatus | None = None
    priority: MaintenancePriority | None = None


class MaintenanceInfo(BaseModel):
    id: uuid.UUID
    property_address: str
    title: str
    description: str
    priority: MaintenancePriority
    status: MaintenanceStatus
    image_urls: list[str]
    reported_by: str
    created_at: datetime
```

## Endpoints (`app/routers/maintenance.py`, mounted in `main.py`)

**Tenant** (`get_current_user`; the caller must be a `LeaseTenant` of the lease / the request's
lease, else 404):

- `POST /api/v1/me/leases/{lease_id}/maintenance` — body `MaintenanceCreate` -> 201
  `MaintenanceInfo`. Derives `property_id`/`organization_id` from the lease; `created_by` = caller;
  `status = open`.
- `GET /api/v1/me/leases/{lease_id}/maintenance` -> `list[MaintenanceInfo]` for that lease, newest
  first.
- `POST /api/v1/me/maintenance/{request_id}/images` — multipart image upload; caller must be the
  request's `created_by`; appends the saved URL to `image_urls`; returns `MaintenanceInfo`.
- `POST /api/v1/me/maintenance/{request_id}/cancel` — caller must be `created_by`; sets
  `status = cancelled` only from `open`/`in_progress` (else 409); returns `MaintenanceInfo`.

**Manager** (`manager = require_roles(landlord, property_manager)`; org-scoped, 404 otherwise):

- `GET /api/v1/maintenance` (optional `?status=`) -> `list[MaintenanceInfo]`, org-wide, newest
  first.
- `GET /api/v1/maintenance/{request_id}` -> `MaintenanceInfo`.
- `PATCH /api/v1/maintenance/{request_id}` — body `MaintenanceUpdate` (status and/or priority) ->
  `MaintenanceInfo`.

A helper builds `MaintenanceInfo` by joining `Property.address` and the reporter's `User.name`.

## Frontend

- `frontend/src/lib/maintenance.ts`: types (`MaintenancePriority`, `MaintenanceStatus`,
  `MaintenanceInfo`) and functions — tenant: `createMaintenance(leaseId, body)`,
  `listLeaseMaintenance(leaseId)`, `uploadMaintenanceImage(id, file)`, `cancelMaintenance(id)`;
  manager: `listMaintenance(status?)`, `getMaintenance(id)`, `updateMaintenance(id, body)`.
- **Tenant portal** (`app/page.tsx`, tenant branch): under each lease, a **Maintenance** section —
  a "Report an issue" form (title, description, priority) and a list of that lease's requests, each
  row showing priority/status badges, its images, an **Add image** control that uploads to that
  request, and a **Cancel** button on `open`/`in_progress` ones.
- **Manager page** `app/app/maintenance/page.tsx`: a list of the org's requests (property, title,
  priority/status badges, reporter) with a status filter; each row expands/links to change status
  and priority and to view images. Add a **Maintenance** link to the manager dashboard nav.

## Testing

**Backend (pytest, primary):**

- Model: insert; `lease_id` CASCADE deletes requests with the lease; enum columns round-trip.
- Tenant create: a lease's tenant creates (201, `status=open`, priority stored); a non-tenant of
  that lease -> 404; a manager (not a `LeaseTenant`) -> 404.
- Tenant list: returns only that lease's requests.
- Tenant image upload: appends a URL; a non-owner -> 404; a bad content type -> 400.
- Tenant cancel: owner cancels an `open` request (`status=cancelled`); cancelling a `resolved`
  one -> 409; a non-owner -> 404.
- Manager list/get/patch: org-scoped; `GET /maintenance` lists the org's requests and filters by
  `?status=`; `PATCH` changes status/priority; cross-org `GET`/`PATCH` -> 404; a tenant calling a
  manager route -> 403.

**Frontend e2e (light):** a landlord logs in, opens the **Maintenance** page from the dashboard,
and sees its empty state. The full tenant report -> manager triage flow is backend-tested (tenant
login is not easily e2e-able).

## Out of Scope (later milestones)

- Email notifications (new request / status change) — Notifications milestone.
- AI categorization / priority detection / cost estimation / contractor recommendation / vision —
  AI Maintenance Assistant.
- Contractor assignment, comment threads, manager image upload, SLA timers.

## File Structure

- Create: `backend/app/models/maintenance.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_maintenance_requests.py`
- Create: `backend/app/core/uploads.py`
- Modify: `backend/app/routers/properties.py` (use `save_image`)
- Create: `backend/app/schemas/maintenance.py`
- Create: `backend/app/routers/maintenance.py`
- Modify: `backend/app/main.py` (mount maintenance router)
- Create: `backend/tests/test_maintenance_model.py`, `test_maintenance_tenant.py`,
  `test_maintenance_manager.py`
- Create: `frontend/src/lib/maintenance.ts`
- Modify: `frontend/src/app/app/page.tsx` (tenant Maintenance section; manager nav link)
- Create: `frontend/src/app/app/maintenance/page.tsx`
- Modify: `frontend/e2e/` (manager Maintenance page empty-state spec)
