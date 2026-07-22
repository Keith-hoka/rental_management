# Milestone 8.2: Rent Overdue and Upcoming Views — Design

**Date:** 2026-07-23
**Status:** Approved (pending spec review)

**Part of:** Milestone 8, sub-project 2 of 3. M8.1 (contractor assignment) is complete; M8.3 adds
the dashboard occupancy-rate and maintenance-status charts.

## Goal

A manager opens Payments and sees who owes money now and what falls due next, grouped by lease and
expandable to the individual charges. The same pass replaces the per-lease query loop that
`dashboard_stats` runs today.

## Architecture

- One service function, `org_charge_statuses`, loads an organization's charges and payment totals
  in a fixed number of queries and reuses the existing pure `allocate` to produce per-lease
  `ChargeStatus` lists. Grouping happens in Python because `allocate` and `summarize` already take
  plain lists and are already tested.
- One endpoint, `GET /api/v1/rent/summary`, returns both buckets. They come from the same scan, so
  two endpoints would mean scanning twice and two round trips for a page that shows both.
- `dashboard_stats` switches to the same function. This is not an unrelated refactor: it currently
  calls `lease_balance` once per lease, and `lease_balance` itself issues two queries, so the
  dashboard costs **2N queries** for N leases. Building the new view the same way would plant a
  second copy of the problem.
- Rejected: pushing the waterfall allocation into SQL window functions. It would be faster still,
  but it duplicates `allocate`'s logic in a second language, and a divergence between the two
  would be very hard to find.

## Tech Stack

- Backend: FastAPI, async SQLAlchemy 2.0, PostgreSQL (existing). **No migration** — this milestone
  adds no column and no table.
- Frontend: Next.js (existing). No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- Accessible names are pinned by 27 Playwright specs. Names introduced here: `Overdue rent`,
  `Upcoming rent`, and a per-row `Show charges for {address}`. Playwright matches names by
  **substring**, so every new name must be checked against what else is on the same page.

---

## Product Rules (confirmed)

- **"Upcoming" means every generated charge with `due_date >= today`.** In practice that is the
  next seven days, because `charge_lead_days` is 7 and charges do not exist beyond it. The card
  says so rather than implying a longer horizon. Raising the setting or forecasting from lease
  terms were both considered and rejected for now; widening the window later is a one-line
  settings change.
- **One row per lease, expandable.** The row answers "who do I call and how much do they owe";
  expanding answers "which periods". A tenant three periods behind is one row, not three.
- **Overdue** is `due_date < today` with an unpaid remainder. A charge paid in full never appears.
  A partly paid charge contributes only its remainder.
- **The same "unpaid remainder" rule governs both buckets.** `allocate` pays charges off oldest
  first, so a tenant who pays ahead leaves a future charge with nothing owing; that charge is
  excluded from `upcoming` exactly as a settled charge is excluded from `overdue`. Both cards
  answer "what is still owed", not "what was billed".
- **Manager-only.** Tenants already see their own charges in the portal; this view is org-wide.
- Several rows may be expanded at once. Chasing arrears means comparing tenants, not reading one.

---

## Service (`backend/app/services/payments.py`)

```python
async def org_charge_statuses(
    session: AsyncSession, organization_id, today: date
) -> dict[uuid.UUID, list[ChargeStatus]]:
    """Allocate payments across charges for every lease in the organization.

    A fixed number of queries regardless of lease count: the per-lease helpers
    would issue two each.
    """
```

Three queries, none of them per-lease:

1. every `Charge` for the organization,
2. `select(Payment.lease_id, func.sum(Payment.amount)).group_by(Payment.lease_id)` for the
   organization,
3. `Lease` joined to `Property.address`, for the display fields.

Then group the charges by `lease_id` in Python and call the existing `allocate(charges, paid,
today)` per lease. `allocate` is unchanged.

`lease_statuses` and `lease_balance` stay as they are: the per-lease pages still want one lease's
worth of data, and making them go through the org-wide pass would be slower, not faster.

---

## Schemas (`backend/app/schemas/rent.py`)

```python
class LeaseChargeGroup(BaseModel):
    lease_id: uuid.UUID
    property_address: str
    tenant_name: str
    total: Decimal          # unpaid remainder for this lease in this bucket
    oldest_due: date        # earliest due date in the group; drives "N days late"
    charges: list[ChargeInfo]


class RentSummary(BaseModel):
    overdue: list[LeaseChargeGroup]
    upcoming: list[LeaseChargeGroup]
```

`ChargeInfo` already exists in `app/schemas/charge.py` and is reused unchanged.

`overdue` is ordered by `oldest_due` ascending, so the longest-overdue lease is first. `upcoming`
is ordered by `oldest_due` ascending, so the next thing due is first.

## Endpoint (`backend/app/routers/rent.py`, mounted in `main.py`)

`GET /api/v1/rent/summary` -> `RentSummary`, dependency `require_roles(landlord,
property_manager)`, scoped to the caller's organization.

A lease appears in a bucket only if it has at least one qualifying charge, so a fully paid-up
organization returns two empty lists rather than a row per lease.

## Dashboard change (`backend/app/services/stats.py`)

Replace the `for lease in leases: await lease_balance(...)` loop with one `org_charge_statuses`
call and `summarize` per lease. **The numbers must not change** — `tests/test_stats.py` is the
guard, and a new test asserts that `dashboard_stats.overdue` equals the total of
`RentSummary.overdue`.

---

## Frontend

**`/app/payments`** gains two cards above the existing `Payment history`:

- **`Overdue rent`** — rows of `{address} · {tenant}`, the outstanding total, and how many days
  past the oldest due date. Empty state: "Nothing overdue."
- **`Upcoming rent`** — the same shape, with the due date instead of a days-late count. Empty
  state: "Nothing due in the next 7 days."

Clicking a row toggles the charge detail beneath it, rendered from `charges` with the same status
badges the lease detail page uses. Expanded rows are held in a `Set` of lease ids so several can
be open at once.

The toggle is a button with `aria-expanded` and `aria-label={\`Show charges for ${address}\`}`.
The label is per-row on purpose: identical names on sibling rows break Playwright's strict mode,
which has already cost time three times in this project.

`frontend/src/lib/rent.ts` provides `getRentSummary()`.

---

## Testing

Backend (`backend/tests/test_rent_summary.py` unless noted):

1. Bucketing: a charge due yesterday and unpaid lands in `overdue`; one due tomorrow lands in
   `upcoming`; one paid in full appears in neither.
2. A lease with two unpaid overdue charges is **one** row whose `total` is their sum.
3. A partly paid charge contributes only its remainder to `total`.
4. Another organization's arrears never appear.
5. **Query count does not grow with lease count**: count statements with a
   `before_cursor_execute` event listener and assert the count for five leases equals the count
   for one. Without this, the N+1 can be reintroduced and no test would go red — a performance
   regression is invisible to ordinary assertions.
6. `dashboard_stats().overdue` equals the sum of `RentSummary.overdue[*].total`. After this
   change two code paths compute "overdue" from the same data; this pins them together.

e2e (`frontend/e2e/rent-summary.spec.ts`): a landlord opens Payments and sees both cards with
their empty states.

**The e2e covers the empty state only, and deliberately so.** `generate_charges` runs on a
schedule, not at startup, so a lease created inside a test has no charges and no overdue state can
be staged through the UI. This matches how M4.1 handled the same constraint. The bucketing rules
are covered by tests 1-3 above; the e2e proves the page renders and is reachable, nothing more.

---

## Out of Scope

- Widening the charge horizon (`charge_lead_days` stays 7).
- Forecasting charges that have not been generated.
- Chasing actions from the view: no "send reminder" button, no bulk email.
- Filtering or sorting controls; the two orderings above are fixed.
- CSV export.
- A tenant-facing version; tenants already see their own charges.

---

## File Structure

| File | Change |
|---|---|
| `backend/app/services/payments.py` | add `org_charge_statuses` |
| `backend/app/schemas/rent.py` | new: `LeaseChargeGroup`, `RentSummary` |
| `backend/app/routers/rent.py` | new: `GET /rent/summary`, mounted in `main.py` |
| `backend/app/services/stats.py` | use the org-wide pass instead of the per-lease loop |
| `backend/tests/test_rent_summary.py` | new |
| `backend/tests/test_stats.py` | add the cross-check |
| `frontend/src/lib/rent.ts` | new: `getRentSummary` |
| `frontend/src/app/app/payments/page.tsx` | the two cards and expandable rows |
| `frontend/e2e/rent-summary.spec.ts` | new |

## Task Breakdown

- **T1** `org_charge_statuses` + the query-count test
- **T2** schemas + `/rent/summary` + bucketing tests 1-4
- **T3** `dashboard_stats` switched over + the cross-check test
- **T4** frontend: the two cards with expandable rows
- **T5** e2e + CI green
