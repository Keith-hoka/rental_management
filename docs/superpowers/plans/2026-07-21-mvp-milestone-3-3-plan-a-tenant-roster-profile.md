# MVP Milestone 3.3 — Plan A: Lease Tenant Roster + User Phone + Profile Editing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a landlord/property_manager record a lease's main tenant (name, email, phone) and a dynamic list of co-tenants (name, email, phone) on the lease form, and let any signed-in user edit their own contact info (name, phone).

**Architecture:** Add a phone to `User`, and `tenant_phone` + a JSON `co_tenants` roster to `Lease`. The lease schemas gain those fields (co-tenants validated as a `CoTenant` model); the existing lease create/update endpoints already pass body fields through, so no router changes are needed there. Add `PATCH /api/v1/auth/me` for profile editing. Frontend: a shared `TenantFields` component drives the tenant section of both lease forms, plus a profile page and a dashboard link.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, pytest + httpx, Next.js 16 (App Router, TypeScript, Tailwind), Postgres.

## Global Constraints

- Python package manager is `uv` only: `uv run`, `uv add` — never `python3` / `pip`.
- No emojis in code, logs, or commit messages.
- Short modules, clear names, docstrings over inline comments. No defensive programming beyond real failure points.
- TDD: every task writes the failing test first (where a test applies).
- **Before every push run the ruff sequence** (all pushes, backend or frontend): `uv run ruff format .` → `uv run ruff check --fix .` → `uv run ruff check .` → `uv run ruff format --check .` (run from `backend/`).
- **Per-task user gate:** every task ends with: run full test suite → ruff → commit → `git push` → report to the user (what was done, test results, CI status) → STOP and wait for approval before the next task.
- This is **Plan A only**. Do NOT implement tenant invitations, `LeaseTenant`, `Invitation.lease_id`, `/me/leases`, or dashboard tenant-role branching — those are Plan B.
- Work on branch `main`. Repo: `https://github.com/Keith-hoka/rental_management`. Local Postgres host port 5433; CI 5432.

## Existing interfaces this plan builds on

- `app/models/user.py`: `User(id, email, hashed_password, name, created_at)`.
- `app/models/lease.py`: `Lease(...)` with `tenant_name`, `tenant_email`, `rent_amount`, `rent_frequency`, `bond_amount`, `notice_period_days`, `start_date`, `end_date`; imports `Date, DateTime, Enum, ForeignKey, Numeric, String, func` from sqlalchemy.
- `app/models/property.py`: precedent for a JSON list column — `image_urls: Mapped[list[str]] = mapped_column(JSON, default=list)`.
- `app/schemas/lease.py`: `LeaseCreate`, `LeaseUpdate`, `LeaseResponse` (`from_attributes=True`), using `EmailStr` and `Decimal`.
- `app/routers/leases.py`: `create_lease` does `Lease(organization_id=prop.organization_id, property_id=property_id, **body.model_dump())`; `update_lease` does `for field, value in body.model_dump(exclude_unset=True).items(): setattr(lease, field, value)`.
- `app/schemas/auth.py`: `MeResponse { id, email, name, role, organization_id }`.
- `app/routers/auth.py`: `GET /api/v1/auth/me` builds `MeResponse` from `user` + `membership` (deps `get_current_user`, `get_current_membership`).
- `app/core/deps.py`: `get_current_user`, `get_current_membership`. `app/core/db.py`: `get_session`.
- `tests/test_leases.py`: `make_property(client, headers, address="1 Lease St") -> str`, `lease_body(**overrides) -> dict`. `tests/test_properties_crud.py`: `landlord_headers(client, email="owner@example.com") -> dict`.
- Frontend `lib/leases.ts`: `Lease`, `LeaseInput`, `LeaseSummary`, `createLease`, `updateLease`, `listLeases`, `listAllLeases`. `lib/api.ts`: `apiFetch` (has `cache: "no-store"`), `ApiError`. `lib/auth.ts`: `getAccessToken`.
- Frontend lease create form `app/app/leases/page.tsx` (state `form: LeaseInput`, `emptyForm()`, `set(key, value)`); edit form `app/app/leases/[leaseId]/page.tsx` (state `form: LeaseInput | null`, `set(key, value)` guarding null, `startEdit(current)`, read-only `<dl>` of `Field` rows).
- Frontend dashboard `app/app/page.tsx` has a link row (Properties, Leases, Team, Change password, Log out). `playwright.config.ts` runs `workers: 1` + `retries: 1` in CI.

## File Structure

- `backend/app/models/user.py`, `backend/app/models/lease.py` — new columns.
- `backend/app/schemas/lease.py` — `CoTenant` + roster fields.
- `backend/app/schemas/auth.py` — `MeResponse.phone` + `ProfileUpdate`.
- `backend/app/routers/auth.py` — `PATCH /me`.
- `backend/alembic/versions/*` — one migration.
- `backend/tests/test_lease_model.py`, `test_leases.py`, `test_profile.py` — tests.
- `frontend/src/lib/leases.ts` — `CoTenant` + roster fields on `Lease`/`LeaseInput`.
- `frontend/src/app/app/leases/TenantFields.tsx` — shared tenant/co-tenant fields component (co-located with the lease pages).
- `frontend/src/app/app/leases/page.tsx`, `frontend/src/app/app/leases/[leaseId]/page.tsx` — wire in `TenantFields`; show roster on the detail view.
- `frontend/src/lib/profile.ts`, `frontend/src/app/app/profile/page.tsx`, `frontend/src/app/app/page.tsx` — profile.
- `frontend/e2e/leases.spec.ts`, `frontend/e2e/profile.spec.ts` — e2e.

---

### Task 1: Model columns + migration (user.phone, lease.tenant_phone, lease.co_tenants)

**Files:**
- Modify: `backend/app/models/user.py`, `backend/app/models/lease.py`
- Create: a migration under `backend/alembic/versions/`
- Test: `backend/tests/test_lease_model.py` (append)

**Interfaces:**
- Produces: `User.phone: str | None`; `Lease.tenant_phone: str | None`; `Lease.co_tenants: list[dict]` (each `{name, email, phone}`), defaulting to `[]`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_lease_model.py`

```python
async def test_lease_roster_columns(db_session):
    org = Organization(name="Roster Org", currency="USD")
    db_session.add(org)
    await db_session.flush()
    prop = Property(organization_id=org.id, address="1 Roster St", type=PropertyType.house)
    db_session.add(prop)
    await db_session.flush()

    lease = Lease(
        organization_id=org.id,
        property_id=prop.id,
        tenant_name="Main Tenant",
        tenant_email="main@example.com",
        tenant_phone="555-1000",
        rent_amount=Decimal("1000.00"),
        rent_frequency=LeaseFrequency.monthly,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        co_tenants=[{"name": "Coco", "email": "coco@example.com", "phone": "555-2000"}],
    )
    db_session.add(lease)
    await db_session.commit()

    found = (await db_session.execute(select(Lease).where(Lease.id == lease.id))).scalar_one()
    assert found.tenant_phone == "555-1000"
    assert found.co_tenants == [{"name": "Coco", "email": "coco@example.com", "phone": "555-2000"}]
```

(The file already imports `Lease`, `LeaseFrequency`, `select`, `date`, `Decimal`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_lease_model.py::test_lease_roster_columns -v`
Expected: FAIL — `TypeError` (unexpected keyword `tenant_phone` / `co_tenants`).

- [ ] **Step 3: Add the User column** — `backend/app/models/user.py`

Add `phone` after `name`:

```python
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
```

- [ ] **Step 4: Add the Lease columns** — `backend/app/models/lease.py`

Add `JSON` to the sqlalchemy import and add the two columns after `tenant_email`:

```python
from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Numeric, String, func
```

```python
    tenant_email: Mapped[str] = mapped_column(String(255))
    tenant_phone: Mapped[str | None] = mapped_column(String(50))
    co_tenants: Mapped[list[dict]] = mapped_column(JSON, default=list)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_lease_model.py -v`
Expected: PASS.

- [ ] **Step 6: Generate the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add user phone and lease tenant roster"
```

Expected: detects added columns `users.phone`, `leases.tenant_phone`, `leases.co_tenants`.

- [ ] **Step 7: Fix the `co_tenants` NOT NULL backfill in the migration**

Autogenerate emits `co_tenants` as `nullable=False` with no server default, which fails on existing rows. Edit the generated `upgrade()` so its `add_column` for `co_tenants` uses a temporary server default, then drops it (mirrors the `properties.status` migration pattern). The `upgrade()` should read:

```python
def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("leases", sa.Column("tenant_phone", sa.String(length=50), nullable=True))
    op.add_column(
        "leases",
        sa.Column("co_tenants", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("leases", "co_tenants", server_default=None)
```

and `downgrade()`:

```python
def downgrade() -> None:
    op.drop_column("leases", "co_tenants")
    op.drop_column("leases", "tenant_phone")
    op.drop_column("users", "phone")
```

- [ ] **Step 8: Apply and round-trip the migration**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic current
```

Expected: upgrade adds the columns; downgrade drops them; re-upgrade succeeds; `current` at the new head.

- [ ] **Step 9: Full suite, ruff, commit, push, report, wait**

```bash
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
git add backend
git commit -m "Add user phone and lease tenant roster columns"
git push
```

---

### Task 2: Lease schemas — CoTenant + tenant_phone + co_tenants

**Files:**
- Modify: `backend/app/schemas/lease.py`
- Test: `backend/tests/test_leases.py` (append)

**Interfaces:**
- Consumes: the new model columns (Task 1).
- Produces: `CoTenant { name: str, email: EmailStr, phone: str | None }`. `LeaseCreate`, `LeaseUpdate`, `LeaseResponse` gain `tenant_phone: str | None` and `co_tenants: list[CoTenant]`. No router change (create/update pass fields through).

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_leases.py`

```python
async def test_create_lease_with_roster(client):
    headers = await landlord_headers(client, "roster@example.com")
    property_id = await make_property(client, headers)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(
            tenant_phone="555-1000",
            co_tenants=[{"name": "Coco", "email": "coco@example.com", "phone": "555-2000"}],
        ),
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tenant_phone"] == "555-1000"
    assert body["co_tenants"] == [
        {"name": "Coco", "email": "coco@example.com", "phone": "555-2000"}
    ]


async def test_create_lease_rejects_invalid_co_tenant_email(client):
    headers = await landlord_headers(client, "badco@example.com")
    property_id = await make_property(client, headers)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(co_tenants=[{"name": "X", "email": "not-an-email", "phone": ""}]),
        headers=headers,
    )
    assert response.status_code == 422


async def test_update_lease_replaces_co_tenants(client):
    headers = await landlord_headers(client, "replaceco@example.com")
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                co_tenants=[{"name": "First", "email": "first@example.com", "phone": ""}]
            ),
            headers=headers,
        )
    ).json()
    response = await client.patch(
        f"/api/v1/leases/{created['id']}",
        json={"co_tenants": [{"name": "Second", "email": "second@example.com", "phone": "9"}]},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert [c["email"] for c in body["co_tenants"]] == ["second@example.com"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_leases.py -k "roster or co_tenant" -v`
Expected: FAIL — the response has no `tenant_phone` / `co_tenants` keys (KeyError / assertion), and the invalid-email case returns 201 instead of 422.

- [ ] **Step 3: Add the schema fields** — `backend/app/schemas/lease.py`

Add the `CoTenant` model (near the top, after the imports) and the two fields to the three lease schemas:

```python
class CoTenant(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
```

In `LeaseCreate` add:

```python
    tenant_phone: str | None = None
    co_tenants: list[CoTenant] = []
```

In `LeaseUpdate` add:

```python
    tenant_phone: str | None = None
    co_tenants: list[CoTenant] | None = None
```

In `LeaseResponse` add:

```python
    tenant_phone: str | None
    co_tenants: list[CoTenant]
```

(Why it works without router changes: `LeaseCreate.model_dump()` serializes `co_tenants` to a `list[dict]` for the JSON column; `LeaseResponse` with `from_attributes` reads the stored `list[dict]` back into `list[CoTenant]`. `LeaseUpdate.co_tenants` is `None` when omitted, so `model_dump(exclude_unset=True)` leaves it out unless the client sends it, and sending it replaces the whole list.)

- [ ] **Step 4: Run full suite** — `cd backend && uv run pytest -v` — all pass.

- [ ] **Step 5: Ruff, commit, push, report, wait** — commit message: `Add tenant_phone and co_tenants to lease schemas`

---

### Task 3: Profile editing — MeResponse.phone + PATCH /auth/me

**Files:**
- Modify: `backend/app/schemas/auth.py`, `backend/app/routers/auth.py`
- Test: `backend/tests/test_profile.py`

**Interfaces:**
- Consumes: `User.phone` (Task 1), `get_current_user`, `get_current_membership`, `get_session`.
- Produces: `MeResponse.phone: str | None`; `ProfileUpdate { name: str | None, phone: str | None }`; `PATCH /api/v1/auth/me` → updated `MeResponse`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_profile.py`

```python
from tests.test_properties_crud import landlord_headers


async def test_update_profile_sets_name_and_phone(client):
    headers = await landlord_headers(client, "profile@example.com")
    response = await client.patch(
        "/api/v1/auth/me", json={"name": "New Name", "phone": "555-9999"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    assert response.json()["phone"] == "555-9999"

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["name"] == "New Name"
    assert me.json()["phone"] == "555-9999"


async def test_update_profile_requires_auth(client):
    response = await client.patch("/api/v1/auth/me", json={"phone": "1"})
    assert response.status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_profile.py -v`
Expected: FAIL — `PATCH /api/v1/auth/me` returns 405 (not defined).

- [ ] **Step 3: Extend MeResponse and add ProfileUpdate** — `backend/app/schemas/auth.py`

Add `phone` to `MeResponse` and add `ProfileUpdate`:

```python
class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    phone: str | None = None
    role: str
    organization_id: uuid.UUID


class ProfileUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
```

- [ ] **Step 4: Populate phone in GET /me and add PATCH /me** — `backend/app/routers/auth.py`

Add `ProfileUpdate` to the existing `app.schemas.auth` import, and add `get_session` to the deps import (from `app.core.db`) if not already imported. In the existing `me` handler add `phone=user.phone`:

```python
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        phone=user.phone,
        role=membership.role.value,
        organization_id=membership.organization_id,
    )
```

Add the update endpoint right after `me`:

```python
@router.patch("/me", response_model=MeResponse)
async def update_me(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    membership: Membership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    """Update the caller's own name / phone."""
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        phone=user.phone,
        role=membership.role.value,
        organization_id=membership.organization_id,
    )
```

(`get_session` is cached per request, so the `user` from `get_current_user` is attached to this same `session`.)

- [ ] **Step 5: Run full suite** — `cd backend && uv run pytest -v` — all pass.

- [ ] **Step 6: Ruff, commit, push, report, wait** — commit message: `Add phone to profile and a PATCH /auth/me endpoint`

---

### Task 4: Frontend lease types + shared TenantFields + create form

**Files:**
- Modify: `frontend/src/lib/leases.ts`
- Create: `frontend/src/app/app/leases/TenantFields.tsx`
- Modify: `frontend/src/app/app/leases/page.tsx`

**Interfaces:**
- Produces: TS `CoTenant { name: string; email: string; phone: string }`; `Lease` gains `tenant_phone: string | null` and `co_tenants: CoTenant[]`; `LeaseInput` gains `tenant_phone: string` and `co_tenants: CoTenant[]`. `TenantFields` component consumed by both lease forms.

- [ ] **Step 1: Add types** — `frontend/src/lib/leases.ts`

Add the `CoTenant` type and the fields to `Lease` and `LeaseInput`:

```typescript
export interface CoTenant {
  name: string;
  email: string;
  phone: string;
}
```

In `interface Lease` add:

```typescript
  tenant_phone: string | null;
  co_tenants: CoTenant[];
```

In `interface LeaseInput` add:

```typescript
  tenant_phone: string;
  co_tenants: CoTenant[];
```

- [ ] **Step 2: Create the shared TenantFields component** — `frontend/src/app/app/leases/TenantFields.tsx`

```tsx
import type { CoTenant } from "@/lib/leases";

type MainField = "tenant_name" | "tenant_email" | "tenant_phone";

interface Props {
  tenantName: string;
  tenantEmail: string;
  tenantPhone: string;
  coTenants: CoTenant[];
  onMain: (field: MainField, value: string) => void;
  onCoTenants: (next: CoTenant[]) => void;
}

export function TenantFields({
  tenantName,
  tenantEmail,
  tenantPhone,
  coTenants,
  onMain,
  onCoTenants,
}: Props) {
  function updateCo(index: number, field: keyof CoTenant, value: string) {
    onCoTenants(coTenants.map((c, i) => (i === index ? { ...c, [field]: value } : c)));
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-gray-700">Main tenant</p>
      <input
        required
        placeholder="Tenant name"
        value={tenantName}
        onChange={(e) => onMain("tenant_name", e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <input
        type="email"
        required
        placeholder="Tenant email"
        value={tenantEmail}
        onChange={(e) => onMain("tenant_email", e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <input
        placeholder="Tenant phone (optional)"
        value={tenantPhone}
        onChange={(e) => onMain("tenant_phone", e.target.value)}
        className="w-full rounded border px-3 py-2"
      />
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-700">Co-tenants</p>
        <button
          type="button"
          onClick={() => onCoTenants([...coTenants, { name: "", email: "", phone: "" }])}
          className="rounded border px-2 py-1 text-sm text-blue-600 transition hover:bg-blue-50"
        >
          Add co-tenant
        </button>
      </div>
      {coTenants.map((c, i) => (
        <div key={i} className="flex gap-2">
          <input
            required
            placeholder="Name"
            aria-label={`Co-tenant ${i + 1} name`}
            value={c.name}
            onChange={(e) => updateCo(i, "name", e.target.value)}
            className="flex-1 rounded border px-2 py-2"
          />
          <input
            type="email"
            required
            placeholder="Email"
            aria-label={`Co-tenant ${i + 1} email`}
            value={c.email}
            onChange={(e) => updateCo(i, "email", e.target.value)}
            className="flex-1 rounded border px-2 py-2"
          />
          <input
            placeholder="Phone"
            aria-label={`Co-tenant ${i + 1} phone`}
            value={c.phone}
            onChange={(e) => updateCo(i, "phone", e.target.value)}
            className="flex-1 rounded border px-2 py-2"
          />
          <button
            type="button"
            aria-label={`Remove co-tenant ${i + 1}`}
            onClick={() => onCoTenants(coTenants.filter((_, idx) => idx !== i))}
            className="rounded border border-red-500 px-2 text-sm text-red-600 transition hover:bg-red-50"
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Wire TenantFields into the create form** — `frontend/src/app/app/leases/page.tsx`

Add the import:

```tsx
import { TenantFields } from "@/app/app/leases/TenantFields";
```

Extend `emptyForm()` with the roster fields:

```tsx
function emptyForm(): LeaseInput {
  return {
    tenant_name: "",
    tenant_email: "",
    tenant_phone: "",
    co_tenants: [],
    rent_amount: 0,
    rent_frequency: "monthly",
    bond_amount: null,
    notice_period_days: null,
    start_date: todayISO(),
    end_date: "",
  };
}
```

Replace the two tenant inputs (the `placeholder="Tenant name"` and `placeholder="Tenant email"` `<input>` elements, between the property `<select>` and the `<div className="flex gap-2">` rent row) with:

```tsx
        <TenantFields
          tenantName={form.tenant_name}
          tenantEmail={form.tenant_email}
          tenantPhone={form.tenant_phone}
          coTenants={form.co_tenants}
          onMain={(field, value) => set(field, value)}
          onCoTenants={(next) => set("co_tenants", next)}
        />
```

- [ ] **Step 4: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 5: Commit, push, report, wait** — commit message: `Add tenant roster fields to the lease create form`

---

### Task 5: Wire TenantFields into the edit form + show the roster on the lease detail

**Files:**
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx`

**Interfaces:**
- Consumes: `TenantFields` (Task 4), `Lease.tenant_phone`, `Lease.co_tenants`.

- [ ] **Step 1: Import TenantFields** — `frontend/src/app/app/leases/[leaseId]/page.tsx`

```tsx
import { TenantFields } from "@/app/app/leases/TenantFields";
```

- [ ] **Step 2: Populate roster fields when editing** — in `startEdit(current)`, set them from the lease (coercing nulls to empty strings):

```tsx
    setForm({
      tenant_name: current.tenant_name,
      tenant_email: current.tenant_email,
      tenant_phone: current.tenant_phone ?? "",
      co_tenants: current.co_tenants.map((c) => ({
        name: c.name,
        email: c.email,
        phone: c.phone ?? "",
      })),
      rent_amount: current.rent_amount,
      rent_frequency: current.rent_frequency,
      bond_amount: current.bond_amount,
      notice_period_days: current.notice_period_days,
      start_date: current.start_date,
      end_date: current.end_date,
    });
```

- [ ] **Step 3: Replace the two tenant inputs in the edit form with TenantFields** — inside the `{editing && form ? (<form ...>` block, replace the `placeholder="Tenant name"` and `placeholder="Tenant email"` `<input>` elements with:

```tsx
          <TenantFields
            tenantName={form.tenant_name}
            tenantEmail={form.tenant_email}
            tenantPhone={form.tenant_phone}
            coTenants={form.co_tenants}
            onMain={(field, value) => set(field, value)}
            onCoTenants={(next) => set("co_tenants", next)}
          />
```

- [ ] **Step 4: Show phone + co-tenants on the read-only detail view** — in the `<dl>` block, after the existing `Email` `Field`, add a `Phone` field, and after the `End` field add a co-tenants list:

```tsx
            <Field label="Phone" value={lease.tenant_phone || "—"} />
```

and after `<Field label="End" value={lease.end_date} />`:

```tsx
            {lease.co_tenants.length > 0 && (
              <div className="py-2">
                <p className="text-gray-500">Co-tenants</p>
                <ul className="mt-1 space-y-1">
                  {lease.co_tenants.map((c, i) => (
                    <li key={i} className="text-gray-800">
                      {c.name} — {c.email}
                      {c.phone ? ` — ${c.phone}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}
```

- [ ] **Step 5: Verify build** — `cd frontend && npm run lint && npm run build` — clean.

- [ ] **Step 6: Commit, push, report, wait** — commit message: `Add tenant roster to the lease edit form and detail view`

---

### Task 6: Frontend profile — lib + page + dashboard link

**Files:**
- Create: `frontend/src/lib/profile.ts`, `frontend/src/app/app/profile/page.tsx`
- Modify: `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: `apiFetch`, `getAccessToken`.
- Produces: `Me { id, email, name, phone, role, organization_id }`; `getMe()`, `updateProfile({ name, phone })`.

- [ ] **Step 1: Profile API module** — `frontend/src/lib/profile.ts`

```typescript
import { apiFetch } from "@/lib/api";

export interface Me {
  id: string;
  email: string;
  name: string;
  phone: string | null;
  role: string;
  organization_id: string;
}

export function getMe() {
  return apiFetch<Me>("/api/v1/auth/me");
}

export function updateProfile(body: { name: string; phone: string }) {
  return apiFetch<Me>("/api/v1/auth/me", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
```

- [ ] **Step 2: Profile page** — `frontend/src/app/app/profile/page.tsx`

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { getMe, updateProfile } from "@/lib/profile";

export default function ProfilePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    getMe()
      .then((me) => {
        if (!active) return;
        setName(me.name);
        setPhone(me.phone ?? "");
        setEmail(me.email);
      })
      .catch(() => {
        if (active) setError("Could not load profile");
      });
    return () => {
      active = false;
    };
  }, [router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setStatus(null);
    try {
      await updateProfile({ name, phone });
      setStatus("Saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Contact info</h1>
      <p className="mb-4 text-sm text-gray-600">{email}</p>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      {status && <p className="mb-2 text-sm text-green-700">{status}</p>}
      <form onSubmit={onSubmit} className="space-y-3">
        <input
          required
          placeholder="Your name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <input
          placeholder="Phone (optional)"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          Save
        </button>
      </form>
      <p className="mt-6">
        <Link href="/app" className="text-blue-600">
          Back to dashboard
        </Link>
      </p>
    </main>
  );
}
```

- [ ] **Step 3: Add the dashboard link** — `frontend/src/app/app/page.tsx`

Add a "Contact info" link in the link row, after the "Change password" link:

```tsx
        <Link href="/app/profile" className="rounded border px-3 py-1 text-blue-600">
          Contact info
        </Link>
```

- [ ] **Step 4: Verify build** — `cd frontend && npm run lint && npm run build` — clean; `/app/profile` appears in the route manifest.

- [ ] **Step 5: Commit, push, report, wait** — commit message: `Add profile contact-info page and dashboard link`

---

### Task 7: e2e — co-tenant on a lease + profile phone

**Files:**
- Modify: `frontend/e2e/leases.spec.ts`
- Create: `frontend/e2e/profile.spec.ts`

**Interfaces:**
- Consumes: the full stack from Tasks 1-6, backend on 8000 with the migration applied.

- [ ] **Step 1: Add a co-tenant in the lease e2e** — in `frontend/e2e/leases.spec.ts`, in the first test (the create flow), after filling the main tenant email and before submitting "Add lease", fill the main tenant phone and add one co-tenant row:

```typescript
  await page.getByPlaceholder("Tenant phone (optional)").fill("555-1000");
  await page.getByRole("button", { name: "Add co-tenant" }).click();
  await page.getByLabel("Co-tenant 1 name").fill("Coco Tenant");
  await page.getByLabel("Co-tenant 1 email").fill("coco@example.com");
  await page.getByLabel("Co-tenant 1 phone").fill("555-2000");
```

Then, on the lease detail page (where the test already asserts `tina@example.com` is visible), also assert the co-tenant shows:

```typescript
  await expect(page.getByText("coco@example.com")).toBeVisible();
```

- [ ] **Step 2: Write the profile e2e** — `frontend/e2e/profile.spec.ts`

```typescript
import { expect, test } from "@playwright/test";

const owner = `profile-e2e-${Date.now()}@example.com`;

test("a user can edit their contact info", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Profile Owner");
  await page.getByPlaceholder("Organization name").fill("Profile Org");
  await page.getByPlaceholder("Email").fill(owner);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Contact info" }).click();
  await expect(page).toHaveURL(/\/app\/profile$/);
  await page.getByPlaceholder("Phone (optional)").fill("555-4242");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved")).toBeVisible();

  // Reload — the saved phone is fetched back.
  await page.reload();
  await expect(page.getByPlaceholder("Phone (optional)")).toHaveValue("555-4242");
});
```

- [ ] **Step 2b: Run e2e locally**

Prereq: Postgres up; backend on 8000 with `uv run alembic upgrade head` applied; frontend startable by Playwright.
Run: `cd frontend && npx playwright test`
Expected: all e2e pass.

- [ ] **Step 3: Commit, push, watch all three CI jobs green**

```bash
git add frontend
git commit -m "Add e2e for lease co-tenant roster and profile editing"
git push
gh run watch --exit-status
```

- [ ] **Step 4: Report — Plan A complete (lease tenant roster + user phone + profile editing). Wait for approval to write Plan B (tenant invitations + portal).**

---

## Next (separate plan)

- **Plan B:** Tenant invitations + portal — `Invitation.lease_id`, `LeaseTenant` join table, `POST /leases/{id}/invite`, extend accept to link the lease, `GET /leases/{id}/tenants`, `GET /api/v1/me/leases` (with landlord contact incl. phone), and dashboard tenant-role branching. Per the same spec.
