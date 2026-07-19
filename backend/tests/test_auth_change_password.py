SIGNUP = {
    "email": "change@example.com",
    "password": "originalpw1",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def signup(client) -> dict[str, str]:
    tokens = (await client.post("/api/v1/auth/signup", json=SIGNUP)).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_change_password_success(client):
    headers = await signup(client)
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": SIGNUP["password"], "new_password": "brandnew123"},
        headers=headers,
    )
    assert response.status_code == 200

    old = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": "brandnew123"}
    )
    assert new.status_code == 200


async def test_change_password_wrong_current_rejected(client):
    headers = await signup(client)
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrongpassword", "new_password": "brandnew123"},
        headers=headers,
    )
    assert response.status_code == 401

    # Password must be unchanged: the original still logs in.
    login = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert login.status_code == 200


async def test_change_password_requires_auth(client):
    response = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "y" * 10},
    )
    assert response.status_code == 401
