# Clause Audit Tail Design

Send stored lease PDFs to the compliance service's clause-audit API, track
the async jobs, and render clause findings (red/green/yellow with quotes
and citations) plus field discrepancies on the lease page. The service side
shipped already (`POST /v1/clause-audits`, multipart, per-tenant in-flight
cap 10); this milestone is SaaS-only — no service changes.

## Decisions (brainstorm outcomes)

- **Button-only trigger.** Each audit costs about US$0.5-1; no automatic
  runs on upload, no backfill. One "Run clause audit" button per
  lease-category document; it audits that document's latest version.
- **Field cross-check on.** The submit payload carries the lease's
  money/date fields so the service also reports document-vs-form
  discrepancies.
- **Two-layer result polling.** A scheduler job polls in-flight jobs every
  minute (results survive closed pages, notifications possible); the lease
  page additionally refetches every 10 s while an audit is in flight.
- **Always notify on completion** — in-app notification plus email to the
  organization's managers, success and failure alike, with a one-line
  summary and a link to the lease.
- **Mirror the existing compliance integration**: a new
  `lease_clause_audits` table and a new `services/clause_audit.py` module;
  results persist in the SaaS, history is kept per document.

## Data model

Table `lease_clause_audits` (one row per button press; history never
overwritten):

```
id (uuid PK), organization_id (indexed),
lease_id (FK leases CASCADE, indexed),
document_id (FK documents CASCADE),
document_version_id (FK document_versions CASCADE),
job_id (String(36), unique — the service job UUID),
status: pending|running|succeeded|failed,
findings (JSON), discrepancies (JSON),
model (String(50)), engine_version (String(20)), error (Text, nullable),
created_at, completed_at (nullable)
```

All lease-side FKs carry `ondelete="CASCADE"`.

## Service client (`backend/app/services/clause_audit.py`)

New module in the `services/compliance.py` style (httpx, `X-API-Key`,
same base URL and key settings):

- `create_clause_audit(filename, content, content_type, payload) -> dict`
  — multipart POST `{url}/v1/clause-audits` with `files={"file": ...}` and
  `data={"payload": json.dumps(payload)}`; timeout 30 s (file upload).
- `get_clause_audit(job_id) -> dict` — GET `{url}/v1/clause-audits/{id}`.
- `lease_fields(lease) -> dict` — the cross-check subset: `rent_amount`,
  `rent_frequency`, `start_date`, `end_date`, `bond_amount`,
  `rent_in_advance_amount`, `holding_deposit_amount`,
  `other_security_amount`, `break_fee_amount`; `None` fields omitted,
  amounts as strings, dates ISO.
- `submit_document_audit(session, lease, document) -> LeaseClauseAudit` —
  loads the document's latest version (max `version_number`), reads the
  file from the uploads directory, POSTs with
  `{"jurisdiction": "NSW", "client_ref": str(lease.id), "lease": lease_fields(lease)}`,
  inserts the row with the returned `job_id` and status.
- `poll_clause_audits(session) -> int` — selects in-flight rows
  (`pending`/`running`), GETs each job, writes terminal results
  (findings, discrepancies, error, `completed_at`) and notifies; failures
  on one row are logged and skipped, never blocking the others (no
  cursor — row state is the state). Returns the number updated.

The service's 429 (tenant in-flight cap) propagates to the caller.

## Endpoints

`POST /api/v1/leases/{lease_id}/documents/{document_id}/clause-audit`
(manager-only, 202, returns the new row):

- compliance disabled -> 503; document not on that lease -> 404; document
  category is not `lease` -> 422; latest version's `content_type` is not
  `application/pdf` -> 422; that document already has an in-flight audit
  -> 409 (double-click guard); service unreachable -> 502
  (`httpx.HTTPError`); service 429 passes through as 429.

`GET /api/v1/leases/{lease_id}/clause-audits` (manager-only) — returns
`{enabled, audits}` mirroring `ComplianceAuditState`; `audits` newest
first, limit 20. The frontend polls this endpoint.

## Scheduler and notifications

- `_clause_poll_job` on an `IntervalTrigger`, new setting
  `clause_poll_interval_minutes` (default 1), registered under
  `compliance_enabled()` alongside the existing compliance jobs. With no
  in-flight rows it costs one SELECT.
- On each job reaching a terminal state: in-app notification via
  `notify_users` to the organization's managers plus email via the
  existing safe-send path. Success summary counts red, yellow and
  discrepancies ("Clause audit finished: 2 red, 1 yellow, 1 field
  mismatch" / "all green"); failure says "Clause audit failed". Both link
  to the lease page.

## Frontend

`ClauseAuditSection` on the lease detail page, below `ComplianceSection`;
hidden entirely when `enabled` is false.

- Lists the lease's `lease`-category documents. Per document: title, "Run
  clause audit" button, latest-audit status chip (Queued / Running
  animated / Failed with error / completed timestamp). Non-PDF latest
  version disables the button with a hint.
- Result panel for each document's latest succeeded audit:
  - Findings ordered red, yellow, green, skipped. Red and yellow render
    expanded: rule label, reasoning, the `clause_quote` as a blockquote,
    and a citation line ("Residential Tenancies Act 2010, s 19 — as at
    2026-07-28"). Green renders as a compact list; skipped reuses the
    existing explanation treatment.
  - `RULE_LABELS` gains the 15 clause rules (8 prohibited + 1 historical
    Regulation contractor rule + 6 mandatory) with English labels, e.g.
    "Prohibited term: professional carpet cleaning (s 19)" and "Required
    term missing: quiet enjoyment (s 50)".
  - Discrepancies as a table: Field | Document says | Form says.
  - Older audits collapse to compact history rows (date + red/yellow
    counts).
- While any listed audit is in flight the section refetches every 10 s;
  polling stops when none are and cleans up on unmount.
- Footer line: "General information, not legal advice."
- Submit errors (409/429/502) show as an inline message under the button;
  a failed audit re-enables the button for retry.

## Testing

Backend (fake httpx per the existing conftest pattern; no real service):

- `lease_fields` subset and `None` omission.
- Submit: multipart body and payload captured and asserted; picks the
  latest version; row created with `job_id`.
- Poll: succeeded job writes findings and notifies (notification row and
  email record asserted); one row's failure does not block others.
- Endpoints: 403 non-manager, 503 disabled, 404 foreign document, 422
  category and content-type, 409 duplicate in-flight, 429 pass-through,
  202 happy path, list shape `{enabled, audits}` and tenant scoping.
- Migration applies.

Frontend e2e: separate env flag `CLAUSE_AUDIT_E2E` (real model, ~US$1 and
1-3 minutes per run — manual only, never regular CI): upload a fixture
PDF, click the button, assert the Queued chip appears. Completion
rendering is covered by backend-fake tests and component-level assertions.

## Out of scope

Automatic triggers and backfill, auditing non-PDF documents, service-side
changes of any kind, re-running clause audits on legislation change
(re-submit is manual), tenant-portal visibility (manager-only for now).
