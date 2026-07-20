# Milestone 3.2: Lease Management — Design

**Date:** 2026-07-21
**Status:** Approved (design), pending spec review

## Goal

Let a landlord or property_manager record and manage leases for a property, and make each property's `vacant`/`occupied` status derive automatically from whether an active lease covers today. When a property is occupied, its detail view shows the active lease (tenant, rent, start/end).

## Scope

**In scope:**
- `Lease` model + migration (organization-scoped, tied to a property).
- Lease CRUD endpoints (landlord + property_manager), organization-scoped.
- Property `status` becomes a derived value (active lease covers today), not a stored column.
- Overlap protection: a property cannot have two leases whose date ranges overlap.
- Property detail response exposes the active lease; frontend shows it and offers lease management.

**Out of scope (Milestone 3.3):**
- Tenant invitations tied to a lease; the tenant `User` account and `tenant_user_id` link.
- Tenant portal (a tenant viewing only their own lease).
- Lease-expiry reminders.

## Key design decisions

1. **Tenant is captured as fields, not an account.** A lease stores `tenant_name` + `tenant_email`. The real tenant `User` does not exist yet — tenants join by invitation in M3.3, where a `tenant_user_id` FK is added and linked on accept. This keeps M3.2 self-contained and testable without tenant accounts, and matches the "tenants join by invitation only" rule.

2. **Property status is derived from leases, not stored.** The stored `Property.status` column is dropped. A property is `occupied` iff an active lease (`start_date <= today <= end_date`) exists for it, else `vacant`. Single source of truth = leases, so status never drifts (no "lease ended but still shows occupied"). No scheduler needed.

3. **No lease status column — lease state derives from dates (YAGNI).**
   - active (current): `start_date <= today <= end_date`
   - upcoming: `today < start_date`
   - ended: `today > end_date`
   - **early termination**: set `end_date` to the move-out date; the lease stops being active the next day. No separate status/flag needed.

## Data model

New file `backend/app/models/lease.py`.

`LeaseFrequency(str, enum.Enum)`: `weekly`, `fortnightly`, `monthly`.

`Lease` table `leases`:

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK, default uuid4 |
| organization_id | UUID | FK -> organizations.id, index. Copied from the property's org, never from the client. |
| property_id | UUID | FK -> properties.id, index |
| tenant_name | str | `String(255)` |
| tenant_email | str | `String(255)` |
| rent_amount | Numeric(10, 2) | exposed as `Decimal` in schemas |
| rent_frequency | LeaseFrequency | `Enum(LeaseFrequency)` |
| bond_amount | Numeric(10, 2), nullable | optional deposit |
| notice_period_days | int, nullable | optional |
| start_date | Date | inclusive |
| end_date | Date | inclusive |
| created_at | datetime(tz) | `server_default=func.now()` |

Register in `app/models/__init__.py` (Alembic autogenerate reads it). Enum reuse note: `LeaseFrequency` is a new type; migration creates it normally. (No enum-reuse collision like the invitations migration had, because no earlier table uses `LeaseFrequency`.)

### Property model change

- Remove `status: Mapped[PropertyStatus]` column from `Property`; drop the column in the migration.
- Keep the `PropertyStatus` enum (`vacant`/`occupied`) — it is now the type of a *computed* value, not a stored column. The migration drops the column but leaves the `propertystatus` enum type in place (still referenced by the schema/response); dropping the now-unused type is optional and out of scope.

## Status derivation and overlap rules

**Today:** computed as `datetime.now(UTC).date()` (consistent with the codebase's timezone-aware convention).

**Active lease for a property:** the (at most one) lease with `start_date <= today <= end_date`.

**Property status:**
- detail (`GET /properties/{id}`): query the active lease; status = `occupied` if present else `vacant`; response includes `active_lease` (null when vacant).
- list (`GET /properties`): compute the set of property ids that have an active lease (single query: leases in the caller's org where `start_date <= today <= end_date`), then map each property to `occupied`/`vacant`.
- status filter (`?status=occupied|vacant`): filter by membership in that active-lease id set (occupied = in the set; vacant = not in the set).

**Overlap protection:** two leases on the same property may not have overlapping date ranges. Ranges `[s1,e1]` and `[s2,e2]` overlap iff `s1 <= e2 AND s2 <= e1`. On create, reject if any existing lease for the property overlaps. On update (PATCH), exclude the lease being edited by id. Violation -> `409 Conflict`. Also validate `start_date <= end_date` -> else `422`.

## API endpoints

All lease endpoints require role `landlord` or `property_manager` (reuse `require_roles(Role.landlord, Role.property_manager)`, same dependency the property endpoints use). Every query is organization-scoped via the caller's membership; cross-org access returns `404` (never leak existence).

Schemas in `backend/app/schemas/lease.py`: `LeaseCreate`, `LeaseUpdate`, `LeaseResponse`.

- **`POST /api/v1/properties/{property_id}/leases`** -> `201 LeaseResponse`
  Body `LeaseCreate`: `tenant_name, tenant_email, rent_amount, rent_frequency, bond_amount?, notice_period_days?, start_date, end_date`. Verifies the property belongs to the caller's org (else 404); enforces `start_date <= end_date` (422) and no overlap (409). `organization_id` taken from the property.

- **`GET /api/v1/properties/{property_id}/leases`** -> `list[LeaseResponse]`
  Leases for that property (org-scoped), newest first. Property not in org -> 404.

- **`GET /api/v1/leases/{lease_id}`** -> `LeaseResponse` (404 cross-org).

- **`PATCH /api/v1/leases/{lease_id}`** -> `LeaseResponse`
  Partial update of the same fields; re-validates date order and overlap (excluding itself). 404 cross-org.

- **`DELETE /api/v1/leases/{lease_id}`** -> `204` (404 cross-org).

`LeaseResponse` fields: `id, property_id, tenant_name, tenant_email, rent_amount, rent_frequency, bond_amount, notice_period_days, start_date, end_date, created_at`.

### Property response change

- `PropertyResponse` gains `active_lease: ActiveLease | None`, where `ActiveLease` = `{ id, tenant_name, rent_amount, rent_frequency, start_date, end_date }`.
- `status` in `PropertyResponse` is now supplied by the endpoint (computed), not read from an ORM column.
- Router file mounts a new `leases_router` in `app/main.py`.

## Frontend

- `frontend/src/lib/leases.ts`: `Lease` type, `listLeases(propertyId)`, `createLease(propertyId, input)`, `getLease(id)`, `updateLease(id, input)`, `deleteLease(id)`.
- **Property detail page** (`app/properties/[id]`): when the property has an `active_lease`, show a summary card (tenant name, rent + frequency, start–end). Add a "Manage leases" link.
- **Leases area** for a property: a page listing the property's leases with a create/edit form (`app/properties/[id]/leases`), including the overlap/date error messages. Exact page layout finalized in the plan.
- **Property list page**: unchanged UI — `status` still arrives as a string; it is now derived server-side.

## Testing strategy

**Backend (pytest):**
- Lease CRUD happy paths; `LeaseResponse` shape.
- Organization scoping: cross-org `GET`/`PATCH`/`DELETE` and cross-org create-on-someone-else's-property -> 404.
- Overlap: overlapping create -> 409; adjacent (non-overlapping) allowed; PATCH excludes itself.
- `start_date > end_date` -> 422.
- **Status derivation:** property with an active lease covering today -> `occupied`; property with only a future lease -> `vacant`; with only a past lease -> `vacant`; with no lease -> `vacant`. Detail response `active_lease` present iff occupied.
- Status filter on the list endpoint returns the right partition.
- RBAC: unauthenticated -> 401; property_manager allowed. (Tenant-role rejection is exercised in M3.3 when the role becomes reachable as a lease viewer.)
- Existing property tests updated for the dropped stored `status` (create no longer accepts/stores status; search-by-status now lease-driven).

**e2e (Playwright):** sign up (landlord) -> create a property (shows `vacant`) -> add a lease covering today -> property detail shows `occupied` + the lease's tenant and dates -> delete the lease -> property returns to `vacant`.

## Migration notes

- One Alembic migration: create `leases` (+ `leasefrequency` enum) and **drop** `properties.status`.
- Verify the upgrade/downgrade round-trip locally (upgrade -> downgrade -> upgrade), as done for the invitations migration.
- The `downgrade` re-adds `properties.status`. Because the original column is NOT NULL with only a Python-side default, the downgrade must add it with a temporary `server_default='vacant'` (so existing rows backfill on a populated table), then drop the server default to match the original model. It also drops the `leases` table and the `leasefrequency` enum type (the `leases` create introduces `leasefrequency`, so its downgrade owns dropping it — the same true-inverse discipline used for `invitationstatus`).
- Local Postgres host port 5433; CI 5432.

## Rhythm

Same as M1/M2/M3.1: many small TDD steps; each task ends with full test run -> ruff sequence (`format` -> `check --fix` -> `check` -> `format --check`) -> commit -> `git push` to `https://github.com/Keith-hoka/rental_management` for CI -> report -> wait for approval.
