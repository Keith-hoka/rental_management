from datetime import date, timedelta

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


async def test_update_lease_changes_fields(client):
    headers = await landlord_headers(client, "upd@example.com")
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    response = await client.patch(
        f"/api/v1/leases/{created['id']}",
        json={"rent_amount": 1750, "tenant_name": "Ned New"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert float(body["rent_amount"]) == 1750.0
    assert body["tenant_name"] == "Ned New"


async def test_update_lease_rejects_overlap(client):
    headers = await landlord_headers(client, "updover@example.com")
    property_id = await make_property(client, headers)
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(start_date="2026-01-01", end_date="2026-03-31"),
        headers=headers,
    )
    second = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(start_date="2026-07-01", end_date="2026-09-30"),
            headers=headers,
        )
    ).json()
    # Pull the second lease back over the first one.
    response = await client.patch(
        f"/api/v1/leases/{second['id']}",
        json={"start_date": "2026-02-01"},
        headers=headers,
    )
    assert response.status_code == 409


async def test_update_lease_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "ua@example.com")
    org_b = await landlord_headers(client, "ub@example.com")
    property_id = await make_property(client, org_a)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_a
        )
    ).json()
    response = await client.patch(
        f"/api/v1/leases/{created['id']}", json={"rent_amount": 1}, headers=org_b
    )
    assert response.status_code == 404


async def test_delete_lease_removes_it(client):
    headers = await landlord_headers(client, "del@example.com")
    property_id = await make_property(client, headers)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    deleted = await client.delete(f"/api/v1/leases/{created['id']}", headers=headers)
    assert deleted.status_code == 204
    listed = await client.get(f"/api/v1/properties/{property_id}/leases", headers=headers)
    assert listed.json() == []


async def test_delete_lease_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "da@example.com")
    org_b = await landlord_headers(client, "db@example.com")
    property_id = await make_property(client, org_a)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_a
        )
    ).json()
    response = await client.delete(f"/api/v1/leases/{created['id']}", headers=org_b)
    assert response.status_code == 404


async def test_list_all_org_leases_with_address_and_state(client):
    headers = await landlord_headers(client, "alllease@example.com")
    today = date.today()
    active_p = await make_property(client, headers, "Alpha St")
    upcoming_p = await make_property(client, headers, "Beta Rd")
    ended_p = await make_property(client, headers, "Gamma Ave")
    await client.post(
        f"/api/v1/properties/{active_p}/leases",
        json=lease_body(
            start_date=str(today - timedelta(days=1)), end_date=str(today + timedelta(days=10))
        ),
        headers=headers,
    )
    await client.post(
        f"/api/v1/properties/{upcoming_p}/leases",
        json=lease_body(
            start_date=str(today + timedelta(days=5)), end_date=str(today + timedelta(days=20))
        ),
        headers=headers,
    )
    await client.post(
        f"/api/v1/properties/{ended_p}/leases",
        json=lease_body(
            start_date=str(today - timedelta(days=40)), end_date=str(today - timedelta(days=20))
        ),
        headers=headers,
    )

    response = await client.get("/api/v1/leases", headers=headers)
    assert response.status_code == 200
    rows = {row["property_address"]: row for row in response.json()}
    assert rows["Alpha St"]["state"] == "active"
    assert rows["Beta Rd"]["state"] == "upcoming"
    assert rows["Gamma Ave"]["state"] == "ended"
    assert rows["Alpha St"]["tenant_name"] == "Tina Tenant"


async def test_list_all_org_leases_is_org_scoped(client):
    org_a = await landlord_headers(client, "aall@example.com")
    org_b = await landlord_headers(client, "ball@example.com")
    property_id = await make_property(client, org_a)
    await client.post(f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=org_a)
    response = await client.get("/api/v1/leases", headers=org_b)
    assert response.status_code == 200
    assert response.json() == []
