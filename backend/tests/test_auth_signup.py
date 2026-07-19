SIGNUP = {
    "email": "keith@example.com",
    "password": "secret123",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def test_signup_returns_tokens(client):
    response = await client.post("/api/v1/auth/signup", json=SIGNUP)
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_signup_duplicate_email_conflicts(client):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    response = await client.post("/api/v1/auth/signup", json=SIGNUP)
    assert response.status_code == 409
