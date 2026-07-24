# Property Inspections Design

**Date:** 2026-07-24
**Milestone:** Phase 2 — Property inspections (the remaining sub-project).

## Goal

Managers schedule and complete property inspections (move-in / move-out /
routine) with a date, overall note, per-area condition checklist, and photos;
tenants read their own lease's inspection reports.

## Decisions (from brainstorming)

- **Structure:** an inspection record **plus a per-item checklist** (area +
  condition + note).
- **Links:** `property_id` required; `lease_id` optional (move-in/out are
  tenancy-specific).
- **Lifecycle:** `scheduled -> completed`; managers edit status / note / date /
  items.
- **Checklist items:** area (free text) + condition (`good/fair/poor`) +
  optional note. Sent as a whole array on create/edit (replace); no per-item
  photos (photos stay at the inspection level).
- **Photos:** reuse the maintenance image pipeline (`save_image` -> public
  `/uploads`), a JSON list of URLs on the inspection.
- **Audience:** managers create/edit/delete; tenants read their lease's
  inspections.

## Model

Two new tables (three PG enums: `inspectiontype`, `inspectionstatus`,
`inspectioncondition`).

`inspections`:

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
| `image_urls` | JSON | default `list`, `/uploads/...` strings |
| `created_by` | uuid FK users.id | |
| `created_at`, `updated_at` | DateTime(tz) | server defaults; `updated_at` `onupdate` |

`inspection_items`:

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `inspection_id` | uuid FK inspections.id | `ondelete="CASCADE"`, indexed |
| `position` | Integer | preserves the form order |
| `area` | String(100) | free text, e.g. "Kitchen" |
| `condition` | Enum(InspectionCondition) | `good`, `fair`, `poor` |
| `note` | Text | nullable |

Migration `down_revision = "697ac076b56e"` (head), hand-written; `downgrade`
drops `inspection_items` then `inspections`, then
`sa.Enum(name="inspectioncondition").drop(op.get_bind())`,
`sa.Enum(name="inspectiontype").drop(...)`,
`sa.Enum(name="inspectionstatus").drop(...)`. Verify upgrade -> downgrade ->
upgrade.

## Backend

Manager endpoints require `require_roles(landlord, property_manager)`,
org-scoped, cross-org 404. Items are handled as a whole array (replace), never
per-item endpoints.

- `POST /api/v1/inspections` — body `{property_id, lease_id?, type, status?, scheduled_for, note?, items: [{area, condition, note?}]}`; `property_id` must be in the org (else 400); `lease_id`, if given, in the org (else 400); `status` defaults `scheduled`; items created with `position` = array index. -> 201 `InspectionInfo`.
- `GET /api/v1/inspections?property_id=` — the org's inspections, newest `scheduled_for` first, optional property filter; each includes its items (ordered by `position`).
- `PATCH /api/v1/inspections/{id}` — `status` / `note` / `scheduled_for` / `items` all optional. If `items` is provided (including `[]`), the inspection's items are **replaced** (delete existing, `flush`, insert new by index); if `items` is omitted, items are left unchanged. Cross-org 404.
- `POST /api/v1/inspections/{id}/images` — `UploadFile`; `save_image` then append to `image_urls`; returns updated `InspectionInfo`; cross-org 404.
- `DELETE /api/v1/inspections/{id}` — 204 (items cascade); unlink stored image files best-effort; cross-org 404.
- **Tenant:** `GET /api/v1/me/leases/{lease_id}/inspections` — inspections on a lease the caller is a tenant of (reuse `_tenant_lease_or_404` from `documents.py`). Read-only, items included.

Schemas: `InspectionItemIn {area, condition, note?}`, `InspectionItemInfo {id,
area, condition, note}`, `InspectionCreate {..., items: list[InspectionItemIn]}`,
`InspectionUpdate {status?, note?, scheduled_for?, items?: list[InspectionItemIn]
| None}`, `InspectionInfo {id, property_id, lease_id, type, status,
scheduled_for, note, image_urls, items: list[InspectionItemInfo], created_at}`.
`InspectionInfo` is built by hand (nested items), not `from_attributes`.

## Frontend

- **Manager `/app/inspections`** (nav "Inspections"): a create form (property
  `Select` from `listProperties`, optional lease `Select`, type `Select`, date,
  note) **plus a dynamic item editor** — repeatable rows of area `Input` +
  condition `Select` (good/fair/poor) + note `Input` + remove button, and an
  "Add item" button. A list of inspections, each showing type · status `Badge` ·
  date · property · its checklist items (area — condition badge — note), with:
  **Edit** (status / note / date / items), **photo upload** (`<input type=file>`
  rendering thumbnails from `/uploads`), and **Delete** via `ConfirmDialog`.
- **Tenant portal:** a read-only "Inspections" `Card` per lease block: type ·
  date · status · note · items · photo thumbnails, from
  `GET /me/leases/{id}/inspections`.
- New files: `frontend/src/lib/inspections.ts`,
  `frontend/src/app/app/inspections/page.tsx`; nav entry in `app-shell.tsx`;
  tenant card + fetch in `frontend/src/app/app/page.tsx`.
- Image URLs are relative (`/uploads/...`); prefix with `API_BASE_URL` for
  `<img src>` (as maintenance images do).

## Testing

**Backend:**
- Model round-trip (inspection + items).
- Create with items (property required; foreign property 400; foreign lease
  400); items returned in `position` order. List (org-scoped, property filter).
  Patch status scheduled -> completed; patch `items` replaces them; patch
  without `items` leaves them. Image upload appends a URL. Delete 204 (items
  gone). Cross-org get/patch/delete 404.
- Tenant `/me` lists own lease's inspections with items; another lease's tenant
  does not see them.

**e2e:**
- Manager signs up, creates a property, opens `/app/inspections`, schedules an
  inspection with one checklist item, edits it to completed, and sees the
  "completed" status and the item.

## Out of scope (this milestone)

- Per-item photos. Showing scheduled inspections on the calendar (cross-feature;
  possible later). Inspection PDF/report export. Notifications on scheduling /
  completion.

## Task breakdown (for the plan)

- **I-T1** — `InspectionType` / `InspectionStatus` / `InspectionCondition` enums
  + `Inspection` + `InspectionItem` models + migration (three enums, two tables,
  reversible) + round-trip test.
- **I-T2** — Schemas (nested items) + manager create / list / patch / delete
  endpoints, with the whole-array item replace and validation (org scope);
  tests.
- **I-T3** — Photo upload endpoint (reuse `save_image`) + tenant
  `/me/leases/{id}/inspections` endpoint; tests.
- **I-T4** — Frontend `inspections.ts` + `/app/inspections` manager page (create
  with item editor / list / edit / upload / delete) + nav; lint/build.
- **I-T5** — Tenant portal read-only Inspections card (with items) + fetch;
  lint/build.
- **I-T6** — e2e (schedule with item -> complete) + full suite + CI green.

Each task ends with: full test run -> ruff sequence (from `backend/`) -> commit
-> push to `https://github.com/Keith-hoka/rental_management` -> report -> wait.
