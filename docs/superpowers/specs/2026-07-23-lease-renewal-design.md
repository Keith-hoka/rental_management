# Milestone 7: Lease Renewal — Design

**Date:** 2026-07-23
**Status:** Approved (pending spec review)

## Goal

A manager renews an expiring lease in one action: the system creates a successor lease for the
same tenants, carries their portal access across, and links the two so the history stays
readable. This closes a loop that is currently broken — M3.4 emails "your lease expires in N
days" and the tenant email literally says "contact your landlord about renewal", because the
product offers nothing to click.

## Architecture

- Renewal creates a **new `Lease` row** that points back at its predecessor through a
  self-referential `renewed_from_id`. The old lease keeps its own charges, payments and
  reminders, so rent history and "how many times has this been renewed" both stay legible.
- The alternative — moving `end_date` forward on the existing row — was rejected. It is already
  possible through the existing edit form, so it would make this milestone a no-op, and it
  overwrites the originally agreed terms: after a rent increase the lease row no longer describes
  the term it was signed for.
- Renewal reuses the existing lease machinery rather than duplicating it: `get_owned_lease` for
  cross-org isolation, `overlapping_lease_exists` for date conflicts, `generate_charges` for
  billing, `_lease_state` for status. The only new service-layer behaviour is copying
  `LeaseTenant` rows and suppressing expiry reminders on a lease that has been renewed.

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
- This migration adds **no enum**, so it is a plain add-column + FK + unique index; `downgrade`
  reverses those. Verify upgrade -> downgrade -> upgrade. Current head: `b83f5c0a1e47`.
- The frontend is pinned by accessible name across 24 Playwright specs. Every name introduced here
  must be new, and no new element may duplicate a name already on the same page.

---

## Product Rules (confirmed)

- **Who renews:** a landlord or property manager, unilaterally. The tenant is notified and sees
  the new lease in their portal, but does not accept or decline in-app — renewal terms are agreed
  offline. A tenant-facing accept/decline state machine was considered and rejected as roughly
  double the work for this milestone.
- **Who the renewal is for:** the same tenants. Tenant identity (`tenant_name`, `tenant_email`,
  `tenant_phone`, `co_tenants`) is copied and **cannot be edited** on the renewal form. A change
  of tenant is a new lease, not a renewal. This is the boundary that keeps "renewal" meaningful.
- **What can change:** `start_date`, `end_date`, `rent_amount`, `rent_frequency`, `bond_amount`,
  `notice_period_days`.
- **One successor per lease**, enforced by a unique constraint, not only by application code.
- **Renewing an already-ended lease is allowed.** A late renewal is a real situation and nothing
  in the data model makes it harmful.
- **Notifications:** in-app only (tenants of the lease + org managers). Email is deliberately out
  of scope — the terms were agreed offline, and the tenant sees it in both the portal and
  Messages.

---

## Data Model

One nullable column on `leases` (`backend/app/models/lease.py`):

```python
renewed_from_id: Mapped[uuid.UUID | None] = mapped_column(
    ForeignKey("leases.id"), unique=True, index=True
)
```

`unique` makes "a lease can be renewed at most once" a database guarantee. PostgreSQL permits
multiple `NULL`s in a unique column, so un-renewed leases are unaffected.

Migration: `op.add_column` + `op.create_foreign_key` + `op.create_index` (unique); `downgrade`
drops all three. No enum is involved.

---

## Schemas (`backend/app/schemas/lease.py`)

```python
class LeaseRenew(BaseModel):
    """Terms for the successor lease. Tenant identity is copied, never supplied."""

    end_date: date
    start_date: date | None = None
    rent_amount: Decimal | None = None
    rent_frequency: LeaseFrequency | None = None
    bond_amount: Decimal | None = None
    notice_period_days: int | None = None
```

`end_date` is required: there is no defensible default for how long the new term runs. Every other
field defaults to the source lease's value; `start_date` defaults to `source.end_date + 1 day`,
because `overlapping_lease_exists` treats ranges as **inclusive** and the same day would 409.

`LeaseResponse` gains two fields:

- `renewed_from_id: uuid.UUID | None` — the column.
- `renewed_to_id: uuid.UUID | None = None` — the reverse lookup. The detail page needs it to
  decide between showing a "Renew lease" button and a "View renewal" link.

`renewed_to_id` is populated **only by `GET /leases/{lease_id}`**, the one caller that needs it,
and defaults to `None` everywhere else. `LeaseResponse` is also returned by create, update and the
per-property list; resolving the reverse lookup in the list endpoint would mean one extra query
per lease for a value nothing renders.

---

## Endpoint (`backend/app/routers/leases.py`)

`POST /api/v1/leases/{lease_id}/renew` -> `201 LeaseResponse`, dependency `require_roles(landlord,
property_manager)`.

1. `get_owned_lease` — 404 outside the caller's org.
2. 409 `"Lease has already been renewed"` if any lease has `renewed_from_id == lease_id`.
3. Resolve defaults from the source lease.
4. 400 if `end_date <= start_date` (the existing date-order rule).
5. 409 `"Lease dates overlap an existing lease"` via `overlapping_lease_exists`.
6. Insert the successor with `renewed_from_id = lease_id`.
7. Copy every `LeaseTenant` row of the source to the new lease id, same `user_id`.
8. `notify_users` (from `app/services/notify.py`) to the lease's tenant user ids plus
   `manager_user_ids`, category `"lease_renewal"`, linking to `/app/leases/{new_id}`.
9. One commit.

Step 7 is not optional bookkeeping: `LeaseTenant` is what `GET /me/leases` reads, so skipping it
would leave the tenant unable to see their own new lease.

## Reminder suppression (`backend/app/services/reminders.py`)

`_expiring_leases` must exclude leases that already have a successor, otherwise a manager keeps
receiving "expires in 7 days" for a lease that was renewed weeks ago. Add to its `where`:

```python
successor = aliased(Lease)
...
.where(~select(successor.id).where(successor.renewed_from_id == Lease.id).exists())
```

The alias is required, not stylistic: without it the subquery references the same `Lease` entity as
the outer query and correlates to itself, so the condition does not mean what it reads as.

## No change needed

`generate_charges` selects every lease with `start_date <= horizon` and anchors periods to
`lease.start_date`, so the successor is picked up with no code change. `_lease_state` derives
`upcoming` / `active` / `ended` from dates alone, so property occupancy follows automatically.
Both claims are asserted by tests below rather than trusted.

---

## Frontend

**`/app/leases/[leaseId]` (existing detail page)**

- A `Renew lease` button when `renewed_to_id` is null.
- A `View renewal` link when it is set (the button is then hidden).
- A `View previous lease` link when `renewed_from_id` is set.

Both links are labelled with those fixed strings rather than the property address. The address is
already the page heading, and a duplicate accessible name breaks Playwright strict mode — the same
trap the redesign hit with the `Leases` link on the property detail page.

**`/app/leases/[leaseId]/renew` (new page)**

Follows the established pattern of giving lease creation its own route (`/app/leases/new`) rather
than a modal.

- Read-only summary of the tenants who carry over, so the copy-not-edit rule is visible.
- Editable `Start`, `End`, `Rent`, `Frequency`, `Bond`, `Notice period`; all prefilled except
  `End`.
- Submit button `Create renewal`.
- On success, redirect to the new lease's detail page.

`frontend/src/lib/leases.ts` gains `renewLease(leaseId, body)`.

**Accessible names introduced:** `Renew lease`, `Create renewal`, `View renewal`,
`View previous lease` — all new. The form's `Start` / `End` / `Rent` / `Frequency` labels match the
create form, but live on a different route, so no strict-mode collision arises.

---

## Testing

Backend (`backend/tests/test_lease_renewal.py` unless noted):

1. Migration round-trip: upgrade -> downgrade -> upgrade.
2. Renewal succeeds: tenant fields copied verbatim, `start_date` defaults to source `end_date` + 1
   day, overridden fields applied, `renewed_from_id` set.
3. Renewing twice -> 409.
4. Renewal whose dates overlap another lease on the same property -> 409.
5. `end_date <= start_date` -> 400; renewing another org's lease -> 404.
6. `LeaseTenant` carry-over, asserted from the tenant's side: `GET /me/leases` as the onboarded
   tenant returns the successor.
7. `run_expiry_reminders` skips a renewed lease (extends `tests/test_reminders.py`).
8. `generate_charges` produces charges for the successor.

Test 8 exists because "charges need no change" is an inference from reading `generate_charges`,
not an observed fact. The test either confirms it or exposes the mistake before the milestone
ships.

e2e (`frontend/e2e/lease-renewal.spec.ts`): landlord signs up, creates a property and a lease,
opens the lease, clicks `Renew lease`, sets a new end date and rent, clicks `Create renewal`,
lands on the successor's detail page, and the predecessor shows `View renewal`.

---

## Out of Scope

- Tenant accept/decline of a renewal offer.
- Renewal emails (in-app notification only).
- Rent-increase helpers such as a percentage calculator or CPI lookup.
- Renewal of a lease onto a *different* property; that is a new lease.
- Bulk renewal of several leases at once.

---

## File Structure

| File | Change |
|---|---|
| `backend/app/models/lease.py` | add `renewed_from_id` |
| `backend/alembic/versions/<rev>_add_lease_renewed_from.py` | new migration |
| `backend/app/schemas/lease.py` | add `LeaseRenew`; extend `LeaseResponse` |
| `backend/app/routers/leases.py` | add `POST /leases/{lease_id}/renew`; populate `renewed_to_id` |
| `backend/app/services/reminders.py` | exclude renewed leases from `_expiring_leases` |
| `backend/tests/test_lease_renewal.py` | new |
| `backend/tests/test_reminders.py` | add the suppression test |
| `frontend/src/lib/leases.ts` | add `renewLease` + the two new response fields |
| `frontend/src/app/app/leases/[leaseId]/page.tsx` | button + the two links |
| `frontend/src/app/app/leases/[leaseId]/renew/page.tsx` | new |
| `frontend/e2e/lease-renewal.spec.ts` | new |

## Task Breakdown

- **T1** model column + migration + round-trip test
- **T2** `LeaseRenew` schema + `/renew` endpoint + API tests (2-5)
- **T3** `LeaseTenant` carry-over + notification + test 6
- **T4** reminder suppression (test 7) + charges integration test (test 8)
- **T5** frontend lib + renew page + detail-page button and links + lint/build
- **T6** e2e + CI green
