# AI Consent Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-feature, organization-level AI consent with a versioned
disclosure and a backend gate on every LLM path, existing organizations
defaulting to off.

**Architecture:** An append-only `ai_feature_consents` event table (newest
event wins, no rows = not consented) behind a small service module; a
`require_ai_consent` dependency gating the clause-audit submit endpoint
(the verified single LLM path); consent read/toggle endpoints; a frontend
settings page with the disclosure and toggles plus a prompt card where
the audit button used to appear. Spec:
`docs/superpowers/specs/2026-08-14-ai-consent-foundation-design.md`.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic (backend), Next.js
app router + Playwright (frontend), pytest.

## Global Constraints

- Repo: `/Users/keithho/LLMProjects/rental_management_app`. Backend
  commands run from `backend/`, frontend from `frontend/`.
- Feature enum values exactly: `clause_audit`, `rent_ai` (reserved,
  gate-able but no endpoint uses it yet).
- Consent state: newest event by the `seq` identity column (amended
  2026-08-14) per (organization, feature); **no rows means not
  consented**. Disabling never deletes data; completed audit results
  stay readable.
- Only the `landlord` role toggles consent; `property_manager` and
  `tenant` get 403 from the toggle endpoint. Reads are open to any
  member.
- Gate failure body exactly:
  `{"detail": {"code": "ai_consent_required", "feature": "clause_audit"}}`
  with status 403.
- `AI_DISCLOSURE_VERSION = "2026-08-14"` in `app/services/ai_consent.py`
  is the only source of the version string; every consent event records
  it.
- Deterministic compliance audits (`drain_audit_queue`,
  `poll_audit_changes`) and `poll_clause_audits` are untouched — the
  clause-audit submit endpoint is the only gated path.
- Disclosure copy must include all four points: what is sent (property
  attributes, rent figures, dates, lease document text), to whom
  (Anthropic, with an OpenAI backup, via our compliance service), what is
  never sent (tenant names, emails, phone numbers, co-tenant details),
  and "General information, not legal advice."
- No emojis. Follow sibling-file conventions in each directory.
- Backend suite: `uv run pytest -q` from `backend/`. Frontend e2e:
  per-repo convention (`npx playwright test e2e/<file>` from
  `frontend/`), run only the specs the task touches.
- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Consent model, migration, and service

**Files:**
- Create: `backend/app/models/ai_consent.py`
- Modify: `backend/app/models/__init__.py` (add imports + `__all__` entries)
- Create: `backend/alembic/versions/<generated>_add_ai_feature_consents.py`
- Create: `backend/app/services/ai_consent.py`
- Test: `backend/tests/test_ai_consent_service.py`

**Interfaces:**
- Produces: `AiFeature` (str enum: `clause_audit`, `rent_ai`),
  `AiFeatureConsent` model;
  `app.services.ai_consent.AI_DISCLOSURE_VERSION: str`;
  `async feature_enabled(session, organization_id, feature: AiFeature) -> bool`;
  `async current_states(session, organization_id) -> dict[AiFeature, bool]`;
  `async record_consent(session, organization_id, feature: AiFeature,
  enabled: bool, acted_by) -> AiFeatureConsent` (adds + flushes, does not
  commit — caller owns the transaction, matching the repo's service
  style).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_ai_consent_service.py`:

```python
from app.models import AiFeature
from app.services.ai_consent import (
    AI_DISCLOSURE_VERSION,
    current_states,
    feature_enabled,
    record_consent,
)
from tests.test_clause_audit_service import _org_and_user
from tests.test_properties_crud import landlord_headers


async def _org(client, db_session, email):
    await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    return org_id, user_id


async def test_no_rows_means_disabled(client, db_session):
    org_id, _ = await _org(client, db_session, "consent0@example.com")
    assert await feature_enabled(db_session, org_id, AiFeature.clause_audit) is False
    states = await current_states(db_session, org_id)
    assert states == {AiFeature.clause_audit: False, AiFeature.rent_ai: False}


async def test_newest_event_wins(client, db_session):
    org_id, user_id = await _org(client, db_session, "consent1@example.com")
    await record_consent(db_session, org_id, AiFeature.clause_audit, True, user_id)
    await db_session.commit()
    assert await feature_enabled(db_session, org_id, AiFeature.clause_audit) is True
    await record_consent(db_session, org_id, AiFeature.clause_audit, False, user_id)
    await db_session.commit()
    assert await feature_enabled(db_session, org_id, AiFeature.clause_audit) is False
    states = await current_states(db_session, org_id)
    assert states[AiFeature.clause_audit] is False


async def test_event_records_version_and_actor(client, db_session):
    org_id, user_id = await _org(client, db_session, "consent2@example.com")
    event = await record_consent(db_session, org_id, AiFeature.rent_ai, True, user_id)
    await db_session.commit()
    assert event.disclosure_version == AI_DISCLOSURE_VERSION
    assert event.acted_by == user_id
    assert event.enabled is True


async def test_features_are_independent(client, db_session):
    org_id, user_id = await _org(client, db_session, "consent3@example.com")
    await record_consent(db_session, org_id, AiFeature.clause_audit, True, user_id)
    await db_session.commit()
    assert await feature_enabled(db_session, org_id, AiFeature.rent_ai) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `uv run pytest tests/test_ai_consent_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'AiFeature'`.

- [ ] **Step 3: Implement model and registration**

Create `backend/app/models/ai_consent.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AiFeature(str, enum.Enum):
    clause_audit = "clause_audit"
    rent_ai = "rent_ai"


class AiFeatureConsent(Base):
    """Append-only consent events; the newest row per feature is the state."""

    __tablename__ = "ai_feature_consents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    feature: Mapped[AiFeature] = mapped_column(Enum(AiFeature))
    enabled: Mapped[bool] = mapped_column()
    disclosure_version: Mapped[str] = mapped_column(String(20))
    acted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

In `backend/app/models/__init__.py`: add
`from app.models.ai_consent import AiFeature, AiFeatureConsent` in
alphabetical import position and `"AiFeature", "AiFeatureConsent"` to
`__all__` in its sorted position.

- [ ] **Step 4: Implement the service**

Create `backend/app/services/ai_consent.py`:

```python
"""Organization-level AI feature consent: append-only events, newest wins."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiFeature, AiFeatureConsent

AI_DISCLOSURE_VERSION = "2026-08-14"


async def feature_enabled(
    session: AsyncSession, organization_id, feature: AiFeature
) -> bool:
    newest = (
        await session.execute(
            select(AiFeatureConsent.enabled)
            .where(
                AiFeatureConsent.organization_id == organization_id,
                AiFeatureConsent.feature == feature,
            )
            .order_by(AiFeatureConsent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return bool(newest)


async def current_states(session: AsyncSession, organization_id) -> dict[AiFeature, bool]:
    return {
        feature: await feature_enabled(session, organization_id, feature)
        for feature in AiFeature
    }


async def record_consent(
    session: AsyncSession,
    organization_id,
    feature: AiFeature,
    enabled: bool,
    acted_by,
) -> AiFeatureConsent:
    event = AiFeatureConsent(
        organization_id=organization_id,
        feature=feature,
        enabled=enabled,
        disclosure_version=AI_DISCLOSURE_VERSION,
        acted_by=acted_by,
    )
    session.add(event)
    await session.flush()
    return event
```

- [ ] **Step 5: Create the migration**

From `backend/`:

```bash
uv run alembic revision -m "add ai_feature_consents"
```

Fill the generated file (down_revision must be the current head —
verify with `uv run alembic heads`; it was `00cbeeefeadc` when this plan
was written):

```python
def upgrade() -> None:
    op.create_table(
        "ai_feature_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "feature",
            sa.Enum("clause_audit", "rent_ai", name="aifeature"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("disclosure_version", sa.String(length=20), nullable=False),
        sa.Column("acted_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["acted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_feature_consents_organization_id"),
        "ai_feature_consents",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ai_feature_consents_organization_id"),
        table_name="ai_feature_consents",
    )
    op.drop_table("ai_feature_consents")
    sa.Enum(name="aifeature").drop(op.get_bind(), checkfirst=True)
```

Match the sibling migrations' import header exactly. Apply it:
`uv run alembic upgrade head` (against the local dev DB).

- [ ] **Step 6: Run the new tests, then the full suite**

Run: `uv run pytest tests/test_ai_consent_service.py -v` — Expected: 4 PASS.
Run: `uv run pytest -q` — Expected: PASS (no regressions).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/ai_consent.py backend/app/models/__init__.py backend/app/services/ai_consent.py backend/alembic/versions backend/tests/test_ai_consent_service.py
git commit -m "Add organization AI consent events, service, and migration"
```

---

### Task 2: Consent endpoints and the clause-audit gate

**Files:**
- Create: `backend/app/schemas/ai_consent.py`
- Create: `backend/app/routers/ai_consents.py`
- Modify: `backend/app/core/deps.py` (append `require_ai_consent`)
- Modify: `backend/app/main.py` (register router — follow how
  `clause_audits` is registered)
- Modify: `backend/app/routers/clause_audits.py:47-52` (add gate
  dependency to `run_clause_audit`)
- Modify: `backend/tests/test_clause_audit_endpoints.py` (existing submit
  tests must enable consent first)
- Test: `backend/tests/test_ai_consent_endpoints.py`

**Interfaces:**
- Consumes: Task 1's service functions and `AiFeature`;
  `require_roles`, `get_current_membership` from `app/core/deps.py`.
- Produces: `GET /api/ai-consents` ->
  `{"features": {"clause_audit": bool, "rent_ai": bool},
  "disclosure_version": "2026-08-14"}`;
  `POST /api/ai-consents/{feature}` body `{"enabled": bool}` -> same
  shape as GET (state after the toggle);
  `app.core.deps.require_ai_consent(feature: AiFeature)` dependency
  factory; test helper
  `enable_clause_audit(db_session, org_id, user_id)` other tests import.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_ai_consent_endpoints.py`:

```python
from app.models import AiFeature
from app.services.ai_consent import AI_DISCLOSURE_VERSION, record_consent
from tests.test_clause_audit_service import _org_and_user
from tests.test_portal import onboard_tenant
from tests.test_properties_crud import landlord_headers


async def enable_clause_audit(db_session, org_id, user_id):
    """Test helper: consent an organization to clause audits."""
    await record_consent(db_session, org_id, AiFeature.clause_audit, True, user_id)
    await db_session.commit()


async def test_get_defaults_all_off(client, db_session):
    headers = await landlord_headers(client, "aic1@example.com")
    response = await client.get("/api/ai-consents", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["features"] == {"clause_audit": False, "rent_ai": False}
    assert body["disclosure_version"] == AI_DISCLOSURE_VERSION


async def test_landlord_toggles_feature(client, db_session):
    headers = await landlord_headers(client, "aic2@example.com")
    response = await client.post(
        "/api/ai-consents/clause_audit", json={"enabled": True}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["features"]["clause_audit"] is True

    response = await client.post(
        "/api/ai-consents/clause_audit", json={"enabled": False}, headers=headers
    )
    assert response.json()["features"]["clause_audit"] is False


async def test_non_landlord_cannot_toggle(client, db_session):
    headers = await landlord_headers(client, "aic3@example.com")
    tenant_headers = await onboard_tenant(client, db_session, headers, "aictenant@example.com")
    response = await client.post(
        "/api/ai-consents/clause_audit", json={"enabled": True}, headers=tenant_headers
    )
    assert response.status_code == 403


async def test_unknown_feature_is_422(client, db_session):
    headers = await landlord_headers(client, "aic4@example.com")
    response = await client.post(
        "/api/ai-consents/toaster", json={"enabled": True}, headers=headers
    )
    assert response.status_code == 422
```

Note for the implementer: `onboard_tenant`'s exact signature lives in
`tests/test_portal.py` — read it and adapt the call if it differs; the
point of the test is that a non-landlord token gets 403.

In `backend/tests/test_clause_audit_endpoints.py`: the submit tests will
start failing with 403 once the gate lands. In `_setup`, after
`org_id, user_id = await _org_and_user(db_session, email)`, add:

```python
    from tests.test_ai_consent_endpoints import enable_clause_audit

    await enable_clause_audit(db_session, org_id, user_id)
```

and add one new test proving the gate:

```python
async def test_post_without_consent_is_403(client, db_session, tmp_path, monkeypatch, compliance_on):
    headers, lease_id, document = await _setup(
        client, db_session, "clgate@example.com", "12 Gate St", tmp_path, monkeypatch,
        consent=False,
    )
    response = await client.post(
        f"/api/v1/leases/{lease_id}/documents/{document.id}/clause-audit", headers=headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "ai_consent_required",
        "feature": "clause_audit",
    }
```

(Give `_setup` a `consent: bool = True` keyword; skip the enable call
when False.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ai_consent_endpoints.py -v`
Expected: FAIL — 404s (router not registered) and the gate test fails
with 202 != 403.

- [ ] **Step 3: Implement schemas, router, gate**

Create `backend/app/schemas/ai_consent.py`:

```python
from pydantic import BaseModel


class AiConsentToggle(BaseModel):
    enabled: bool


class AiConsentState(BaseModel):
    features: dict[str, bool]
    disclosure_version: str
```

Create `backend/app/routers/ai_consents.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_membership, require_roles
from app.models import AiFeature, Membership, Role
from app.schemas.ai_consent import AiConsentState, AiConsentToggle
from app.services.ai_consent import AI_DISCLOSURE_VERSION, current_states, record_consent

router = APIRouter(prefix="/api", tags=["ai-consents"])

landlord_only = require_roles(Role.landlord)


async def _state(session: AsyncSession, organization_id) -> AiConsentState:
    states = await current_states(session, organization_id)
    return AiConsentState(
        features={feature.value: enabled for feature, enabled in states.items()},
        disclosure_version=AI_DISCLOSURE_VERSION,
    )


@router.get("/ai-consents", response_model=AiConsentState)
async def get_ai_consents(
    membership: Membership = Depends(get_current_membership),
    session: AsyncSession = Depends(get_session),
) -> AiConsentState:
    return await _state(session, membership.organization_id)


@router.post("/ai-consents/{feature}", response_model=AiConsentState)
async def set_ai_consent(
    feature: AiFeature,
    body: AiConsentToggle,
    membership: Membership = Depends(landlord_only),
    session: AsyncSession = Depends(get_session),
) -> AiConsentState:
    await record_consent(
        session, membership.organization_id, feature, body.enabled, membership.user_id
    )
    await session.commit()
    return await _state(session, membership.organization_id)
```

Append to `backend/app/core/deps.py`:

```python
def require_ai_consent(feature):
    """Dependency factory: 403 unless the organization enabled this AI feature."""

    async def checker(
        membership: Membership = Depends(get_current_membership),
        session: AsyncSession = Depends(get_session),
    ) -> Membership:
        from app.services.ai_consent import feature_enabled

        if not await feature_enabled(session, membership.organization_id, feature):
            raise HTTPException(
                status_code=403,
                detail={"code": "ai_consent_required", "feature": feature.value},
            )
        return membership

    return checker
```

(The function-local import mirrors avoiding a module cycle:
deps -> services -> models only; if no cycle exists, hoist the import to
the top — check and prefer the top-level import.)

In `backend/app/routers/clause_audits.py`: import `AiFeature` from
`app.models` and `require_ai_consent` from `app.core.deps`, then change
`run_clause_audit`'s membership dependency line from

```python
    membership: Membership = Depends(manager),
```

to

```python
    membership: Membership = Depends(manager),
    _consent: Membership = Depends(require_ai_consent(AiFeature.clause_audit)),
```

Register the router in `backend/app/main.py` exactly the way
`clause_audits` is registered (import + `app.include_router`).

- [ ] **Step 4: Run the new tests, gate test, then the full suite**

Run: `uv run pytest tests/test_ai_consent_endpoints.py tests/test_clause_audit_endpoints.py -v`
Expected: PASS (including the new 403 test and the consent-enabled
existing tests).
Run: `uv run pytest -q` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/ai_consent.py backend/app/routers/ai_consents.py backend/app/core/deps.py backend/app/main.py backend/app/routers/clause_audits.py backend/tests/test_ai_consent_endpoints.py backend/tests/test_clause_audit_endpoints.py
git commit -m "Gate clause audits behind organization AI consent"
```

---

### Task 3: Settings page, prompt card, e2e

**Files:**
- Create: `frontend/src/lib/aiConsent.ts`
- Create: `frontend/src/content/aiDisclosure.tsx`
- Create: `frontend/src/app/app/settings/ai/page.tsx`
- Modify: `frontend/src/components/app-shell.tsx` (nav entry "AI
  settings" -> `/app/settings/ai`, following the existing nav-item
  pattern)
- Modify: the clause-audit UI section component
  (`frontend/src/app/app/leases/ClauseAuditSection.tsx`) — consent-aware
  prompt card
- Test: `frontend/e2e/ai-consent.spec.ts`; Modify:
  `frontend/e2e/clause-audit.spec.ts` (enable consent before auditing)

**Interfaces:**
- Consumes: `GET /api/ai-consents`, `POST /api/ai-consents/{feature}`
  (Task 2 shapes); the repo's existing fetch-client conventions in
  `frontend/src/lib/clauseAudit.ts` (copy its auth/header helper usage
  exactly).
- Produces: `getAiConsents(): Promise<AiConsentState>`,
  `setAiConsent(feature: string, enabled: boolean): Promise<AiConsentState>`
  with `type AiConsentState = { features: Record<string, boolean>;
  disclosure_version: string }`.

- [ ] **Step 1: Write the e2e (failing)**

Create `frontend/e2e/ai-consent.spec.ts`, following the setup/login
helpers used by `frontend/e2e/clause-audit.spec.ts` (read it first and
reuse its login fixture/pattern):

There is no shared login helper module: `clause-audit.spec.ts` signs up
inline (`page.goto("/signup")`, placeholders "Your name" /
"Organization name" / "Email" / "Password (min 8 chars)", button
"Sign up", then `page.getByTestId("welcome")`). Reuse that exact inline
pattern with a fresh `ai-consent-${Date.now()}@example.com` email:

```typescript
import { expect, test } from "@playwright/test";

async function signupLandlord(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Consent Owner");
  await page.getByPlaceholder("Organization name").fill("Consent Org");
  await page.getByPlaceholder("Email").fill(`ai-consent-${Date.now()}@example.com`);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();
}

test("landlord enables clause audit from the AI settings page", async ({ page }) => {
  await signupLandlord(page);
  await page.goto("/app/settings/ai");
  await expect(page.getByText("AI features disclosure")).toBeVisible();
  await expect(page.getByText("never sent")).toBeVisible();

  const toggle = page.getByRole("switch", { name: /clause audit/i });
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(toggle).toBeChecked();
});

test("unconsented lease page shows the enable prompt instead of the audit button", async ({ page }) => {
  // log in, create a lease with a document via existing helpers,
  // do NOT enable consent
  await expect(page.getByText(/AI features are disabled/)).toBeVisible();
  await expect(page.getByRole("link", { name: /settings/i })).toBeVisible();
});
```

The comment lines are instructions to the implementer: fill them with
the same helper calls `clause-audit.spec.ts` uses (read that file; do
not invent new helpers). The assertions shown are the contract.

- [ ] **Step 2: Run it to verify it fails**

Run (from `frontend/`): `npx playwright test e2e/ai-consent.spec.ts`
Expected: FAIL — `/app/settings/ai` 404s.

- [ ] **Step 3: Implement client, content, page, card**

Create `frontend/src/lib/aiConsent.ts` (mirror the fetch/auth pattern of
`frontend/src/lib/clauseAudit.ts` exactly — same base-URL and header
helpers):

```typescript
import { apiFetch } from "./api";

export type AiConsentState = {
  features: Record<string, boolean>;
  disclosure_version: string;
};

export async function getAiConsents(): Promise<AiConsentState> {
  return apiFetch("/api/ai-consents");
}

export async function setAiConsent(
  feature: string,
  enabled: boolean,
): Promise<AiConsentState> {
  return apiFetch(`/api/ai-consents/${feature}`, {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}
```

(If `lib/api.ts` exposes a differently named helper, use that — match
`clauseAudit.ts`.)

Create `frontend/src/content/aiDisclosure.tsx` — a component exporting
the disclosure copy with the four mandatory points as separate headed
sections: "What we send" (property attributes such as address, type,
bedrooms; rent figures and dates; lease document text you submit for
audit), "Who processes it" (Anthropic, with an OpenAI backup, via our
compliance service), "What we never send" (tenant names, emails, phone
numbers, co-tenant details), "About the results" (general information,
not legal advice). Title the page section "AI features disclosure".

Create `frontend/src/app/app/settings/ai/page.tsx`: client component
that loads `getAiConsents()`, renders the disclosure, the version
(`Disclosure version: {disclosure_version}`), and one labelled switch
per feature (`Clause audit`, `Rent AI (coming soon)` — the rent_ai
toggle renders but is the reserved feature). Landlord sees interactive
switches wired to `setAiConsent`; other roles see the switches disabled
(the role comes from the same session/me source the app-shell already
uses — reuse it). Follow the styling of an existing settings-like page
(`app/app/profile/page.tsx`) for layout classes.

Nav: add an "AI settings" item pointing at `/app/settings/ai` in
`frontend/src/components/app-shell.tsx`, following the existing nav-item
array/pattern.

Prompt card: in `ClauseAuditSection.tsx`, load `getAiConsents()`
alongside the existing state; when `features.clause_audit` is false,
render (in place of the submit control):

```tsx
<div data-testid="ai-consent-card">
  <p>AI features are disabled. A landlord can enable them in Settings.</p>
  <Link href="/app/settings/ai">Open AI settings</Link>
</div>
```

styled like the existing jurisdiction prompt cards in the same file.
Keep results of past audits rendered regardless of consent.

- [ ] **Step 4: Update the clause-audit e2e**

`frontend/e2e/clause-audit.spec.ts` submits audits; with consent
defaulting off it will now hit the prompt card. After its login/setup
and before the audit interaction, navigate to `/app/settings/ai` and
click the clause-audit switch on (same actions as the new spec's first
test), then continue the existing flow.

- [ ] **Step 5: Run the e2e specs**

Run: `npx playwright test e2e/ai-consent.spec.ts e2e/clause-audit.spec.ts`
Expected: PASS (clause-audit spec notes in the repo may mark live parts
skipped/deferred — leave that convention as is; the consent-gated UI
parts must pass).

- [ ] **Step 6: Run the backend suite once more (unchanged) and commit**

Run (from `backend/`): `uv run pytest -q` — Expected: PASS.

```bash
git add frontend/src/lib/aiConsent.ts frontend/src/content/aiDisclosure.tsx frontend/src/app/app/settings/ai frontend/src/components/app-shell.tsx frontend/src/app/app/leases/ClauseAuditSection.tsx frontend/e2e/ai-consent.spec.ts frontend/e2e/clause-audit.spec.ts
git commit -m "Add the AI settings page, disclosure, and consent-gated audit UI"
```
