# Milestone 4.2: Payments + Balances + Tenant View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Managers record rent payments against a lease; the system waterfall-allocates them across charges to derive per-charge status, overdue flags, and outstanding balance, all visible to managers and tenants.

**Architecture:** `Payment` rows belong to a lease. A pure `allocate(charges, total_paid, today)` computes each charge's paid amount/status/overdue; `summarize(...)` reduces to outstanding/overdue/credit. Status is never stored — always derived — so payment edits/deletes need no cascade.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, Next.js. No new dependencies.

## Global Constraints

- Package manager: `uv` only (`uv run ...`, `uv add ...`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before EVERY push, from `backend/`, in order:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- **Ruff gotcha:** test files keep ALL imports at the top (E402). When a later task adds a test needing new imports, edit the top import block — never append imports mid-file.
- Each task ends with: full test run -> ruff sequence -> commit -> `git push` (CI) -> report -> WAIT for approval.
- Migration adds a PostgreSQL enum: after autogenerate, ADD the enum drop to `downgrade` (`sa.Enum(name="paymentmethod").drop(op.get_bind())` after `drop_table`), and verify upgrade -> downgrade -> upgrade. If the 2nd upgrade errors "type already exists", the enum drop is missing. Current head: `a1f62405d415`.
- Product rules: payment attaches to the lease (waterfall oldest-first); overdue = past-due and not fully covered (no grace); outstanding counts only `due_date <= today`; overpayment = credit.
- Backend tests: `cd backend && uv run pytest -q`. Frontend: `npm run lint`, `npm run build`, e2e `npx playwright test` from `frontend/`.
- Restart the e2e backend after new endpoints: `lsof -ti tcp:8000 | xargs kill` then `uv run uvicorn app.main:app --port 8000`.

---

## Task Overview

1. `Payment` model + `PaymentMethod` enum + migration
2. `allocate` + `summarize` pure logic
3. Payment schemas + record/list/delete endpoints
4. Async status helpers + charges-with-status + balance endpoint
5. Tenant portal: balance on `/me/leases` + `/me/leases/{id}/charges`
6. Frontend manager: payments lib + status badges + record form + payments list
7. Frontend tenant: portal charges + balance
8. e2e: record a payment

---

### Task 1: `Payment` model + `PaymentMethod` enum + migration

**Files:**
- Create: `backend/app/models/payment.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_payments.py`
- Test: `backend/tests/test_payment_model.py`

**Interfaces:**
- Produces: `Payment(id, organization_id, lease_id, amount, paid_on, method, note, created_at)` and `PaymentMethod{cash, bank_transfer, other}` importable from `app.models`.

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/test_payment_model.py`:

```python
import uuid
from datetime import date

from sqlalchemy import select

from app.models import Lease, Payment, PaymentMethod
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease(client, db_session, headers, property_id):
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    return (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()


def _payment(lease, method=PaymentMethod.cash, note="first"):
    return Payment(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        amount=1000,
        paid_on=date(2026, 1, 5),
        method=method,
        note=note,
    )


async def test_insert_and_read_payment(client, db_session):
    headers = await landlord_headers(client, "pmodel@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_payment(lease))
    await db_session.commit()

    rows = (
        (await db_session.execute(select(Payment).where(Payment.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert float(rows[0].amount) == 1000.0
    assert rows[0].method == PaymentMethod.cash


async def test_delete_lease_cascades_payments(client, db_session):
    headers = await landlord_headers(client, "pcascade@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_payment(lease, method=PaymentMethod.other, note=None))
    await db_session.commit()

    await client.delete(f"/api/v1/leases/{lease.id}", headers=headers)

    rows = (
        (await db_session.execute(select(Payment).where(Payment.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert rows == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && uv run pytest tests/test_payment_model.py -q`
Expected: FAIL with `ImportError: cannot import name 'Payment' from 'app.models'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/payment.py`:

```python
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PaymentMethod(str, enum.Enum):
    cash = "cash"
    bank_transfer = "bank_transfer"
    other = "other"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    lease_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leases.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    paid_on: Mapped[date] = mapped_column(Date)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 4: Register the model**

Edit `backend/app/models/__init__.py`: add `from app.models.payment import Payment, PaymentMethod` and add `"Payment"` and `"PaymentMethod"` to `__all__`.

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && uv run pytest tests/test_payment_model.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Generate and fix the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "add payments"
```

Open the generated file. `upgrade()` should `op.create_table('payments', ...)` with the columns,
the `method` column as `sa.Enum('cash', 'bank_transfer', 'other', name='paymentmethod')`, the two
FKs (`lease_id` with `ondelete='CASCADE'`), and indexes on `lease_id` and `organization_id`.
Confirm `down_revision = "a1f62405d415"`.

**Fix the downgrade** — after `op.drop_table('payments')`, the enum type must be dropped:

```python
def downgrade() -> None:
    op.drop_index(op.f("ix_payments_organization_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_lease_id"), table_name="payments")
    op.drop_table("payments")
    sa.Enum(name="paymentmethod").drop(op.get_bind())
```

Verify the round-trip:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all three succeed. (If the 2nd upgrade errors "type paymentmethod already exists", the
enum drop line is missing from downgrade.)

- [ ] **Step 7: Full test run + ruff**

```bash
cd backend && uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/models/payment.py backend/app/models/__init__.py \
        backend/alembic/versions backend/tests/test_payment_model.py
git commit -m "Add Payment model, PaymentMethod enum, and migration"
git push
```
Then report and wait for approval.

---

### Task 2: `allocate` + `summarize` pure logic

**Files:**
- Create: `backend/app/services/payments.py`
- Test: `backend/tests/test_payment_allocation.py`

**Interfaces:**
- Consumes: `Charge` from `app.models`.
- Produces: `ChargeStatus{charge, amount_paid: Decimal, status, overdue: bool}`, `Balance{outstanding, overdue_amount, credit}`, `allocate(charges, total_paid, today) -> list[ChargeStatus]`, `summarize(statuses, total_paid, today) -> Balance` in `app.services.payments`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_payment_allocation.py`:

```python
from datetime import date
from decimal import Decimal

from app.models import Charge
from app.services.payments import allocate, summarize

TODAY = date(2026, 6, 1)


def _charge(due, amount):
    return Charge(period_start=due, period_end=due, due_date=due, amount_due=Decimal(amount))


def test_exact_payment_marks_paid():
    st = allocate([_charge(date(2026, 1, 1), 1000)], Decimal(1000), TODAY)
    assert st[0].status == "paid"
    assert st[0].amount_paid == Decimal(1000)
    assert st[0].overdue is False


def test_partial_payment_is_overdue_when_past_due():
    st = allocate([_charge(date(2026, 1, 1), 1000)], Decimal(400), TODAY)
    assert st[0].status == "partial"
    assert st[0].amount_paid == Decimal(400)
    assert st[0].overdue is True


def test_waterfall_across_three():
    charges = [
        _charge(date(2026, 1, 1), 1000),
        _charge(date(2026, 2, 1), 1000),
        _charge(date(2026, 3, 1), 1000),
    ]
    by_due = {s.charge.due_date: s for s in allocate(charges, Decimal(1500), TODAY)}
    assert by_due[date(2026, 1, 1)].status == "paid"
    assert by_due[date(2026, 2, 1)].status == "partial"
    assert by_due[date(2026, 2, 1)].amount_paid == Decimal(500)
    assert by_due[date(2026, 3, 1)].status == "unpaid"


def test_overpay_leaves_credit():
    st = allocate([_charge(date(2026, 1, 1), 1000)], Decimal(1500), TODAY)
    bal = summarize(st, Decimal(1500), TODAY)
    assert st[0].status == "paid"
    assert bal.credit == Decimal(500)
    assert bal.outstanding == Decimal(0)


def test_summarize_outstanding_and_overdue():
    charges = [
        _charge(date(2026, 1, 1), 1000),  # past due
        _charge(date(2026, 6, 1), 1000),  # due today
        _charge(date(2026, 12, 1), 1000),  # upcoming
    ]
    st = allocate(charges, Decimal(0), TODAY)
    bal = summarize(st, Decimal(0), TODAY)
    assert bal.outstanding == Decimal(2000)  # Jan + Jun (due_date <= today)
    assert bal.overdue_amount == Decimal(1000)  # only Jan (< today)
    assert bal.credit == Decimal(0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_payment_allocation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.payments'`.

- [ ] **Step 3: Create the pure logic**

Create `backend/app/services/payments.py`:

```python
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from app.models import Charge

ChargeState = Literal["unpaid", "partial", "paid"]


@dataclass
class ChargeStatus:
    charge: Charge
    amount_paid: Decimal
    status: ChargeState
    overdue: bool


@dataclass
class Balance:
    outstanding: Decimal
    overdue_amount: Decimal
    credit: Decimal


def allocate(charges: list[Charge], total_paid: Decimal, today: date) -> list[ChargeStatus]:
    """Waterfall-allocate total_paid across charges, oldest due date first."""
    pool = total_paid
    result: list[ChargeStatus] = []
    for charge in sorted(charges, key=lambda c: (c.due_date, c.period_start)):
        allocated = min(pool, charge.amount_due)
        pool -= allocated
        if allocated <= 0:
            status: ChargeState = "unpaid"
        elif allocated < charge.amount_due:
            status = "partial"
        else:
            status = "paid"
        overdue = charge.due_date < today and allocated < charge.amount_due
        result.append(ChargeStatus(charge, allocated, status, overdue))
    return result


def summarize(statuses: list[ChargeStatus], total_paid: Decimal, today: date) -> Balance:
    """Reduce per-charge allocation to outstanding / overdue / credit totals."""
    outstanding = Decimal("0")
    overdue_amount = Decimal("0")
    allocated_total = Decimal("0")
    for s in statuses:
        allocated_total += s.amount_paid
        remaining = s.charge.amount_due - s.amount_paid
        if s.charge.due_date <= today:
            outstanding += remaining
        if s.charge.due_date < today:
            overdue_amount += remaining
    return Balance(
        outstanding=outstanding,
        overdue_amount=overdue_amount,
        credit=total_paid - allocated_total,
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && uv run pytest tests/test_payment_allocation.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
git add backend/app/services/payments.py backend/tests/test_payment_allocation.py
git commit -m "Add payment allocation and balance logic"
git push
```
Then report and wait for approval.

---

### Task 3: Payment schemas + record/list/delete endpoints

**Files:**
- Create: `backend/app/schemas/payment.py`
- Create: `backend/app/routers/payments.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_payments_api.py`

**Interfaces:**
- Consumes: `Payment` (Task 1); `manager`, `get_owned_lease` from `app.routers.leases`.
- Produces: `PaymentCreate`, `PaymentInfo`, `BalanceInfo` in `app.schemas.payment`; the payments router with `POST/GET/DELETE /api/v1/leases/{lease_id}/payments`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_payments_api.py`:

```python
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers

PAY = {"amount": 1000, "paid_on": "2026-01-05", "method": "cash", "note": "rent"}


async def _lease_id(client, headers, property_id):
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]


async def test_record_payment_201(client):
    headers = await landlord_headers(client, "pay1@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    resp = await client.post(f"/api/v1/leases/{lid}/payments", json=PAY, headers=headers)
    assert resp.status_code == 201
    assert float(resp.json()["amount"]) == 1000.0
    assert resp.json()["method"] == "cash"


async def test_record_payment_rejects_nonpositive(client):
    headers = await landlord_headers(client, "pay0@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    resp = await client.post(
        f"/api/v1/leases/{lid}/payments", json={**PAY, "amount": 0}, headers=headers
    )
    assert resp.status_code == 422


async def test_list_payments_newest_first(client):
    headers = await landlord_headers(client, "payl@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    await client.post(
        f"/api/v1/leases/{lid}/payments", json={**PAY, "paid_on": "2026-01-01"}, headers=headers
    )
    await client.post(
        f"/api/v1/leases/{lid}/payments", json={**PAY, "paid_on": "2026-02-01"}, headers=headers
    )
    body = (await client.get(f"/api/v1/leases/{lid}/payments", headers=headers)).json()
    assert [p["paid_on"] for p in body] == ["2026-02-01", "2026-01-01"]


async def test_delete_payment(client):
    headers = await landlord_headers(client, "payd@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    pid = (
        await client.post(f"/api/v1/leases/{lid}/payments", json=PAY, headers=headers)
    ).json()["id"]
    deleted = await client.delete(f"/api/v1/leases/{lid}/payments/{pid}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/leases/{lid}/payments", headers=headers)).json() == []


async def test_payments_cross_org_404(client):
    org_a = await landlord_headers(client, "paya@example.com")
    org_b = await landlord_headers(client, "payb@example.com")
    lid = await _lease_id(client, org_a, await make_property(client, org_a))
    resp = await client.post(f"/api/v1/leases/{lid}/payments", json=PAY, headers=org_b)
    assert resp.status_code == 404


async def test_payments_requires_auth(client):
    headers = await landlord_headers(client, "payauth@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    resp = await client.get(f"/api/v1/leases/{lid}/payments")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_payments_api.py -q`
Expected: FAIL (routes 404 -> the 201/422/204/newest-first assertions fail).

- [ ] **Step 3: Add the schemas**

Create `backend/app/schemas/payment.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import PaymentMethod


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_on: date
    method: PaymentMethod
    note: str | None = None


class PaymentInfo(BaseModel):
    id: uuid.UUID
    amount: Decimal
    paid_on: date
    method: PaymentMethod
    note: str | None


class BalanceInfo(BaseModel):
    outstanding: Decimal
    overdue_amount: Decimal
    credit: Decimal
```

- [ ] **Step 4: Create the payments router**

Create `backend/app/routers/payments.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Membership, Payment
from app.routers.leases import get_owned_lease, manager
from app.schemas.payment import PaymentCreate, PaymentInfo

router = APIRouter(prefix="/api/v1", tags=["payments"])


@router.post("/leases/{lease_id}/payments", status_code=201, response_model=PaymentInfo)
async def record_payment(
    lease_id: uuid.UUID,
    body: PaymentCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PaymentInfo:
    """Record a payment against a lease in the caller's organization."""
    lease = await get_owned_lease(lease_id, membership, session)
    payment = Payment(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        amount=body.amount,
        paid_on=body.paid_on,
        method=body.method,
        note=body.note,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return PaymentInfo(
        id=payment.id,
        amount=payment.amount,
        paid_on=payment.paid_on,
        method=payment.method,
        note=payment.note,
    )


@router.get("/leases/{lease_id}/payments", response_model=list[PaymentInfo])
async def list_payments(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentInfo]:
    """List a lease's payments, newest first."""
    await get_owned_lease(lease_id, membership, session)
    result = await session.execute(
        select(Payment)
        .where(Payment.lease_id == lease_id)
        .order_by(Payment.paid_on.desc(), Payment.created_at.desc())
    )
    return [
        PaymentInfo(
            id=p.id, amount=p.amount, paid_on=p.paid_on, method=p.method, note=p.note
        )
        for p in result.scalars().all()
    ]


@router.delete("/leases/{lease_id}/payments/{payment_id}", status_code=204)
async def delete_payment(
    lease_id: uuid.UUID,
    payment_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a payment on a lease in the caller's organization."""
    await get_owned_lease(lease_id, membership, session)
    payment = (
        await session.execute(
            select(Payment).where(Payment.id == payment_id, Payment.lease_id == lease_id)
        )
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    await session.delete(payment)
    await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 5: Mount the router**

Edit `backend/app/main.py`: add `from app.routers.payments import router as payments_router` with the
other router imports, and `app.include_router(payments_router)` after the other `include_router`
calls.

- [ ] **Step 6: Run to verify they pass + full suite + ruff**

```bash
cd backend && uv run pytest tests/test_payments_api.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: payments tests pass; full suite passes; ruff clean.

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/schemas/payment.py backend/app/routers/payments.py \
        backend/app/main.py backend/tests/test_payments_api.py
git commit -m "Add payment record/list/delete endpoints"
git push
```
Then report and wait for approval.

---

### Task 4: Async status helpers + charges-with-status + balance endpoint

**Files:**
- Modify: `backend/app/services/payments.py`
- Modify: `backend/app/schemas/charge.py`
- Modify: `backend/app/routers/leases.py`
- Modify: `backend/app/routers/payments.py`
- Test: `backend/tests/test_payments_api.py`

**Interfaces:**
- Consumes: `allocate`, `summarize` (Task 2); `Charge`, `Payment`.
- Produces: `lease_statuses(session, lease_id, today) -> list[ChargeStatus]` and `lease_balance(session, lease_id, today) -> Balance` in `app.services.payments`; `ChargeInfo` gains `amount_paid`, `status`, `overdue`; `GET /api/v1/leases/{lease_id}/balance`.

- [ ] **Step 1: Write the failing tests**

Edit the top import block of `backend/tests/test_payments_api.py` to become:

```python
import uuid
from datetime import date

from sqlalchemy import select

from app.models import Charge, Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers
```

Then append:

```python
async def _add_charge(db_session, lease_id, due, amount):
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    db_session.add(
        Charge(
            organization_id=lease.organization_id,
            lease_id=lease.id,
            period_start=due,
            period_end=due,
            due_date=due,
            amount_due=amount,
        )
    )
    await db_session.commit()


async def test_charges_reflect_payment_status(client, db_session):
    headers = await landlord_headers(client, "paycs@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    await _add_charge(db_session, lid, date(2026, 1, 1), 1000)

    await client.post(
        f"/api/v1/leases/{lid}/payments", json={**PAY, "amount": 1000}, headers=headers
    )

    charges = (await client.get(f"/api/v1/leases/{lid}/charges", headers=headers)).json()
    assert charges[0]["status"] == "paid"
    assert float(charges[0]["amount_paid"]) == 1000.0


async def test_balance_endpoint_matches(client, db_session):
    headers = await landlord_headers(client, "paybal@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    await _add_charge(db_session, lid, date(2020, 1, 1), 1000)  # past due

    await client.post(
        f"/api/v1/leases/{lid}/payments", json={**PAY, "amount": 300}, headers=headers
    )

    bal = (await client.get(f"/api/v1/leases/{lid}/balance", headers=headers)).json()
    assert float(bal["outstanding"]) == 700.0
    assert float(bal["overdue_amount"]) == 700.0
    assert float(bal["credit"]) == 0.0
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_payments_api.py -q`
Expected: FAIL — charges response has no `status`/`amount_paid`; `/balance` returns 404.

- [ ] **Step 3: Add async helpers to the service**

Edit `backend/app/services/payments.py`. Add to the top imports:

```python
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Charge, Payment
```

(The `from app.models import Charge` line already exists — replace it with the combined
`from app.models import Charge, Payment`.) Append these functions:

```python
async def _total_paid(session: AsyncSession, lease_id) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.lease_id == lease_id
        )
    )
    return Decimal(result.scalar_one())


async def _charges(session: AsyncSession, lease_id) -> list[Charge]:
    result = await session.execute(select(Charge).where(Charge.lease_id == lease_id))
    return list(result.scalars().all())


async def lease_statuses(session: AsyncSession, lease_id, today: date) -> list[ChargeStatus]:
    return allocate(await _charges(session, lease_id), await _total_paid(session, lease_id), today)


async def lease_balance(session: AsyncSession, lease_id, today: date) -> Balance:
    charges = await _charges(session, lease_id)
    total = await _total_paid(session, lease_id)
    return summarize(allocate(charges, total, today), total, today)
```

- [ ] **Step 4: Extend `ChargeInfo`**

Replace `backend/app/schemas/charge.py` with:

```python
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ChargeInfo(BaseModel):
    id: uuid.UUID
    period_start: date
    period_end: date
    due_date: date
    amount_due: Decimal
    amount_paid: Decimal
    status: Literal["unpaid", "partial", "paid"]
    overdue: bool
```

- [ ] **Step 5: Rewrite the charges endpoint to include status**

In `backend/app/routers/leases.py`, add `from app.services.payments import lease_statuses`
near the other imports. Replace the body of `list_lease_charges` with:

```python
@router.get("/leases/{lease_id}/charges", response_model=list[ChargeInfo])
async def list_lease_charges(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[ChargeInfo]:
    """List rent charges for the given lease with payment status, newest due date first."""
    await get_owned_lease(lease_id, membership, session)
    statuses = await lease_statuses(session, lease_id, datetime.now(UTC).date())
    statuses.reverse()  # allocate sorts ascending by due date; newest first for the response
    return [
        ChargeInfo(
            id=s.charge.id,
            period_start=s.charge.period_start,
            period_end=s.charge.period_end,
            due_date=s.charge.due_date,
            amount_due=s.charge.amount_due,
            amount_paid=s.amount_paid,
            status=s.status,
            overdue=s.overdue,
        )
        for s in statuses
    ]
```

(`leases.py` already imports `UTC`, `datetime` — used by `list_all_leases`. The old `Charge`
column-select import stays; `Charge` may become unused in this file — if ruff flags F401, remove
`Charge` from the `from app.models import (...)` block.)

- [ ] **Step 6: Add the balance endpoint**

In `backend/app/routers/payments.py`, add imports:

```python
from datetime import UTC, datetime

from app.schemas.payment import BalanceInfo, PaymentCreate, PaymentInfo
from app.services.payments import lease_balance
```

(Merge `BalanceInfo` into the existing `from app.schemas.payment import ...` line.) Append:

```python
@router.get("/leases/{lease_id}/balance", response_model=BalanceInfo)
async def get_balance(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> BalanceInfo:
    """Outstanding / overdue / credit summary for a lease in the caller's organization."""
    await get_owned_lease(lease_id, membership, session)
    balance = await lease_balance(session, lease_id, datetime.now(UTC).date())
    return BalanceInfo(
        outstanding=balance.outstanding,
        overdue_amount=balance.overdue_amount,
        credit=balance.credit,
    )
```

- [ ] **Step 7: Run tests + full suite + ruff**

```bash
cd backend && uv run pytest tests/test_payments_api.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 8: Commit and push**

```bash
git add backend/app/services/payments.py backend/app/schemas/charge.py \
        backend/app/routers/leases.py backend/app/routers/payments.py backend/tests/test_payments_api.py
git commit -m "Derive charge status and lease balance from payments"
git push
```
Then report and wait for approval.

---

### Task 5: Tenant portal — balance + charges

**Files:**
- Modify: `backend/app/schemas/tenant.py`
- Modify: `backend/app/routers/portal.py`
- Test: `backend/tests/test_tenant_charges.py`

**Interfaces:**
- Consumes: `lease_balance`, `lease_statuses` (Task 4); `ChargeInfo` (Task 4).
- Produces: `TenantLease` gains `outstanding`, `overdue_amount`; `GET /api/v1/me/leases/{lease_id}/charges`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tenant_charges.py`:

```python
import uuid
from datetime import date

from sqlalchemy import select

from app.models import Charge, Lease
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _add_charge(db_session, lease_id, due, amount):
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    db_session.add(
        Charge(
            organization_id=lease.organization_id,
            lease_id=lease.id,
            period_start=due,
            period_end=due,
            due_date=due,
            amount_due=amount,
        )
    )
    await db_session.commit()


async def test_my_leases_includes_balance(client, db_session):
    headers = await landlord_headers(client, "tcb@example.com")
    lease_id = await make_lease(client, headers, "Bal St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "tcb-t@example.com")
    await _add_charge(db_session, lease_id, date(2020, 1, 1), 1200)  # past due, unpaid

    body = (await client.get("/api/v1/me/leases", headers=tenant)).json()
    assert float(body[0]["outstanding"]) == 1200.0
    assert float(body[0]["overdue_amount"]) == 1200.0


async def test_my_lease_charges_returns_status(client, db_session):
    headers = await landlord_headers(client, "tcs@example.com")
    lease_id = await make_lease(client, headers, "Chg St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "tcs-t@example.com")
    await _add_charge(db_session, lease_id, date(2020, 1, 1), 1000)

    resp = await client.get(f"/api/v1/me/leases/{lease_id}/charges", headers=tenant)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "unpaid"
    assert data[0]["overdue"] is True


async def test_my_lease_charges_other_tenant_404(client, db_session):
    headers = await landlord_headers(client, "tco@example.com")
    lease_a = await make_lease(client, headers, "A2 St")
    lease_b = await make_lease(client, headers, "B2 St")
    ta = await onboard_tenant(client, db_session, headers, lease_a, "tco-a@example.com", "TA")
    await onboard_tenant(client, db_session, headers, lease_b, "tco-b@example.com", "TB")

    resp = await client.get(f"/api/v1/me/leases/{lease_b}/charges", headers=ta)
    assert resp.status_code == 404


async def test_my_lease_charges_landlord_404(client, db_session):
    headers = await landlord_headers(client, "tcl@example.com")
    lease_id = await make_lease(client, headers, "LL St")
    resp = await client.get(f"/api/v1/me/leases/{lease_id}/charges", headers=headers)
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_tenant_charges.py -q`
Expected: FAIL — `outstanding` missing on `/me/leases`; `/me/leases/{id}/charges` 404 for everyone.

- [ ] **Step 3: Extend `TenantLease`**

In `backend/app/schemas/tenant.py`, add to `TenantLease` (after `landlord_phone`):

```python
    outstanding: Decimal
    overdue_amount: Decimal
```

(`Decimal` is already imported in that file.)

- [ ] **Step 4: Compute balance + add tenant charges route**

Rewrite `backend/app/routers/portal.py`:

```python
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models import Lease, LeaseTenant, Membership, Property, Role, User
from app.routers.leases import _lease_state
from app.schemas.charge import ChargeInfo
from app.schemas.tenant import TenantLease
from app.services.payments import lease_balance, lease_statuses

router = APIRouter(prefix="/api/v1/me", tags=["portal"])


@router.get("/leases", response_model=list[TenantLease])
async def my_leases(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TenantLease]:
    """List leases the current user is a tenant of, with landlord contact and balance."""
    today = datetime.now(UTC).date()
    result = await session.execute(
        select(Lease, Property.address)
        .join(LeaseTenant, LeaseTenant.lease_id == Lease.id)
        .join(Property, Property.id == Lease.property_id)
        .where(LeaseTenant.user_id == user.id)
        .order_by(Lease.start_date.desc())
    )

    leases: list[TenantLease] = []
    for lease, address in result.all():
        landlord = (
            await session.execute(
                select(User.name, User.email, User.phone)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.organization_id == lease.organization_id,
                    Membership.role == Role.landlord,
                )
            )
        ).first()
        balance = await lease_balance(session, lease.id, today)
        leases.append(
            TenantLease(
                id=lease.id,
                property_address=address,
                rent_amount=lease.rent_amount,
                rent_frequency=lease.rent_frequency,
                start_date=lease.start_date,
                end_date=lease.end_date,
                bond_amount=lease.bond_amount,
                notice_period_days=lease.notice_period_days,
                state=_lease_state(lease, today),
                landlord_name=landlord.name if landlord else "",
                landlord_email=landlord.email if landlord else "",
                landlord_phone=landlord.phone if landlord else None,
                outstanding=balance.outstanding,
                overdue_amount=balance.overdue_amount,
            )
        )
    return leases


@router.get("/leases/{lease_id}/charges", response_model=list[ChargeInfo])
async def my_lease_charges(
    lease_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ChargeInfo]:
    """List rent charges with status for a lease the current user is a tenant of."""
    owned = (
        await session.execute(
            select(LeaseTenant.id).where(
                LeaseTenant.lease_id == lease_id, LeaseTenant.user_id == user.id
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    statuses = await lease_statuses(session, lease_id, datetime.now(UTC).date())
    statuses.reverse()
    return [
        ChargeInfo(
            id=s.charge.id,
            period_start=s.charge.period_start,
            period_end=s.charge.period_end,
            due_date=s.charge.due_date,
            amount_due=s.charge.amount_due,
            amount_paid=s.amount_paid,
            status=s.status,
            overdue=s.overdue,
        )
        for s in statuses
    ]
```

- [ ] **Step 5: Run tests + full suite + ruff**

```bash
cd backend && uv run pytest tests/test_tenant_charges.py -q
uv run pytest -q
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: all pass; ruff clean.

- [ ] **Step 6: Commit and push**

```bash
git add backend/app/schemas/tenant.py backend/app/routers/portal.py backend/tests/test_tenant_charges.py
git commit -m "Expose balance and charge status to tenants in the portal"
git push
```
Then report and wait for approval.

---

### Task 6: Frontend manager — payments + status + balance

**Files:**
- Create: `frontend/src/lib/payments.ts`
- Modify: `frontend/src/lib/charges.ts`
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx`

**Interfaces:**
- Consumes: payment + balance + charges-with-status endpoints (Tasks 3-4).
- Produces: `@/lib/payments` client; extended `ChargeInfo`.

- [ ] **Step 1: Create the payments lib**

Create `frontend/src/lib/payments.ts`:

```typescript
import { apiFetch } from "@/lib/api";

export type PaymentMethod = "cash" | "bank_transfer" | "other";

export interface PaymentInfo {
  id: string;
  amount: number;
  paid_on: string;
  method: PaymentMethod;
  note: string | null;
}

export interface BalanceInfo {
  outstanding: number;
  overdue_amount: number;
  credit: number;
}

export interface PaymentBody {
  amount: number;
  paid_on: string;
  method: PaymentMethod;
  note: string | null;
}

export function recordPayment(leaseId: string, body: PaymentBody) {
  return apiFetch<PaymentInfo>(`/api/v1/leases/${leaseId}/payments`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listLeasePayments(leaseId: string) {
  return apiFetch<PaymentInfo[]>(`/api/v1/leases/${leaseId}/payments`);
}

export function deleteLeasePayment(leaseId: string, paymentId: string) {
  return apiFetch<void>(`/api/v1/leases/${leaseId}/payments/${paymentId}`, {
    method: "DELETE",
  });
}

export function getLeaseBalance(leaseId: string) {
  return apiFetch<BalanceInfo>(`/api/v1/leases/${leaseId}/balance`);
}
```

- [ ] **Step 2: Extend `ChargeInfo`**

Edit `frontend/src/lib/charges.ts` — extend the interface:

```typescript
export interface ChargeInfo {
  id: string;
  period_start: string;
  period_end: string;
  due_date: string;
  amount_due: number;
  amount_paid: number;
  status: "unpaid" | "partial" | "paid";
  overdue: boolean;
}
```

- [ ] **Step 3: Wire state + effect + handlers into the lease-detail page**

Edit `frontend/src/app/app/leases/[leaseId]/page.tsx`.

Add imports:

```tsx
import {
  recordPayment,
  listLeasePayments,
  deleteLeasePayment,
  getLeaseBalance,
  type PaymentInfo,
  type BalanceInfo,
  type PaymentMethod,
} from "@/lib/payments";
```

Add state (next to `charges`):

```tsx
  const [balance, setBalance] = useState<BalanceInfo | null>(null);
  const [payments, setPayments] = useState<PaymentInfo[]>([]);
  const [payAmount, setPayAmount] = useState("");
  const [payDate, setPayDate] = useState("");
  const [payMethod, setPayMethod] = useState<PaymentMethod>("bank_transfer");
  const [payNote, setPayNote] = useState("");
```

In the effect, alongside `listLeaseCharges`, add:

```tsx
    getLeaseBalance(leaseId)
      .then((b) => {
        if (active) setBalance(b);
      })
      .catch(() => {
        if (active) setBalance(null);
      });
    listLeasePayments(leaseId)
      .then((p) => {
        if (active) setPayments(p);
      })
      .catch(() => {
        if (active) setPayments([]);
      });
```

Add handlers (near the other async handlers, after `onRevoke`):

```tsx
  async function refreshMoney() {
    const [c, b, p] = await Promise.all([
      listLeaseCharges(leaseId),
      getLeaseBalance(leaseId),
      listLeasePayments(leaseId),
    ]);
    setCharges(c);
    setBalance(b);
    setPayments(p);
  }

  async function onRecordPayment(e: React.FormEvent) {
    e.preventDefault();
    await recordPayment(leaseId, {
      amount: Number(payAmount),
      paid_on: payDate,
      method: payMethod,
      note: payNote || null,
    });
    setPayAmount("");
    setPayDate("");
    setPayNote("");
    await refreshMoney();
  }

  async function onDeletePayment(paymentId: string) {
    await deleteLeasePayment(leaseId, paymentId);
    await refreshMoney();
  }
```

- [ ] **Step 4: Update the Rent charges section + add Payments section**

Replace the existing "Rent charges" `<section>` (the `charges.length === 0 ? ... ` block) with a
version that shows a balance summary and per-charge status, and add a Payments section after it:

```tsx
          <section className="mt-8">
            <h2 className="mb-2 font-semibold">Rent charges</h2>
            {balance && (
              <p className="mb-2 text-sm text-gray-600">
                Outstanding <span className="font-medium text-gray-800">${balance.outstanding}</span>
                {" · "}Overdue{" "}
                <span className="font-medium text-red-600">${balance.overdue_amount}</span>
                {balance.credit > 0 && (
                  <>
                    {" · "}Credit{" "}
                    <span className="font-medium text-green-700">${balance.credit}</span>
                  </>
                )}
              </p>
            )}
            {charges.length === 0 ? (
              <p className="text-sm text-gray-500">No charges yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-gray-700">
                {charges.map((c) => (
                  <li key={c.id} className="flex justify-between">
                    <span>
                      {c.period_start} – {c.period_end} · due {c.due_date}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-gray-500">
                        ${c.amount_paid} / ${c.amount_due}
                      </span>
                      <ChargeBadge status={c.status} overdue={c.overdue} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="mt-8">
            <h2 className="mb-2 font-semibold">Payments</h2>
            <form onSubmit={onRecordPayment} className="mb-3 flex flex-wrap gap-2">
              <input
                type="number"
                min="0.01"
                step="0.01"
                required
                placeholder="Amount"
                value={payAmount}
                onChange={(e) => setPayAmount(e.target.value)}
                className="w-28 rounded border px-2 py-1 text-sm"
              />
              <input
                type="date"
                required
                aria-label="Payment date"
                value={payDate}
                onChange={(e) => setPayDate(e.target.value)}
                className="rounded border px-2 py-1 text-sm"
              />
              <select
                aria-label="Payment method"
                value={payMethod}
                onChange={(e) => setPayMethod(e.target.value as PaymentMethod)}
                className="rounded border px-2 py-1 text-sm"
              >
                <option value="bank_transfer">Bank transfer</option>
                <option value="cash">Cash</option>
                <option value="other">Other</option>
              </select>
              <input
                type="text"
                placeholder="Note (optional)"
                value={payNote}
                onChange={(e) => setPayNote(e.target.value)}
                className="flex-1 rounded border px-2 py-1 text-sm"
              />
              <button type="submit" className="rounded bg-blue-600 px-3 py-1 text-sm text-white">
                Record payment
              </button>
            </form>
            {payments.length === 0 ? (
              <p className="text-sm text-gray-500">No payments yet.</p>
            ) : (
              <ul className="space-y-1 text-sm text-gray-700">
                {payments.map((p) => (
                  <li key={p.id} className="flex items-center justify-between">
                    <span>
                      {p.paid_on} · ${p.amount} · {p.method}
                      {p.note ? ` · ${p.note}` : ""}
                    </span>
                    <button
                      onClick={() => onDeletePayment(p.id)}
                      className="rounded border border-red-500 px-2 py-0.5 text-xs text-red-600 transition hover:bg-red-50"
                    >
                      Delete
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
```

Add a small `ChargeBadge` component near the `Field` helper at the top of the file:

```tsx
function ChargeBadge({ status, overdue }: { status: string; overdue: boolean }) {
  const label = overdue ? "Overdue" : status.charAt(0).toUpperCase() + status.slice(1);
  const color = overdue
    ? "bg-red-100 text-red-800"
    : status === "paid"
      ? "bg-green-100 text-green-800"
      : status === "partial"
        ? "bg-yellow-100 text-yellow-800"
        : "bg-gray-100 text-gray-700";
  return <span className={`rounded px-2 py-0.5 text-xs ${color}`}>{label}</span>;
}
```

- [ ] **Step 5: Lint + build**

Run from `frontend/`: `npm run lint` then `npm run build`. Expected: clean; build succeeds.

- [ ] **Step 6: Ruff (backend, keeps CI green) + commit**

```bash
cd backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add frontend/src/lib/payments.ts frontend/src/lib/charges.ts "frontend/src/app/app/leases/[leaseId]/page.tsx"
git commit -m "Add payments UI, charge status badges, and balance to lease detail"
git push
```
Then report and wait for approval.

---

### Task 7: Frontend tenant — portal charges + balance

**Files:**
- Modify: `frontend/src/lib/charges.ts`
- Modify: `frontend/src/app/app/page.tsx`

**Interfaces:**
- Consumes: `/me/leases` (now with `outstanding`/`overdue_amount`) and `/me/leases/{id}/charges` (Task 5).
- Produces: `listMyLeaseCharges(leaseId)` in `@/lib/charges`; tenant balance + charges UI.

- [ ] **Step 1: Add the tenant charges client**

Edit `frontend/src/lib/charges.ts` — add:

```typescript
export function listMyLeaseCharges(leaseId: string) {
  return apiFetch<ChargeInfo[]>(`/api/v1/me/leases/${leaseId}/charges`);
}
```

- [ ] **Step 2: Read the tenant branch**

Read `frontend/src/app/app/page.tsx` to locate the `me.role === "tenant"` branch and how it maps
`listMyLeases()` results (the `TenantLease` type in `@/lib/tenants` now includes `outstanding` and
`overdue_amount`). Identify where the lease card renders.

- [ ] **Step 3: Show balance + charges in the tenant view**

In the tenant branch, for the tenant's lease, add an outstanding/overdue line to the card:

```tsx
<p className="text-sm text-gray-600">
  Outstanding <span className="font-medium text-gray-800">${lease.outstanding}</span>
  {" · "}Overdue <span className="font-medium text-red-600">${lease.overdue_amount}</span>
</p>
```

Add state `const [charges, setCharges] = useState<ChargeInfo[]>([])` (import `ChargeInfo` and
`listMyLeaseCharges` from `@/lib/charges`), fetch `listMyLeaseCharges(lease.id)` in the tenant
effect (guarded), and render a read-only list:

```tsx
<section className="mt-4">
  <h2 className="mb-2 font-semibold">Rent charges</h2>
  {charges.length === 0 ? (
    <p className="text-sm text-gray-500">No charges yet.</p>
  ) : (
    <ul className="space-y-1 text-sm text-gray-700">
      {charges.map((c) => (
        <li key={c.id} className="flex justify-between">
          <span>
            {c.period_start} – {c.period_end} · due {c.due_date}
          </span>
          <span>
            ${c.amount_paid} / ${c.amount_due} ·{" "}
            {c.overdue ? "Overdue" : c.status}
          </span>
        </li>
      ))}
    </ul>
  )}
</section>
```

(Match the existing tenant-branch structure — if it uses a single `me`/`lease` object, hang the
fetch off that lease's id; keep the `let active = true` cleanup pattern used elsewhere.)

- [ ] **Step 4: Lint + build**

Run from `frontend/`: `npm run lint` then `npm run build`. Expected: clean; build succeeds.

- [ ] **Step 5: Ruff (backend) + commit**

```bash
cd backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add frontend/src/lib/charges.ts frontend/src/app/app/page.tsx
git commit -m "Show rent charges and balance to tenants in the portal"
git push
```
Then report and wait for approval.

---

### Task 8: e2e — record a payment

**Files:**
- Create: `frontend/e2e/payments.spec.ts`

**Interfaces:**
- Consumes: the payments UI (Task 6).

- [ ] **Step 1: Restart the local backend (new endpoints)**

```bash
lsof -ti tcp:8000 | xargs kill
cd backend && uv run uvicorn app.main:app --port 8000
```
(Leave running in a second shell for the e2e run.)

- [ ] **Step 2: Write the spec**

Create `frontend/e2e/payments.spec.ts`:

```typescript
import { expect, test } from "@playwright/test";

const landlord = `payments-${Date.now()}@example.com`;

test("landlord records a payment on a lease", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Pay Landlord");
  await page.getByPlaceholder("Organization name").fill("Pay Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.getByRole("link", { name: "Properties" }).click();
  await page.getByRole("link", { name: "New property" }).click();
  await page.getByPlaceholder("Address", { exact: true }).fill("9 Pay Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app");
  await page.getByRole("link", { name: "Leases" }).click();
  await page.getByLabel("Property").selectOption({ label: "9 Pay Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Pat Payer");
  await page.getByPlaceholder("Tenant email").fill("pat@example.com");
  await page.getByLabel("Rent").fill("1200");
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 1);
  const end = new Date(today);
  end.setDate(end.getDate() + 30);
  await page.getByLabel("Start").fill(start.toISOString().slice(0, 10));
  await page.getByLabel("End").fill(end.toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Add lease" }).click();
  await expect(page.getByText("Pat Payer", { exact: false })).toBeVisible();

  // Open the lease detail and record a payment (no charges yet -> becomes a credit).
  await page.getByRole("link", { name: "9 Pay Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByPlaceholder("Amount").fill("500");
  await page.getByLabel("Payment date").fill(today.toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Record payment" }).click();

  // The payment appears in the list and the balance shows a credit.
  await expect(page.getByText("bank_transfer", { exact: false })).toBeVisible();
  await expect(page.getByText("Credit", { exact: false })).toBeVisible();
});
```

- [ ] **Step 3: Run the e2e suite (serial, CI-safe)**

Run from `frontend/`: `npx playwright test`
Expected: all specs pass, including `payments`.

- [ ] **Step 4: Lint + build + ruff**

```bash
cd frontend && npm run lint && npm run build
cd ../backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
```
Expected: clean.

- [ ] **Step 5: Commit, push, watch CI green**

```bash
git add "frontend/e2e/payments.spec.ts"
git commit -m "Add record-payment e2e"
git push
gh run watch --exit-status
```
Expected: all three CI jobs (backend, frontend, e2e) green.

- [ ] **Step 6: Report — Milestone 4.2 complete**

Report: managers record/list/delete payments; charge status (paid/partial/unpaid/overdue) and
lease balance are derived via waterfall allocation and shown to managers and tenants. Wait for
approval to plan **Milestone 4.3** (dashboard stats + charts) — the final M4 sub-project.

---

## Self-Review

**Spec coverage:**
- Payment model + enum + CASCADE + migration -> Task 1. ✓
- allocate/summarize (waterfall, partial, overpay credit, overdue, outstanding rules) -> Task 2. ✓
- Record/list/delete payment endpoints -> Task 3; balance endpoint + charges-with-status -> Task 4. ✓
- Tenant `/me/leases` balance + `/me/leases/{id}/charges` -> Task 5. ✓
- Manager UI (balance, badges, record form, payments list) -> Task 6; tenant UI -> Task 7. ✓
- e2e record-payment -> Task 8. ✓
- Out of scope (online pay, dashboard, late fees, refunds) -> not planned. ✓

**Placeholder scan:** No TBD/TODO; code shown in every code step; only `<rev>` is the Alembic id. ✓

**Type consistency:** `allocate(charges, total_paid, today) -> list[ChargeStatus]`,
`summarize(statuses, total_paid, today) -> Balance`, `lease_statuses`/`lease_balance` async;
`ChargeStatus{charge, amount_paid, status, overdue}`; `ChargeInfo` gains `amount_paid`/`status`/`overdue`
(backend + frontend match); `PaymentCreate`/`PaymentInfo`/`BalanceInfo` fields match the frontend
`PaymentBody`/`PaymentInfo`/`BalanceInfo`; `PaymentMethod` values `cash`/`bank_transfer`/`other`
consistent across model, schema, and TS. ✓
