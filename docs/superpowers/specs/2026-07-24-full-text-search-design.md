# Full-text Search Design

**Date:** 2026-07-24
**Milestone:** Phase 2 — Full-text search (sub-project 2 of the remaining three)

## Goal

A management-side search that finds properties, leases/tenants, maintenance
requests, and documents by a substring of their text, from a search box in the
app header, showing grouped results on a dedicated page.

## Decisions (from brainstorming)

- **Scope — four groups:** properties, leases/tenants, maintenance, documents.
- **Matching:** case-insensitive substring (`ILIKE '%q%'`), mirroring the
  existing property list search. No word/stem ranking.
- **UI:** a search box in the `AppShell` header; pressing Enter navigates to
  `/app/search?q=<term>` which renders grouped results. The page has its own box
  to refine.
- **Audience:** management side only (the box lives in `AppShell`; tenants use
  `PortalShell`). The endpoint requires a manager and is org-scoped.
- **Cap:** at most 10 hits per group (truncated silently).
- **Not searched:** co-tenants (a JSON array) — only the lease's main
  `tenant_name` / `tenant_email`.

## No new model or migration

Search is a read-only query over existing tables. Nothing is stored.

## Backend

One endpoint, org-scoped, manager only (`require_roles(landlord,
property_manager)`).

`GET /api/v1/search?q=<term>` -> `SearchResults`

```
SearchHit:
  title:    str
  subtitle: str | None
  link:     str

SearchResults:
  properties:  list[SearchHit]
  leases:      list[SearchHit]
  maintenance: list[SearchHit]
  documents:   list[SearchHit]
```

`q` is stripped; if empty, every group is `[]` (no query runs). Otherwise
`term = f"%{q}%"` and each group runs one `ILIKE` query, org-scoped, `LIMIT 10`:

| group | table / filter | title / subtitle / link |
|---|---|---|
| properties | `Property` where `address ILIKE term OR description ILIKE term` | `address` / `type` value / `/app/properties/{id}` |
| leases | `Lease` join `Property` where `tenant_name ILIKE term OR tenant_email ILIKE term` | `tenant_name` / property `address` / `/app/leases/{id}` |
| maintenance | `MaintenanceRequest` where `title ILIKE term OR description ILIKE term` | `title` / `status` value / `/app/maintenance` |
| documents | `Document` where `title ILIKE term` | `title` / `category` value / `/app/leases/{lease_id}` |

(A `%` or `_` typed in `q` acts as an ILIKE wildcard; acceptable for v1 and
consistent with the existing property search, which does not escape either.)

## Frontend

- **Header box** (`AppShell`): a small `<form>` with a text `<input>` (aria-label
  "Search"); on submit, `router.push('/app/search?q=' + encodeURIComponent(value))`.
  Rendered only in the manager shell.
- **`/app/search` page** (`"use client"`): reads `q` from the URL
  (`useSearchParams`, wrapped in the Suspense boundary Next requires), shows an
  input prefilled with `q` that re-submits to the same route, calls `search(q)`,
  and renders the four groups. Each hit is a link (`title` bold + `subtitle`
  muted) to its `link`. A group with no hits is omitted; if every group is empty
  and `q` is non-empty, show "No results". With no `q`, prompt to type a term.
- New files: `frontend/src/lib/search.ts` (client + types),
  `frontend/src/app/app/search/page.tsx`. Header box added to
  `frontend/src/components/app-shell.tsx`.

## Testing

**Backend** (`backend/tests/test_search.py`):
- Seed a property, a lease, a maintenance request, and a document whose text all
  share a term; search it; assert one hit in each group with the right `link`.
- Case-insensitive: a lower-case query finds a mixed-case record.
- Org scope: a second org's records never appear.
- Empty `q` -> all groups empty, no error.
- A term matching nothing -> all groups empty.

**e2e** (`frontend/e2e/search.spec.ts`):
- Manager signs up, creates a property (distinctive address).
- Types the address fragment in the header search box, submits.
- Lands on `/app/search`, sees the property under Properties, clicks it, arrives
  at the property page.

## Out of scope (this milestone)

- Tenant-side search.
- Co-tenants (JSON) matching.
- Relevance ranking / highlighting.
- Per-result detail pages that do not exist (maintenance links to the list;
  documents link to their lease).
- Debounced live dropdown (submit-to-page only).

## Task breakdown (for the plan)

- **T1** — `SearchHit` / `SearchResults` schemas + `GET /api/v1/search` endpoint
  (four ILIKE groups, org scope, cap 10, empty-q short-circuit); mount router;
  tests.
- **T2** — Frontend `search.ts` client + `/app/search` results page + the
  header search box in `AppShell`; lint/build.
- **T3** — e2e `search.spec.ts` + full suite + CI green.

Each task ends with: full test run -> ruff sequence (from `backend/`) -> commit
-> push to `https://github.com/Keith-hoka/rental_management` -> report -> wait.
