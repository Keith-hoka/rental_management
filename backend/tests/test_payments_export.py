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
    response = await client.get(f"/api/v1/payments/export?start={start}&end={end}", headers=headers)

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
