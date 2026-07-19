NEW_PROPERTY = {
    "address": "1 Main St",
    "type": "house",
    "bedrooms": 3,
    "bathrooms": 2,
    "parking": 1,
    "description": "Nice house",
    "status": "vacant",
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
