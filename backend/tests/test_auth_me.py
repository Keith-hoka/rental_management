SIGNUP = {
    "email": "me@example.com",
    "password": "secret123",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def signup_and_get_tokens(client) -> dict:
    response = await client.post("/api/v1/auth/signup", json=SIGNUP)
    return response.json()


async def test_me_returns_profile(client):
    tokens = await signup_and_get_tokens(client)
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == SIGNUP["email"]
    assert body["role"] == "landlord"
    assert body["organization_id"]


async def test_me_without_token_unauthorized(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_refresh_returns_new_pair(client):
    tokens = await signup_and_get_tokens(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_rejects_access_token(client):
    tokens = await signup_and_get_tokens(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert response.status_code == 401
