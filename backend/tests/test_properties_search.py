from datetime import date, timedelta

from tests.test_leases import lease_body
from tests.test_properties_crud import landlord_headers


async def make_property(client, headers, address, ptype="house"):
    return await client.post(
        "/api/v1/properties",
        json={
            "address": address,
            "type": ptype,
            "bedrooms": 2,
            "bathrooms": 1,
            "parking": 0,
            "image_urls": [],
        },
        headers=headers,
    )


async def test_search_by_address_substring(client):
    headers = await landlord_headers(client, "search@example.com")
    await make_property(client, headers, "12 Oak Avenue")
    await make_property(client, headers, "99 Pine Street")

    response = await client.get("/api/v1/properties?search=oak", headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["address"] == "12 Oak Avenue"


async def test_filter_by_status_and_type(client):
    headers = await landlord_headers(client, "filter@example.com")
    await make_property(client, headers, "A", ptype="house")
    occupied = (await make_property(client, headers, "B", ptype="condo")).json()
    today = date.today()
    await client.post(
        f"/api/v1/properties/{occupied['id']}/leases",
        json=lease_body(
            start_date=str(today - timedelta(days=1)),
            end_date=str(today + timedelta(days=10)),
        ),
        headers=headers,
    )

    vacant_list = await client.get("/api/v1/properties?status=vacant", headers=headers)
    assert [p["address"] for p in vacant_list.json()] == ["A"]

    occupied_list = await client.get("/api/v1/properties?status=occupied", headers=headers)
    assert [p["address"] for p in occupied_list.json()] == ["B"]

    condo = await client.get("/api/v1/properties?type=condo", headers=headers)
    assert [p["address"] for p in condo.json()] == ["B"]


async def test_search_matches_city_state_and_postcode(client):
    headers = await landlord_headers(client, "region-search@example.com")
    await client.post(
        "/api/v1/properties",
        json={
            "address": "12 Oak Avenue",
            "city": "Sydney",
            "state": "NSW",
            "postcode": "2000",
            "type": "house",
            "image_urls": [],
        },
        headers=headers,
    )
    await make_property(client, headers, "99 Pine Street")

    for term in ("sydney", "nsw", "2000"):
        results = (await client.get(f"/api/v1/properties?search={term}", headers=headers)).json()
        assert [p["address"] for p in results] == ["12 Oak Avenue"], term

    # A property with no region set must not match a region term.
    results = (await client.get("/api/v1/properties?search=pine", headers=headers)).json()
    assert [p["address"] for p in results] == ["99 Pine Street"]
