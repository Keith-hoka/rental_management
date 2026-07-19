from datetime import timedelta

from app.core.security import create_token

SIGNUP = {
    "email": "reset@example.com",
    "password": "oldpassword",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def test_forgot_password_always_accepts(client):
    response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 202


async def test_reset_password_changes_login(client):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    me = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert me.status_code == 200

    token = create_token(SIGNUP["email"], "reset", timedelta(minutes=30))
    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "newpassword1"}
    )
    assert response.status_code == 200

    old = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}
    )
    assert old.status_code == 401
    new = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": "newpassword1"}
    )
    assert new.status_code == 200


async def test_reset_password_rejects_access_token(client):
    tokens = (await client.post("/api/v1/auth/signup", json=SIGNUP)).json()
    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": tokens["access_token"], "new_password": "x" * 10},
    )
    assert response.status_code == 401
