from sqlalchemy import select

from app.models import Membership, Notification, User
from tests.test_properties_crud import landlord_headers


async def _user_and_org(db_session, email):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    org_id = (
        await db_session.execute(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        )
    ).scalar_one()
    return user, org_id


async def _add(db_session, user, org_id, title):
    db_session.add(
        Notification(
            organization_id=org_id,
            user_id=user.id,
            category="lease_expiry",
            title=title,
            body="body",
            link="/app",
        )
    )
    await db_session.commit()


async def test_lists_own_notifications(client, db_session):
    email = "napi@example.com"
    headers = await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)
    await _add(db_session, user, org_id, "First")

    body = (await client.get("/api/v1/me/notifications", headers=headers)).json()
    assert len(body) == 1
    assert body[0]["title"] == "First"
    assert body[0]["read_at"] is None


async def test_unread_filter_and_count(client, db_session):
    email = "nunread@example.com"
    headers = await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)
    await _add(db_session, user, org_id, "One")

    counted = await client.get("/api/v1/me/notifications/unread_count", headers=headers)
    assert counted.json()["count"] == 1
    unread = (await client.get("/api/v1/me/notifications?unread=true", headers=headers)).json()
    assert len(unread) == 1


async def test_mark_read_and_read_all(client, db_session):
    email = "nread@example.com"
    headers = await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)
    await _add(db_session, user, org_id, "One")
    await _add(db_session, user, org_id, "Two")

    listed = (await client.get("/api/v1/me/notifications", headers=headers)).json()
    marked = await client.post(f"/api/v1/me/notifications/{listed[0]['id']}/read", headers=headers)
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None

    counted = await client.get("/api/v1/me/notifications/unread_count", headers=headers)
    assert counted.json()["count"] == 1

    cleared = await client.post("/api/v1/me/notifications/read_all", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["count"] == 0

    counted = await client.get("/api/v1/me/notifications/unread_count", headers=headers)
    assert counted.json()["count"] == 0


async def test_cannot_read_another_users_notification(client, db_session):
    owner_email = "nown@example.com"
    await landlord_headers(client, owner_email)
    owner, org_id = await _user_and_org(db_session, owner_email)
    await _add(db_session, owner, org_id, "Theirs")
    row = (await db_session.execute(select(Notification))).scalars().first()

    other = await landlord_headers(client, "nother@example.com")
    resp = await client.post(f"/api/v1/me/notifications/{row.id}/read", headers=other)
    assert resp.status_code == 404
    assert (await client.get("/api/v1/me/notifications", headers=other)).json() == []


async def test_requires_auth(client):
    assert (await client.get("/api/v1/me/notifications")).status_code == 401


async def test_delete_own_notification(client, db_session):
    email = "ndel@example.com"
    headers = await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)
    await _add(db_session, user, org_id, "Goes away")
    await _add(db_session, user, org_id, "Stays")
    listed = (await client.get("/api/v1/me/notifications", headers=headers)).json()
    doomed = next(n for n in listed if n["title"] == "Goes away")

    assert (
        await client.delete(f"/api/v1/me/notifications/{doomed['id']}", headers=headers)
    ).status_code == 204

    remaining = (await client.get("/api/v1/me/notifications", headers=headers)).json()
    assert [n["title"] for n in remaining] == ["Stays"]


async def test_cannot_delete_another_users_notification(client, db_session):
    owner_email = "ndown@example.com"
    await landlord_headers(client, owner_email)
    owner, org_id = await _user_and_org(db_session, owner_email)
    await _add(db_session, owner, org_id, "Not yours")
    row = (
        (await db_session.execute(select(Notification).where(Notification.user_id == owner.id)))
        .scalars()
        .first()
    )

    other = await landlord_headers(client, "ndother@example.com")
    resp = await client.delete(f"/api/v1/me/notifications/{row.id}", headers=other)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Notification not found"

    still_there = (
        await db_session.execute(select(Notification).where(Notification.id == row.id))
    ).scalar_one_or_none()
    assert still_there is not None, "another user's delete must not remove the row"
