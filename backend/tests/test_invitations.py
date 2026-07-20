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


async def test_create_invitation_returns_201(client):
    headers = await landlord_headers(client)
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "pm@example.com", "role": "property_manager"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "pm@example.com"
    assert body["role"] == "property_manager"
    assert body["status"] == "pending"


async def test_create_invitation_requires_auth(client):
    response = await client.post(
        "/api/v1/invitations", json={"email": "pm@example.com", "role": "property_manager"}
    )
    assert response.status_code == 401


async def test_create_invitation_rejects_tenant_role(client):
    headers = await landlord_headers(client)
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "t@example.com", "role": "tenant"},
        headers=headers,
    )
    assert response.status_code == 422
