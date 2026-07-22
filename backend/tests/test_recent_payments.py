from tests.test_leases import make_property
from tests.test_payments_api import PAY, _lease_id
from tests.test_portal import onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _pay(client, headers, address="1 Recent St"):
    lease_id = await _lease_id(client, headers, await make_property(client, headers, address))
    await client.post(f"/api/v1/leases/{lease_id}/payments", json=PAY, headers=headers)
    return lease_id


async def test_lists_payments_with_property_and_tenant(client):
    headers = await landlord_headers(client, "rp1@example.com")
    await _pay(client, headers, "12 Recent Ave")

    body = (await client.get("/api/v1/payments/recent", headers=headers)).json()

    assert len(body) == 1
    assert body[0]["property_address"] == "12 Recent Ave"
    assert body[0]["tenant_name"] == "Tina Tenant"
    assert float(body[0]["amount"]) == 1000.0


async def test_newest_first_and_limited(client):
    headers = await landlord_headers(client, "rp2@example.com")
    lease_id = await _pay(client, headers, "1 Order St")
    for day in ("2026-02-01", "2026-03-01"):
        await client.post(
            f"/api/v1/leases/{lease_id}/payments",
            json={**PAY, "paid_on": day},
            headers=headers,
        )

    body = (await client.get("/api/v1/payments/recent?limit=2", headers=headers)).json()

    assert len(body) == 2
    assert [p["paid_on"] for p in body] == ["2026-03-01", "2026-02-01"]


async def test_other_organizations_are_not_visible(client):
    owner = await landlord_headers(client, "rp3@example.com")
    await _pay(client, owner, "9 Private Way")

    other = await landlord_headers(client, "rp3-other@example.com")
    assert (await client.get("/api/v1/payments/recent", headers=other)).json() == []


async def test_tenants_are_refused(client, db_session):
    headers = await landlord_headers(client, "rp4@example.com")
    lease_id = await _pay(client, headers, "4 Tenant Way")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "rp4-t@example.com")

    assert (await client.get("/api/v1/payments/recent", headers=tenant)).status_code == 403
