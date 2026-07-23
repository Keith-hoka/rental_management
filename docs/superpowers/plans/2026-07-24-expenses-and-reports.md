# Expenses and Monthly Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Managers record property expenses, and a reports page shows a 12-month accrual P&L, expenses by category, and a per-property P&L.

**Architecture:** A new `Expense` table with CRUD (Part A). A read-only `GET /api/v1/reports/monthly` aggregates charges (accrual income) and expenses into a monthly series, a category breakdown, and a per-property breakdown (Part B). Two new frontend pages.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, PostgreSQL, python-dateutil, Next.js 16, Recharts, Playwright. No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- The migration adds **one PG enum** (`expensecategory`). Hand-write it (no `--autogenerate`); `downgrade` drops the table then `sa.Enum(name="expensecategory").drop(op.get_bind())`. Current head: `551fe4865e44`. Verify upgrade -> downgrade -> upgrade.
- Management side only: endpoints require `require_roles(landlord, property_manager)`; pages live in the manager `AppShell`.
- Recharts: `isAnimationActive={false}`; colors from CSS tokens, matching the dashboard charts in `frontend/src/app/app/page.tsx`.
- Report amounts are floats, rounded to 2 dp. Expense-list amounts stay Decimal (serialized as strings) like charges/payments.
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- Backend commands from `backend/`, frontend from `frontend/`; always `cd` explicitly.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/expense.py` | `ExpenseCategory`, `Expense` |
| `backend/app/models/__init__.py` | register them |
| `backend/alembic/versions/<rev>_add_expenses.py` | table + enum, reversible |
| `backend/app/schemas/expense.py` | `ExpenseCreate`, `ExpenseInfo` |
| `backend/app/routers/expenses.py` | CRUD |
| `backend/app/schemas/report.py` | `MonthPoint`, `CategoryTotal`, `PropertyPnl`, `MonthlyReport` |
| `backend/app/services/reports.py` | `monthly_report(session, org, months)` |
| `backend/app/routers/reports.py` | the endpoint |
| `backend/app/main.py` | mount both routers |
| `backend/tests/test_expenses.py`, `backend/tests/test_reports.py` | the feature |
| `frontend/src/lib/expenses.ts`, `frontend/src/lib/reports.ts` | clients |
| `frontend/src/app/app/expenses/page.tsx`, `frontend/src/app/app/reports/page.tsx` | pages |
| `frontend/src/components/app-shell.tsx` | nav entries |
| `frontend/e2e/expenses-reports.spec.ts` | end-to-end |

---

### Task E-T1: Expense model, enum, migration

**Files:** Create `backend/app/models/expense.py`; Modify `backend/app/models/__init__.py`; Create migration; Test `backend/tests/test_expenses.py`.

**Interfaces:** Produces `ExpenseCategory` (maintenance/insurance/tax/utilities/management/other); `Expense(id, organization_id, amount, spent_on, category, note, property_id, created_by, created_at)`.

- [ ] **Step 1: Failing test** — `backend/tests/test_expenses.py`:

```python
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models import Expense, ExpenseCategory
from tests.test_calendar import _org_and_user
from tests.test_properties_crud import landlord_headers


async def test_expense_round_trip(client, db_session):
    email = "expmodel@example.com"
    await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    expense = Expense(
        organization_id=org_id,
        amount=Decimal("125.50"),
        spent_on=date(2026, 7, 10),
        category=ExpenseCategory.insurance,
        created_by=user_id,
    )
    db_session.add(expense)
    await db_session.commit()
    stored = (
        await db_session.execute(select(Expense).where(Expense.id == expense.id))
    ).scalar_one()
    assert stored.category == ExpenseCategory.insurance
    assert stored.amount == Decimal("125.50")
    assert stored.property_id is None
```

- [ ] **Step 2: Run -> fail** (`ImportError: Expense`). `cd backend && uv run pytest tests/test_expenses.py -q`.

- [ ] **Step 3: Model** — `backend/app/models/expense.py`:

```python
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ExpenseCategory(str, enum.Enum):
    maintenance = "maintenance"
    insurance = "insurance"
    tax = "tax"
    utilities = "utilities"
    management = "management"
    other = "other"


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    spent_on: Mapped[date] = mapped_column(Date)
    category: Mapped[ExpenseCategory] = mapped_column(Enum(ExpenseCategory))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Register `Expense, ExpenseCategory` in `backend/app/models/__init__.py` (import + `__all__`).

- [ ] **Step 4: Migration** — `cd backend && uv run alembic revision -m "add expenses"` (no autogenerate). Fill:

```python
import sqlalchemy as sa
from alembic import op

# revision / down_revision set by the revision command; down_revision == "551fe4865e44"


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "maintenance", "insurance", "tax", "utilities", "management", "other",
                name="expensecategory",
            ),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("property_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_expenses_organization_id"), "expenses", ["organization_id"])
    op.create_index(op.f("ix_expenses_property_id"), "expenses", ["property_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_expenses_property_id"), table_name="expenses")
    op.drop_index(op.f("ix_expenses_organization_id"), table_name="expenses")
    op.drop_table("expenses")
    sa.Enum(name="expensecategory").drop(op.get_bind())
```

- [ ] **Step 5: Round-trip + test** — `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run pytest tests/test_expenses.py -q` -> clean + pass.

- [ ] **Step 6: Full run, ruff, commit, push** (`Add the Expense model and migration`). Report and wait.

---

### Task E-T2: Expense schemas + CRUD

**Files:** Create `backend/app/schemas/expense.py`, `backend/app/routers/expenses.py`; Modify `backend/app/main.py`; Test `backend/tests/test_expenses.py`.

**Interfaces:** Consumes `Expense`, `manager` dep, `Property`. Produces `POST/GET/DELETE /api/v1/expenses`, `ExpenseInfo`.

- [ ] **Step 1: Failing tests** — append to `backend/tests/test_expenses.py`:

```python
from tests.test_leases import make_property


def _body(amount="80.00", spent_on="2026-07-05", category="utilities", **kw):
    return {"amount": amount, "spent_on": spent_on, "category": category, **kw}


async def test_create_list_delete_expense(client):
    headers = await landlord_headers(client, "expcrud@example.com")
    created = await client.post("/api/v1/expenses", json=_body(note="Water"), headers=headers)
    assert created.status_code == 201
    expense_id = created.json()["id"]
    listed = (await client.get("/api/v1/expenses", headers=headers)).json()
    assert [e["id"] for e in listed] == [expense_id]
    assert listed[0]["category"] == "utilities"
    assert (
        await client.delete(f"/api/v1/expenses/{expense_id}", headers=headers)
    ).status_code == 204


async def test_expense_rejects_foreign_property(client):
    owner = await landlord_headers(client, "expprop@example.com")
    stranger = await landlord_headers(client, "exppropx@example.com")
    foreign = await make_property(client, stranger, "9 Foreign St")
    r = await client.post("/api/v1/expenses", json=_body(property_id=foreign), headers=owner)
    assert r.status_code == 400


async def test_cross_org_expense_delete_is_404(client):
    owner = await landlord_headers(client, "expowner@example.com")
    expense_id = (await client.post("/api/v1/expenses", json=_body(), headers=owner)).json()["id"]
    stranger = await landlord_headers(client, "expthief@example.com")
    assert (
        await client.delete(f"/api/v1/expenses/{expense_id}", headers=stranger)
    ).status_code == 404
```

- [ ] **Step 2: Run -> fail** (404, router missing).

- [ ] **Step 3: Schemas** — `backend/app/schemas/expense.py`:

```python
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import ExpenseCategory


class ExpenseCreate(BaseModel):
    amount: Decimal
    spent_on: date
    category: ExpenseCategory
    note: str | None = None
    property_id: uuid.UUID | None = None


class ExpenseInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: Decimal
    spent_on: date
    category: ExpenseCategory
    note: str | None
    property_id: uuid.UUID | None
    created_at: datetime
```

- [ ] **Step 4: Router** — `backend/app/routers/expenses.py` (mirror `app/routers/calendar.py`'s `_check_property` / `_owned` pattern): `POST` (validate property in org -> else 400), `GET` (org, order by `spent_on` desc), `DELETE` (org-scoped 404). Mount in `main.py`.

- [ ] **Step 5: Run tests -> pass.**

- [ ] **Step 6: Full run, ruff, commit, push** (`Add expense create, list and delete`). Report and wait.

---

### Task E-T3: Frontend expenses page

**Files:** Create `frontend/src/lib/expenses.ts`, `frontend/src/app/app/expenses/page.tsx`; Modify `frontend/src/components/app-shell.tsx`.

- [ ] **Step 1: Client** — `expenses.ts`: `ExpenseCategory` union, `ExpenseInfo`, `ExpenseInput`; `listExpenses()`, `createExpense(body)`, `deleteExpense(id)` (via `apiFetch`; POST/DELETE like `@/lib/leases`).

- [ ] **Step 2: Page** — `/app/expenses` (mirror the lease-detail Payments card idiom): a form (amount `Input` number, date `Input`, category `Select` of the six, note `Input`, property `Select` from `listProperties`) and a list of `Card`/rows showing `spent_on`, `category`, `$amount`, note, with a `Delete` (`variant="danger"`) opening `ConfirmDialog` (`label="Delete expense"`). Wrap in `AppShell` + `useShell`.

- [ ] **Step 3: Nav** — add `{ href: "/app/expenses", label: "Expenses" }` to `MANAGE` in `app-shell.tsx` (near Payments).

- [ ] **Step 4: Lint + build** -> clean; `/app/expenses` in the route list.

- [ ] **Step 5: Commit and push** (`Add the expenses page`). Report and wait.

---

### Task R-T1: Monthly report aggregation

**Files:** Create `backend/app/schemas/report.py`, `backend/app/services/reports.py`, `backend/app/routers/reports.py`; Modify `backend/app/main.py`; Test `backend/tests/test_reports.py`.

**Interfaces:** Produces `GET /api/v1/reports/monthly?months=12` -> `MonthlyReport{months, by_category, by_property}`.

- [ ] **Step 1: Failing test** — `backend/tests/test_reports.py`:

```python
import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.models import Charge, Expense, ExpenseCategory, Lease
from tests.test_calendar import _org_and_user
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def test_monthly_report_aggregates(client, db_session):
    email = "rep@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    property_id = await make_property(client, headers, "1 Report St")
    today = date.today()
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)), end_date=str(today + timedelta(days=30))
            ),
            headers=headers,
        )
    ).json()["id"]
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    db_session.add(
        Charge(
            organization_id=org_id, lease_id=lease.id, period_start=today,
            period_end=today + timedelta(days=29), due_date=today, amount_due=Decimal("1000"),
        )
    )
    db_session.add(
        Expense(organization_id=org_id, amount=Decimal("200"), spent_on=today,
                category=ExpenseCategory.maintenance, property_id=uuid.UUID(property_id),
                created_by=user_id)
    )
    db_session.add(
        Expense(organization_id=org_id, amount=Decimal("50"), spent_on=today,
                category=ExpenseCategory.insurance, created_by=user_id)  # unassigned
    )
    await db_session.commit()

    body = (await client.get("/api/v1/reports/monthly?months=12", headers=headers)).json()

    assert len(body["months"]) == 12
    this_month = f"{today.year:04d}-{today.month:02d}"
    point = next(m for m in body["months"] if m["month"] == this_month)
    assert point["income"] == 1000.0
    assert point["expenses"] == 250.0
    assert point["net"] == 750.0
    cats = {c["category"]: c["total"] for c in body["by_category"]}
    assert cats["maintenance"] == 200.0 and cats["insurance"] == 50.0
    props = {p["address"]: p for p in body["by_property"]}
    assert props["1 Report St"]["income"] == 1000.0
    assert props["1 Report St"]["expenses"] == 200.0
    assert props["(Unassigned)"]["expenses"] == 50.0


async def test_monthly_report_is_org_scoped(client, db_session):
    stranger = await landlord_headers(client, "repother@example.com")
    body = (await client.get("/api/v1/reports/monthly?months=3", headers=stranger)).json()
    assert body["by_category"] == [] and body["by_property"] == []
    assert all(m["income"] == 0 and m["expenses"] == 0 for m in body["months"])
```

(`from sqlalchemy import select` at the top too.)

- [ ] **Step 2: Run -> fail** (404).

- [ ] **Step 3: Schemas** — `backend/app/schemas/report.py`:

```python
import uuid

from pydantic import BaseModel


class MonthPoint(BaseModel):
    month: str
    income: float
    expenses: float
    net: float


class CategoryTotal(BaseModel):
    category: str
    total: float


class PropertyPnl(BaseModel):
    property_id: uuid.UUID | None
    address: str
    income: float
    expenses: float
    net: float


class MonthlyReport(BaseModel):
    months: list[MonthPoint]
    by_category: list[CategoryTotal]
    by_property: list[PropertyPnl]
```

- [ ] **Step 4: Aggregation** — `backend/app/services/reports.py`:

```python
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Charge, Expense, Lease, Property
from app.schemas.report import CategoryTotal, MonthlyReport, MonthPoint, PropertyPnl


def _key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


async def monthly_report(session: AsyncSession, org, months: int) -> MonthlyReport:
    first_this = date.today().replace(day=1)
    start = first_this - relativedelta(months=months - 1)
    end = first_this + relativedelta(months=1) - relativedelta(days=1)
    keys = [_key(start + relativedelta(months=i)) for i in range(months)]

    income_m: dict[str, float] = defaultdict(float)
    for due, amt in (
        await session.execute(
            select(Charge.due_date, Charge.amount_due).where(
                Charge.organization_id == org, Charge.due_date >= start, Charge.due_date <= end
            )
        )
    ).all():
        income_m[_key(due)] += float(amt)

    expense_m: dict[str, float] = defaultdict(float)
    cat: dict[str, float] = defaultdict(float)
    for spent, amt, category in (
        await session.execute(
            select(Expense.spent_on, Expense.amount, Expense.category).where(
                Expense.organization_id == org, Expense.spent_on >= start, Expense.spent_on <= end
            )
        )
    ).all():
        expense_m[_key(spent)] += float(amt)
        cat[category.value] += float(amt)

    months_out = [
        MonthPoint(
            month=k,
            income=round(income_m[k], 2),
            expenses=round(expense_m[k], 2),
            net=round(income_m[k] - expense_m[k], 2),
        )
        for k in keys
    ]
    by_category = sorted(
        (CategoryTotal(category=c, total=round(t, 2)) for c, t in cat.items()),
        key=lambda x: x.total,
        reverse=True,
    )

    # Per property: income via Charge -> Lease.property_id, expenses via Expense.property_id.
    prop_income: dict[uuid.UUID, float] = defaultdict(float)
    for pid, total in (
        await session.execute(
            select(Lease.property_id, func.sum(Charge.amount_due))
            .join(Charge, Charge.lease_id == Lease.id)
            .where(Charge.organization_id == org, Charge.due_date >= start, Charge.due_date <= end)
            .group_by(Lease.property_id)
        )
    ).all():
        prop_income[pid] += float(total)

    prop_expense: dict[uuid.UUID | None, float] = defaultdict(float)
    for pid, total in (
        await session.execute(
            select(Expense.property_id, func.sum(Expense.amount))
            .where(Expense.organization_id == org, Expense.spent_on >= start, Expense.spent_on <= end)
            .group_by(Expense.property_id)
        )
    ).all():
        prop_expense[pid] += float(total)

    addresses = dict(
        (
            await session.execute(
                select(Property.id, Property.address).where(Property.organization_id == org)
            )
        ).all()
    )

    by_property = []
    for pid in set(prop_income) | (set(prop_expense) - {None}):
        inc = round(prop_income.get(pid, 0.0), 2)
        exp = round(prop_expense.get(pid, 0.0), 2)
        by_property.append(
            PropertyPnl(
                property_id=pid, address=addresses.get(pid, ""),
                income=inc, expenses=exp, net=round(inc - exp, 2),
            )
        )
    if None in prop_expense:
        exp = round(prop_expense[None], 2)
        by_property.append(
            PropertyPnl(property_id=None, address="(Unassigned)", income=0.0, expenses=exp, net=round(-exp, 2))
        )
    by_property.sort(key=lambda p: p.net)

    return MonthlyReport(months=months_out, by_category=by_category, by_property=by_property)
```

(add `import uuid` at the top.)

- [ ] **Step 5: Endpoint** — `backend/app/routers/reports.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Membership
from app.routers.leases import manager
from app.schemas.report import MonthlyReport
from app.services.reports import monthly_report

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get("/reports/monthly", response_model=MonthlyReport)
async def monthly(
    months: int = 12,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> MonthlyReport:
    """A months-long accrual P&L series, expenses by category, and per-property P&L."""
    months = max(1, min(months, 24))
    return await monthly_report(session, membership.organization_id, months)
```

Mount `reports_router` in `main.py`.

- [ ] **Step 6: Run tests -> pass.** Then full run, ruff, commit, push (`Add the monthly report aggregation`). Report and wait.

---

### Task R-T2: Frontend reports page

**Files:** Create `frontend/src/lib/reports.ts`, `frontend/src/app/app/reports/page.tsx`; Modify `frontend/src/components/app-shell.tsx`.

- [ ] **Step 1: Client** — `reports.ts`: `MonthPoint`, `CategoryTotal`, `PropertyPnl`, `MonthlyReport` types; `getMonthlyReport(months = 12)` via `apiFetch`.

- [ ] **Step 2: Page** — `/app/reports` (mirror the dashboard charts in `frontend/src/app/app/page.tsx`): fetch on mount; render
  - a monthly P&L `Card` with a table (Month / Income / Expenses / Net);
  - a `Card` "Income vs expenses" with a Recharts `BarChart` over `months` (two bars: income, expenses; `isAnimationActive={false}`; token colors);
  - a `Card` "Expenses by category" table;
  - a `Card` "By property" table (Address / Income / Expenses / Net).
  Wrap in `AppShell` + `useShell`; empty-safe when everything is zero.

- [ ] **Step 3: Nav** — add `{ href: "/app/reports", label: "Reports" }` to `MANAGE`.

- [ ] **Step 4: Lint + build** -> clean; `/app/reports` in the route list.

- [ ] **Step 5: Commit and push** (`Add the reports page`). Report and wait.

---

### Task R-T3: End-to-end + CI

**Files:** Create `frontend/e2e/expenses-reports.spec.ts`.

- [ ] **Step 1: Spec** — manager signs up, creates a property; goes to `/app/expenses`, adds an expense (amount, today, a category, optional the property); asserts it lists. Goes to `/app/reports`; asserts the current month's Expenses value and the category row reflect it. Finalise selectors against the built pages when the test first runs (do not leave guessed).

- [ ] **Step 2: Run the new spec** — `cd frontend && npx playwright test expenses-reports` -> 1 passed.
- [ ] **Step 3: Whole e2e suite** — `npx playwright test --workers=1` -> all pass.
- [ ] **Step 4: Full backend run + ruff** (from `backend/`).
- [ ] **Step 5: Commit and push** (`Add expenses and reports e2e`).
- [ ] **Step 6: Confirm CI green** — `gh run list --limit 3`; read logs on failure. Report and wait.
