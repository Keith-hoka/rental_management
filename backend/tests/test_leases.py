from tests.test_properties_crud import landlord_headers


async def make_property(client, headers, address="1 Lease St") -> str:
    """Create a property via the API and return its id."""
    response = await client.post(
        "/api/v1/properties",
        json={"address": address, "type": "house"},
        headers=headers,
    )
    return response.json()["id"]


def lease_body(**overrides) -> dict:
    body = {
        "tenant_name": "Tina Tenant",
        "tenant_email": "tina@example.com",
        "rent_amount": 1500,
        "rent_frequency": "monthly",
        "bond_amount": 3000,
        "notice_period_days": 21,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    }
    body.update(overrides)
    return body


async def test_create_lease_returns_201(client):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tenant_name"] == "Tina Tenant"
    assert body["property_id"] == property_id
    assert float(body["rent_amount"]) == 1500.0
    assert body["id"]


async def test_create_lease_requires_auth(client):
    headers = await landlord_headers(client)
    property_id = await make_property(client, headers)
    response = await client.post(f"/api/v1/properties/{property_id}/leases", json=lease_body())
    assert response.status_code == 401


async def test_create_lease_on_other_org_property_is_404(client):
    org_a = await landlord_headers(client, "a@example.com")
    org_b = await landlord_headers(client, "b@example.com")
    property_id = await make_property(client, org_a)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_b
    )
    assert response.status_code == 404


async def test_create_lease_rejects_start_after_end(client):
    headers = await landlord_headers(client, "order@example.com")
    property_id = await make_property(client, headers)
    response = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-12-31", end_date="2026-01-01"),
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_lease_rejects_overlap(client):
    headers = await landlord_headers(client, "overlap@example.com")
    property_id = await make_property(client, headers)
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-01-01", end_date="2026-06-30"),
        headers=headers,
    )
    overlapping = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-06-01", end_date="2026-12-31"),
        headers=headers,
    )
    assert overlapping.status_code == 409


async def test_create_lease_allows_adjacent_ranges(client):
    headers = await landlord_headers(client, "adjacent@example.com")
    property_id = await make_property(client, headers)
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-01-01", end_date="2026-06-30"),
        headers=headers,
    )
    adjacent = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-07-01", end_date="2026-12-31"),
        headers=headers,
    )
    assert adjacent.status_code == 201


async def test_list_leases_for_property(client):
    headers = await landlord_headers(client, "list@example.com")
    property_id = await make_property(client, headers)
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-01-01", end_date="2026-06-30"),
        headers=headers,
    )
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-07-01", end_date="2026-12-31"),
        headers=headers,
    )
    response = await client.get(f"/api/v1/properties/{property_id}/leases", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_leases_for_other_org_property_is_404(client):
    org_a = await landlord_headers(client, "la@example.com")
    org_b = await landlord_headers(client, "lb@example.com")
    property_id = await make_property(client, org_a)
    response = await client.get(f"/api/v1/properties/{property_id}/leases", headers=org_b)
    assert response.status_code == 404


async def test_get_lease_returns_it(client):
    headers = await landlord_headers(client, "getlease@example.com")
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    response = await client.get(f"/api/v1/leases/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_lease_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "ga@example.com")
    org_b = await landlord_headers(client, "gb@example.com")
    property_id = await make_property(client, org_a)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_a
        )
    ).json()
    response = await client.get(f"/api/v1/leases/{created['id']}", headers=org_b)
    assert response.status_code == 404
