import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models import CalendarEvent, Charge, MaintenanceRequest, Membership, User
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _org_and_user(db_session, email):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    org_id = (
        await db_session.execute(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        )
    ).scalar_one()
    return org_id, user.id


async def test_calendar_event_round_trip(client, db_session):
    email = "calmodel@example.com"
    await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)

    start = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    event = CalendarEvent(
        organization_id=org_id,
        title="Inspection",
        start_at=start,
        end_at=start + timedelta(hours=1),
        created_by=user_id,
    )
    db_session.add(event)
    await db_session.commit()

    stored = (
        await db_session.execute(select(CalendarEvent).where(CalendarEvent.id == event.id))
    ).scalar_one()
    assert stored.title == "Inspection"
    assert stored.property_id is None


def _event_body(start="2026-08-01T09:00:00Z", end="2026-08-01T10:00:00Z", **kw):
    return {"title": "Viewing", "start_at": start, "end_at": end, **kw}


async def test_create_event(client):
    headers = await landlord_headers(client, "calcreate@example.com")
    r = await client.post("/api/v1/calendar/events", json=_event_body(), headers=headers)
    assert r.status_code == 201
    assert r.json()["title"] == "Viewing"


async def test_create_event_rejects_end_before_start(client):
    headers = await landlord_headers(client, "calbad@example.com")
    body = _event_body(start="2026-08-01T10:00:00Z", end="2026-08-01T09:00:00Z")
    r = await client.post("/api/v1/calendar/events", json=body, headers=headers)
    assert r.status_code == 400


async def test_create_event_rejects_foreign_property(client):
    owner = await landlord_headers(client, "calpropowner@example.com")
    stranger = await landlord_headers(client, "calpropstranger@example.com")
    foreign_property = await make_property(client, stranger, "9 Foreign St")
    r = await client.post(
        "/api/v1/calendar/events",
        json=_event_body(property_id=foreign_property),
        headers=owner,
    )
    assert r.status_code == 400


async def test_cross_org_event_is_404(client):
    owner = await landlord_headers(client, "calowner@example.com")
    event_id = (
        await client.post("/api/v1/calendar/events", json=_event_body(), headers=owner)
    ).json()["id"]
    stranger = await landlord_headers(client, "calthief@example.com")
    assert (
        await client.patch(
            f"/api/v1/calendar/events/{event_id}", json={"title": "x"}, headers=stranger
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/calendar/events/{event_id}", headers=stranger)
    ).status_code == 404


async def test_update_and_delete_event(client):
    headers = await landlord_headers(client, "caledit@example.com")
    event_id = (
        await client.post("/api/v1/calendar/events", json=_event_body(), headers=headers)
    ).json()["id"]
    patched = await client.patch(
        f"/api/v1/calendar/events/{event_id}", json={"title": "Renamed"}, headers=headers
    )
    assert patched.json()["title"] == "Renamed"
    assert (
        await client.delete(f"/api/v1/calendar/events/{event_id}", headers=headers)
    ).status_code == 204


async def _lease_in_range(client, headers, address):
    """A lease whose start and end both fall within a +/-40-day window of today."""
    property_id = await make_property(client, headers, address)
    today = date.today()
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=10)),
            ),
            headers=headers,
        )
    ).json()["id"]
    return property_id, lease_id


async def test_feed_returns_all_kinds(client, db_session):
    email = "calfeed@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    property_id, lease_id = await _lease_in_range(client, headers, "1 Calendar Way")

    today = date.today()
    db_session.add(
        Charge(
            organization_id=org_id,
            lease_id=uuid.UUID(lease_id),
            period_start=today,
            period_end=today + timedelta(days=29),
            due_date=today,
            amount_due=Decimal("1500"),
        )
    )
    db_session.add(
        MaintenanceRequest(
            organization_id=org_id,
            property_id=uuid.UUID(property_id),
            lease_id=uuid.UUID(lease_id),
            created_by=user_id,
            title="Leaking tap",
            description="Kitchen",
        )
    )
    await db_session.commit()

    await client.post(
        "/api/v1/calendar/events",
        json=_event_body(start=f"{today}T09:00:00Z", end=f"{today}T10:00:00Z", title="Site visit"),
        headers=headers,
    )

    start = today - timedelta(days=40)
    end = today + timedelta(days=40)
    body = (await client.get(f"/api/v1/calendar?start={start}&end={end}", headers=headers)).json()

    kinds = {e["kind"] for e in body}
    assert kinds == {"lease_start", "lease_end", "rent_due", "maintenance", "event"}

    event = next(e for e in body if e["kind"] == "event")
    assert event["all_day"] is False
    assert event["event_id"]
    assert event["start_at"]
    lease_end = next(e for e in body if e["kind"] == "lease_end")
    assert lease_end["all_day"] is True
    assert lease_end["date"]
    assert lease_end["link"] == f"/app/leases/{lease_id}"
    rent = next(e for e in body if e["kind"] == "rent_due")
    assert rent["link"] == f"/app/leases/{lease_id}"
    maint = next(e for e in body if e["kind"] == "maintenance")
    assert maint["link"] == "/app/maintenance"


async def test_feed_is_org_scoped(client, db_session):
    owner = await landlord_headers(client, "calfeedowner@example.com")
    await _lease_in_range(client, owner, "2 Private Way")
    stranger = await landlord_headers(client, "calfeedthief@example.com")
    today = date.today()
    body = (
        await client.get(
            f"/api/v1/calendar?start={today - timedelta(days=40)}&end={today + timedelta(days=40)}",
            headers=stranger,
        )
    ).json()
    assert body == []
