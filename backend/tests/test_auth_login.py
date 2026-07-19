SIGNUP = {
    "email": "login@example.com",
    "password": "secret123",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def test_login_returns_tokens(client):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    response = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_wrong_password_unauthorized(client):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    response = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": "wrong"}
    )
    assert response.status_code == 401


async def test_login_unknown_email_unauthorized(client):
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert response.status_code == 401
