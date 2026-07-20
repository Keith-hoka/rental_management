from datetime import date, timedelta

from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def add_lease(client, headers, property_id, start, end):
    return await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date=str(start), end_date=str(end)),
        headers=headers,
    )


async def test_property_is_occupied_with_active_lease(client):
    headers = await landlord_headers(client, "occ@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await add_lease(
        client, headers, property_id, today - timedelta(days=5), today + timedelta(days=30)
    )

    detail = await client.get(f"/api/v1/properties/{property_id}", headers=headers)
    body = detail.json()
    assert body["status"] == "occupied"
    assert body["active_lease"]["tenant_name"] == "Tina Tenant"
    assert body["active_lease"]["start_date"]


async def test_property_is_vacant_without_lease(client):
    headers = await landlord_headers(client, "vac@example.com")
    property_id = await make_property(client, headers)
    detail = await client.get(f"/api/v1/properties/{property_id}", headers=headers)
    body = detail.json()
    assert body["status"] == "vacant"
    assert body["active_lease"] is None


async def test_property_with_future_lease_is_vacant(client):
    headers = await landlord_headers(client, "fut@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await add_lease(
        client, headers, property_id, today + timedelta(days=10), today + timedelta(days=40)
    )
    detail = await client.get(f"/api/v1/properties/{property_id}", headers=headers)
    assert detail.json()["status"] == "vacant"


async def test_property_with_past_lease_is_vacant(client):
    headers = await landlord_headers(client, "past@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await add_lease(
        client, headers, property_id, today - timedelta(days=40), today - timedelta(days=10)
    )
    detail = await client.get(f"/api/v1/properties/{property_id}", headers=headers)
    assert detail.json()["status"] == "vacant"


async def test_status_filter_uses_active_lease(client):
    headers = await landlord_headers(client, "sf@example.com")
    await make_property(client, headers, "Vacant Rd")
    occupied_id = await make_property(client, headers, "Occupied Rd")
    today = date.today()
    await add_lease(
        client, headers, occupied_id, today - timedelta(days=1), today + timedelta(days=10)
    )

    occupied = await client.get("/api/v1/properties?status=occupied", headers=headers)
    assert [p["address"] for p in occupied.json()] == ["Occupied Rd"]
    vacant = await client.get("/api/v1/properties?status=vacant", headers=headers)
    assert [p["address"] for p in vacant.json()] == ["Vacant Rd"]
