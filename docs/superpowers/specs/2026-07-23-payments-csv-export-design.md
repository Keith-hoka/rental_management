# Milestone 9.1: Payment History CSV Export — Design

**Date:** 2026-07-23
**Status:** Approved (pending spec review)

**Part of:** Phase 2, sub-project 1 of 6. The remaining Phase 2 pieces are document management,
inspections, full-text search, a calendar view, and monthly reports. This is the smallest and
adds no data model, so it opens the phase.

**Phase 2 dependency noted for later:** monthly reports need income, **expenses**, vacancy and
ROI. Income and vacancy exist (payments and the M8.3 occupancy series), but there is no expense,
cost or invoice concept anywhere in the models, and M8.1 explicitly left contractor quotes and
invoices out. Monthly reports therefore cannot be built until an expense-tracking sub-project
exists, or must ship as an income-and-vacancy half. This is out of scope here but recorded so the
Phase 2 ordering accounts for it.

## Goal

A manager exports the organization's payment history as a CSV, optionally narrowed to a date
range, for reporting and reconciliation.

## Architecture

- **Server-side, not a client-side dump.** The payments page loads only the most recent 100
  payments; exporting what the user asked for — all payments, any date range — has to come from a
  new endpoint, because the browser does not hold the rest.
- The CSV is written with Python's `csv` module into an in-memory `StringIO`, never by joining
  strings. Property addresses already contain commas ("12 Smith St, Unit 3") and a payment note
  may contain quotes or newlines; hand-joined output would misalign columns in Excel, and do so
  silently. Loading the whole result into memory rather than streaming is deliberate: fifty
  properties across five years of monthly rent is ~3000 rows, and streaming would only make it
  harder to test for no real gain.
- **Download uses an authenticated fetch, not a plain link.** The frontend authenticates with a
  Bearer token in the `Authorization` header; a bare `<a href>` navigation does not send that
  header and would 401. The page fetches the CSV with the header, wraps the body in a `Blob`,
  and clicks a synthetic `<a download>` at an object URL, revoking it afterwards.
- Rejected: a one-time download token in the URL. It adds moving parts, and a credential in a
  query string lands in browser history and intermediary logs.

## Tech Stack

- Backend: FastAPI, async SQLAlchemy 2.0, PostgreSQL (existing). Python standard-library `csv`.
  **No migration, no new dependency.**
- Frontend: Next.js (existing). No new dependency.

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push (CI) -> report -> wait.
- Accessible names introduced: `Export CSV`, `Export from`, `Export to`. Playwright matches names
  by **substring**, so the date fields are prefixed rather than a bare `From` / `To` that a
  looser locator elsewhere could also match.

---

## Product Rules (confirmed)

- **Scope is all payments, with an optional date range**, not just the 100 rows on screen.
  Reporting and reconciliation are the point, and both work by year or quarter; exporting only the
  visible page would be near useless for them.
- **Both `start` and `end` are optional**, and both are inclusive. Omitting both exports
  everything; omitting one leaves that side open.
- **Manager-only, organization-scoped.** A tenant has no payment-history export.
- **The date filter is on `paid_on`**, the same field the history table sorts by.

---

## Backend

Endpoint in `backend/app/routers/payments.py`:

`GET /api/v1/payments/export?start=&end=` -> `200 text/csv`, dependency `require_roles(landlord,
property_manager)`, scoped to the caller's organization.

- `start: date | None = None`, `end: date | None = None`. When present they filter
  `Payment.paid_on >= start` and `Payment.paid_on <= end`.
- Rows are ordered by `paid_on` ascending, then by property address, so a reconciler reads oldest
  first.
- Response headers: `Content-Type: text/csv; charset=utf-8` and
  `Content-Disposition: attachment; filename="payments-<today>.csv"`, where `<today>` is the
  server date.

The query joins the same tables the existing `recent_payments` endpoint does (payment -> lease ->
property) to resolve `property_address` and `tenant_name`.

Columns, matching the on-screen table plus the note it omits for width:

```
paid_on, property_address, tenant_name, method, amount, note
```

`method` is written as its plain value (`bank_transfer`, not `Bank transfer`); a reconciler wants
the stored token, and casing is the display's concern.

Implementation shape:

```python
buffer = io.StringIO()
writer = csv.writer(buffer)
writer.writerow(["paid_on", "property_address", "tenant_name", "method", "amount", "note"])
for row in rows:
    writer.writerow([row.paid_on, row.address, row.tenant_name, row.method.value, row.amount, row.note or ""])
return Response(
    content=buffer.getvalue(),
    media_type="text/csv; charset=utf-8",
    headers={"Content-Disposition": f'attachment; filename="payments-{today}.csv"'},
)
```

`csv.writer` handles the quoting: an address with a comma is wrapped in quotes, a note with a
quote has it doubled, a note with a newline is quoted. That correctness is exactly what a
hand-built string gets wrong.

---

## Frontend

`frontend/src/lib/payments.ts` gains `exportPayments(start?: string, end?: string): Promise<Blob>`.
It fetches `/api/v1/payments/export` with the auth header (reusing the token accessor `apiFetch`
uses), reads the response as a `Blob`, and returns it. It does not go through `apiFetch`, which
assumes a JSON body.

`frontend/src/app/app/payments/page.tsx`: an `Export from` date input, an `Export to` date input,
and an `Export CSV` button in the `Payment history` card's actions. The click:

```ts
const blob = await exportPayments(from || undefined, to || undefined);
const url = URL.createObjectURL(blob);
const a = document.createElement("a");
a.href = url;
a.download = "payments.csv";
a.click();
URL.revokeObjectURL(url);
```

The synthetic anchor is what carries the download through a fetch that a plain link could not
authenticate. A helper `downloadBlob(blob, filename)` in `frontend/src/lib/download.ts` holds this
so the page does not grow DOM plumbing; it is the one piece any later Phase 2 export (reports,
document downloads) will reuse.

The saved filename comes from the anchor's `download` attribute, so the client names the file
`payments.csv`. The server's `Content-Disposition` filename (`payments-<today>.csv`) would only
take effect on a direct navigation, which this flow deliberately does not use; it stays on the
response for correctness and for any non-browser client, but the browser save uses the client
name. Both end in `.csv`, which is all the e2e asserts.

---

## Testing

Backend (`backend/tests/test_payments_export.py`):

1. Export returns `text/csv` with the header row and one data row per payment.
2. `start`/`end` narrow the result to payments whose `paid_on` is in range, inclusive on both
   ends.
3. Another organization's payments never appear.
4. **A note containing a comma and a double quote round-trips through Python's `csv` reader** —
   parse the response back with `csv.reader` and assert the note field equals the original. This
   is the test a hand-joined implementation fails.
5. The response carries `Content-Disposition: attachment` with a `.csv` filename.

e2e (`frontend/e2e/payments-export.spec.ts`): a landlord records a payment, clicks `Export CSV`,
and Playwright's `page.waitForEvent("download")` fires with a `.csv` suggested filename. The
download's content is not asserted in the browser — that is tests 1-4's job; the e2e proves the
button triggers a real download rather than a navigation or a silent no-op.

---

## Out of Scope

- Exporting charges, leases, tenants, or maintenance; this is payments only.
- Column selection, or reordering.
- XLSX or PDF; CSV only.
- Scheduled or emailed exports.
- A tenant-facing export.
- Streaming very large exports; the in-memory build is sufficient at this scale.

---

## File Structure

| File | Change |
|---|---|
| `backend/app/routers/payments.py` | add `GET /payments/export` |
| `backend/tests/test_payments_export.py` | new |
| `frontend/src/lib/payments.ts` | add `exportPayments` |
| `frontend/src/lib/download.ts` | new: `downloadBlob` |
| `frontend/src/app/app/payments/page.tsx` | date inputs and the export button |
| `frontend/e2e/payments-export.spec.ts` | new |

## Task Breakdown

- **T1** the export endpoint + tests 1-5 (including the quoting round-trip)
- **T2** frontend `exportPayments`, `downloadBlob`, the button and date inputs
- **T3** e2e + CI green
