# Milestone 8.1: Contractor Assignment — Design

**Date:** 2026-07-23
**Status:** Approved (pending spec review)

**Part of:** Milestone 8, sub-project 1 of 3. M8.2 adds rent overdue/upcoming views; M8.3 adds the
dashboard occupancy-rate and maintenance-status charts. M8.1 comes first because it is the only
one of the three that changes the data model, and settling here that assignment does **not**
introduce a new maintenance status is what makes M8.3's status chart safe to build.

## Goal

A manager keeps a directory of the contractors they use, assigns one to a maintenance request, and
the contractor receives a work order by email. The tenant sees who is coming and how to reach them.

## Architecture

- A `Contractor` row belongs to an organization. A maintenance request points at one through a
  nullable `contractor_id`; reassignment overwrites it.
- Assignment is **orthogonal to status**. It records who is doing the work, not that work has
  started: a job assigned today may not begin until next week, and folding the two together would
  make `in_progress` mean less than it does now.
- Assignment lives on its own endpoints rather than the existing maintenance `PATCH`. The reason is
  concrete, not stylistic: `MaintenanceUpdate` uses `field: X | None = None`, where `None` means
  "not supplied", so `contractor_id: null` and an omitted key are indistinguishable and unassigning
  could not be expressed. A dedicated endpoint also puts the outbound email behind a route named
  for what it does.
- The work-order email reuses `safe_send` from `app/services/notify.py`, which logs and swallows
  failures. A mistyped contractor address must not fail the assignment.

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
- This migration adds **no enum**: a new table plus one nullable FK column, both reversed in
  `downgrade`. Verify upgrade -> downgrade -> upgrade. Current head: `0e4536ea7e9a`.
- Accessible names are pinned by 25 Playwright specs. Names introduced here: `Contractors`,
  `Add contractor`, `Assign`, `Unassign`, `Trade`, `Contractor`. No new element may duplicate a
  name already on the same page.

---

## Product Rules (confirmed)

- **Contractors are an entity, not free text.** Managers reuse the same handful of trades, so a
  per-organization directory is worth its CRUD: no retyping a phone number per job, and no three
  spellings of the same plumber.
- **Assignment does not change status.** The manager still moves `open -> in_progress -> resolved`
  themselves.
- **One contractor per request.** Reassignment overwrites. There is no assignment history table:
  the change leaves a notification behind, which is enough of a trail for now.
- **A contractor's email is optional.** A phone-only contractor must still be recordable. With no
  email on file, no work order is sent and the UI says so rather than silently doing nothing.
- **The tenant sees the assigned contractor's name and phone**, so they know who is coming and can
  arrange access directly.
- **The work order does not include the tenant's phone.** This asymmetry is deliberate and is the
  one judgement call here that was not user-specified: giving the tenant a contractor's number is
  the manager sharing their own supplier's details, whereas giving an external contractor the
  tenant's number shares a third party's data they never agreed to share. The address, issue,
  priority and the manager's email as reply contact are enough to do the job.

---

## Data Model

New table, `backend/app/models/contractor.py`:

```python
class Contractor(Base):
    __tablename__ = "contractors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    trade: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

One new column on `maintenance_requests`:

```python
contractor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contractors.id"), index=True)
```

Register `Contractor` in `app/models/__init__.py`. The migration creates the table, adds the
column, its FK and its index; `downgrade` drops the column then the table. No enum is involved.

---

## Schemas (`backend/app/schemas/contractor.py`)

```python
class ContractorCreate(BaseModel):
    name: str
    trade: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class ContractorUpdate(BaseModel):
    name: str | None = None
    trade: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class ContractorInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    trade: str | None
    phone: str | None
    email: EmailStr | None
    created_at: datetime


class AssignContractor(BaseModel):
    contractor_id: uuid.UUID
```

`ContractorUpdate` carries the same "`None` means not supplied" limitation criticised above, so it
cannot clear `trade`, `phone` or `email` back to empty — only overwrite them. That is accepted
here rather than overlooked: unassigning a contractor is a real workflow and needed its own route,
whereas blanking a phone number is not, and inventing a sentinel for it would cost more than it
returns. If it ever matters, the fix is a separate route, not a sentinel value.

`MaintenanceInfo` (`app/schemas/maintenance.py`) gains three fields:

```python
    contractor_id: uuid.UUID | None = None
    contractor_name: str | None = None
    contractor_phone: str | None = None
```

One schema serves both roles. What a tenant is allowed to see — name and phone — is exactly what
these carry, so no second schema is needed; `_to_info` resolves them with one lookup. The id is
included because the manager's picker needs it to show the current selection.

---

## Endpoints

Contractor directory, `backend/app/routers/contractors.py` (prefix `/api/v1`, tag `contractors`),
all under `require_roles(landlord, property_manager)` and scoped to the caller's organization:

| Method | Path | Behaviour |
|---|---|---|
| POST | `/contractors` | 201 `ContractorInfo` |
| GET | `/contractors` | list, ordered by name |
| PATCH | `/contractors/{id}` | 404 outside the org |
| DELETE | `/contractors/{id}` | 204, or **409** if requests still reference it |

The 409 carries the count: `"Contractor is assigned to N maintenance requests"`. Refusing beats
silently unassigning the jobs, and beats a raw FK error.

Assignment, added to `backend/app/routers/maintenance.py`:

| Method | Path | Behaviour |
|---|---|---|
| POST | `/maintenance/{request_id}/assign` | body `AssignContractor` -> `MaintenanceInfo`; sends the work order; notifies the tenants |
| DELETE | `/maintenance/{request_id}/assign` | clears `contractor_id` -> `MaintenanceInfo`; sends nothing |

Both use the existing `get_owned_request` for org isolation. Assigning a contractor from another
organization is a 404, checked against the contractor's `organization_id` — not merely its
existence.

## Work order and notification

On assign, when the contractor has an email:

```
Subject: Maintenance job - {property_address}
Body:    {title}, {description}, priority {priority},
         reply to {manager email}
```

sent through `safe_send`. With no email on file nothing is sent and the assignment still succeeds.

Also on assign, an in-app notification to the lease's tenants (via `lease_tenant_user_ids` and
`notify_users`, category `"maintenance_assigned"`, linking to `/app`), so the tenant learns someone
is coming without having to poll the page.

## Handling the live development Resend key

The development `.env` holds a working `resend_api_key`. This milestone is the first to send mail
from a request handler rather than a scheduled job, so it is the first where merely exercising the
UI can send.

- **Backend tests** are already safe: the autouse `disable_real_email` fixture in
  `tests/conftest.py` sets the key to `None`.
- **e2e and manual verification** hit the real development backend. That backend must be started
  with `RESEND_API_KEY` empty for these runs — the same mechanism the tests rely on.

Relying on the send merely *failing* is not the plan. It happens to be true (the sending domain is
unverified, so Resend rejects everything except the account owner's own address, and `safe_send`
swallows the error), but "it fails anyway" is luck, not a safeguard. Emptying the key is the
safeguard.

---

## Frontend

**`/app/contractors`** (new page, plus a `Contractors` link in the AppShell main menu): a list of
the organization's contractors and a form to add one, with `Name`, `Trade`, `Phone`, `Email`
fields and an `Add contractor` button. Each row can be edited and deleted; a delete that returns
409 shows the message rather than failing silently.

**`/app/maintenance`** (existing list): each request gains a contractor `Select` labelled
`Contractor` and an `Assign` button, plus `Unassign` when one is set. When the assigned contractor
has no email, the row notes that no work order was sent.

**Tenant portal maintenance list**: when a request has a contractor, show the name and phone.

`frontend/src/lib/contractors.ts` provides `listContractors`, `createContractor`,
`updateContractor`, `deleteContractor`; `frontend/src/lib/maintenance.ts` gains
`assignContractor(requestId, contractorId)` and `unassignContractor(requestId)`.

---

## Testing

Backend (`backend/tests/test_contractors.py` unless noted):

1. Migration round-trip: upgrade -> downgrade -> upgrade.
2. Contractor CRUD happy path; listing is scoped to the organization.
3. Reading, updating or deleting another organization's contractor is a 404.
4. Deleting a contractor that is still assigned returns 409 with the count.
5. Assign sets `contractor_id` and the response carries the name and phone.
6. Assign sends the work order: monkeypatch `app.services.notify.send_email` and assert the
   recipient and subject.
7. A contractor with no email on file gets no work order, and the assignment still succeeds.
8. Unassign clears the contractor and sends nothing.
9. Assigning a contractor belonging to another organization is a 404.
10. The tenant sees the contractor's name and phone through
    `GET /me/leases/{lease_id}/maintenance` (in `tests/test_maintenance.py`).
11. Assign writes a `maintenance_assigned` notification for the lease's tenants.

e2e (`frontend/e2e/contractor-assignment.spec.ts`): a landlord adds a contractor, a tenant reports
an issue, the landlord assigns the contractor, and **the tenant sees the contractor's name and
phone in their own portal**. The test crosses both roles on purpose: the cross-role visibility rule
is the part of this feature most likely to break silently, and a directory-only test would not
touch it.

---

## Out of Scope

- Contractor logins or a contractor portal. They receive email; they do not sign in.
- Assignment history (who was assigned before, and when).
- More than one contractor per request.
- Quotes, invoices, or job costs.
- Contractor ratings, and scheduling or calendar integration.
- Notifying the contractor of anything after the initial assignment — status changes and
  cancellations do not email them.

---

## File Structure

| File | Change |
|---|---|
| `backend/app/models/contractor.py` | new |
| `backend/app/models/__init__.py` | register `Contractor` |
| `backend/app/models/maintenance.py` | add `contractor_id` |
| `backend/alembic/versions/<rev>_add_contractors.py` | new migration |
| `backend/app/schemas/contractor.py` | new |
| `backend/app/schemas/maintenance.py` | three fields on `MaintenanceInfo` |
| `backend/app/routers/contractors.py` | new, mounted in `main.py` |
| `backend/app/routers/maintenance.py` | assign / unassign; `_to_info` resolves the contractor |
| `backend/tests/test_contractors.py` | new |
| `backend/tests/test_maintenance.py` | tenant visibility case |
| `frontend/src/lib/contractors.ts` | new |
| `frontend/src/lib/maintenance.ts` | assign / unassign |
| `frontend/src/app/app/contractors/page.tsx` | new |
| `frontend/src/components/app-shell.tsx` | `Contractors` nav link |
| `frontend/src/app/app/maintenance/page.tsx` | picker, Assign, Unassign |
| `frontend/src/app/app/page.tsx` | tenant branch shows the assigned contractor |
| `frontend/e2e/contractor-assignment.spec.ts` | new |

## Task Breakdown

- **T1** `Contractor` model + `contractor_id` column + migration + round-trip
- **T2** contractor schemas + CRUD router + tests 2-4
- **T3** assign / unassign + `MaintenanceInfo` fields + tests 5, 8, 9
- **T4** work-order email + tenant notification + tests 6, 7, 10, 11
- **T5** frontend: contractors page, nav link, maintenance picker, tenant portal display
- **T6** e2e + CI green
