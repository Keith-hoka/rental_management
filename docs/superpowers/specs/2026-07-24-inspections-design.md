# Property Inspections Design

**Date:** 2026-07-24
**Milestone:** Phase 2 — Property inspections (the remaining sub-project).

## Goal

Managers schedule and complete property inspections (move-in / move-out /
routine) with a date, overall note, and photos; tenants read their own lease's
inspection reports.

## Decisions (from brainstorming)

- **Structure:** one inspection record (no per-item checklist).
- **Links:** `property_id` required; `lease_id` optional (move-in/out are
  tenancy-specific).
- **Lifecycle:** `scheduled -> completed`; managers edit status / note / date.
- **Photos:** reuse the maintenance image pipeline (`save_image` -> public
  `/uploads`), stored as a JSON list of URLs.
- **Audience:** managers create/edit/delete; tenants read their lease's
  inspections.

## Model

New table `inspections` (two PG enums: `inspectiontype`, `inspectionstatus`).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `organization_id` | uuid FK organizations.id | indexed |
| `property_id` | uuid FK properties.id | required, `ondelete="CASCADE"`, indexed |
| `lease_id` | uuid FK leases.id | nullable, `ondelete="SET NULL"`, indexed |
| `type` | Enum(InspectionType) | `move_in`, `move_out`, `routine` |
| `status` | Enum(InspectionStatus) | `scheduled` (default), `completed` |
| `scheduled_for` | Date | the inspection date |
| `note` | Text | nullable |
| `image_urls` | JSON | default `list`, `/uploads/...` strings (like maintenance) |
| `created_by` | uuid FK users.id | |
| `created_at`, `updated_at` | DateTime(tz) | server defaults; `updated_at` `onupdate` |

Migration `down_revision = "697ac076b56e"` (head), hand-written; `downgrade`
drops the table then `sa.Enum(name="inspectiontype").drop(op.get_bind())` and
`sa.Enum(name="inspectionstatus").drop(op.get_bind())`. Verify upgrade ->
downgrade -> upgrade.

## Backend

Manager endpoints require `require_roles(landlord, property_manager)`,
org-scoped, cross-org 404.

- `POST /api/v1/inspections` — body `{property_id, lease_id?, type, status?, scheduled_for, note?}`; `property_id` must be in the org (else 400); `lease_id`, if given, must be in the org (else 400); `status` defaults to `scheduled`. -> 201 `InspectionInfo`.
- `GET /api/v1/inspections?property_id=` — the org's inspections, newest `scheduled_for` first, optionally filtered by property.
- `PATCH /api/v1/inspections/{id}` — update `status` / `note` / `scheduled_for`; cross-org 404.
- `POST /api/v1/inspections/{id}/images` — `UploadFile`; `save_image` then append to `image_urls`; returns the updated `InspectionInfo`; cross-org 404.
- `DELETE /api/v1/inspections/{id}` — 204; also unlink the stored image files (best-effort, like documents/maintenance); cross-org 404.
- **Tenant:** `GET /api/v1/me/leases/{lease_id}/inspections` — the inspections on a lease the caller is a tenant of (reuse the `_tenant_lease_or_404` pattern from `documents.py`). Read-only.

`InspectionInfo`: `{id, property_id, lease_id, type, status, scheduled_for, note, image_urls, created_at}` (`from_attributes`).

## Frontend

- **Manager `/app/inspections`** (nav "Inspections"): a create form (property
  `Select` from `listProperties`, optional lease `Select`, type `Select`, date,
  note) and a list. Each row shows type · a status `Badge` · date · property
  address, with: an **Edit** control (status `Select` scheduled/completed, note,
  date), a **photo upload** (`<input type=file>` like the property/maintenance
  upload) rendering thumbnails from `/uploads`, and **Delete** via
  `ConfirmDialog`.
- **Tenant portal:** a read-only "Inspections" `Card` in each lease block
  (mirroring the Documents card): type · date · status · note · photo thumbnails,
  from `GET /me/leases/{id}/inspections`.
- New files: `frontend/src/lib/inspections.ts`,
  `frontend/src/app/app/inspections/page.tsx`; nav entry in `app-shell.tsx`;
  tenant card + fetch in `frontend/src/app/app/page.tsx`.

Image URLs are relative (`/uploads/...`); prefix with `API_BASE_URL` for the
`<img src>` (the same way maintenance images are shown).

## Testing

**Backend:**
- Model round-trip.
- Create (property required; foreign property 400; foreign lease 400); list
  (org-scoped, property filter); patch status scheduled -> completed; image
  upload appends a URL; delete 204; cross-org get/patch/delete 404.
- Tenant `/me` lists own lease's inspections; a tenant of another lease gets 404
  / does not see them.

**e2e:**
- Manager signs up, creates a property, opens `/app/inspections`, schedules an
  inspection, edits it to completed, and sees the "completed" status.

## Out of scope (this milestone)

- Per-item / per-room checklist. Showing scheduled inspections on the calendar
  (cross-feature; possible later). Inspection PDF/report export. Notifications on
  scheduling/completion.

## Task breakdown (for the plan)

- **I-T1** — `InspectionType` + `InspectionStatus` enums + `Inspection` model +
  migration (two enums, reversible) + round-trip test.
- **I-T2** — Schemas + manager create / list / patch / delete endpoints
  (validation, org scope); tests.
- **I-T3** — Photo upload endpoint (reuse `save_image`) + tenant `/me/leases/{id}/
  inspections` endpoint; tests.
- **I-T4** — Frontend `inspections.ts` + `/app/inspections` manager page (create /
  list / edit / upload / delete) + nav; lint/build.
- **I-T5** — Tenant portal read-only Inspections card + fetch; lint/build.
- **I-T6** — e2e (schedule -> complete) + full suite + CI green.

Each task ends with: full test run -> ruff sequence (from `backend/`) -> commit
-> push to `https://github.com/Keith-hoka/rental_management` -> report -> wait.
