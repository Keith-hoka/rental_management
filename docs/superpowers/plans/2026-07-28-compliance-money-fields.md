# Compliance Money Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the four compliance money amounts on leases so the s33/s24/s160/s107 rules return real verdicts, and re-audit automatically when compliance-relevant fields change.

**Architecture:** Four nullable `Numeric(10,2)` columns on `Lease` named exactly as the service API fields; schemas/renew follow the `bond_amount` pattern; `update_lease` diffs nine compliance-relevant fields and re-enqueues via the existing outbox; the mapper sends any non-null value; the frontend adds grouped optional inputs and stops claiming the app "does not record" these fields.

**Tech Stack:** Existing app stack. No new dependencies. Compliance service untouched.

## Global Constraints

- Repo: `/Users/keithho/LLMProjects/rental_management_app`; backend commands from `backend/` with `uv`; every task ends: backend `uv run pytest -q` -> ruff sequence (`format` -> `check --fix` -> `check` -> `format --check`) -> (frontend task: `npm run lint`) -> commit -> push -> CI green -> report -> WAIT.
- Field names verbatim everywhere: `rent_in_advance_amount`, `holding_deposit_amount`, `other_security_amount`, `break_fee_amount`.
- Compliance-relevant fields for the edit trigger, verbatim: `rent_amount`, `rent_frequency`, `start_date`, `end_date`, `bond_amount` plus the four above.
- All four fields optional end to end; no backfill; the service repo is not touched.
- Frontend copy: the skipped hint for these fields becomes "not filled in for this lease" (the old "not recorded in this app" becomes false).

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/models/lease.py` | four columns |
| `backend/alembic/versions/<gen>_add_lease_money_fields.py` | migration |
| `backend/app/schemas/lease.py` | four fields on Create/Update/Renew/Response |
| `backend/app/routers/leases.py` | renew copy; update diff -> enqueue |
| `backend/app/services/compliance.py` | mapper sends the four |
| `backend/tests/test_leases_money_fields.py` | new backend tests |
| `backend/tests/test_compliance_mapper.py` | mapper eval extension |
| `frontend/src/lib/leases.ts` | types |
| `frontend/src/app/app/leases/new/page.tsx`, `[leaseId]/page.tsx`, `[leaseId]/renew/page.tsx` | inputs + facts |
| `frontend/src/app/app/leases/ComplianceSection.tsx` | hint copy |
| `frontend/e2e/compliance.spec.ts` | assertion copy |

---

### Task 1: Columns, schemas, renew copy

**Files:**
- Modify: `backend/app/models/lease.py`, `backend/app/schemas/lease.py`, `backend/app/routers/leases.py` (renew only)
- Create: migration, `backend/tests/test_leases_money_fields.py`

**Interfaces:**
- Consumes: existing `Lease`, `LeaseCreate/Update/Renew/Response`, `renew_lease`.
- Produces: `Lease.rent_in_advance_amount/holding_deposit_amount/other_security_amount/break_fee_amount: Decimal | None`; the same four optional fields on all four schemas; renew copies each from source unless overridden.

- [ ] **Step 1: Failing tests** — `backend/tests/test_leases_money_fields.py`:

```python
from sqlalchemy import select

from app.models import ComplianceAuditQueue
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers

MONEY = {
    "rent_in_advance_amount": 1200,
    "holding_deposit_amount": 600,
    "other_security_amount": 0,
    "break_fee_amount": 2400,
}


async def _create_lease(client, headers, **overrides):
    property_id = await make_property(client, headers, "5 Money St")
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(**overrides),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_create_persists_and_returns_money_fields(client):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers, **MONEY)
    for field, value in MONEY.items():
        assert float(lease[field]) == float(value)


async def test_money_fields_default_to_null(client):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers)
    for field in MONEY:
        assert lease[field] is None


async def test_renew_copies_money_fields(client):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers, **MONEY)
    renewed = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew", json={"end_date": "2027-12-31"}, headers=headers
        )
    ).json()
    for field, value in MONEY.items():
        assert float(renewed[field]) == float(value)


async def test_renew_overrides_money_fields(client):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers, **MONEY)
    renewed = (
        await client.post(
            f"/api/v1/leases/{lease['id']}/renew",
            json={"end_date": "2027-12-31", "break_fee_amount": 3000},
            headers=headers,
        )
    ).json()
    assert float(renewed["break_fee_amount"]) == 3000.0
    assert float(renewed["holding_deposit_amount"]) == 600.0
```

- [ ] **Step 2: Run -> fail.** `cd backend && uv run pytest tests/test_leases_money_fields.py -q` — creation 201 but the response lacks the fields (KeyError) since schemas don't know them.

- [ ] **Step 3: Model** — in `backend/app/models/lease.py`, after `bond_amount`:

```python
    rent_in_advance_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    holding_deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    other_security_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    break_fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
```

- [ ] **Step 4: Migration** — `cd backend && uv run alembic revision -m "add lease money fields"`; body:

```python
def upgrade() -> None:
    """Add the four compliance money columns to leases."""
    op.add_column("leases", sa.Column("rent_in_advance_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("leases", sa.Column("holding_deposit_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("leases", sa.Column("other_security_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("leases", sa.Column("break_fee_amount", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    """Drop the four compliance money columns."""
    op.drop_column("leases", "break_fee_amount")
    op.drop_column("leases", "other_security_amount")
    op.drop_column("leases", "holding_deposit_amount")
    op.drop_column("leases", "rent_in_advance_amount")
```

Verify: `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`.

- [ ] **Step 5: Schemas** — in `backend/app/schemas/lease.py` add to `LeaseCreate`, `LeaseUpdate`, `LeaseRenew` and `LeaseResponse` (after each `bond_amount` line; all `Decimal | None = None`, except `LeaseResponse` where the pattern is `Decimal | None`):

```python
    rent_in_advance_amount: Decimal | None = None
    holding_deposit_amount: Decimal | None = None
    other_security_amount: Decimal | None = None
    break_fee_amount: Decimal | None = None
```

- [ ] **Step 6: Renew copy** — in `renew_lease`'s `Lease(...)` construction in `backend/app/routers/leases.py`, after the `bond_amount=` line, following its exact pattern:

```python
        rent_in_advance_amount=(
            body.rent_in_advance_amount
            if body.rent_in_advance_amount is not None
            else source.rent_in_advance_amount
        ),
        holding_deposit_amount=(
            body.holding_deposit_amount
            if body.holding_deposit_amount is not None
            else source.holding_deposit_amount
        ),
        other_security_amount=(
            body.other_security_amount
            if body.other_security_amount is not None
            else source.other_security_amount
        ),
        break_fee_amount=(
            body.break_fee_amount if body.break_fee_amount is not None else source.break_fee_amount
        ),
```

- [ ] **Step 7: Run -> pass; backend full suite; ruff; commit** (`Add the compliance money fields to leases`); push; CI green. Report and WAIT.

---

### Task 2: Edits re-enqueue the audit

**Files:**
- Modify: `backend/app/routers/leases.py` (`update_lease`)
- Modify: `backend/tests/test_leases_money_fields.py`

**Interfaces:**
- Consumes: `compliance_enabled`/`enqueue_audit` (already imported in this router), `compliance_on` fixture from `tests/conftest.py`.
- Produces: module constant `COMPLIANCE_FIELDS: tuple[str, ...]` and the diff-then-enqueue behavior in `update_lease`.

- [ ] **Step 1: Failing tests** — append to `backend/tests/test_leases_money_fields.py`:

```python
async def test_editing_compliance_field_enqueues(client, db_session, compliance_on):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers)
    await db_session.execute(ComplianceAuditQueue.__table__.delete())
    await db_session.commit()
    patched = await client.patch(
        f"/api/v1/leases/{lease['id']}", json={"break_fee_amount": 2500}, headers=headers
    )
    assert patched.status_code == 200
    queued = (await db_session.execute(select(ComplianceAuditQueue))).scalar_one()
    assert str(queued.lease_id) == lease["id"]


async def test_editing_tenant_details_does_not_enqueue(client, db_session, compliance_on):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers)
    await db_session.execute(ComplianceAuditQueue.__table__.delete())
    await db_session.commit()
    await client.patch(
        f"/api/v1/leases/{lease['id']}", json={"tenant_name": "Renamed"}, headers=headers
    )
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None


async def test_editing_when_disabled_does_not_enqueue(client, db_session):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers)
    await client.patch(
        f"/api/v1/leases/{lease['id']}", json={"break_fee_amount": 2500}, headers=headers
    )
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None


async def test_unchanged_value_does_not_enqueue(client, db_session, compliance_on):
    headers = await landlord_headers(client)
    lease = await _create_lease(client, headers, **MONEY)
    await db_session.execute(ComplianceAuditQueue.__table__.delete())
    await db_session.commit()
    await client.patch(
        f"/api/v1/leases/{lease['id']}", json={"break_fee_amount": 2400}, headers=headers
    )
    assert (await db_session.execute(select(ComplianceAuditQueue))).first() is None
```

(The first two tests clear the queue first because creating the lease with `compliance_on` already enqueued it.)

- [ ] **Step 2: Run -> fail** (first test: no queue row after the patch).

- [ ] **Step 3: Implement** — in `backend/app/routers/leases.py`, add at module level near the other constants:

```python
COMPLIANCE_FIELDS = (
    "rent_amount",
    "rent_frequency",
    "start_date",
    "end_date",
    "bond_amount",
    "rent_in_advance_amount",
    "holding_deposit_amount",
    "other_security_amount",
    "break_fee_amount",
)
```

and in `update_lease`, replace the setattr/commit block:

```python
    before = tuple(getattr(lease, field) for field in COMPLIANCE_FIELDS)
    for field, value in data.items():
        setattr(lease, field, value)
    if compliance_enabled():
        after = tuple(getattr(lease, field) for field in COMPLIANCE_FIELDS)
        if after != before:
            await enqueue_audit(session, lease.id)
    await session.commit()
    await session.refresh(lease)
    return lease
```

- [ ] **Step 4: Run -> pass; backend full suite; ruff; commit** (`Re-audit leases when compliance fields change`); push; CI green. Report and WAIT.

---

### Task 3: Mapper sends the four fields

**Files:**
- Modify: `backend/app/services/compliance.py` (`chain_to_audit_payload`), `backend/tests/test_compliance_mapper.py`

**Interfaces:**
- Consumes: `chain_to_audit_payload(chain) -> dict`, the `_lease(...)` test helper.
- Produces: payload includes each of the four fields (stringified) from the newest chain lease when non-null; omitted when null. `bond_amount` handling folds into the same loop.

- [ ] **Step 1: Failing tests** — in `backend/tests/test_compliance_mapper.py`, extend `_lease` with money kwargs and add tests:

```python
def _lease(start, end, rent, bond=None, prev=None, **money):
    lease = Lease(
        id=uuid_mod.uuid4(),
        organization_id=uuid_mod.uuid4(),
        property_id=uuid_mod.uuid4(),
        tenant_name="T",
        tenant_email="t@example.com",
        co_tenants=[],
        rent_amount=Decimal(rent),
        rent_frequency=LeaseFrequency.weekly,
        bond_amount=Decimal(bond) if bond is not None else None,
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        renewed_from_id=prev.id if prev is not None else None,
        **{name: Decimal(value) for name, value in money.items()},
    )
    return lease


def test_payload_sends_money_fields_when_set():
    lease = _lease(
        "2026-01-01",
        "2026-12-31",
        600,
        rent_in_advance_amount=1200,
        holding_deposit_amount=600,
        other_security_amount=0,
        break_fee_amount=2400,
    )
    body = chain_to_audit_payload([lease])["lease"]
    assert body["rent_in_advance_amount"] == "1200"
    assert body["holding_deposit_amount"] == "600"
    assert body["other_security_amount"] == "0"
    assert body["break_fee_amount"] == "2400"


def test_payload_omits_null_money_fields():
    body = chain_to_audit_payload([_lease("2026-01-01", "2026-12-31", 600)])["lease"]
    for field in (
        "rent_in_advance_amount",
        "holding_deposit_amount",
        "other_security_amount",
        "break_fee_amount",
    ):
        assert field not in body


def test_payload_uses_newest_lease_money_fields():
    first = _lease("2024-01-01", "2024-12-31", 600, break_fee_amount=9999)
    second = _lease("2025-01-01", "2025-12-31", 600, prev=first, break_fee_amount=2400)
    body = chain_to_audit_payload([first, second])["lease"]
    assert body["break_fee_amount"] == "2400"
```

- [ ] **Step 2: Run -> fail** (fields absent from payload).

- [ ] **Step 3: Implement** — in `chain_to_audit_payload`, replace the `bond_amount` if-block with one loop:

```python
    for field in (
        "bond_amount",
        "rent_in_advance_amount",
        "holding_deposit_amount",
        "other_security_amount",
        "break_fee_amount",
    ):
        value = getattr(newest, field)
        if value is not None:
            lease_body[field] = str(value)
```

- [ ] **Step 4: Run -> pass; backend full suite; ruff; commit** (`Send the money fields to the compliance audit`); push; CI green. Report and WAIT.

---

### Task 4: Frontend inputs, facts and hint copy

**Files:**
- Modify: `frontend/src/lib/leases.ts`, `frontend/src/app/app/leases/new/page.tsx`, `frontend/src/app/app/leases/[leaseId]/page.tsx`, `frontend/src/app/app/leases/[leaseId]/renew/page.tsx`, `frontend/src/app/app/leases/ComplianceSection.tsx`, `frontend/e2e/compliance.spec.ts`

**Interfaces:**
- Consumes: Task 1's API fields.
- Produces: the four fields on the `Lease`/`LeaseInput` TS interfaces (`number | null`); inputs on the three forms; facts rows; hint copy "not filled in for this lease".

- [ ] **Step 1: Types** — in `frontend/src/lib/leases.ts` add to both `Lease` and `LeaseInput` interfaces after `bond_amount`:

```typescript
  rent_in_advance_amount: number | null;
  holding_deposit_amount: number | null;
  other_security_amount: number | null;
  break_fee_amount: number | null;
```

(In `LeaseInput` mark them optional if the existing interface marks `bond_amount` optional — mirror it exactly.)

- [ ] **Step 2: New-lease form** — in `new/page.tsx`: add the four keys (`null`) to the initial form object next to `bond_amount: null`, and after the Bond/Notice inputs add a grouped block using the page's existing label/Input pattern:

```tsx
        <p className="mt-4 text-sm font-medium text-text">Upfront money & fees (optional)</p>
        <div className="grid grid-cols-2 gap-3">
          {(
            [
              ["rent_in_advance_amount", "Rent in advance"],
              ["holding_deposit_amount", "Holding fee"],
              ["other_security_amount", "Other security"],
              ["break_fee_amount", "Break fee"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="text-sm text-muted">
              {label}
              <Input
                type="number"
                value={form[key] ?? ""}
                onChange={(e) => set(key, e.target.value === "" ? null : Number(e.target.value))}
              />
            </label>
          ))}
        </div>
```

Adapt the wrapper markup to the page's actual form layout (same elements the Bond field uses; keep the four in one visual group under the heading).

- [ ] **Step 3: Edit form and facts** — in `[leaseId]/page.tsx`: add the four fields where the edit form state is built from `current` (next to `bond_amount: current.bond_amount`), render the same grouped four-input block in the edit form next to the existing Bond input, and add four facts rows after the Bond `Field`:

```tsx
            <Field
              label="Rent in advance"
              value={
                lease.rent_in_advance_amount != null ? `$${lease.rent_in_advance_amount}` : "—"
              }
            />
            <Field
              label="Holding fee"
              value={
                lease.holding_deposit_amount != null ? `$${lease.holding_deposit_amount}` : "—"
              }
            />
            <Field
              label="Other security"
              value={lease.other_security_amount != null ? `$${lease.other_security_amount}` : "—"}
            />
            <Field
              label="Break fee"
              value={lease.break_fee_amount != null ? `$${lease.break_fee_amount}` : "—"}
            />
```

- [ ] **Step 4: Renew page** — in `renew/page.tsx`: four `useState<number | null>(null)` hooks initialised from the loaded source lease (same as `setBond(l.bond_amount)`), four inputs following the Bond input pattern, and include the four values in the POST body next to `bond_amount: bond`.

- [ ] **Step 5: Hint copy** — in `ComplianceSection.tsx` replace the constant and its uses:

```typescript
const NOT_FILLED = "not filled in for this lease";

const FIELD_HINTS: Record<string, string> = {
  bond_amount: "the bond amount",
  rent_in_advance_amount: `the advance rent amount (${NOT_FILLED})`,
  holding_deposit_amount: `the holding fee amount (${NOT_FILLED})`,
  other_security_amount: `the other-security amount (${NOT_FILLED})`,
  break_fee_amount: `the break fee amount (${NOT_FILLED})`,
  rent_increases: "a rent increase history, which builds from renewals with a higher rent",
  end_date: "the end date",
};
```

and in `frontend/e2e/compliance.spec.ts` change the assertion `page.getByText("not recorded in this app")` to `page.getByText("not filled in for this lease")`.

- [ ] **Step 6: Verify** — `cd frontend && npm run lint`; run the disabled e2e (`npx playwright test e2e/compliance.spec.ts` with backend on 8000 without compliance env); then the live pass: compliance service on 8100 (`API_KEYS=dev-key:rentalapp uv run uvicorn app.main:app --port 8100` in the service repo), backend with `COMPLIANCE_API_URL=http://localhost:8100 COMPLIANCE_API_KEY=dev-key`, `COMPLIANCE_E2E=1 npx playwright test e2e/compliance.spec.ts`. Also fill the four fields on a lease in the browser and confirm the audit now shows red/green verdicts for s33/s24/s160/s107 (record which).

- [ ] **Step 7: Backend full suite still green; ruff; commit** (`Capture the compliance money fields in the lease forms`); push; CI green. Report and WAIT — milestone complete.
