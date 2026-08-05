# State-to-Jurisdiction Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Submit compliance and clause audits under the property's real jurisdiction (NSW or VIC), skip with a visible prompt when the state is missing or unsupported, and re-audit stored results that ran under the wrong jurisdiction.

**Architecture:** A pure mapper module resolves `Property.state` to a jurisdiction at submit time; both audit tables store the jurisdiction each row was audited under; the queue drain drops unresolvable rows without retry; the frontend gates its trigger buttons on a live-computed status and badges results with their jurisdiction.

**Tech Stack:** existing only - FastAPI + async SQLAlchemy + Alembic backend, Next.js frontend. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-05-jurisdiction-wiring-design.md`

## Global Constraints

- Repo: `/Users/keithho/LLMProjects/rental_management_app`. Python via `uv` only; frontend via the repo's existing npm scripts.
- Every task ends: backend full suite (`cd backend && uv run pytest`) -> ruff sequence from the repo root (`uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`, run inside `backend/`) -> frontend `npm run lint && npm run build` when frontend files changed -> commit -> push origin main -> CI green.
- No emojis. Docstrings over comments. TDD: failing test first, watched to fail for the right reason.
- Names exactly: module `backend/app/services/jurisdiction.py`; `SUPPORTED_JURISDICTIONS = {"NSW", "VIC"}`; `normalize_state`, `jurisdiction_for`, `JurisdictionUnresolved`; reasons exactly `"ok" | "missing" | "unsupported"`; new columns named `jurisdiction`; backfill flag `--fix-jurisdictions`.
- The eight state codes: NSW, VIC, QLD, SA, WA, TAS, ACT, NT.
- Skips never call the compliance service. Existing audit rows backfill to `"NSW"`.
- No compliance-service (lease-compliance-service repo) change of any kind.

---

### Task 1: Jurisdiction mapper, columns, migration

**Files:**
- Create: `backend/app/services/jurisdiction.py`
- Modify: `backend/app/models/compliance.py` (LeaseAudit), `backend/app/models/clause_audit.py` (LeaseClauseAudit)
- Create: one Alembic migration under `backend/alembic/versions/`
- Test: `backend/tests/test_jurisdiction.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `normalize_state(text: str | None) -> str | None`; `jurisdiction_for(property_state: str | None) -> tuple[str | None, str]` (reason `"ok"|"missing"|"unsupported"`); `JurisdictionUnresolved(reason)` exception with a `.reason` attribute; `SUPPORTED_JURISDICTIONS`; `LeaseAudit.jurisdiction` and `LeaseClauseAudit.jurisdiction` (`str`, server_default "NSW"). Tasks 2-4 rely on all of these names.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_jurisdiction.py`:

```python
import pytest

from app.services.jurisdiction import (
    SUPPORTED_JURISDICTIONS,
    JurisdictionUnresolved,
    jurisdiction_for,
    normalize_state,
)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("NSW", "NSW"),
        ("nsw", "NSW"),
        (" New South Wales ", "NSW"),
        ("VIC", "VIC"),
        ("Vic.", "VIC"),
        ("victoria", "VIC"),
        ("Queensland", "QLD"),
        ("qld", "QLD"),
        ("South Australia", "SA"),
        ("Western Australia", "WA"),
        ("Tasmania", "TAS"),
        ("tas", "TAS"),
        ("ACT", "ACT"),
        ("Australian Capital Territory", "ACT"),
        ("Northern Territory", "NT"),
        ("nt", "NT"),
    ],
)
def test_normalize_state_aliases(text, code):
    assert normalize_state(text) == code


@pytest.mark.parametrize("text", [None, "", "  ", "Sydney", "N.S.W. Australia", "12345"])
def test_normalize_state_unrecognisable(text):
    assert normalize_state(text) is None


def test_supported_set():
    assert SUPPORTED_JURISDICTIONS == {"NSW", "VIC"}


def test_jurisdiction_for_three_reasons():
    assert jurisdiction_for("Victoria") == ("VIC", "ok")
    assert jurisdiction_for(None) == (None, "missing")
    assert jurisdiction_for("gibberish") == (None, "missing")
    assert jurisdiction_for("QLD") == (None, "unsupported")


def test_exception_carries_reason():
    exc = JurisdictionUnresolved("missing")
    assert exc.reason == "missing"
    assert isinstance(exc, Exception)
```

Note: "N.S.W. Australia" normalises to "nswaustralia", which matches no
alias - unrecognisable is correct (only whole-value aliases map; we do
not substring-guess).

- [ ] **Step 2: Watch them fail**

Run: `cd backend && uv run pytest tests/test_jurisdiction.py -v`
Expected: collection error - `ModuleNotFoundError` on `app.services.jurisdiction`.

- [ ] **Step 3: Implement the mapper**

`backend/app/services/jurisdiction.py`:

```python
"""Map free-text property state to a compliance jurisdiction."""

from typing import Literal

SUPPORTED_JURISDICTIONS = {"NSW", "VIC"}

_ALIASES = {
    "nsw": "NSW",
    "newsouthwales": "NSW",
    "vic": "VIC",
    "victoria": "VIC",
    "qld": "QLD",
    "queensland": "QLD",
    "sa": "SA",
    "southaustralia": "SA",
    "wa": "WA",
    "westernaustralia": "WA",
    "tas": "TAS",
    "tasmania": "TAS",
    "act": "ACT",
    "australiancapitalterritory": "ACT",
    "nt": "NT",
    "northernterritory": "NT",
}

Reason = Literal["ok", "missing", "unsupported"]


class JurisdictionUnresolved(Exception):
    """The property's state does not resolve to a supported jurisdiction."""

    def __init__(self, reason: Reason) -> None:
        super().__init__(reason)
        self.reason: Reason = reason


def normalize_state(text: str | None) -> str | None:
    """The state/territory code for free text, or None when unrecognisable."""
    if text is None:
        return None
    key = "".join(ch for ch in text.lower() if ch.isalpha())
    return _ALIASES.get(key)


def jurisdiction_for(property_state: str | None) -> tuple[str | None, Reason]:
    """Resolve a state value to (supported code, "ok"), or (None, why not)."""
    code = normalize_state(property_state)
    if code is None:
        return (None, "missing")
    if code not in SUPPORTED_JURISDICTIONS:
        return (None, "unsupported")
    return (code, "ok")
```

- [ ] **Step 4: Add the columns**

In `backend/app/models/compliance.py`, inside `LeaseAudit` after `findings`:

```python
    jurisdiction: Mapped[str] = mapped_column(String(3), nullable=False, server_default="NSW")
```

(Import `String` from sqlalchemy if the file does not already.) Same
line inside `LeaseClauseAudit` in `backend/app/models/clause_audit.py`
after `engine_version`.

- [ ] **Step 5: Generate and verify the migration**

```bash
cd backend && uv run alembic revision --autogenerate -m "add jurisdiction to audit tables"
```

Open the generated file: it must add exactly the two columns, each
`sa.String(length=3), server_default="NSW", nullable=False`, and drop
them in downgrade. Remove any unrelated autogenerated noise. Then:

```bash
uv run alembic upgrade head
```

Add a round-trip test at the end of `backend/tests/test_jurisdiction.py`
(the suite's `db_session` fixture runs on the migrated test DB; mirror
`tests/test_compliance_mapper.py::test_compliance_tables_round_trip`'s
use of `make_lease_row`):

```python
async def test_audit_rows_default_to_nsw(db_session):
    import uuid as uuid_mod
    from datetime import date

    from sqlalchemy import select, text

    from app.models import LeaseAudit
    from tests.test_lease_model import make_lease_row

    lease = await make_lease_row(db_session)
    await db_session.execute(
        text(
            "INSERT INTO lease_audits (id, lease_id, organization_id, audit_id, as_at, findings)"
            " VALUES (:id, :lease_id, :org, :audit_id, :as_at, '[]')"
        ),
        {
            "id": str(uuid_mod.uuid4()),
            "lease_id": str(lease.id),
            "org": str(lease.organization_id),
            "audit_id": str(uuid_mod.uuid4()),
            "as_at": date(2026, 8, 5),
        },
    )
    row = (
        await db_session.execute(select(LeaseAudit).where(LeaseAudit.lease_id == lease.id))
    ).scalar_one()
    assert row.jurisdiction == "NSW"
```

(The raw INSERT omits the column deliberately - it proves the server
default that the migration applies to pre-existing rows.)

- [ ] **Step 6: Run the tests, then the full suite**

```bash
cd backend && uv run pytest tests/test_jurisdiction.py -v
uv run pytest
```

Expected: all new tests pass; full suite green.

- [ ] **Step 7: Ruff, commit, push, CI**

```bash
cd backend && uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
git add -A && git commit -m "Add the jurisdiction mapper and audit jurisdiction columns"
git push origin main
```

---

### Task 2: Submit paths, queue drain, status endpoints

**Files:**
- Modify: `backend/app/services/compliance.py` (payload signature, resolver, run_lease_audit, drain)
- Modify: `backend/app/services/clause_audit.py:88-115` (submit_document_audit)
- Modify: `backend/app/routers/compliance.py` (422 on unresolved; state response)
- Modify: `backend/app/routers/clause_audits.py` (422 on unresolved; list response)
- Modify: `backend/app/schemas/compliance.py`, `backend/app/schemas/clause_audit.py` (new fields)
- Test: `backend/tests/test_compliance_mapper.py`, `backend/tests/test_compliance_endpoints.py`, `backend/tests/test_compliance_jobs.py`, `backend/tests/test_clause_audit_service.py`, `backend/tests/test_clause_audit_endpoints.py`

**Interfaces:**
- Consumes: Task 1's `jurisdiction_for`, `JurisdictionUnresolved`, columns.
- Produces: `chain_to_audit_payload(chain, jurisdiction: str) -> dict`; `resolve_jurisdiction(session, lease) -> str` (raises `JurisdictionUnresolved`); `ComplianceAuditState` gains `jurisdiction_status: Literal["ok", "missing", "unsupported"]` and `jurisdiction: str | None`; `ComplianceAuditInfo` gains `jurisdiction: str`; the clause list response gains the same two state fields and per-audit `jurisdiction`. Tasks 3-4 rely on these.

- [ ] **Step 1: Write the failing tests**

Read each named test file first and mirror its fixtures (`db_session`,
`make_lease_row`, how the service is mocked - these files already mock
`create_audit`/HTTP with monkeypatch or respx; reuse the same idiom).
The essential new tests (adapt constructor details to the file's
helpers, keep the assertions):

In `test_compliance_mapper.py` - update every existing
`chain_to_audit_payload(chain)` call to
`chain_to_audit_payload(chain, "NSW")`, and add:

```python
def test_payload_carries_the_given_jurisdiction():
    # build the minimal single-lease chain the file already builds
    payload = chain_to_audit_payload(chain, "VIC")
    assert payload["jurisdiction"] == "VIC"


async def test_resolve_jurisdiction_by_property_state(db_session):
    lease = await make_lease_row(db_session)  # its property row is reachable
    # set the property state to Victoria, then:
    assert await compliance.resolve_jurisdiction(db_session, lease) == "VIC"


async def test_resolve_jurisdiction_missing_raises(db_session):
    lease = await make_lease_row(db_session)  # leave/blank the state
    with pytest.raises(JurisdictionUnresolved) as excinfo:
        await compliance.resolve_jurisdiction(db_session, lease)
    assert excinfo.value.reason == "missing"
```

(`make_lease_row` creates a property; look at `tests/test_lease_model.py`
for how to reach and update it - set `property.state = "Victoria"` via a
fetched row and flush.)

In `test_compliance_jobs.py` (drain behaviour):

```python
async def test_drain_drops_unresolvable_rows_without_calling_the_service(db_session, monkeypatch):
    called = []

    async def fake_create_audit(payload):
        called.append(payload)
        raise AssertionError("service must not be called")

    monkeypatch.setattr(compliance, "create_audit", fake_create_audit)
    lease = await make_lease_row(db_session)  # property state left unset
    await compliance.enqueue_audit(db_session, lease.id)
    await db_session.commit()

    done = await compliance.drain_audit_queue(db_session)

    assert done == 0
    assert called == []
    remaining = (await db_session.execute(select(ComplianceAuditQueue))).scalars().all()
    assert remaining == []
```

In `test_compliance_endpoints.py`:

```python
async def test_run_audit_returns_422_when_state_missing(client, ...):
    # existing authenticated-lease setup with the property state unset
    response = await client.post(f"/api/v1/leases/{lease_id}/compliance-audit")
    assert response.status_code == 422
    assert "missing" in response.json()["detail"]


async def test_state_endpoint_reports_jurisdiction_status(client, ...):
    # property state "Victoria" -> GET returns jurisdiction_status "ok", jurisdiction "VIC"
    # property state unset -> "missing", None
    # property state "QLD" -> "unsupported", None
```

In `test_clause_audit_service.py` / `test_clause_audit_endpoints.py`:
mirror the same three shapes for `submit_document_audit` (payload
jurisdiction, stored row jurisdiction, `JurisdictionUnresolved` raised)
and the clause trigger endpoint 422 + list-response status fields.

- [ ] **Step 2: Watch them fail**

Run the five files: signature errors on `chain_to_audit_payload`,
missing `resolve_jurisdiction`, 200-vs-422, missing response fields.

- [ ] **Step 3: Implement**

`backend/app/services/compliance.py`:

```python
from app.models import ComplianceAuditQueue, ComplianceSyncState, Lease, LeaseAudit, Property
from app.services.jurisdiction import JurisdictionUnresolved, jurisdiction_for
```

```python
async def resolve_jurisdiction(session: AsyncSession, lease: Lease) -> str:
    """The audit jurisdiction from the lease's property state; raises when unresolved."""
    state = (
        await session.execute(select(Property.state).where(Property.id == lease.property_id))
    ).scalar_one()
    code, reason = jurisdiction_for(state)
    if code is None:
        raise JurisdictionUnresolved(reason)
    return code
```

`chain_to_audit_payload(chain: list[Lease], jurisdiction: str) -> dict` -
same body, final line becomes:

```python
    return {"jurisdiction": jurisdiction, "client_ref": str(newest.id), "lease": lease_body}
```

`run_lease_audit`:

```python
async def run_lease_audit(session: AsyncSession, lease: Lease) -> LeaseAudit:
    """Audit one lease now and store the result. The caller commits."""
    jurisdiction = await resolve_jurisdiction(session, lease)
    chain = await load_chain(session, lease)
    body = await create_audit(chain_to_audit_payload(chain, jurisdiction))
    audit = LeaseAudit(
        lease_id=lease.id,
        organization_id=lease.organization_id,
        audit_id=uuid.UUID(body["id"]),
        as_at=date.fromisoformat(body["as_at"]),
        findings=body["findings"],
        jurisdiction=jurisdiction,
    )
    session.add(audit)
    await session.flush()
    return audit
```

`drain_audit_queue` - insert a dedicated handler BEFORE the generic one
(an unset state is not transient; retrying is waste):

```python
        try:
            await run_lease_audit(session, lease)
        except JurisdictionUnresolved as exc:
            logger.info(
                "Dropping queued audit for lease %s: jurisdiction %s", row.lease_id, exc.reason
            )
            await session.delete(row)
            await session.commit()
            continue
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the drain
```

(dropped rows are deleted but do not increment `done`.)

`backend/app/schemas/compliance.py`:

```python
from typing import Literal


class ComplianceAuditInfo(BaseModel):
    id: uuid.UUID
    audit_id: uuid.UUID
    as_at: date
    findings: list
    jurisdiction: str
    created_at: datetime


class ComplianceAuditState(BaseModel):
    enabled: bool
    audit: ComplianceAuditInfo | None = None
    jurisdiction_status: Literal["ok", "missing", "unsupported"] = "ok"
    jurisdiction: str | None = None
```

`backend/app/routers/compliance.py` - `_info` gains
`jurisdiction=audit.jurisdiction`; `run_audit_now` catches:

```python
    except compliance.JurisdictionUnresolved as exc:
        raise HTTPException(
            status_code=422, detail=f"Property state unresolved: {exc.reason}"
        ) from exc
```

(re-export or import `JurisdictionUnresolved` in `services/compliance.py`'s
namespace - it is already imported there, so `compliance.JurisdictionUnresolved`
works.) `latest_audit` resolves the live status:

```python
    state_value = (
        await session.execute(select(Property.state).where(Property.id == lease.property_id))
    ).scalar_one()
    code, reason = jurisdiction_for(state_value)
    return ComplianceAuditState(
        enabled=compliance.enabled(),
        audit=_info(row) if row else None,
        jurisdiction_status=reason,
        jurisdiction=code,
    )
```

(import `Property` and `jurisdiction_for` in the router; keep the
existing `enabled`/row logic - only the return value grows.)

`backend/app/services/clause_audit.py` - `submit_document_audit` starts:

```python
    jurisdiction = await resolve_jurisdiction(session, lease)
```

(import `resolve_jurisdiction` from `app.services.compliance`), the
payload uses `"jurisdiction": jurisdiction`, and the row gains
`jurisdiction=jurisdiction`.

`backend/app/routers/clause_audits.py` - the trigger endpoint catches
`JurisdictionUnresolved` -> 422 exactly like the deterministic router;
the list endpoint's response model (see
`backend/app/schemas/clause_audit.py` for the actual class names -
mirror the deterministic pattern) gains
`jurisdiction_status`/`jurisdiction` resolved the same way, and the
per-audit schema gains `jurisdiction: str`.

- [ ] **Step 4: Run the five test files, then the full suite** - green.

- [ ] **Step 5: Ruff, commit, push, CI** - message "Wire property state to audit jurisdiction in both submit paths".

---

### Task 3: Backfill --fix-jurisdictions

**Files:**
- Modify: `backend/app/compliance_backfill.py`
- Test: `backend/tests/test_compliance_backfill.py` (extend; create if the existing backfill has no test file - check first)

**Interfaces:**
- Consumes: Task 1 mapper, Task 2 `resolve_jurisdiction`/columns, existing `enqueue_audit`, `clause_audit.submit_document_audit`, `clause_audit.latest_version`.
- Produces: `uv run python -m app.compliance_backfill --fix-jurisdictions`.

- [ ] **Step 1: Write the failing tests**

Seed with the suite's helpers: a lease whose property state is
"Victoria" with a stored `LeaseAudit(jurisdiction="NSW")` (must be
selected), one whose latest audit is already "VIC" (skipped), one with
state unset (listed only), one with state "QLD" (listed only). Assert:

```python
async def test_fix_jurisdictions_selects_mismatched_leases(db_session, monkeypatch):
    enqueued = []

    async def fake_enqueue(session, lease_id):
        enqueued.append(lease_id)

    monkeypatch.setattr("app.compliance_backfill.enqueue_audit", fake_enqueue)
    report = await fix_jurisdictions(db_session, execute=True)
    assert enqueued == [mismatched_lease.id]
    assert report["deterministic_enqueued"] == 1
    assert report["skipped_matching"] >= 1
    assert report["missing"] == [missing_lease.id]
    assert report["unsupported"] == [qld_lease.id]
```

Plus a clause variant: a `LeaseClauseAudit(jurisdiction="NSW")` on a
VIC-mapped lease selects for resubmission (monkeypatch
`submit_document_audit`, assert it was called once with that lease's
document/version); a matching row is skipped. And a `execute=False`
(default) dry-run test: report populated, nothing enqueued or submitted.

- [ ] **Step 2: Watch them fail** - `fix_jurisdictions` does not exist.

- [ ] **Step 3: Implement**

Extend `backend/app/compliance_backfill.py`:

```python
import argparse

from sqlalchemy.orm import aliased

from app.models import Document, DocumentVersion, Lease, LeaseAudit, LeaseClauseAudit, Property
from app.services import clause_audit
from app.services.compliance import enqueue_audit
from app.services.jurisdiction import jurisdiction_for


async def fix_jurisdictions(session: AsyncSession, execute: bool = False) -> dict:
    """Find audits stored under a jurisdiction their property no longer maps to.

    Dry-run by default: reports what would change; execute=True enqueues
    deterministic re-audits and resubmits mismatched clause audits.
    """
    successor = aliased(Lease)
    rows = (
        await session.execute(
            select(Lease, Property.state).join(Property, Property.id == Lease.property_id).where(
                Lease.end_date >= datetime.now(UTC).date(),
                ~select(successor.id).where(successor.renewed_from_id == Lease.id).exists(),
            )
        )
    ).all()
    report: dict = {
        "deterministic_enqueued": 0,
        "clause_resubmitted": 0,
        "skipped_matching": 0,
        "missing": [],
        "unsupported": [],
    }
    for lease, state in rows:
        code, reason = jurisdiction_for(state)
        if reason == "missing":
            report["missing"].append(lease.id)
            continue
        if reason == "unsupported":
            report["unsupported"].append(lease.id)
            continue
        latest_audit = (
            await session.execute(
                select(LeaseAudit)
                .where(LeaseAudit.lease_id == lease.id)
                .order_by(LeaseAudit.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_audit is not None and latest_audit.jurisdiction != code:
            if execute:
                await enqueue_audit(session, lease.id)
            report["deterministic_enqueued"] += 1
        elif latest_audit is not None:
            report["skipped_matching"] += 1
        clause_rows = (
            await session.execute(
                select(LeaseClauseAudit)
                .where(LeaseClauseAudit.lease_id == lease.id)
                .order_by(LeaseClauseAudit.created_at.desc())
            )
        ).scalars().all()
        seen_documents: set = set()
        for clause_row in clause_rows:
            if clause_row.document_id in seen_documents:
                continue
            seen_documents.add(clause_row.document_id)
            if clause_row.jurisdiction == code:
                report["skipped_matching"] += 1
                continue
            if execute:
                document = (
                    await session.execute(
                        select(Document).where(Document.id == clause_row.document_id)
                    )
                ).scalar_one()
                version = await clause_audit.latest_version(session, document.id)
                if version is not None:
                    await clause_audit.submit_document_audit(session, lease, document, version)
            report["clause_resubmitted"] += 1
    if execute:
        await session.commit()
    return report
```

Wire argparse in `main()`: no flag -> the existing never-audited
backfill; `--fix-jurisdictions` -> dry-run report printed;
`--fix-jurisdictions --execute` -> perform. Print each report key on its
own line, listing the missing/unsupported lease ids.

Adjust field names to the actual models if any differ (verify
`Document`/`latest_version` signatures in `services/clause_audit.py`
before writing).

- [ ] **Step 4: Tests green, full suite green.**

- [ ] **Step 5: Ruff, commit, push, CI** - "Add --fix-jurisdictions backfill for mismatched audits".

---

### Task 4: Frontend and env-gated e2e

**Files:**
- Modify: `frontend/src/app/app/properties/new/page.tsx`, `frontend/src/app/app/properties/[id]/edit/page.tsx` (state dropdown)
- Modify: `frontend/src/lib/compliance.ts`, `frontend/src/lib/clauseAudit.ts` (types)
- Modify: `frontend/src/app/app/leases/ComplianceSection.tsx`, `frontend/src/app/app/leases/ClauseAuditSection.tsx`
- Modify: the lease page that mounts both sections (grep `ComplianceSection` under `frontend/src/app/app/leases/` for the mount site) - pass `propertyId`
- Test: extend the env-gated e2e (locate: `grep -rln "E2E" backend/tests/`; it is the tail-milestone file that talks to the real service when its env vars are set)

**Interfaces:**
- Consumes: Task 2's response fields (`jurisdiction_status`, `jurisdiction` on both state responses; `jurisdiction` per audit).
- Produces: UI only.

- [ ] **Step 1: State dropdown**

Add to both property form pages (top of file):

```tsx
const AU_STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT", "NT"] as const;
```

Replace the state `<Input .../>` block with a select. If
`@/components/ui` exports a `Select`, use it with these options;
otherwise a native element styled like the file's inputs:

```tsx
<select
  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text"
  value={form.state}
  onChange={(e) => set("state", e.target.value)}
>
  <option value="">State / territory</option>
  {AU_STATES.map((code) => (
    <option key={code} value={code}>
      {code}
    </option>
  ))}
</select>
```

On the edit page, if the loaded value is legacy free text that is not
one of the eight codes, keep it selectable by appending it as an extra
option when present (so an unnormalised value is visible, not silently
blanked):

```tsx
{form.state && !AU_STATES.includes(form.state as (typeof AU_STATES)[number]) ? (
  <option value={form.state}>{form.state}</option>
) : null}
```

- [ ] **Step 2: Types**

`frontend/src/lib/compliance.ts`:

```tsx
export interface ComplianceAudit {
  id: string;
  audit_id: string;
  as_at: string;
  findings: ComplianceFinding[];
  jurisdiction: string;
  created_at: string;
}

export type JurisdictionStatus = "ok" | "missing" | "unsupported";

export interface ComplianceAuditState {
  enabled: boolean;
  audit: ComplianceAudit | null;
  jurisdiction_status: JurisdictionStatus;
  jurisdiction: string | null;
}
```

`frontend/src/lib/clauseAudit.ts`: add `jurisdiction: string` to its
audit interface and `jurisdiction_status: JurisdictionStatus` (import
the type from `@/lib/compliance`) plus `jurisdiction: string | null` to
its list-state interface, mirroring the backend response.

- [ ] **Step 3: ComplianceSection**

Edits to `ComplianceSection.tsx`:

1. Props: `{ leaseId, propertyId }: { leaseId: string; propertyId: string }` -
   update the mount site to pass the lease's property id.
2. Add the four VIC labels to `RULE_LABELS`:

```tsx
  "vic.bond_max_1_month": "Bond cap (s 31)",
  "vic.advance_max_1_month": "Rent in advance cap (s 40)",
  "vic.rent_increase_frequency": "Rent increase frequency (s 44)",
  "vic.fixed_term_increase_provision": "Fixed-term increase provision (s 44)",
```

3. Card title becomes jurisdiction-aware and the body gates on status.
   Replace the `return (<Card ...>)` block's opening with:

```tsx
  const title = state.jurisdiction ? `${state.jurisdiction} compliance` : "Compliance";
  const blocked = state.jurisdiction_status !== "ok";
  return (
    <Card
      className="mt-5"
      title={title}
      actions={
        <Button onClick={check} disabled={running || blocked}>
          {running ? "Checking..." : "Check now"}
        </Button>
      }
    >
      {blocked && (
        <p className="mb-2 text-sm text-muted">
          {state.jurisdiction_status === "missing" ? (
            <>
              Set the property&apos;s state to enable compliance checks.{" "}
              <a className="underline" href={`/app/properties/${propertyId}/edit`}>
                Edit property
              </a>
            </>
          ) : (
            "Compliance checks are not yet supported for this property's state."
          )}
        </p>
      )}
```

4. In the results block, add the audited-as badge beside the as-at line:

```tsx
            <Badge tone="neutral">audited as {audit.jurisdiction}</Badge>
            <span className="text-xs text-muted">as at {audit.as_at}</span>
```

Existing results stay rendered when blocked (they carry their own
badge). Everything else (counts, rows, skippedDetail) is untouched.

- [ ] **Step 4: ClauseAuditSection**

1. Props gain `propertyId: string` (update the mount site).
2. Add the sixteen VIC labels to `CLAUSE_RULE_LABELS`:

```tsx
  "vic.clause.renter_insurance": "Prohibited term: renter must take out insurance (s 27B)",
  "vic.clause.provider_liability_exemption": "Prohibited term: provider liability exemption (s 27B)",
  "vic.clause.breach_penalty": "Prohibited term: breach penalty or remaining rent (s 27B)",
  "vic.clause.professional_cleaning_required": "Prohibited term: professional cleaning required (s 27B)",
  "vic.clause.professional_cleaning_cost": "Prohibited term: professional cleaning cost (s 27B)",
  "vic.clause.no_breach_rent_inducement": "Prohibited term: conditional rent inducement (s 27B)",
  "vic.clause.preparation_costs": "Prohibited term: agreement preparation costs (s 27B(2))",
  "vic.clause.unreviewed_contract": "Prohibited term: binds renter to unreviewed contract (reg 11)",
  "vic.clause.renter_indemnity": "Prohibited term: renter indemnifies provider (reg 11)",
  "vic.clause.late_availability_claim_waiver": "Prohibited term: bars claim for late availability (reg 11)",
  "vic.clause.costly_payment_method": "Prohibited term: costly payment method (reg 11)",
  "vic.clause.third_party_services": "Prohibited term: nominated third-party services (reg 11)",
  "vic.clause.safety_maintenance_transfer": "Prohibited term: safety maintenance transferred (reg 11)",
  "vic.clause.tribunal_costs_transfer": "Prohibited term: Tribunal costs transferred (reg 11)",
  "vic.clause.insurance_excess_transfer": "Prohibited term: provider's insurance excess transferred (reg 11)",
  "vic.clause.fixed_break_fees": "Prohibited term: fixed break fees without basis (reg 11)",
```

3. Same status gating: compute `blocked` from
   `state.jurisdiction_status`, disable every "Run clause audit" button
   when blocked, and render the same missing/unsupported paragraph
   (with the property-edit link) at the top of the card.
4. `StatusChip` row gains an audited-as chip:
   `<Badge tone="neutral">{audit.jurisdiction}</Badge>` next to the
   status chip on each latest audit line.

- [ ] **Step 5: e2e extension**

Locate the env-gated e2e file (`grep -rln "E2E" backend/tests/`), read
its gating and fixtures, and add one VIC case following its existing
shape: create a property with `state="VIC"` and a lease, run the
deterministic audit against the real service, assert the stored row's
`jurisdiction == "VIC"`, every finding rule_id starts with `"vic."`,
and the state endpoint reports `jurisdiction_status == "ok"`,
`jurisdiction == "VIC"`. Add a second, non-gated (regular suite) case
asserting a property with no state yields `jurisdiction_status ==
"missing"` from the state endpoint - if Task 2's endpoint tests already
pin exactly that, skip this duplicate.

- [ ] **Step 6: Verify**

```bash
cd backend && uv run pytest
cd ../frontend && npm run lint && npm run build
```

Expected: suite green; lint and build clean.

- [ ] **Step 7: Ruff (backend), commit, push, CI** - "Jurisdiction-aware compliance UI and VIC e2e".

---

### Task 5: Rollout (interactive)

No repo changes except the ledger and memory. Run by the controller.

- [ ] **Step 1: Migrate the local app database**

```bash
cd /Users/keithho/LLMProjects/rental_management_app/backend && uv run alembic upgrade head
```

- [ ] **Step 2: Backfill - report first, then execute**

```bash
uv run python -m app.compliance_backfill --fix-jurisdictions
```

Review the dry-run report (counts, missing/unsupported lists, how many
clause resubmissions and their quota cost). Then:

```bash
uv run python -m app.compliance_backfill --fix-jurisdictions --execute
```

Drain runs on the app's scheduler; optionally trigger the drain job
manually per the repo's job runner to see the re-audits land.

- [ ] **Step 3: Live acceptance in the running app**

With backend and frontend running: set one real property's state to VIC
via the new dropdown -> its lease's compliance section reads "VIC
compliance" -> Check now -> findings show `vic.*` labels with the
"audited as VIC" badge; clause audit on its lease PDF returns
`vic.clause.*` findings. A property with no state shows the
set-the-state prompt with both trigger buttons disabled, and the link
lands on the property edit page.

- [ ] **Step 4: Ledger and memory**

Append completion to the service repo's
`.superpowers/sdd/progress.md` (this workflow's ledger) and update the
milestone memory: (d) done - the VIC milestone is complete.

---

## Self-review

- Spec coverage: mapper + supported-set constant + three reasons
  (Task 1); columns + NSW backfill via server_default (Task 1); both
  submit paths + 422s + drop-without-retry drain + judgment-free
  enqueue (Task 2); status fields computed live (Task 2);
  `--fix-jurisdictions` dry-run/execute with per-row report (Task 3);
  dropdown + legacy-value option, badges, three-state prompt cards,
  VIC labels for both sections (Task 4); e2e VIC case (Task 4);
  migration + backfill + live acceptance + ledger/memory (Task 5);
  skip_reason/capability carry-ins are decisions recorded in the spec,
  no code.
- Placeholders: endpoint-test snippets marked "adapt constructor
  details to the file's helpers" name the exact fixtures to mirror and
  pin the assertions - the repo's test files own their setup idioms;
  same for the clause schema class names (discoverable facts, with the
  file named).
- Type consistency: `jurisdiction_for` takes the state string
  everywhere; `resolve_jurisdiction(session, lease)` used in both
  services; reason literals `"ok"/"missing"/"unsupported"` identical in
  mapper, schemas, and frontend types; `chain_to_audit_payload(chain,
  jurisdiction)` matches all updated call sites.
