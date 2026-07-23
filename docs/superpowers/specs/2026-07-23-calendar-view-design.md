# Calendar View Design

**Date:** 2026-07-23
**Milestone:** Phase 2 — Calendar view (sub-project 1 of the remaining four)

## Goal

A single organization-wide calendar for the management side (landlord and
property_manager share it). It overlays existing dated records and lets managers
add, edit, and delete their own timed events. Read-only for now on the tenant
side (no tenant calendar this milestone).

## Decisions (from brainstorming)

- **Audience:** management side only. Landlord and property_manager already share
  one manager UI, so this is one org-scoped calendar. No tenant calendar.
- **Overlaid (derived, read-only) records — all four:**
  - `lease_start` — `Lease.start_date`
  - `lease_end` — `Lease.end_date`
  - `rent_due` — `Charge.due_date`
  - `maintenance` — `MaintenanceRequest.created_at`
- **Custom events are timed:** `start_at` / `end_at` datetimes (timezone-aware,
  stored UTC, displayed local). No all-day flag, no recurrence this milestone.
- **Custom event link:** optional `property_id` only (not lease).
- **Frontend:** a hand-built month grid (date math + CSS grid), no calendar
  library.

## Data model

New table `calendar_events` (no enum, so a plain table migration).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | `default=uuid.uuid4` |
| `organization_id` | uuid FK organizations.id | indexed, org scope |
| `title` | String(200) | required |
| `description` | Text | nullable |
| `start_at` | DateTime(timezone=True) | required |
| `end_at` | DateTime(timezone=True) | required, must be `>= start_at` |
| `property_id` | uuid FK properties.id | nullable, `ondelete="SET NULL"` |
| `created_by` | uuid FK users.id | who created it |
| `created_at` | DateTime(timezone=True) | `server_default=func.now()` |

Registered in `app/models/__init__.py`. Migration `down_revision = "591d2d4c3249"`
(current head), hand-written, plain `create_table` / `drop_table` (no enum).

## API

Prefix `/api/v1`. All endpoints require a manager (`require_roles(landlord,
property_manager)`), org-scoped; cross-org access returns 404.

### Aggregation feed

`GET /api/v1/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD`

Returns every entry whose date falls in `[start, end]` (inclusive), across the
five kinds, for the caller's organization. `start`/`end` are required query
params (the frontend always sends the visible month's range).

Response: `list[CalendarEntry]`

```
CalendarEntry:
  kind:      "lease_start" | "lease_end" | "rent_due" | "maintenance" | "event"
  title:     str
  all_day:   bool                 # true for the four derived kinds
  date:      str | null           # "YYYY-MM-DD", set when all_day is true
  start_at:  datetime | null      # set when all_day is false (custom events)
  end_at:    datetime | null      # set when all_day is false (custom events)
  link:      str | null           # derived → target page; custom event → null
  event_id:  uuid | null          # set only when kind == "event"
```

**Timezone correctness:** derived records are calendar dates, not instants.
Sending them as `date` strings (not midnight-UTC datetimes) and placing them on
that exact date avoids a tz-shift that would move, say, an end date onto the
previous day for viewers west of UTC. Custom events are true instants and use
tz-aware `start_at` / `end_at`.

Derived entries and their sources (all filtered `organization_id == caller org`):

| kind | source | date used | title | link |
|---|---|---|---|---|
| `lease_start` | Lease (join Property for address) | `start_date` | `"Lease starts: {address}"` | `/app/leases/{lease_id}` |
| `lease_end` | Lease (join Property for address) | `end_date` | `"Lease ends: {address}"` | `/app/leases/{lease_id}` |
| `rent_due` | Charge | `due_date` | `"Rent due ${amount_due}"` | `/app/leases/{lease_id}` |
| `maintenance` | MaintenanceRequest | `created_at` (date part) | `title` | `/app/maintenance` |
| `event` | CalendarEvent overlapping range | — | `title` | null |

A custom event overlaps the range when `start_at <= end AND end_at >= start`
(compared at day granularity).

### Custom event CRUD

- `POST /api/v1/calendar/events` — body `{title, description?, start_at, end_at, property_id?}`; 201 → `CalendarEventInfo`. `end_at < start_at` → 400. A `property_id` outside the caller's org → 400.
- `PATCH /api/v1/calendar/events/{id}` — same fields, all optional; org-scoped 404; re-validates `end_at >= start_at`.
- `DELETE /api/v1/calendar/events/{id}` — 204; org-scoped 404.

`CalendarEventInfo`: `{id, title, description, start_at, end_at, property_id, created_at}`.

## Frontend

New route `/app/calendar`, in the manager `AppShell`, with a nav entry
"Calendar". Not shown to tenants.

- **Month grid:** compute the weeks for the current month by hand (leading/
  trailing days from adjacent months greyed), render as a CSS grid (7 columns).
  Previous / next month buttons; a "Today" button to jump back.
- **Fetch:** on month change, `GET /api/v1/calendar?start=<first visible day>&end=<last visible day>` (the visible range includes the leading/trailing days).
- **Chips:** each day cell lists its entries as small chips, colored by kind —
  `lease_end` danger, `rent_due` warning, `lease_start` brand-blue, `maintenance`
  neutral, `event` brand. All-day entries placed by `date`; timed events placed
  by the local date of `start_at`, chip shows the local start time.
- **Interactions:**
  - Click a derived chip → navigate to its `link`.
  - Click a custom-event chip → edit dialog (title / description / start / end /
    optional property), with a Delete that goes through `ConfirmDialog`.
  - Click an empty area of a day → "Add event" dialog pre-filled with that day.
- **Timezone:** `datetime-local` inputs are local; convert to ISO (with the
  browser's offset) before POST/PATCH. Display converts `start_at` back to local.

New files: `frontend/src/lib/calendar.ts` (client + types), `frontend/src/app/app/calendar/page.tsx` (page), and a small `MonthGrid` component (may live in the page file if it stays short). Nav entry added to `AppShell`.

## Testing

**Backend** (`backend/tests/test_calendar.py`):
- `CalendarEvent` model round-trip.
- Create event → 201; `end_at < start_at` → 400; `property_id` from another org → 400.
- Patch event; cross-org patch/delete → 404.
- Delete event → 204, row gone.
- Feed returns a custom event within range and omits one outside it.
- Feed returns each derived kind: seed a lease (start+end in range), a charge
  (due in range), a maintenance request, assert one entry per kind with the
  right `link` and `date`.
- Feed is org-scoped: a second org's records never appear.

**e2e** (`frontend/e2e/calendar.spec.ts`):
- Manager signs up, creates a property and a lease whose end date is this month.
- Opens Calendar; the lease-end entry shows on the calendar.
- Adds a custom event (title + start/end); it appears on its day.
- Edits the event's title; the chip updates.
- Deletes it through the confirmation; it disappears.

## Out of scope (this milestone)

- Tenant calendar (`/me/...` feed + portal UI).
- All-day custom events (an `all_day` flag) and recurrence.
- Linking custom events to a lease (only property).
- Multi-day rendering of a timed event across cells — a timed event is shown on
  the local date of its `start_at` only.

## Task breakdown (for the plan)

- **T1** — `CalendarEvent` model, register, migration (`down_revision =
  591d2d4c3249`), round-trip test.
- **T2** — Schemas (`CalendarEventCreate`, `CalendarEventInfo`) + CRUD endpoints
  (create/patch/delete) with validation and org scope; tests.
- **T3** — Feed endpoint `GET /api/v1/calendar` aggregating the four derived
  kinds plus custom events; tests (each kind, range, org scope).
- **T4** — Frontend `calendar.ts` client + `/app/calendar` month-grid page
  rendering the feed + nav entry; lint/build.
- **T5** — Add/edit/delete custom-event dialogs (ConfirmDialog for delete),
  timezone conversion; lint/build.
- **T6** — e2e `calendar.spec.ts` + full suite + CI green.

Each task ends with: full test run → ruff sequence (`format`, `check --fix`,
`check`, `format --check` from `backend/`) → commit → push to
`https://github.com/Keith-hoka/rental_management` → report → wait for approval.
