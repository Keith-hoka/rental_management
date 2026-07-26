# Compliance Integration Design

Make this app the first client of `lease-compliance-service`
(`~/LLMProjects/lease-compliance-service`): audit leases against NSW
tenancy law, show findings on the lease detail page, enrol every audited
lease in the service's change monitor, and turn detected changes into
in-app + email notifications. Findings are general information, not legal
advice — every surface that shows them carries that disclaimer.

## Decisions (brainstorm outcomes)

- **Scope: full package.** On-demand audits, automatic audits on lease
  create/renew, a one-off backfill for existing leases, and a daily poll
  of the service's `audit-changes` feed into notifications.
- **Delivery: queue table (outbox), not fire-and-forget.** Create/renew
  enqueue a row in the same transaction as the lease write; a scheduler
  job drains the queue with retries. Audits are never silently lost when
  the compliance service is down. The manual button stays synchronous —
  the user wants an immediate result.
- **Persistence: both sides.** This app stores results in `lease_audits`
  (instant display, in-app history, poll updates land there). The
  compliance service also gains `GET /v1/audits?client_ref=` so any
  public client can list audit history without local storage.
- **`client_ref` = lease UUID.** The service's tenant is this app as a
  whole (one API key); organizations stay internal to this app.

## Architecture

Three flows, all through `app/services/compliance.py` (the only module
that talks HTTP to the service):

1. **Manual**: lease detail button -> `POST /leases/{id}/compliance-audit`
   -> synchronous service call -> store `lease_audits` row -> return it.
2. **Automatic**: create/renew handlers insert a `compliance_audit_queue`
   row in the lease's transaction. An APScheduler interval job (every
   `compliance_queue_interval_minutes`, default 2) drains the queue:
   build payload, call the service, store the result, delete the row.
   Failures keep the row with `attempts + 1` and `last_error`; rows at
   `compliance_queue_max_attempts` (default 10) are skipped and visible
   for inspection. Queue-driven audits do not notify — they are initial
   state, not change.
3. **Change poll**: a daily job (hour `compliance_poll_hour`, default 7)
   pages through `GET /v1/audit-changes?since=<cursor>` (loop while a
   batch fills the limit), fetches each change's full new audit via
   `GET /v1/audits/{id}`, stores it, and notifies. Cursor lives in
   `compliance_sync_state`; it advances to the batch's max `created_at`.

Feature flag: `compliance_api_url` and `compliance_api_key` (both empty
by default) — when unset, the button/section hide, handlers do not
enqueue, and neither job registers. Same pattern as `resend_api_key`.

## Field mapping and renewal-chain synthesis

Direct: current lease's `rent_amount`, `rent_frequency` (identical
enums), `end_date`, `bond_amount` (when set). Fields this app does not
track (advance rent, holding deposit, other security, break fee,
disclosure flag) are omitted so those rules skip honestly.

**`start_date` is the renewal chain root's start date** (walk
`renewed_from_id` to the first lease). The 12-month first-increase rule
(s41(1A)(a)) measures from the start of the *tenancy*, and s41(2) makes
successive agreements continuous — sending the current agreement's start
would flag a lawful renewal-day increase as red. Caveat: the break-fee
rule reads `start_date`/`end_date` as the agreement term, which this
mapping distorts; it cannot fire today because `break_fee_amount` is
never sent. Revisit the mapping before ever adding break-fee data.

**`rent_increases` synthesis:** for each adjacent pair in the chain
(chronological), emit `{effective_on: successor.start_date, new_amount:
successor.rent_amount}` only when the successor's rent is strictly
greater. Decreases and unchanged rent emit nothing. `notice_given_on` is
never sent (not tracked). **An empty synthesis sends `None`, not `[]`** —
this app cannot see in-place rent edits, so an empty list would assert
"never increased", which may be false; `None` makes the increase rules
skip instead of reporting a possibly-false green. A non-empty list only
contains true events; invisible edits can under-report, never fabricate.

Mapper: `load_chain(session, lease)` + pure
`chain_to_audit_payload(chain)` in `app/services/compliance.py`,
unit-testable without HTTP.

## Schema (one migration)

| table | columns | semantics |
|---|---|---|
| `lease_audits` | `id`, `lease_id` FK indexed, `organization_id` FK, `audit_id` **unique**, `as_at`, `findings` JSON, `created_at` | audit history; detail page reads the newest; the unique `audit_id` makes queue and poll writes idempotent |
| `compliance_audit_queue` | `id`, `lease_id` FK **unique**, `attempts` (default 0), `last_error` nullable, `created_at` | outbox; deleted on success so the table is the remaining work; unique `lease_id` dedupes re-enqueues while pending |
| `compliance_sync_state` | `key` pk, `value` | poll cursor (`audit_changes_cursor` = last seen `created_at`) |

## Endpoints (this app, existing org-scoped auth)

- `POST /leases/{lease_id}/compliance-audit` — synchronous audit now;
  404 outside the caller's org; clear error when disabled or the service
  is unreachable (frontend shows a toast). Exact prefix and dependency
  names follow `routers/leases.py`.
- `GET /leases/{lease_id}/compliance-audit` — newest `lease_audits` row
  or null.

## Compliance service prerequisite (cross-repo, first task)

`GET /v1/audits?client_ref=<required>&limit=20` — tenant-scoped, newest
first, returns the existing `AuditInfo` list. Implemented in the service
repo with its own tests, commit and CI.

## Poll filtering and notifications

Skip entirely (no store, no notification, log a count): unknown or
unparseable `client_ref`, superseded leases (another lease has
`renewed_from_id` pointing at it), ended leases (`end_date` before
today). Active leases get a `lease_audits` row and one notification via
the existing `notify.py` helper (in-app + email): category `compliance`,
body listing each rule's verdict transition, link to the lease detail
page, recipients per the lease-expiry reminder pattern.

## Backfill

`uv run python -m app.compliance_backfill` — enqueue every lease with no
`lease_audits` row that is neither superseded nor ended, then print the
count. The drain job serialises the actual calls.

## Config additions

`compliance_api_url = ""`, `compliance_api_key = ""`,
`compliance_queue_interval_minutes = 2`, `compliance_poll_hour = 7`,
`compliance_queue_max_attempts = 10`.

## Frontend

Compliance section on the lease detail page: verdict badges
(red/green/skipped counts), per-rule rows (summary + section citation),
the not-legal-advice disclaimer, and a "check now" button. Entire
section hidden when the feature is disabled.

## Testing

- Mapper unit tests are this milestone's eval (exact-assert): chain
  synthesis (increase/decrease/flat, root start date, empty -> None,
  ordering) and payload shape.
- App tests never require the compliance service: endpoint and job tests
  fake `create_audit`/`get_audit`/`list_changes` at the service-function
  boundary.
- Endpoints: POST stores and returns; disabled -> clear error;
  cross-org 404; GET returns newest.
- Queue: enqueue happens in the lease transaction; drain success deletes
  the row and stores the audit; failure increments `attempts`; capped
  rows are skipped.
- Poll: active lease stores + notifies; superseded/ended skipped; cursor
  advances; re-running a batch creates no duplicates (unique `audit_id`).
- Backfill: enqueues only active, never-audited leases.
- e2e: seeded `lease_audits` renders the section with badges and the
  disclaimer. The button flow needs a live service and is not covered by
  e2e (documented).
- Service repo: list-endpoint tests in the existing `test_api.py` style.

Every task ends with its own repo's full suite, ruff sequence, commit,
push and green CI.

## Out of scope

Un-enrolling superseded leases inside the compliance service (the poll
filter handles the noise; a service-side deactivation API is a future
candidate), webhooks, auditing mid-agreement rent edits (invisible to
the chain), VIC, Regulation-based rules, and any LLM features.
