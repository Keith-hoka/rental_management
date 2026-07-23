from sqlalchemy import select

from app.models import Invitation, Notification, User
from tests.test_invitations import landlord_headers
from tests.test_portal import make_lease, onboard_tenant


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


async def _invitation_accepted_rows(db_session):
    return (
        (
            await db_session.execute(
                select(Notification).where(Notification.category == "invitation_accepted")
            )
        )
        .scalars()
        .all()
    )


async def test_accepting_a_team_invite_notifies_the_inviting_manager(client, db_session):
    headers = await landlord_headers(client, "invnotify@example.com")
    token = await create_invite(client, db_session, headers, email="pmnew@example.com")

    await client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "name": "Pam", "password": "pmsecret1"},
    )

    rows = await _invitation_accepted_rows(db_session)
    landlord = (
        await db_session.execute(select(User).where(User.email == "invnotify@example.com"))
    ).scalar_one()
    # The inviting landlord is notified; the new manager is not told about themselves.
    assert [n.user_id for n in rows] == [landlord.id]
    assert rows[0].link == "/app/team"
    assert "Pam" in rows[0].body


async def test_accepting_a_tenant_invite_notifies_the_manager(client, db_session):
    headers = await landlord_headers(client, "invtenant@example.com")
    lease_id = await make_lease(client, headers, "1 Notify Lease")
    await onboard_tenant(client, db_session, headers, lease_id, "tnew@example.com", name="Ted")

    rows = await _invitation_accepted_rows(db_session)
    landlord = (
        await db_session.execute(select(User).where(User.email == "invtenant@example.com"))
    ).scalar_one()
    assert [n.user_id for n in rows] == [landlord.id]
    assert rows[0].link == f"/app/leases/{lease_id}"
    assert "Ted" in rows[0].body


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
