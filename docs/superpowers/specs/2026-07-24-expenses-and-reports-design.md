# Expenses and Monthly Reports Design

**Date:** 2026-07-24
**Milestone:** Phase 2 — Expenses + monthly reports (the last sub-project). Two
parts: **A. Expenses** (a new model + CRUD), then **B. Monthly reports** built on
top of it (the recorded dependency).

## Goal

Managers record property expenses (amount, date, category, optional property),
and a reports page shows a 12-month profit-and-loss series (accrual income minus
expenses), expenses broken down by category, and a per-property P&L.

## Decisions (from brainstorming)

- **Expense fields:** amount, date, category (fixed enum), optional note,
  optional property link.
- **Categories (enum `expensecategory`):** `maintenance`, `insurance`, `tax`,
  `utilities`, `management`, `other`.
- **Expense actions:** create / list / delete only (no edit), like payments.
- **Report income basis:** accrual — the sum of `Charge.amount_due` whose
  `due_date` falls in the month (what was billed, regardless of receipt).
- **Report window:** the last 12 months (default, `?months=`).
- **Report breakdowns:** overall monthly series, expenses by category, and
  per-property P&L (period totals, not property x month).
- **Audience:** management side only (endpoints require a manager, org-scoped).

## Part A — Expenses

### Model

New table `expenses` (one PG enum `expensecategory`).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `organization_id` | uuid FK organizations.id | indexed |
| `amount` | Numeric(10, 2) | |
| `spent_on` | Date | the expense date |
| `category` | Enum(ExpenseCategory) | |
| `note` | String(500) | nullable |
| `property_id` | uuid FK properties.id | nullable, `ondelete="SET NULL"` |
| `created_by` | uuid FK users.id | |
| `created_at` | DateTime(tz) | server default now |

Migration `down_revision = "551fe4865e44"` (current head), hand-written (the
enum autogenerate gotcha): `downgrade` drops the table, then
`sa.Enum(name="expensecategory").drop(op.get_bind())`. Verify upgrade ->
downgrade -> upgrade.

### Endpoints

Manager only (`require_roles(landlord, property_manager)`), org-scoped, cross-org
404.

- `POST /api/v1/expenses` — body `{amount, spent_on, category, note?, property_id?}` -> 201 `ExpenseInfo`. A `property_id` outside the org -> 400.
- `GET /api/v1/expenses` — the org's expenses, newest `spent_on` first.
- `DELETE /api/v1/expenses/{id}` — 204; cross-org 404.

`ExpenseInfo`: `{id, amount, spent_on, category, note, property_id, created_at}`
(amount as the usual Decimal-string, like charges/payments).

### Frontend `/app/expenses`

Add-expense form (amount / date / category select / note / optional property
select) and a list, each row deletable through `ConfirmDialog`. Nav entry
"Expenses".

## Part B — Monthly reports

### Endpoint

`GET /api/v1/reports/monthly?months=12` (manager, org-scoped) -> `MonthlyReport`.

```
MonthPoint:     { month: str "YYYY-MM", income: float, expenses: float, net: float }
CategoryTotal:  { category: str, total: float }
PropertyPnl:    { property_id: uuid | null, address: str, income: float, expenses: float, net: float }

MonthlyReport:
  months:      list[MonthPoint]       # oldest -> newest, exactly `months` entries (zeros where empty)
  by_category: list[CategoryTotal]    # expenses in the window, per category, desc by total
  by_property: list[PropertyPnl]      # per-property P&L over the window
```

**Window:** the `months` calendar months ending with the current month.
`period_start` = first day of the earliest month; `period_end` = last day of the
current month. All amounts are floats (display aggregates; the chart wants
numbers).

**months[]** — bucket by `YYYY-MM`:
- `income` = sum `Charge.amount_due` where org and `due_date` in that month.
- `expenses` = sum `Expense.amount` where org and `spent_on` in that month.
- `net` = income - expenses. Every one of the `months` keys is present (0 if empty).

**by_category** — sum `Expense.amount` grouped by `category`, org, `spent_on` in
[period_start, period_end].

**by_property** — over [period_start, period_end], org:
- property income = sum `Charge.amount_due` via `Charge -> Lease -> Property`,
  grouped by property (`id`, `address`).
- property expenses = sum `Expense.amount` where `property_id` = that property.
- Merge on property id; `net` = income - expenses.
- Expenses with `property_id = NULL` become one row `{property_id: null, address:
  "(Unassigned)", income: 0, expenses: <sum>, net: -<sum>}`, so property expense
  totals reconcile with the overall.

### Frontend `/app/reports`

- A monthly P&L table (Month / Income / Expenses / Net).
- A grouped bar chart of income vs expenses per month (Recharts,
  `isAnimationActive={false}`, colors from CSS tokens — matches the dashboard
  charts).
- An expenses-by-category table.
- A per-property P&L table.
Nav entry "Reports".

## Testing

**Backend:**
- `Expense` model round-trip; create (+ foreign-property 400), list, delete,
  cross-org 404.
- Report: seed a charge (due this month) and expenses (this month, one linked to
  a property, one unassigned); assert the current month's `income`/`expenses`/
  `net`, that `by_category` sums per category, and `by_property` has the property
  row and an `(Unassigned)` row. Org-scoped: another org's data never appears.

**e2e:**
- Manager signs up, creates a property, opens `/app/expenses`, adds an expense,
  sees it listed. Opens `/app/reports`, sees the expense reflected in the current
  month's Expenses and in the category table.

## Out of scope (this milestone)

- Tenant-side. Expense editing. Property x month matrix (per-property is period
  totals). Report CSV export. Cash-basis (payments) income.

## Task breakdown (for the plan)

- **E-T1** — `ExpenseCategory` enum + `Expense` model + migration (enum,
  reversible) + round-trip test.
- **E-T2** — Expense schemas + create/list/delete endpoints (validation, org
  scope); tests.
- **E-T3** — Frontend `expenses.ts` + `/app/expenses` page + nav; lint/build.
- **R-T1** — Report schemas + monthly aggregation endpoint (`months[]`,
  `by_category`, `by_property` incl. unassigned); tests.
- **R-T2** — Frontend `reports.ts` + `/app/reports` page (table + chart +
  category + property tables) + nav; lint/build.
- **R-T3** — e2e (add expense -> reports reflects it) + full suite + CI green.

Each task ends with: full test run -> ruff sequence (from `backend/`) -> commit
-> push to `https://github.com/Keith-hoka/rental_management` -> report -> wait.
