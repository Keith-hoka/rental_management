from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import CalendarEvent, Membership, User
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
