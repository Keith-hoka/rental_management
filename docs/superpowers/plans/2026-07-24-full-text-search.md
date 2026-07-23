# Full-text Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A header search box for managers that finds properties, leases/tenants, maintenance requests, and documents by case-insensitive substring, showing grouped results at `/app/search?q=`.

**Architecture:** One read-only endpoint `GET /api/v1/search` running four org-scoped ILIKE queries (cap 10 each) into a grouped `SearchResults` payload. No new table, no migration. The frontend adds a header form in `AppShell` and a results page that reads `q` from the URL.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Next.js 16, Playwright. No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- No new model or migration — search is a read-only query.
- Management side only: the endpoint requires `require_roles(landlord, property_manager)`; the box renders in `AppShell` (tenants use `PortalShell`).
- Matching is `ILIKE '%q%'` exactly like the existing property list search; `%`/`_` in `q` act as wildcards (accepted for v1, do not escape).
- `useSearchParams` requires a Suspense boundary — mirror `src/app/accept-invite/page.tsx` (inner component reads params; default export wraps it in `<Suspense>`).
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- Backend commands run from `backend/`, frontend from `frontend/`; always `cd` explicitly.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/schemas/search.py` | `SearchHit`, `SearchResults` |
| `backend/app/routers/search.py` | the endpoint |
| `backend/app/main.py` | mount the router |
| `backend/tests/test_search.py` | the whole feature |
| `frontend/src/lib/search.ts` | client + types |
| `frontend/src/app/app/search/page.tsx` | results page |
| `frontend/src/components/app-shell.tsx` | header search box |
| `frontend/e2e/search.spec.ts` | end-to-end |

---

### Task 1: Search endpoint

**Files:**
- Create: `backend/app/schemas/search.py`
- Create: `backend/app/routers/search.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_search.py`

**Interfaces:**
- Consumes: `Property`, `Lease`, `MaintenanceRequest`, `Document`; `manager` dep from `app.routers.leases`.
- Produces: `GET /api/v1/search?q=` -> `SearchResults{properties, leases, maintenance, documents: list[SearchHit{title, subtitle, link}]}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_search.py`:

```python
import uuid
from datetime import date, timedelta

from app.models import MaintenanceRequest
from tests.test_calendar import _org_and_user
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _seed(client, db_session, email, marker):
    """A property, lease, maintenance request and document all containing marker."""
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    property_id = await make_property(client, headers, f"1 {marker} St")
    today = date.today()
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                tenant_name=f"Tina {marker}",
                tenant_email=f"tina-{marker.lower()}@example.com",
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=30)),
            ),
            headers=headers,
        )
    ).json()["id"]
    db_session.add(
        MaintenanceRequest(
            organization_id=org_id,
            property_id=uuid.UUID(property_id),
            lease_id=uuid.UUID(lease_id),
            created_by=user_id,
            title=f"Fix {marker} tap",
            description="Kitchen",
        )
    )
    await db_session.commit()
    return headers, property_id, lease_id


async def test_search_finds_all_groups(client, db_session, tmp_path, monkeypatch):
    headers, property_id, lease_id = await _seed(client, db_session, "srchall@example.com", "Zebra")
    from app.core.config import settings

    monkeypatch.setattr(settings, "documents_dir", str(tmp_path))
    await client.post(
        f"/api/v1/leases/{lease_id}/documents",
        data={"title": "Zebra lease scan", "category": "lease"},
        files={"file": ("z.pdf", b"%PDF-1.4 z", "application/pdf")},
        headers=headers,
    )

    body = (await client.get("/api/v1/search?q=zebra", headers=headers)).json()

    assert [h["link"] for h in body["properties"]] == [f"/app/properties/{property_id}"]
    assert [h["link"] for h in body["leases"]] == [f"/app/leases/{lease_id}"]
    assert body["maintenance"][0]["title"] == "Fix Zebra tap"
    assert body["documents"][0]["link"] == f"/app/leases/{lease_id}"


async def test_search_is_org_scoped(client, db_session):
    await _seed(client, db_session, "srchowner@example.com", "Quokka")
    stranger = await landlord_headers(client, "srchthief@example.com")
    body = (await client.get("/api/v1/search?q=quokka", headers=stranger)).json()
    assert body == {"properties": [], "leases": [], "maintenance": [], "documents": []}


async def test_search_empty_query_returns_nothing(client):
    headers = await landlord_headers(client, "srchempty@example.com")
    body = (await client.get("/api/v1/search?q=", headers=headers)).json()
    assert body == {"properties": [], "leases": [], "maintenance": [], "documents": []}


async def test_search_no_match(client, db_session):
    headers, _, _ = await _seed(client, db_session, "srchnone@example.com", "Walrus")
    body = (await client.get("/api/v1/search?q=xyzzy", headers=headers)).json()
    assert body == {"properties": [], "leases": [], "maintenance": [], "documents": []}
```

(The lower-case `q=zebra` finding the mixed-case "Zebra" records is the case-insensitivity check.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_search.py -q`
Expected: FAIL — 404 for `/api/v1/search` (router missing).

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/search.py`:

```python
from pydantic import BaseModel


class SearchHit(BaseModel):
    title: str
    subtitle: str | None = None
    link: str


class SearchResults(BaseModel):
    properties: list[SearchHit]
    leases: list[SearchHit]
    maintenance: list[SearchHit]
    documents: list[SearchHit]
```

- [ ] **Step 4: Write the endpoint**

Create `backend/app/routers/search.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Document, Lease, MaintenanceRequest, Membership, Property
from app.routers.leases import manager
from app.schemas.search import SearchHit, SearchResults

router = APIRouter(prefix="/api/v1", tags=["search"])

LIMIT = 10


@router.get("/search", response_model=SearchResults)
async def search(
    q: str = "",
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> SearchResults:
    """Substring search across the org's properties, leases, maintenance and documents."""
    q = q.strip()
    empty = SearchResults(properties=[], leases=[], maintenance=[], documents=[])
    if not q:
        return empty
    term = f"%{q}%"
    org = membership.organization_id

    properties = (
        (
            await session.execute(
                select(Property)
                .where(
                    Property.organization_id == org,
                    or_(Property.address.ilike(term), Property.description.ilike(term)),
                )
                .limit(LIMIT)
            )
        )
        .scalars()
        .all()
    )
    leases = (
        await session.execute(
            select(Lease, Property.address)
            .join(Property, Property.id == Lease.property_id)
            .where(
                Lease.organization_id == org,
                or_(Lease.tenant_name.ilike(term), Lease.tenant_email.ilike(term)),
            )
            .limit(LIMIT)
        )
    ).all()
    requests = (
        (
            await session.execute(
                select(MaintenanceRequest)
                .where(
                    MaintenanceRequest.organization_id == org,
                    or_(
                        MaintenanceRequest.title.ilike(term),
                        MaintenanceRequest.description.ilike(term),
                    ),
                )
                .limit(LIMIT)
            )
        )
        .scalars()
        .all()
    )
    documents = (
        (
            await session.execute(
                select(Document)
                .where(Document.organization_id == org, Document.title.ilike(term))
                .limit(LIMIT)
            )
        )
        .scalars()
        .all()
    )

    return SearchResults(
        properties=[
            SearchHit(title=p.address, subtitle=p.type.value, link=f"/app/properties/{p.id}")
            for p in properties
        ],
        leases=[
            SearchHit(title=lease.tenant_name, subtitle=address, link=f"/app/leases/{lease.id}")
            for lease, address in leases
        ],
        maintenance=[
            SearchHit(title=r.title, subtitle=r.status.value, link="/app/maintenance")
            for r in requests
        ],
        documents=[
            SearchHit(title=d.title, subtitle=d.category.value, link=f"/app/leases/{d.lease_id}")
            for d in documents
        ],
    )
```

Mount in `backend/app/main.py`: `from app.routers.search import router as search_router` and `app.include_router(search_router)` alongside the others.

- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_search.py -q` -> PASS.

- [ ] **Step 6: Full test run, ruff, commit, push**

```bash
cd backend && uv run pytest
uv run ruff format . && uv run ruff check --fix . && uv run ruff check . && uv run ruff format --check .
cd .. && git add backend/app/schemas/search.py backend/app/routers/search.py backend/app/main.py backend/tests/test_search.py
git commit -m "Add the search endpoint"
git push origin main
```
Then report and wait for approval.

---

### Task 2: Frontend client, results page, header box

**Files:**
- Create: `frontend/src/lib/search.ts`
- Create: `frontend/src/app/app/search/page.tsx`
- Modify: `frontend/src/components/app-shell.tsx`

**Interfaces:**
- Consumes: `apiFetch`; `AppShell`, `useShell`, `Card`, `PageHeader`, `Input`, `EmptyState`; the Suspense pattern from `src/app/accept-invite/page.tsx`.
- Produces: `search(q)`; the `/app/search` route; an `aria-label="Search"` input in the header.

- [ ] **Step 1: Add the client**

Create `frontend/src/lib/search.ts`:

```ts
import { apiFetch } from "@/lib/api";

export interface SearchHit {
  title: string;
  subtitle: string | null;
  link: string;
}

export interface SearchResults {
  properties: SearchHit[];
  leases: SearchHit[];
  maintenance: SearchHit[];
  documents: SearchHit[];
}

export function search(q: string) {
  return apiFetch<SearchResults>(`/api/v1/search?q=${encodeURIComponent(q)}`);
}
```

- [ ] **Step 2: Add the header search box**

In `frontend/src/components/app-shell.tsx`, inside the `<header>`, before the `ml-auto` right-side div, add a small form (needs `useRouter` — the file is already a client component):

```tsx
          <form
            className="hidden md:block"
            onSubmit={(e) => {
              e.preventDefault();
              const value = query.trim();
              if (value) router.push(`/app/search?q=${encodeURIComponent(value)}`);
            }}
          >
            <input
              type="search"
              aria-label="Search"
              placeholder="Search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-56 rounded-lg border border-strong bg-surface px-3 py-1.5 text-sm text-text placeholder:text-muted"
            />
          </form>
```

with `const router = useRouter();` and `const [query, setQuery] = useState("");` added to the component (import `useRouter` from `next/navigation`, `useState` from `react`). Keep it `hidden md:block` so the narrow header is unchanged.

- [ ] **Step 3: Add the results page**

Create `frontend/src/app/app/search/page.tsx`, mirroring the accept-invite Suspense split:

```tsx
"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { search, type SearchHit, type SearchResults } from "@/lib/search";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Card, EmptyState, Input, PageHeader } from "@/components/ui";

const GROUPS: { key: keyof SearchResults; label: string }[] = [
  { key: "properties", label: "Properties" },
  { key: "leases", label: "Leases" },
  { key: "maintenance", label: "Maintenance" },
  { key: "documents", label: "Documents" },
];

function HitList({ hits }: { hits: SearchHit[] }) {
  return (
    <ul className="space-y-1">
      {hits.map((h, i) => (
        <li key={i}>
          <Link href={h.link} className="block rounded-lg p-2 hover:bg-surface-2">
            <span className="font-medium text-text">{h.title}</span>
            {h.subtitle && <span className="ml-2 text-sm text-muted">{h.subtitle}</span>}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function SearchResultsView() {
  const { me, unread, logOut } = useShell();
  const router = useRouter();
  const q = useSearchParams().get("q") ?? "";
  const [term, setTerm] = useState(q);
  const [results, setResults] = useState<SearchResults | null>(null);

  useEffect(() => {
    setTerm(q);
    if (!me || !q) {
      setResults(null);
      return;
    }
    let active = true;
    search(q)
      .then((r) => active && setResults(r))
      .catch(() => active && setResults(null));
    return () => {
      active = false;
    };
  }, [me, q]);

  if (!me) return null;

  const total = results ? GROUPS.reduce((n, g) => n + results[g.key].length, 0) : 0;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <PageHeader title="Search" />
      <form
        className="mb-5"
        onSubmit={(e) => {
          e.preventDefault();
          const value = term.trim();
          if (value) router.push(`/app/search?q=${encodeURIComponent(value)}`);
        }}
      >
        <Input
          type="search"
          aria-label="Search term"
          placeholder="Search properties, tenants, maintenance, documents"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        />
      </form>
      {!q ? (
        <EmptyState>Type a search term above.</EmptyState>
      ) : results === null || total === 0 ? (
        <EmptyState>No results.</EmptyState>
      ) : (
        <div className="space-y-5">
          {GROUPS.filter((g) => results[g.key].length > 0).map((g) => (
            <Card key={g.key} title={g.label}>
              <HitList hits={results[g.key]} />
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchResultsView />
    </Suspense>
  );
}
```

- [ ] **Step 4: Lint and build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both clean; `/app/search` appears in the route list.

- [ ] **Step 5: Commit and push** (`Add the search page and header box`). Report and wait.

---

### Task 3: End-to-end + CI

**Files:**
- Create: `frontend/e2e/search.spec.ts`

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/search.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const landlord = `search-${Date.now()}@example.com`;

test("a manager searches from the header and opens a property hit", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Search Owner");
  await page.getByPlaceholder("Organization name").fill("Search Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("42 Xanadu Lane");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  // Search from the header box.
  await page.getByLabel("Search", { exact: true }).fill("xanadu");
  await page.getByLabel("Search", { exact: true }).press("Enter");
  await expect(page).toHaveURL(/\/app\/search\?q=xanadu$/);

  // The property appears under Properties; clicking it opens the detail page.
  await expect(page.getByRole("heading", { name: "Properties" })).toBeVisible();
  await page.getByRole("link", { name: /42 Xanadu Lane/ }).click();
  await expect(page).toHaveURL(/\/app\/properties\/[0-9a-f-]+$/);
});
```

(`getByLabel("Search", { exact: true })` avoids the page input labelled "Search term" — Playwright matches by substring otherwise.)

- [ ] **Step 2: Run the new spec** — `cd frontend && npx playwright test search` -> 1 passed.
- [ ] **Step 3: Run the whole e2e suite** — `npx playwright test --workers=1` -> all pass.
- [ ] **Step 4: Full backend run + ruff** (from `backend/`).
- [ ] **Step 5: Commit and push** (`Add search e2e`).
- [ ] **Step 6: Confirm CI green** — `gh run list --limit 3`; read logs on failure before changing anything. Report and wait.
