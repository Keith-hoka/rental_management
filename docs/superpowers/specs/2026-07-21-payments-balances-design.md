# Milestone 4.2: Payments + Balances + Tenant View — Design

**Date:** 2026-07-21
**Status:** Approved (pending spec review)
**Part of:** Milestone 4 (rent charges -> payments+balances -> dashboard stats). Sub-project 2 of 3.

## Goal

Managers record rent payments against a lease; the system auto-allocates each lease's total
payments across its charges (oldest first) to derive per-charge status (unpaid/partial/paid),
overdue flags, and an outstanding balance. Tenants see their own charges, status, and balance
in the portal.

## Architecture

- A `Payment` row belongs to a lease (not a specific charge). Payment amounts are pooled per
  lease.
- A pure `allocate(charges, total_paid, today)` function performs the waterfall: it fills each
  charge (sorted by due date) from the pooled total, oldest first, and returns each charge's
  allocated amount, status, and overdue flag. Nothing is stored per-charge — status is always
  derived, so editing or deleting a payment needs no cascade.
- `summarize(...)` reduces those per-charge results to `{outstanding, overdue_amount, credit}`.
- Manager endpoints record/list/delete payments and read charges-with-status and the balance.
  Tenant portal endpoints expose the same computation for the caller's own leases.

## Tech Stack

- Backend: FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL (existing).
- Frontend: Next.js. No new dependencies.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, run from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- Migration adds a PostgreSQL enum: follow the established enum-migration handling
  (see the alembic-enum-migration-gotcha note) — create the enum type once, drop it in
  downgrade, and verify upgrade -> downgrade -> upgrade round-trip. Current head: `a1f62405d415`.

---

## Product Rules (confirmed)

- **Payment attaches to the lease**, not a charge. A lease's charges are settled by its pooled
  payments, allocated oldest-charge-first (waterfall).
- **Overdue** = a charge whose `due_date < today` and is not fully covered by allocation. No
  grace period (consistent with M4.1).
- **Outstanding balance** counts only charges that are already due (`due_date <= today`):
  `sum(amount_due - amount_paid)` over those charges. Upcoming charges are not "owed" yet.
  Overpayment beyond all charges is a **credit** (the waterfall applies it to future charges
  as they are generated).
- **Payments are deletable** by a manager (re-allocation is automatic since status is derived).
- **Payment fields:** amount, paid_on (date), method (enum `cash`/`bank_transfer`/`other`),
  optional note.
- Tenants never record payments (no online payments — out of scope). The tenant portal is
  read-only over their own charges and balance.

## Data Model

New file `app/models/payment.py`:

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

Register `Payment` and `PaymentMethod` in `app/models/__init__.py`. `ondelete="CASCADE"` removes
payments with the lease. One migration creates the `payments` table and the `paymentmethod`
enum; downgrade drops the table and the enum type; verify the round-trip.

## Allocation + Status (pure logic)

New file `app/services/payments.py`:

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
    credit = total_paid - allocated_total
    return Balance(outstanding=outstanding, overdue_amount=overdue_amount, credit=credit)
```

These are pure and unit-tested with in-memory `Charge` objects. A small helper
`_lease_charge_status(session, lease_id, today)` loads a lease's charges and the sum of its
payments, then calls `allocate` — used by both the manager and tenant endpoints.

## Manager Endpoints (`app/routers/payments.py`, mounted like other routers)

All use `manager = require_roles(landlord, property_manager)` and `get_owned_lease` for 404.

- `POST /api/v1/leases/{lease_id}/payments` — body `PaymentCreate` -> 201 `PaymentInfo`. Creates
  a `Payment` with the lease's `organization_id`.
- `GET /api/v1/leases/{lease_id}/payments` -> `list[PaymentInfo]`, newest first
  (`paid_on` desc, then `created_at` desc).
- `DELETE /api/v1/leases/{lease_id}/payments/{payment_id}` -> 204; 404 if the payment is not on
  that lease.
- `GET /api/v1/leases/{lease_id}/balance` -> `BalanceInfo` (from `summarize`).

The existing `GET /api/v1/leases/{lease_id}/charges` (in `app/routers/leases.py`) is **extended**
to return charges with allocation: `ChargeInfo` gains `amount_paid`, `status`, `overdue`. It
computes them via `allocate` (loading the lease's payments sum).

## Tenant Portal Endpoints (`app/routers/portal.py`)

Use `get_current_user`; the caller must be a `LeaseTenant` of the lease (else 404).

- Extend `TenantLease` with `outstanding: Decimal` and `overdue_amount: Decimal`, computed per
  lease in `my_leases` via `_lease_charge_status` + `summarize`.
- `GET /api/v1/me/leases/{lease_id}/charges` -> `list[ChargeInfo]` (the same extended schema)
  for a lease the caller is a tenant of.

## Schemas

- `app/schemas/payment.py`: `PaymentCreate {amount: Decimal (gt=0), paid_on: date,
  method: PaymentMethod, note: str | None = None}`; `PaymentInfo {id: uuid, amount: Decimal,
  paid_on: date, method: PaymentMethod, note: str | None}`; `BalanceInfo {outstanding: Decimal,
  overdue_amount: Decimal, credit: Decimal}`.
- `app/schemas/charge.py`: extend `ChargeInfo` with `amount_paid: Decimal`,
  `status: Literal["unpaid","partial","paid"]`, `overdue: bool`.
- `app/schemas/tenant.py`: add `outstanding: Decimal`, `overdue_amount: Decimal` to `TenantLease`.

## Frontend

- `frontend/src/lib/payments.ts`: `PaymentMethod` type; `PaymentInfo`, `BalanceInfo`;
  `recordPayment(leaseId, body)`, `listLeasePayments(leaseId)`, `deleteLeasePayment(leaseId, id)`,
  `getLeaseBalance(leaseId)`.
- `frontend/src/lib/charges.ts`: extend `ChargeInfo` with `amount_paid`, `status`, `overdue`;
  add `listMyLeaseCharges(leaseId)` -> `GET /api/v1/me/leases/{id}/charges`.
- **Manager lease-detail page** (`app/leases/[leaseId]/page.tsx`): a balance summary
  (Outstanding / Overdue / Credit); the Rent-charges rows show a status badge
  (Paid/Partial/Unpaid/Overdue) and amount paid; a "Record payment" form (amount, date, method,
  note) that POSTs then refreshes charges + balance + payments; a payments list with a delete
  button per row.
- **Tenant portal** (`app/page.tsx` tenant branch): show Outstanding / Overdue for the lease and
  a charges list with status badges (fetched via `listMyLeaseCharges`).

## Testing

**Backend (pytest, primary):**

- `allocate`: exact payment marks one charge paid; partial payment -> partial; a pool covering
  1.5 charges -> first paid, second partial, third unpaid; overpayment leaves the last charges
  paid and a positive `credit`; overdue flag set only for past-due unpaid/partial charges.
- `summarize`: outstanding counts only `due_date <= today`; overdue_amount only `due_date <
  today`; credit equals unallocated pool.
- Payment endpoints: record (201, amount>0 enforced -> 422 on 0/negative), list newest-first,
  delete (204 + re-derived status), cross-org 404, unauth 401.
- Charges-with-status endpoint reflects payments; balance endpoint matches `summarize`.
- Tenant: `/me/leases` includes outstanding/overdue; `/me/leases/{id}/charges` returns the
  tenant's charges; a tenant cannot read another tenant's lease charges (404); landlord (no
  LeaseTenant) 404 on the tenant charges route.
- CASCADE: deleting a lease removes its payments.

**Frontend e2e (light):** a manager creates a lease, records a payment (no charges yet, so it
becomes a credit), and sees it in the payments list with the balance showing the credit. This
needs no charge generation.

## Out of Scope (M4.2)

- Online payments / tenant self-pay (prohibited financial actions — never build).
- Dashboard stats and charts — **Milestone 4.3**.
- Late fees, partial refunds, reconciliation/export, editing a payment (delete + re-add covers
  corrections), multi-currency display.

## File Structure

- Create: `backend/app/models/payment.py`
- Modify: `backend/app/models/__init__.py` (register `Payment`, `PaymentMethod`)
- Create: `backend/alembic/versions/<rev>_add_payments.py`
- Create: `backend/app/services/payments.py` (allocate/summarize + `_lease_charge_status`)
- Create: `backend/app/schemas/payment.py`
- Modify: `backend/app/schemas/charge.py` (extend `ChargeInfo`)
- Modify: `backend/app/schemas/tenant.py` (extend `TenantLease`)
- Create: `backend/app/routers/payments.py`
- Modify: `backend/app/main.py` (mount payments router)
- Modify: `backend/app/routers/leases.py` (charges endpoint returns status)
- Modify: `backend/app/routers/portal.py` (balance on `/me/leases`; `/me/leases/{id}/charges`)
- Create: `backend/tests/test_payment_allocation.py`, `test_payments_api.py`,
  `test_tenant_charges.py`
- Create: `frontend/src/lib/payments.ts`; Modify: `frontend/src/lib/charges.ts`
- Modify: `frontend/src/app/app/leases/[leaseId]/page.tsx`,
  `frontend/src/app/app/page.tsx`
- Modify: `frontend/e2e/` (record-payment spec)
