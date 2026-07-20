from sqlalchemy import select

from app.models import Invitation
from tests.test_invitations import landlord_headers


async def create_invite(client, db_session, headers, email="pm@example.com") -> str:
    """Create an invitation and read its token from the DB (the API never returns it)."""
    await client.post(
        "/api/v1/invitations",
        json={"email": email, "role": "property_manager"},
        headers=headers,
    )
    invite = (
        (await db_session.execute(select(Invitation).where(Invitation.email == email)))
        .scalars()
        .first()
    )
    return invite.token


async def test_accept_invitation_creates_property_manager(client, db_session):
    headers = await landlord_headers(client, "inviter@example.com")
    token = await create_invite(client, db_session, headers)

    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "PM", "password": "pmsecret1"},
    )
    assert response.status_code == 201
    assert response.json()["access_token"]

    # The new property_manager can log in and read properties (allowed for the role).
    login = await client.post(
        "/api/v1/auth/login", json={"email": "pm@example.com", "password": "pmsecret1"}
    )
    assert login.status_code == 200
    pm_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await client.get("/api/v1/auth/me", headers=pm_headers)
    assert me.json()["role"] == "property_manager"
    props = await client.get("/api/v1/properties", headers=pm_headers)
    assert props.status_code == 200


async def test_accept_invitation_rejects_unknown_token(client):
    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": "does-not-exist", "name": "X", "password": "secret123"},
    )
    assert response.status_code == 400


async def test_accept_invitation_is_single_use(client, db_session):
    headers = await landlord_headers(client, "inviter2@example.com")
    token = await create_invite(client, db_session, headers, email="pm2@example.com")

    first = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "PM", "password": "pmsecret1"},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "PM", "password": "pmsecret1"},
    )
    assert second.status_code == 400


async def test_accept_invitation_conflicts_when_email_registered(client, db_session):
    headers = await landlord_headers(client, "inviter3@example.com")
    # Register the invitee email first via signup.
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "already@example.com",
            "password": "secret123",
            "name": "Already",
            "organization_name": "Their Org",
        },
    )
    token = await create_invite(client, db_session, headers, email="already@example.com")

    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "Dup", "password": "secret123"},
    )
    assert response.status_code == 409
