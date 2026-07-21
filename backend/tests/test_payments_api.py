from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers

PAY = {"amount": 1000, "paid_on": "2026-01-05", "method": "cash", "note": "rent"}


async def _lease_id(client, headers, property_id):
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]


async def test_record_payment_201(client):
    headers = await landlord_headers(client, "pay1@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    resp = await client.post(f"/api/v1/leases/{lid}/payments", json=PAY, headers=headers)
    assert resp.status_code == 201
    assert float(resp.json()["amount"]) == 1000.0
    assert resp.json()["method"] == "cash"


async def test_record_payment_rejects_nonpositive(client):
    headers = await landlord_headers(client, "pay0@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    resp = await client.post(
        f"/api/v1/leases/{lid}/payments", json={**PAY, "amount": 0}, headers=headers
    )
    assert resp.status_code == 422


async def test_list_payments_newest_first(client):
    headers = await landlord_headers(client, "payl@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    await client.post(
        f"/api/v1/leases/{lid}/payments", json={**PAY, "paid_on": "2026-01-01"}, headers=headers
    )
    await client.post(
        f"/api/v1/leases/{lid}/payments", json={**PAY, "paid_on": "2026-02-01"}, headers=headers
    )
    body = (await client.get(f"/api/v1/leases/{lid}/payments", headers=headers)).json()
    assert [p["paid_on"] for p in body] == ["2026-02-01", "2026-01-01"]


async def test_delete_payment(client):
    headers = await landlord_headers(client, "payd@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    pid = (await client.post(f"/api/v1/leases/{lid}/payments", json=PAY, headers=headers)).json()[
        "id"
    ]
    deleted = await client.delete(f"/api/v1/leases/{lid}/payments/{pid}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/leases/{lid}/payments", headers=headers)).json() == []


async def test_payments_cross_org_404(client):
    org_a = await landlord_headers(client, "paya@example.com")
    org_b = await landlord_headers(client, "payb@example.com")
    lid = await _lease_id(client, org_a, await make_property(client, org_a))
    resp = await client.post(f"/api/v1/leases/{lid}/payments", json=PAY, headers=org_b)
    assert resp.status_code == 404


async def test_payments_requires_auth(client):
    headers = await landlord_headers(client, "payauth@example.com")
    lid = await _lease_id(client, headers, await make_property(client, headers))
    resp = await client.get(f"/api/v1/leases/{lid}/payments")
    assert resp.status_code == 401
