# Milestone 3.3: Tenant Invitations + Tenant Portal — Design

**Date:** 2026-07-21
**Status:** Approved (design), pending spec review

## Goal

Let a landlord or property_manager invite tenants (including multiple co-tenants) to a specific lease by email. An invited tenant accepts via the existing emailed link, joins the organization with role `tenant` linked to that lease, and lands in a read-only tenant portal that shows their lease(s) and their landlord's contact details.

## Scope

**In scope:**
- Tie `Invitation` to a lease (`lease_id`); a lease-scoped invite endpoint that emails the tenant.
- Co-tenants: a `LeaseTenant` join table so one lease can have many tenant users.
- Extend the existing accept endpoint to create the tenant membership and link the lease.
- Tenant portal: a tenant sees only their own lease(s) + landlord contact; cannot reach property/lease management.
- Landlord/PM view of a lease's joined tenants + an invite form.

**Out of scope (Milestone 3.4):**
- Lease-expiry reminders (needs a scheduler — separate subsystem).
- Tenant self-service beyond viewing their lease (maintenance requests, documents, payments).

## Key design decisions

1. **Invites are lease-scoped and email-addressed.** `POST /api/v1/leases/{lease_id}/invite` takes an `email`. The frontend pre-fills it with the lease's `tenant_email` (one click for the primary tenant) but allows any email, so co-tenants can be invited by repeating the form. The invitation carries `lease_id`.

2. **Co-tenants via a join table.** Instead of a single `Lease.tenant_user_id`, a `LeaseTenant(lease_id, user_id)` association links tenant users to leases many-to-many. `Lease.tenant_name` / `tenant_email` remain the primary tenant's contact captured at lease creation.

3. **Reuse the existing accept endpoint + accept page.** `POST /api/v1/invitations/accept` and `/accept-invite` already collect name + password and auto-login. For a tenant invite (`lease_id` set), acceptance additionally creates the `LeaseTenant` link. No new accept page.

4. **Tenant portal is user-scoped and read-only.** A tenant's leases are found via `LeaseTenant.user_id == current_user.id`, not org-scoping. The portal shows lease terms and the org's landlord contact. Tenants keep role `tenant`, which is excluded from every management endpoint (`require_roles(landlord, property_manager)` → 403).

5. **Onboarding is for new tenants only (this milestone).** The accept flow creates a brand-new account and returns 409 if the email is already registered. So co-tenants (several *different* emails on one lease) are fully supported, but linking an *already-registered* user to an additional lease (a returning tenant, or the same person on two units) is out of scope here — it would need a separate "link existing user" flow. The invite endpoint therefore only guards against inviting an email that is already a tenant *of this lease* (409); other already-registered emails are caught at accept time.

6. **The lease carries a tenant roster (contact records), separate from accounts.** The lease stores the main tenant (`tenant_name`, `tenant_email`, `tenant_phone`) plus a `co_tenants` list of `{name, email, phone}` — the landlord's record of who lives there, entered/edited on the lease form (co-tenant rows are add/remove). This roster is independent of `LeaseTenant` (who has actually accepted an invite and created an account). The invite flow simply sends invitations to roster emails; accepting turns a roster email into a `LeaseTenant` account. `co_tenants` is a JSON column (edited as a unit with the lease, like `image_urls`); co-tenant emails are optional (a landlord may record a co-tenant they don't intend to invite).

## Data model

New file `backend/app/models/lease_tenant.py`:

```python
class LeaseTenant(Base):
    __tablename__ = "lease_tenants"
    __table_args__ = (UniqueConstraint("lease_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lease_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leases.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
```

Modify `backend/app/models/invitation.py`:
- Add `lease_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leases.id"), nullable=True, index=True)` (None for property_manager invites; set for tenant invites).

Modify `backend/app/models/user.py`:
- Add `phone: Mapped[str | None] = mapped_column(String(50))` — an optional contact phone shown to tenants and editable by the user.

Modify `backend/app/models/lease.py` (tenant roster):
- Add `tenant_phone: Mapped[str | None] = mapped_column(String(50))` — the main tenant's phone.
- Add `co_tenants: Mapped[list[dict]] = mapped_column(JSON, default=list)` — a list of `{name, email, phone}` co-tenant contact records.

Register `LeaseTenant` in `app/models/__init__.py`.

**Migration:** one Alembic migration — add `users.phone` (nullable), add `leases.tenant_phone` (nullable) and `leases.co_tenants` (JSON, server_default `'[]'` so existing rows backfill), add `invitations.lease_id` (nullable FK), and create `lease_tenants` (with the unique constraint and indexes). No enum changes. Verify an upgrade → downgrade → upgrade round-trip; downgrade drops `lease_tenants` and the added columns (all nullable / defaulted, so no backfill issue).

## API endpoints

### Invite a tenant (landlord/property_manager)

`POST /api/v1/leases/{lease_id}/invite` → `201 InvitationResponse`
- Dependency: `manager = require_roles(Role.landlord, Role.property_manager)`.
- Body `TenantInviteRequest`: `{ email: EmailStr }`.
- Verify the lease is in the caller's org (reuse `get_owned_lease`; else 404).
- If a registered user with that email is already a `LeaseTenant` of this lease → 409.
- Create `Invitation(organization_id=lease.organization_id, email=body.email, role=Role.tenant, lease_id=lease.id, token=secrets.token_urlsafe(32), expires_at=now+7d)`.
- Email an accept link `{frontend_url}/accept-invite?token={token}` (failure logged, does not fail the request — same pattern as team invites).
- Lives in `app/routers/leases.py`.

### List a lease's joined tenants (landlord/property_manager)

`GET /api/v1/leases/{lease_id}/tenants` → `list[LeaseTenantInfo]`
- 404 if the lease is not in the caller's org.
- Returns the accepted tenants: `LeaseTenantInfo { name: str, email: EmailStr }` (join `LeaseTenant` → `User`).

### Accept an invitation (public — extend existing)

`POST /api/v1/invitations/accept` (unchanged signature) — after creating the `User` and `Membership(role=invite.role)`, if `invite.lease_id is not None`, also `session.add(LeaseTenant(lease_id=invite.lease_id, user_id=user.id))`. Errors unchanged (400 invalid/expired/used; 409 email already registered).

### Tenant portal (any authenticated user; only tenants have data)

`GET /api/v1/me/leases` → `list[TenantLease]`
- Dependency: `get_current_user` (no role gate).
- Leases where the current user is a `LeaseTenant` (`join LeaseTenant on lease_id, filter user_id == current_user.id`), joined to `Property` for the address.
- For each lease's organization, look up the landlord (the `Membership` with `role == Role.landlord`) → that `User`'s name + email + phone.
- `TenantLease`: `{ id, property_address, rent_amount, rent_frequency, start_date, end_date, bond_amount, notice_period_days, state, landlord_name, landlord_email, landlord_phone }` (`landlord_phone` may be null), where `state` ∈ `active|upcoming|ended` derived from today (same rule as the leases overview).
- Lives in a new `app/routers/portal.py` (prefix `/api/v1/me`).

Schemas in `backend/app/schemas/tenant.py`: `TenantInviteRequest`, `LeaseTenantInfo`, `TenantLease`.

**Lease schema changes** (`backend/app/schemas/lease.py`): add a `CoTenant` model `{ name: str, email: EmailStr, phone: str | None }`. `LeaseCreate`, `LeaseUpdate`, and `LeaseResponse` gain `tenant_phone: str | None` and `co_tenants: list[CoTenant]` (default `[]`). Update also replaces the whole `co_tenants` list. `TenantLease` (portal) does not expose co-tenants — a tenant sees their own lease terms + landlord contact, not the other tenants' details.

### Edit own contact info (any authenticated user)

`GET /api/v1/auth/me` — extend `MeResponse` with `phone: str | None` (the current user's phone).

`PATCH /api/v1/auth/me` → updated `MeResponse`
- Dependency: `get_current_user`.
- Body `ProfileUpdate`: `{ name?: str, phone?: str | None }` (email is the login identity and is not editable here).
- Updates the current user's `name` / `phone` and returns the refreshed `MeResponse`. Lives in `app/routers/auth.py`. `ProfileUpdate` in `app/schemas/auth.py`.

## Frontend

- `frontend/src/lib/tenants.ts`: `inviteTenant(leaseId, email)`, `listLeaseTenants(leaseId)`, `listMyLeases()` + the `LeaseTenantInfo` / `TenantLease` types.
- `frontend/src/lib/profile.ts`: `getMe()`, `updateProfile({ name, phone })` + the `Me` type (`{ id, email, name, phone, role, organization_id }`).
- **Lease create/edit forms** (`app/leases/page.tsx` add form and `app/leases/[leaseId]` edit form): the tenant section becomes a **main tenant** group (name, email, phone) plus a **co-tenants** group — a dynamic list where each row has name / email / phone and a "Remove" button, and an "Add co-tenant" button appends a blank row. On submit the whole `co_tenants` array is sent; `tenant_phone` and co-tenant phones are optional.
- **Lease detail page** (`app/leases/[leaseId]`, landlord/PM): a "Tenants" section that (a) lists the roster (main tenant + co-tenants) each with name/email and an "Invite" button that calls `inviteTenant(leaseId, email)` and shows "Invitation sent", and (b) lists who has actually joined (from `listLeaseTenants`). Surfaces the 409 (already a tenant) error.
- **Profile page** (`app/profile/page.tsx`): a form to edit the current user's name + phone (reads `getMe`, saves `updateProfile`). Reachable by any signed-in user.
- **Dashboard** (`app/page.tsx`): branch on `me.role`.
  - `landlord` / `property_manager`: the existing dashboard (Properties, Leases, Team, …) plus a **Contact info** link to `/app/profile`.
  - `tenant`: a "Your lease" view — for each lease from `listMyLeases`, a read-only card (property, rent + frequency, term, bond, notice, state) plus "Landlord contact: {landlord_name} — {landlord_email} — {landlord_phone}" (phone omitted when null). Only Change password + Log out otherwise (no Properties/Leases/Team links).
- The accept page (`/accept-invite`) is reused unchanged; a tenant who accepts is auto-logged-in and lands on the tenant dashboard.

## Security / RBAC

- Invite and tenant-list endpoints require `landlord` or `property_manager`; a `tenant` calling them gets 403.
- All management endpoints already require `landlord`/`property_manager`, so a tenant cannot list or mutate properties or leases.
- `/api/v1/me/leases` returns only leases the caller is a `LeaseTenant` of — tenants cannot see each other's leases; a landlord calling it gets an empty list (they are nobody's tenant).
- An invitation's `organization_id` and `lease_id` come from the server-side lease, never the client.

## Testing strategy

**Backend (pytest):**
- Invite: landlord/PM invites a tenant for a lease → 201; unauthenticated → 401; a `tenant`-role caller → 403; lease in another org → 404; inviting an email already joined to that lease → 409.
- Accept (read the token from the DB via `db_session`, as in M3.1): creates a tenant `User` + `Membership(role=tenant)` + `LeaseTenant`; the tenant can log in, `/me` shows role `tenant`; a second, different email accepted for the same lease yields two `LeaseTenant` rows (co-tenants).
- Tenant portal: `/api/v1/me/leases` returns the tenant's lease with correct `landlord_name`/`landlord_email`/`landlord_phone` and `state`; the landlord's phone reflects what the landlord saved via `PATCH /auth/me`; tenant A does not see tenant B's lease; a landlord gets an empty list.
- Tenant RBAC: a tenant calling `GET /api/v1/properties` or `GET /api/v1/leases` → 403.
- Lease tenants list: landlord sees the joined tenants' name/email; cross-org → 404.
- Lease roster: creating and updating a lease with `tenant_phone` and a `co_tenants` list round-trips (the response echoes them); a co-tenant with an invalid email → 422; updating replaces the whole `co_tenants` list.
- Profile: `PATCH /api/v1/auth/me` updates the caller's name + phone and `GET /api/v1/auth/me` returns the new phone; requires auth (401 without a token).

**e2e (Playwright):** landlord signs up → edits contact info on `/app/profile` (sets a phone) → creates a property + a lease that includes a main tenant and one added co-tenant row → opens the lease detail → invites a tenant from the roster (Invite → "Invitation sent"). The full accept-and-see-portal path is covered by backend tests because the invite token is emailed only (never returned by the API), matching the team-invitation e2e boundary.

## Migration notes

- One migration: `add invitations.lease_id and lease_tenants`.
- No enum types are added or reused, so no `create_type` / enum-drop handling is needed; still verify upgrade → downgrade → upgrade locally.
- Local Postgres host port 5433; CI 5432.

## Rhythm

Same as prior milestones: many small TDD steps; each task ends with full test run → ruff sequence (`format` → `check --fix` → `check` → `format --check`) → commit → `git push` to `https://github.com/Keith-hoka/rental_management` for CI → report → wait for approval.

## Roadmap (next)

- **Milestone 3.4:** Lease-expiry reminders — a scheduled job (APScheduler) that finds leases nearing `end_date` and emails the landlord/tenant; configurable lead time. Introduces the scheduling subsystem deferred here.
- **Milestone 4:** Rent charges (scheduled generation), payment recording, dashboard stats + charts.
