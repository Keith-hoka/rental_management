import re

from app.core.security import create_token

SIGNUP = {
    "email": "reset@example.com",
    "password": "oldpassword",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def request_reset_token(client, monkeypatch, email: str) -> str:
    """Trigger forgot-password and return the reset token from the emailed link."""
    captured = {}

    async def capture(to: str, subject: str, html: str) -> None:
        captured["html"] = html

    monkeypatch.setattr("app.routers.auth.send_email", capture)
    await client.post("/api/v1/auth/forgot-password", json={"email": email})
    return re.search(r"token=([A-Za-z0-9._-]+)", captured["html"]).group(1)


async def test_forgot_password_always_accepts(client):
    response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 202


async def test_reset_password_changes_login(client, monkeypatch):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    token = await request_reset_token(client, monkeypatch, SIGNUP["email"])

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


async def test_reset_password_link_is_single_use(client, monkeypatch):
    await client.post("/api/v1/auth/signup", json=SIGNUP)
    token = await request_reset_token(client, monkeypatch, SIGNUP["email"])

    first = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "firstreset1"}
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "secondreset2"}
    )
    assert second.status_code == 401

    # The second attempt must not have changed the password.
    login = await client.post(
        "/api/v1/auth/login", json={"email": SIGNUP["email"], "password": "firstreset1"}
    )
    assert login.status_code == 200


async def test_reset_password_rejects_access_token(client):
    tokens = (await client.post("/api/v1/auth/signup", json=SIGNUP)).json()
    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": tokens["access_token"], "new_password": "x" * 10},
    )
    assert response.status_code == 401


async def test_reset_password_rejects_token_without_fingerprint(client, monkeypatch):
    """A reset token minted without a password fingerprint must be rejected."""
    from datetime import timedelta

    await client.post("/api/v1/auth/signup", json=SIGNUP)
    stale = create_token(SIGNUP["email"], "reset", timedelta(minutes=30))
    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": stale, "new_password": "nope123456"}
    )
    assert response.status_code == 401
