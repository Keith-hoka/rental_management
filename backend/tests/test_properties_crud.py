NEW_PROPERTY = {
    "address": "1 Main St",
    "type": "house",
    "bedrooms": 3,
    "bathrooms": 2,
    "parking": 1,
    "description": "Nice house",
    "image_urls": ["http://img/1.jpg"],
}


async def landlord_headers(client, email: str = "owner@example.com") -> dict:
    tokens = (
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "secret123",
                "name": "Owner",
                "organization_name": "Owner Org",
            },
        )
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_create_property_returns_201(client):
    headers = await landlord_headers(client)
    response = await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["address"] == "1 Main St"
    assert body["type"] == "house"
    assert body["status"] == "vacant"
    assert body["organization_id"]
    assert body["id"]


async def test_create_property_requires_auth(client):
    response = await client.post("/api/v1/properties", json=NEW_PROPERTY)
    assert response.status_code == 401


async def test_get_property_returns_it(client):
    headers = await landlord_headers(client)
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)).json()
    response = await client.get(f"/api/v1/properties/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_property_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "a2@example.com")
    org_b = await landlord_headers(client, "b2@example.com")
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)).json()
    response = await client.get(f"/api/v1/properties/{created['id']}", headers=org_b)
    assert response.status_code == 404


async def test_update_property_changes_fields(client):
    headers = await landlord_headers(client)
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)).json()
    response = await client.patch(
        f"/api/v1/properties/{created['id']}",
        json={"bedrooms": 4},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bedrooms"] == 4
    assert body["status"] == "vacant"
    assert body["address"] == NEW_PROPERTY["address"]


async def test_update_property_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "a3@example.com")
    org_b = await landlord_headers(client, "b3@example.com")
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)).json()
    response = await client.patch(
        f"/api/v1/properties/{created['id']}", json={"bedrooms": 4}, headers=org_b
    )
    assert response.status_code == 404


async def test_delete_property_removes_it(client):
    headers = await landlord_headers(client)
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)).json()
    response = await client.delete(f"/api/v1/properties/{created['id']}", headers=headers)
    assert response.status_code == 204

    listed = await client.get("/api/v1/properties", headers=headers)
    assert listed.json() == []


async def test_delete_property_in_other_org_is_404(client):
    org_a = await landlord_headers(client, "a4@example.com")
    org_b = await landlord_headers(client, "b4@example.com")
    created = (await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=org_a)).json()
    response = await client.delete(f"/api/v1/properties/{created['id']}", headers=org_b)
    assert response.status_code == 404


async def test_create_and_update_state_and_postcode(client):
    headers = await landlord_headers(client, "region@example.com")
    created = await client.post(
        "/api/v1/properties",
        json={**NEW_PROPERTY, "state": "NSW", "postcode": "2000"},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["state"] == "NSW"
    assert created.json()["postcode"] == "2000"

    updated = await client.patch(
        f"/api/v1/properties/{created.json()['id']}",
        json={"state": "VIC", "postcode": "3000"},
        headers=headers,
    )
    assert updated.json()["state"] == "VIC"
    assert updated.json()["postcode"] == "3000"


async def test_state_and_postcode_default_to_null(client):
    headers = await landlord_headers(client, "noregion@example.com")
    response = await client.post("/api/v1/properties", json=NEW_PROPERTY, headers=headers)
    assert response.json()["state"] is None
    assert response.json()["postcode"] is None
