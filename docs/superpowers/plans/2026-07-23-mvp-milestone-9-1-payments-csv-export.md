# Milestone 9.1: Payment History CSV Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A manager exports the organization's payment history as a CSV, optionally narrowed to a date range.

**Architecture:** A server-side endpoint builds the CSV with Python's `csv` module into an in-memory buffer and returns it as `text/csv`. The frontend downloads it with an authenticated fetch — a Bearer-token header a plain link cannot send — then clicks a synthetic `<a download>` at a blob URL.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, PostgreSQL, standard-library `csv`, Next.js 16 App Router, Playwright. **No migration, no new dependency.**

## Global Constraints

- Package manager: `uv` only (`uv run`, `uv add`), never `python3` / `pip`.
- No emojis in code, logs, or print statements.
- Short modules/functions; docstrings over inline comments; do not program defensively.
- Ruff sequence before every push, from `backend/`:
  `uv run ruff format .` -> `uv run ruff check --fix .` -> `uv run ruff check .` -> `uv run ruff format --check .`
- Test files keep all imports at the top (ruff E402).
- Each task ends with: full test run -> ruff sequence -> commit -> push to `https://github.com/Keith-hoka/rental_management` (CI) -> report -> wait for approval.
- Accessible names introduced: `Export CSV`, `Export from`, `Export to`. Playwright matches names by **substring**; the date fields are prefixed so a looser `From` / `To` locator elsewhere cannot also match them.
- Backend commands run from `backend/`, frontend commands from `frontend/`. The shell keeps its working directory between commands — always `cd` explicitly.
- Never pipe a Playwright failure through `tail`: a strict-mode violation prints its matched-element list *above* the "waiting for..." line, so tailing hides the cause.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/routers/payments.py` | add `GET /payments/export` |
| `backend/tests/test_payments_export.py` | endpoint behaviour and CSV quoting |
| `frontend/src/lib/download.ts` | `downloadBlob`, reusable by later Phase 2 exports |
| `frontend/src/lib/payments.ts` | `exportPayments` |
| `frontend/src/app/app/payments/page.tsx` | date inputs and the export button |
| `frontend/e2e/payments-export.spec.ts` | the button triggers a real download |

---

### Task 1: The export endpoint

**Files:**
- Modify: `backend/app/routers/payments.py`
- Test: `backend/tests/test_payments_export.py`

**Interfaces:**
- Produces: `GET /api/v1/payments/export?start=&end=` -> `200 text/csv`, columns
  `paid_on, property_address, tenant_name, method, amount, note`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_payments_export.py`:

```python
import csv
import io
from datetime import date, timedelta

from tests.test_portal import make_lease
from tests.test_properties_crud import landlord_headers


async def _pay(client, headers, lease_id, amount, paid_on, note=None):
    body = {"amount": amount, "paid_on": str(paid_on), "method": "bank_transfer"}
    if note is not None:
        body["note"] = note
    await client.post(f"/api/v1/leases/{lease_id}/payments", json=body, headers=headers)


def _rows(text):
    return list(csv.reader(io.StringIO(text)))


async def test_export_returns_csv_with_a_row_per_payment(client):
    headers = await landlord_headers(client, "exp@example.com")
    lease_id = await make_lease(client, headers, "1 Export St")
    today = date.today()
    await _pay(client, headers, lease_id, 500, today)
    await _pay(client, headers, lease_id, 300, today)

    response = await client.get("/api/v1/payments/export", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = _rows(response.text)
    assert rows[0] == ["paid_on", "property_address", "tenant_name", "method", "amount", "note"]
    assert len(rows) == 3  # header + two payments
    assert rows[1][1] == "1 Export St"
    assert rows[1][3] == "bank_transfer"


async def test_date_range_filters_inclusively(client):
    headers = await landlord_headers(client, "exprange@example.com")
    lease_id = await make_lease(client, headers, "2 Range Rd")
    today = date.today()
    await _pay(client, headers, lease_id, 100, today - timedelta(days=10))
    await _pay(client, headers, lease_id, 200, today)
    await _pay(client, headers, lease_id, 300, today + timedelta(days=10))

    start = today
    end = today
    response = await client.get(
        f"/api/v1/payments/export?start={start}&end={end}", headers=headers
    )

    rows = _rows(response.text)[1:]
    assert [r[4] for r in rows] == ["200.00"]


async def test_export_is_org_scoped(client):
    owner = await landlord_headers(client, "expowner@example.com")
    lease_id = await make_lease(client, owner, "3 Mine Way")
    await _pay(client, owner, lease_id, 400, date.today())

    stranger = await landlord_headers(client, "expstranger@example.com")
    response = await client.get("/api/v1/payments/export", headers=stranger)

    assert _rows(response.text) == [
        ["paid_on", "property_address", "tenant_name", "method", "amount", "note"]
    ]


async def test_note_with_comma_and_quote_round_trips(client):
    headers = await landlord_headers(client, "expquote@example.com")
    lease_id = await make_lease(client, headers, "4 Quote Ct")
    note = 'Paid in cash, tenant said "keep the change"'
    await _pay(client, headers, lease_id, 250, date.today(), note=note)

    response = await client.get("/api/v1/payments/export", headers=headers)

    # Parse it back the way a spreadsheet would; a hand-joined CSV fails here.
    rows = _rows(response.text)
    assert rows[1][5] == note


async def test_export_sets_attachment_disposition(client):
    headers = await landlord_headers(client, "expdisp@example.com")
    await make_lease(client, headers, "5 Disp Dr")

    response = await client.get("/api/v1/payments/export", headers=headers)

    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert ".csv" in disposition
```

`make_lease` returns a lease id and is imported from `tests/test_portal.py`; `landlord_headers`
from `tests/test_properties_crud.py`. Both are used across the existing payment tests.

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && uv run pytest tests/test_payments_export.py -v`
Expected: all five FAIL with 404 — the route does not exist.

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routers/payments.py`, add `csv` and `io` to the imports at the top, and `date` to
the `datetime` import:

```python
import csv
import io
import uuid
from datetime import UTC, date, datetime
```

Add the endpoint immediately after `recent_payments`:

```python
@router.get("/payments/export")
async def export_payments(
    start: date | None = None,
    end: date | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """The organization's payments as CSV, optionally within an inclusive date range."""
    query = (
        select(Payment, Property.address, Lease.tenant_name)
        .join(Lease, Lease.id == Payment.lease_id)
        .join(Property, Property.id == Lease.property_id)
        .where(Payment.organization_id == membership.organization_id)
    )
    if start is not None:
        query = query.where(Payment.paid_on >= start)
    if end is not None:
        query = query.where(Payment.paid_on <= end)
    query = query.order_by(Payment.paid_on.asc(), Property.address.asc())
    rows = (await session.execute(query)).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["paid_on", "property_address", "tenant_name", "method", "amount", "note"])
    for payment, address, tenant_name in rows:
        writer.writerow(
            [
                payment.paid_on,
                address,
                tenant_name,
                payment.method.value,
                payment.amount,
                payment.note or "",
            ]
        )

    today = datetime.now(UTC).date()
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="payments-{today}.csv"'},
    )
```

`csv.writer` does the quoting: the address `12 Smith St, Unit 3` is wrapped in quotes, a note with
a `"` has it doubled, a note with a newline is quoted. That is the correctness a hand-built string
gets wrong, and test 4 is what proves it.

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/test_payments_export.py -v`
Expected: 5 passed.

- [ ] **Step 5: Full test run**

Run: `cd backend && uv run pytest`
Expected: all pass.

- [ ] **Step 6: Ruff sequence**

```bash
cd backend
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 7: Commit and push**

```bash
git add backend/app/routers/payments.py backend/tests/test_payments_export.py
git commit -m "Add the payment CSV export endpoint"
git push origin main
```

Then report and wait for approval.

---

### Task 2: The frontend export button

**Files:**
- Create: `frontend/src/lib/download.ts`
- Modify: `frontend/src/lib/payments.ts`, `frontend/src/app/app/payments/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/payments/export` (Task 1); `API_BASE_URL` and `getAccessToken` (existing).
- Produces: `downloadBlob(blob, filename)`, `exportPayments(start?, end?) -> Promise<Blob>`; the
  accessible names `Export CSV`, `Export from`, `Export to`.

- [ ] **Step 1: Add the download helper**

Create `frontend/src/lib/download.ts`:

```ts
/**
 * Save a Blob as a file. A fetch-downloaded body cannot be reached by a plain
 * link, so a synthetic anchor at an object URL carries it to disk. Later Phase 2
 * exports (reports, documents) reuse this.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 2: Add the API client**

In `frontend/src/lib/payments.ts`, add to the top import:

```ts
import { apiFetch, API_BASE_URL } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
```

and append:

```ts
export async function exportPayments(start?: string, end?: string): Promise<Blob> {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const query = params.toString();
  // Not apiFetch: that assumes a JSON body. The auth header is still required,
  // so a plain link would 401.
  const response = await fetch(
    `${API_BASE_URL}/api/v1/payments/export${query ? `?${query}` : ""}`,
    {
      cache: "no-store",
      headers: { Authorization: `Bearer ${getAccessToken() ?? ""}` },
    },
  );
  if (!response.ok) throw new Error("Export failed");
  return response.blob();
}
```

- [ ] **Step 3: Add the button and date inputs**

In `frontend/src/app/app/payments/page.tsx`, add the imports:

```tsx
import { exportPayments } from "@/lib/payments";
import { downloadBlob } from "@/lib/download";
import { Button, Card, Input, PageHeader } from "@/components/ui";
```

(`Button` and `Input` join the existing `@/components/ui` import rather than a second one; keep
`Card` and `PageHeader` that are already there.)

Add state beside the existing `payments` state:

```tsx
  const [exportFrom, setExportFrom] = useState("");
  const [exportTo, setExportTo] = useState("");
```

Add the handler next to `logOut`:

```tsx
  async function onExport() {
    const blob = await exportPayments(exportFrom || undefined, exportTo || undefined);
    downloadBlob(blob, "payments.csv");
  }
```

Replace the `Payment history` card's `actions` prop:

```tsx
        actions={<span className="text-sm text-muted">${total.toFixed(2)}</span>}
```

with:

```tsx
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted">${total.toFixed(2)}</span>
            <Input
              type="date"
              aria-label="Export from"
              value={exportFrom}
              onChange={(e) => setExportFrom(e.target.value)}
              className="w-40"
            />
            <Input
              type="date"
              aria-label="Export to"
              value={exportTo}
              onChange={(e) => setExportTo(e.target.value)}
              className="w-40"
            />
            <Button variant="secondary" size="sm" onClick={onExport}>
              Export CSV
            </Button>
          </div>
        }
```

The saved file is named by the anchor's `download` attribute (`payments.csv`); the server's
`payments-<today>.csv` would only apply to a direct navigation, which this flow does not use.

- [ ] **Step 4: Lint, typecheck and build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: both clean. `npm run build` runs the TypeScript check.

- [ ] **Step 5: Check by hand**

The backend must be running. Sign in as a landlord, record a payment on a lease, open
`/app/payments`, and click `Export CSV` — a `payments.csv` downloads. Open it: the header row and
the payment are present, and a note containing a comma stays in one cell. Set `Export from` past
the payment date and confirm the download is empty of rows.

- [ ] **Step 6: Commit and push**

```bash
git add frontend/src/lib/download.ts frontend/src/lib/payments.ts frontend/src/app/app/payments/page.tsx
git commit -m "Add the payment CSV export button"
git push origin main
```

Then report and wait for approval.

---

### Task 3: End-to-end coverage

**Files:**
- Create: `frontend/e2e/payments-export.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-2.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/payments-export.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const landlord = `export-${Date.now()}@example.com`;

function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("a landlord exports the payment history as CSV", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Your name").fill("Export Owner");
  await page.getByPlaceholder("Organization name").fill("Export Org");
  await page.getByPlaceholder("Email").fill(landlord);
  await page.getByPlaceholder("Password (min 8 chars)").fill("secret123");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByTestId("welcome")).toBeVisible();

  await page.goto("/app/properties/new");
  await page.getByPlaceholder("Address", { exact: true }).fill("6 Export Way");
  await page.getByRole("button", { name: "Create property" }).click();
  await expect(page).toHaveURL(/\/app\/properties$/);

  await page.goto("/app/leases/new");
  await page.getByLabel("Property").selectOption({ label: "6 Export Way (vacant)" });
  await page.getByPlaceholder("Tenant name").fill("Ed Exporter");
  await page.getByPlaceholder("Tenant email").fill(`tenant-${Date.now()}@example.com`);
  await page.getByLabel("Rent").fill("700");
  await page.getByLabel("Start").fill(isoDate(-1));
  await page.getByLabel("End").fill(isoDate(60));
  await page.getByRole("button", { name: "Add lease" }).click();

  // Record a payment so the export has a row.
  await page.getByRole("link", { name: "6 Export Way" }).click();
  await expect(page).toHaveURL(/\/app\/leases\/[0-9a-f-]+$/);
  await page.getByPlaceholder("Amount").fill("700");
  await page.getByLabel("Payment date").fill(isoDate(0));
  await page.getByRole("button", { name: "Record payment" }).click();

  await page.goto("/app/payments");
  // The download comes from a fetch + synthetic anchor, so it fires a real
  // download event rather than a navigation.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.csv$/);
});
```

The record-payment controls (`Amount`, `Payment date`, `Record payment`) live on the lease detail
page, which is why the test opens the lease before exporting; this mirrors `e2e/payments.spec.ts`.

- [ ] **Step 2: Restart the backend so the new route is served**

The e2e hits a live backend. If it was started before Task 1, `/api/v1/payments/export` returns
404 and the export throws; restart so the route exists.

- [ ] **Step 3: Run the new spec**

Run: `cd frontend && npx playwright test payments-export`
Expected: 1 passed.

- [ ] **Step 4: Run the whole e2e suite**

Run: `cd frontend && npx playwright test --workers=1`
Expected: all pass (29 existing plus this one). Use `--workers=1` to match CI.

- [ ] **Step 5: Full backend test run and ruff sequence**

```bash
cd backend
uv run pytest
uv run ruff format .
uv run ruff check --fix .
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 6: Commit and push**

```bash
git add frontend/e2e/payments-export.spec.ts
git commit -m "Add payment CSV export e2e"
git push origin main
```

- [ ] **Step 7: Confirm CI is green**

Run: `gh run list --limit 3`
Expected: the newest run for `main` succeeds. If it fails, read the log before changing anything — the failure is evidence, not noise.

Then report and wait for approval.
