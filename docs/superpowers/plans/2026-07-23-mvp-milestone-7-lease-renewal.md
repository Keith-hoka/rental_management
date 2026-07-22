# Milestone 7: Lease Renewal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A manager renews an expiring lease in one action, producing a successor lease for the same tenants that is linked back to its predecessor and carries the tenants' portal access across.

**Architecture:** Renewal adds one nullable self-referential column `Lease.renewed_from_id` and one endpoint `POST /api/v1/leases/{lease_id}/renew` that copies tenant identity from the source lease, applies overridden terms, copies `LeaseTenant` rows, and writes in-app notifications. Everything else is reuse: `get_owned_lease` for org isolation, `overlapping_lease_exists` for date conflicts, `generate_charges` and `_lease_state` unchanged. The one behaviour change elsewhere is that `_expiring_leases` stops returning leases that already have a successor.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js 16 App Router, Tailwind v4, Playwright. No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- This migration adds **no enum**: plain add-column + FK + unique index, reversed in `downgrade`. Verify upgrade -> downgrade -> upgrade. Current head: `b83f5c0a1e47`.
- Accessible names are pinned by 24 Playwright specs. The only new names introduced are `Renew lease`, `Create renewal`, `View renewal`, `View previous lease`. No new element may duplicate a name already present on the same page.
- Backend tests run from `backend/` with `uv run pytest`. Frontend commands run from `frontend/`.
- **Correction to the spec:** the spec's Endpoint section says date-order violations return 400. The existing `create_lease` returns **422** (`"start_date must be on or before end_date"`). This plan uses 422 to match the code. Everything else in the spec stands.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/lease.py` | add the `renewed_from_id` column |
| `backend/alembic/versions/<rev>_add_lease_renewed_from.py` | schema change, reversible |
| `backend/app/schemas/lease.py` | `LeaseRenew` input; `renewed_from_id` / `renewed_to_id` on `LeaseResponse` |
| `backend/app/routers/leases.py` | the `/renew` endpoint; populate `renewed_to_id` on the single-lease GET |
| `backend/app/services/reminders.py` | exclude renewed leases from `_expiring_leases` |
| `backend/tests/test_lease_renewal.py` | all renewal behaviour |
| `backend/tests/test_reminders.py` | the suppression case |
| `frontend/src/lib/leases.ts` | `renewLease` + the two new response fields |
| `frontend/src/app/app/leases/[leaseId]/page.tsx` | button + the two cross-links |
| `frontend/src/app/app/leases/[leaseId]/renew/page.tsx` | the renewal form |
| `frontend/e2e/lease-renewal.spec.ts` | end-to-end renewal |

---

### Task 1: Model column + migration

**Files:**
- Modify: `backend/app/models/lease.py:34`
- Create: `backend/alembic/versions/<rev>_add_lease_renewed_from.py`
- Test: `backend/tests/test_lease_renewal.py`

**Interfaces:**
- Produces: `Lease.renewed_from_id: uuid.UUID | None` — nullable, unique, indexed, FK to `leases.id`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_lease_renewal.py`:

```python
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def test_renewed_from_id_defaults_to_none(client, db_session):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(created["id"])))
    ).scalar_one()
    assert lease.renewed_from_id is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_lease_renewal.py -v`
Expected: FAIL with `AttributeError: 'Lease' object has no attribute 'renewed_from_id'`.

- [ ] **Step 3: Add the column**

In `backend/app/models/lease.py`, after the `created_at` line (currently line 34), add:

```python
    renewed_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leases.id"), unique=True, index=True
    )
```

`unique` makes "at most one successor per lease" a database guarantee. PostgreSQL allows many `NULL`s in a unique column, so un-renewed leases are unaffected.

- [ ] **Step 4: Generate the migration file**

Run: `cd backend && uv run alembic revision -m "add lease renewed_from"`

Replace the generated `upgrade`/`downgrade` with this (keep the generated `revision` / `down_revision` values; `down_revision` must be `b83f5c0a1e47`):

```python
def upgrade() -> None:
    op.add_column("leases", sa.Column("renewed_from_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_leases_renewed_from_id_leases", "leases", "leases", ["renewed_from_id"], ["id"]
    )
    op.create_index(
        "ix_leases_renewed_from_id", "leases", ["renewed_from_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_leases_renewed_from_id", table_name="leases")
    op.drop_constraint("fk_leases_renewed_from_id_leases", "leases", type_="foreignkey")
    op.drop_column("leases", "renewed_from_id")
```

Do not use `alembic revision --autogenerate` here. Autogenerate has repeatedly produced broken enum handling in this project; a hand-written migration is the established practice.

- [ ] **Step 5: Verify the migration round-trips**

```bash
cd backend
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all three succeed with no error. The middle step proves `downgrade` is real, not decorative.

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_lease_renewal.py -v`
Expected: PASS.

- [ ] **Step 7: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 8: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 9: Commit and push**

```bash
git add backend/app/models/lease.py backend/alembic/versions backend/tests/test_lease_renewal.py
git commit -m "Add Lease.renewed_from_id column and migration"
git push origin main
```

Then report and wait for approval.

---

### Task 2: LeaseRenew schema + the renew endpoint

**Files:**
- Modify: `backend/app/schemas/lease.py`, `backend/app/routers/leases.py`
- Test: `backend/tests/test_lease_renewal.py`

**Interfaces:**
- Consumes: `Lease.renewed_from_id` (Task 1).
- Produces:
  - `LeaseRenew` with fields `end_date: date`, `start_date: date | None`, `rent_amount: Decimal | None`, `rent_frequency: LeaseFrequency | None`, `bond_amount: Decimal | None`, `notice_period_days: int | None`.
  - `POST /api/v1/leases/{lease_id}/renew` -> `201 LeaseResponse`.
  - `LeaseResponse.renewed_from_id: uuid.UUID | None`, `LeaseResponse.renewed_to_id: uuid.UUID | None = None`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_lease_renewal.py`:

```python
async def _make_lease(client, headers, **overrides):
    property_id = await make_property(client, headers, overrides.pop("address", "1 Renew St"))
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(**overrides),
            headers=headers,
        )
    ).json()
    return property_id, created


async def test_renew_copies_tenant_and_defaults_start_to_day_after(client):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-12-31"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tenant_name"] == lease["tenant_name"]
    assert body["tenant_email"] == lease["tenant_email"]
    assert body["start_date"] == "2027-01-01"
    assert body["end_date"] == "2027-12-31"
    assert float(body["rent_amount"]) == float(lease["rent_amount"])
    assert body["rent_frequency"] == lease["rent_frequency"]
    assert body["renewed_from_id"] == lease["id"]
    assert body["id"] != lease["id"]


async def test_renew_applies_overrides(client):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-06-30", "rent_amount": 1650, "rent_frequency": "weekly"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert float(body["rent_amount"]) == 1650.0
    assert body["rent_frequency"] == "weekly"


async def test_renewing_twice_is_rejected(client):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    first = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-12-31"},
        headers=headers,
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2028-12-31"},
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "Lease has already been renewed"


async def test_renew_rejects_overlapping_dates(client):
    headers = await landlord_headers(client)
    property_id, lease = await _make_lease(client, headers)
    # A second lease already occupies 2027, so the renewal cannot start in it.
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2027-01-01", end_date="2027-12-31"),
        headers=headers,
    )
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-06-30"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Lease dates overlap an existing lease"


async def test_renew_rejects_end_before_start(client):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"start_date": "2027-06-01", "end_date": "2027-01-01"},
        headers=headers,
    )
    assert response.status_code == 422


async def test_renew_other_org_lease_is_404(client):
    owner = await landlord_headers(client, "renew-owner@example.com")
    _, lease = await _make_lease(client, owner)
    stranger = await landlord_headers(client, "renew-stranger@example.com")
    response = await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": "2027-12-31"},
        headers=stranger,
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_lease_renewal.py -v`
Expected: the six new tests FAIL with 404/405 (the route does not exist).

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/lease.py`, after `LeaseUpdate`, add:

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

`end_date` is the only required field: there is no defensible default for how long the new term runs.

In the same file, add two fields to `LeaseResponse`, after `created_at`:

```python
    renewed_from_id: uuid.UUID | None = None
    renewed_to_id: uuid.UUID | None = None
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/routers/leases.py`, extend the schema import on the existing line:

```python
from app.schemas.lease import LeaseCreate, LeaseRenew, LeaseResponse, LeaseSummary, LeaseUpdate
```

Then add, immediately after `get_owned_lease`:

```python
async def successor_id(session: AsyncSession, lease_id: uuid.UUID) -> uuid.UUID | None:
    """The id of the lease that renewed this one, if it has been renewed."""
    return (
        await session.execute(select(Lease.id).where(Lease.renewed_from_id == lease_id))
    ).scalar_one_or_none()


@router.post("/leases/{lease_id}/renew", status_code=201, response_model=LeaseResponse)
async def renew_lease(
    lease_id: uuid.UUID,
    body: LeaseRenew,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Create a successor lease for the same tenants, linked back to the source."""
    source = await get_owned_lease(lease_id, membership, session)
    if await successor_id(session, lease_id) is not None:
        raise HTTPException(status_code=409, detail="Lease has already been renewed")

    start = body.start_date or source.end_date + timedelta(days=1)
    if start > body.end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if await overlapping_lease_exists(session, source.property_id, start, body.end_date):
        raise HTTPException(status_code=409, detail="Lease dates overlap an existing lease")

    renewal = Lease(
        organization_id=source.organization_id,
        property_id=source.property_id,
        tenant_name=source.tenant_name,
        tenant_email=source.tenant_email,
        tenant_phone=source.tenant_phone,
        co_tenants=source.co_tenants,
        rent_amount=body.rent_amount if body.rent_amount is not None else source.rent_amount,
        rent_frequency=body.rent_frequency or source.rent_frequency,
        bond_amount=body.bond_amount if body.bond_amount is not None else source.bond_amount,
        notice_period_days=(
            body.notice_period_days
            if body.notice_period_days is not None
            else source.notice_period_days
        ),
        start_date=start,
        end_date=body.end_date,
        renewed_from_id=source.id,
    )
    session.add(renewal)
    await session.commit()
    await session.refresh(renewal)
    return renewal
```

`timedelta` is already imported at the top of this file.

- [ ] **Step 5: Populate `renewed_to_id` on the single-lease GET**

Change the body of the existing `get_lease` handler (at `backend/app/routers/leases.py:117`) so it fills the reverse link:

```python
@router.get("/leases/{lease_id}", response_model=LeaseResponse)
async def get_lease(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> LeaseResponse:
    """One lease in the caller's organization, including its renewal link."""
    lease = await get_owned_lease(lease_id, membership, session)
    response = LeaseResponse.model_validate(lease)
    response.renewed_to_id = await successor_id(session, lease_id)
    return response
```

Only this endpoint resolves the reverse lookup. `LeaseResponse` is also returned by create, update and the per-property list; doing it there would cost one extra query per lease for a value nothing renders.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_lease_renewal.py -v`
Expected: all seven PASS.

- [ ] **Step 7: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass. In particular `tests/test_leases.py` must stay green — `get_lease` changed from returning a model to returning a schema.

- [ ] **Step 8: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 9: Commit and push**

```bash
git add backend/app/schemas/lease.py backend/app/routers/leases.py backend/tests/test_lease_renewal.py
git commit -m "Add the lease renewal endpoint"
git push origin main
```

Then report and wait for approval.

---

### Task 3: Carry tenant access across, and notify

**Files:**
- Modify: `backend/app/routers/leases.py`
- Test: `backend/tests/test_lease_renewal.py`

**Interfaces:**
- Consumes: `renew_lease` (Task 2); `notify_users`, `manager_user_ids`, `lease_tenant_user_ids` from `app/services/notify.py`.
- Produces: `LeaseTenant` rows on the successor; `Notification` rows with category `"lease_renewal"`.

- [ ] **Step 1: Write the failing tests**

Add these imports to the top of `backend/tests/test_lease_renewal.py` (ruff E402 — imports stay at the top):

```python
from app.models import Notification
from tests.test_portal import onboard_tenant
```

Append:

```python
async def test_renewal_carries_tenant_portal_access(client, db_session):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    tenant_headers = await onboard_tenant(
        client, db_session, headers, lease["id"], "renew-tenant@example.com"
    )
    renewal = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew",
            json={"end_date": "2027-12-31"},
            headers=headers,
        )
    ).json()

    mine = (await client.get("/api/v1/me/leases", headers=tenant_headers)).json()
    ids = {entry["id"] for entry in mine}
    assert renewal["id"] in ids, "the tenant cannot see the lease they were renewed onto"
    assert lease["id"] in ids


async def test_renewal_notifies_tenant_and_manager(client, db_session):
    headers = await landlord_headers(client)
    _, lease = await _make_lease(client, headers)
    await onboard_tenant(client, db_session, headers, lease["id"], "renew-notify@example.com")
    renewal = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew",
            json={"end_date": "2027-12-31"},
            headers=headers,
        )
    ).json()

    rows = (
        (
            await db_session.execute(
                select(Notification).where(Notification.category == "lease_renewal")
            )
        )
        .scalars()
        .all()
    )
    # One landlord plus one onboarded tenant.
    assert len(rows) == 2
    assert all(row.link == f"/app/leases/{renewal['id']}" for row in rows)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_lease_renewal.py -k "carries or notifies" -v`
Expected: FAIL — the first because the successor id is missing from the tenant's leases, the second because no `lease_renewal` rows exist.

- [ ] **Step 3: Implement both side effects**

In `backend/app/routers/leases.py`, add to the imports:

```python
from app.services.notify import lease_tenant_user_ids, manager_user_ids, notify_users
```

In `renew_lease`, replace the block from `session.add(renewal)` to `return renewal` with:

```python
    session.add(renewal)
    await session.flush()

    # LeaseTenant is what GET /me/leases reads, so without this copy the tenant
    # cannot see the lease they were just renewed onto.
    for user_id in await lease_tenant_user_ids(session, source.id):
        session.add(LeaseTenant(lease_id=renewal.id, user_id=user_id))

    recipients = await manager_user_ids(session, source.organization_id)
    recipients += await lease_tenant_user_ids(session, source.id)
    await notify_users(
        session,
        recipients,
        source.organization_id,
        "lease_renewal",
        "Lease renewed",
        f"The lease for {source.tenant_name} now runs to {renewal.end_date}.",
        f"/app/leases/{renewal.id}",
    )

    await session.commit()
    await session.refresh(renewal)
    return renewal
```

`await session.flush()` assigns `renewal.id` before it is referenced by the `LeaseTenant` rows and the notification link, without ending the transaction — so the whole renewal still commits or rolls back as one unit.

`LeaseTenant` is already imported at the top of this file.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_lease_renewal.py -v`
Expected: all nine PASS.

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 6: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/routers/leases.py backend/tests/test_lease_renewal.py
git commit -m "Carry tenant access to the renewal and notify both sides"
git push origin main
```

Then report and wait for approval.

---

### Task 4: Stop reminding about renewed leases, and prove charges follow

**Files:**
- Modify: `backend/app/services/reminders.py:28-37`
- Test: `backend/tests/test_reminders.py`, `backend/tests/test_lease_renewal.py`

**Interfaces:**
- Consumes: `Lease.renewed_from_id` (Task 1); `renew_lease` (Task 2).
- Produces: no new public interface. `_expiring_leases` keeps its signature `(session, today, window_end) -> list[tuple[Lease, str]]`.

- [ ] **Step 1: Write the failing reminder test**

Append to `backend/tests/test_reminders.py` (its existing imports and the `captured` fixture stay as they are):

```python
async def test_renewed_leases_stop_getting_expiry_reminders(client, db_session, captured):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers, "9 Reminder St")
    today = date.today()
    lease = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=7)),
            ),
            headers=headers,
        )
    ).json()

    await client.post(
        f"/api/v1/leases/{lease['id']}/renew",
        json={"end_date": str(today + timedelta(days=372))},
        headers=headers,
    )

    sent = await run_expiry_reminders(db_session, today)
    assert sent == 0, "a renewed lease should not generate an expiry reminder"
```

If `landlord_headers`, `make_property`, `lease_body`, `date`, `timedelta` or `run_expiry_reminders` are not already imported at the top of `test_reminders.py`, add them there — not inside the function (ruff E402).

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_reminders.py -k renewed -v`
Expected: FAIL with `assert 1 == 0` — the reminder still fires.

- [ ] **Step 3: Exclude renewed leases**

In `backend/app/services/reminders.py`, add `aliased` to the SQLAlchemy imports:

```python
from sqlalchemy import select
from sqlalchemy.orm import aliased
```

Replace `_expiring_leases` with:

```python
async def _expiring_leases(
    session: AsyncSession, today: date, window_end: date
) -> list[tuple[Lease, str]]:
    """Leases (with property address) ending in [today, window_end] that have no successor."""
    successor = aliased(Lease)
    result = await session.execute(
        select(Lease, Property.address)
        .join(Property, Property.id == Lease.property_id)
        .where(
            Lease.end_date >= today,
            Lease.end_date <= window_end,
            ~select(successor.id).where(successor.renewed_from_id == Lease.id).exists(),
        )
    )
    return list(result.all())
```

The alias is required, not stylistic: without it the subquery references the same `Lease` entity as the outer query and correlates to itself, so the condition would not mean what it reads as.

- [ ] **Step 4: Run it to verify it passes**

Run: `cd backend && uv run pytest tests/test_reminders.py -v`
Expected: all PASS, including the existing M3.4 reminder tests — an un-renewed lease must still be reminded about.

- [ ] **Step 5: Write the charges test**

Append to `backend/tests/test_lease_renewal.py`. Add `from app.services.charges import generate_charges` and `from app.models import Charge` to the imports at the top:

```python
async def test_charges_are_generated_for_the_renewal(client, db_session):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers, "11 Charge St")
    today = date.today()
    lease = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=3)),
            ),
            headers=headers,
        )
    ).json()
    renewal = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew",
            json={"end_date": str(today + timedelta(days=120)), "rent_frequency": "weekly"},
            headers=headers,
        )
    ).json()

    await generate_charges(db_session, today)

    charges = (
        (
            await db_session.execute(
                select(Charge).where(Charge.lease_id == uuid.UUID(renewal["id"]))
            )
        )
        .scalars()
        .all()
    )
    assert charges, "the successor lease produced no rent charges"
    assert all(c.period_start >= date.fromisoformat(renewal["start_date"]) for c in charges)
```

Add `from datetime import date, timedelta` to the top of the file if it is not already there.

This test exists because "charges need no change" is an inference from reading `generate_charges`, not an observed fact. If the inference is wrong, this fails now rather than in production.

- [ ] **Step 6: Run it**

Run: `cd backend && uv run pytest tests/test_lease_renewal.py -k charges -v`
Expected: PASS with no production-code change. **If it fails, stop and report** — the spec's "no change needed" claim is then wrong and needs a design decision, not a patch.

- [ ] **Step 7: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 8: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 9: Commit and push**

```bash
git add backend/app/services/reminders.py backend/tests/test_reminders.py backend/tests/test_lease_renewal.py
git commit -m "Stop reminding about renewed leases; cover renewal charges"
git push origin main
```

Then report and wait for approval.

---

### Task 5: Frontend renewal page, button and cross-links

**Files:**
- Modify: `frontend/src/lib/leases.ts`, `frontend/src/app/app/leases/[leaseId]/page.tsx:259`
- Create: `frontend/src/app/app/leases/[leaseId]/renew/page.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/leases/{id}/renew` (Task 2); `Lease.renewed_from_id` / `renewed_to_id` on the GET response (Task 2).
- Produces: `renewLease(id, input)`; the accessible names `Renew lease`, `Create renewal`, `View renewal`, `View previous lease`.

- [ ] **Step 1: Extend the API client**

In `frontend/src/lib/leases.ts`, add two fields to the `Lease` interface after `created_at`:

```ts
  renewed_from_id: string | null;
  renewed_to_id: string | null;
```

Add the input type after `LeaseInput`:

```ts
export interface LeaseRenewInput {
  end_date: string;
  start_date?: string;
  rent_amount?: number;
  rent_frequency?: LeaseFrequency;
  bond_amount?: number | null;
  notice_period_days?: number | null;
}
```

Add the call after `updateLease`:

```ts
export function renewLease(id: string, input: LeaseRenewInput) {
  return apiFetch<Lease>(`/api/v1/leases/${id}/renew`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
```

- [ ] **Step 2: Create the renewal page**

Create `frontend/src/app/app/leases/[leaseId]/renew/page.tsx`:

```tsx
"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getLease, renewLease, type Lease, type LeaseFrequency } from "@/lib/leases";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Button, Card, Field, Input, PageHeader, Select } from "@/components/ui";

function dayAfter(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

export default function RenewLeasePage({ params }: { params: Promise<{ leaseId: string }> }) {
  const { leaseId } = use(params);
  const router = useRouter();
  const { me, unread, logOut } = useShell();
  const [lease, setLease] = useState<Lease | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rent, setRent] = useState(0);
  const [frequency, setFrequency] = useState<LeaseFrequency>("monthly");
  const [bond, setBond] = useState<number | null>(null);
  const [noticeDays, setNoticeDays] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    let active = true;
    getLease(leaseId)
      .then((l) => {
        if (!active) return;
        setLease(l);
        setStartDate(dayAfter(l.end_date));
        setRent(l.rent_amount);
        setFrequency(l.rent_frequency);
        setBond(l.bond_amount);
        setNoticeDays(l.notice_period_days);
      })
      .catch(() => active && setError("Lease not found"));
    return () => {
      active = false;
    };
  }, [leaseId, me]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const renewal = await renewLease(leaseId, {
        start_date: startDate,
        end_date: endDate,
        rent_amount: rent,
        rent_frequency: frequency,
        bond_amount: bond,
        notice_period_days: noticeDays,
      });
      router.push(`/app/leases/${renewal.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Renewal failed");
    }
  }

  if (!me) return null;
  if (!lease)
    return (
      <AppShell me={me} unread={unread} onLogOut={logOut}>
        {error && <p className="text-danger">{error}</p>}
      </AppShell>
    );

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Renew lease" />
        <p className="mb-4 text-sm text-muted">
          The same tenants carry over. To let someone else move in, add a new lease instead.
        </p>
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
      <Card className="mx-auto max-w-2xl">
        <div className="mb-4 rounded-lg border border-border p-3 text-sm">
          <p className="font-medium text-text">{lease.tenant_name}</p>
          <p className="text-muted">{lease.tenant_email}</p>
          {lease.co_tenants.map((c) => (
            <p key={c.email} className="text-muted">
              {c.name} ({c.email})
            </p>
          ))}
        </div>
        <form onSubmit={onSubmit} className="space-y-3">
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Rent">
                <Input
                  type="number"
                  min={0}
                  required
                  value={rent || ""}
                  onChange={(e) => setRent(Number(e.target.value))}
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="Frequency">
                <Select
                  value={frequency}
                  onChange={(e) => setFrequency(e.target.value as LeaseFrequency)}
                >
                  <option value="weekly">Weekly</option>
                  <option value="fortnightly">Fortnightly</option>
                  <option value="monthly">Monthly</option>
                </Select>
              </Field>
            </div>
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Bond (optional)">
                <Input
                  type="number"
                  min={0}
                  value={bond ?? ""}
                  onChange={(e) => setBond(e.target.value === "" ? null : Number(e.target.value))}
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="Notice period (days)">
                <Input
                  type="number"
                  min={0}
                  value={noticeDays ?? ""}
                  onChange={(e) =>
                    setNoticeDays(e.target.value === "" ? null : Number(e.target.value))
                  }
                />
              </Field>
            </div>
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <Field label="Start">
                <Input
                  type="date"
                  required
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="End">
                <Input
                  type="date"
                  required
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                />
              </Field>
            </div>
          </div>
          <Button type="submit" className="w-full">
            Create renewal
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="w-full"
            onClick={() => router.push(`/app/leases/${leaseId}`)}
          >
            Cancel
          </Button>
        </form>
      </Card>
    </AppShell>
  );
}
```

`End` is left blank deliberately — the new term length is the one thing the manager must decide.

- [ ] **Step 3: Add the button and cross-links to the detail page**

In `frontend/src/app/app/leases/[leaseId]/page.tsx`, replace line 259:

```tsx
        <PageHeader title={editing ? "Edit lease" : "Lease"} />
```

with:

```tsx
        <PageHeader
          title={editing ? "Edit lease" : "Lease"}
          actions={
            !editing && (
              <>
                {lease.renewed_to_id ? (
                  <Link href={`/app/leases/${lease.renewed_to_id}`} className={linkButtonOutline}>
                    View renewal
                  </Link>
                ) : (
                  <Link href={`/app/leases/${leaseId}/renew`} className={linkButtonOutline}>
                    Renew lease
                  </Link>
                )}
                {lease.renewed_from_id && (
                  <Link
                    href={`/app/leases/${lease.renewed_from_id}`}
                    className={linkButtonSecondary}
                  >
                    View previous lease
                  </Link>
                )}
              </>
            )
          }
        />
```

Add `linkButtonOutline` and `linkButtonSecondary` to the existing `@/components/ui` import on line 9, and confirm `Link` from `next/link` is imported (add it if not).

These links are labelled with fixed strings rather than the property address: the address is already the page heading, and a duplicate accessible name breaks Playwright strict mode — the trap the redesign hit with the `Leases` link on the property detail page.

- [ ] **Step 4: Lint, typecheck and build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: both clean. `npm run build` runs the TypeScript check.

- [ ] **Step 5: Restart the backend, then check the page by hand**

The backend must be restarted to serve the new route. Then sign in, open a lease, and confirm: `Renew lease` appears; the form prefills rent/frequency/bond/notice and a start date one day after the old end; submitting lands on the new lease; the old lease now shows `View renewal` and the new one `View previous lease`.

- [ ] **Step 6: Commit and push**

```bash
git add frontend/src/lib/leases.ts "frontend/src/app/app/leases/[leaseId]/page.tsx" "frontend/src/app/app/leases/[leaseId]/renew/page.tsx"
git commit -m "Add the lease renewal page, button and cross-links"
git push origin main
```

Then report and wait for approval.

---

### Task 6: End-to-end coverage

**Files:**
- Create: `frontend/e2e/lease-renewal.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-5.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/lease-renewal.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const email = `renewal-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("a landlord renews a lease and the two are linked", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Renewal Owner");
  await page.getByPlaceholder("Organization name").fill("Renewal Org");
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("3 Renewal Road");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "3 Renewal Road (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Rita Renewal");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent").fill("500");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(20));
  await page.getByRole("button", { name: "Add lease" }).click();

  await page.getByRole("link", { name: "3 Renewal Road" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  const originalUrl = page.url();

  await page.getByRole("link", { name: "Renew lease" }).click();
  await expect(page.getByRole("heading", { name: "Renew lease" })).toBeVisible();
  // The start date is prefilled from the old lease's end date; only the term
  // length and the new rent need deciding.
  await expect(page.getByLabel("Start")).toHaveValue(isoDate(21));
  // Not toHaveValue("500"): Pydantic serialises Decimal as a JSON string, so the
  // prefilled rent may render as "500.00". Assert that prefill happened without
  // guessing the serialisation. Tighten this once Step 5 of Task 5 shows the
  // actual value in the browser.
  await expect(page.getByLabel("Rent")).not.toHaveValue("");
  await page.getByLabel("Rent").fill("550");
  await page.getByLabel("End").fill(isoDate(385));
  await page.getByRole("button", { name: "Create renewal" }).click();

  // Lands on the successor, which links back.
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await expect(page).not.toHaveURL(originalUrl);
  await expect(page.getByRole("link", { name: "View previous lease" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Renew lease" })).toHaveCount(0);

  // The predecessor now offers the renewal instead of a second renew.
  await page.goto(originalUrl);
  await expect(page.getByRole("heading", { name: "Lease" })).toBeVisible();
  await expect(page.getByRole("link", { name: "View renewal" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Renew lease" })).toHaveCount(0);
});
```

The final block asserts a positive condition (`heading` visible, then `View renewal` visible) *before* the `toHaveCount(0)`. A `toHaveCount(0)` fired during a client-side navigation passes against an empty DOM and never retries — that exact mistake produced a test that stayed green against a reintroduced bug earlier in this project.

- [ ] **Step 2: Restart the backend so the new route is served**

The e2e run hits a live backend. If it was started before Task 2, the `/renew` route returns 404.

- [ ] **Step 3: Run the new spec**

Run: `cd frontend && npx playwright test lease-renewal`
Expected: 1 passed.

- [ ] **Step 4: Run the whole e2e suite**

Run: `cd frontend && npx playwright test`
Expected: all pass (24 existing plus this one).

- [ ] **Step 5: Full backend test run and ruff sequence**

```bash
cd backend
uv run pytest
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 6: Commit and push**

```bash
git add frontend/e2e/lease-renewal.spec.ts
git commit -m "Add lease renewal e2e"
git push origin main
```

- [ ] **Step 7: Confirm CI is green**

Run: `gh run list --limit 3`
Expected: the newest run for `main` completes successfully. If it fails, read the log before changing anything — the failure is evidence, not noise.

Then report and wait for approval.
