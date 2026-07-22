from datetime import date, timedelta

from sqlalchemy import select

from app.models import Notification
from app.services.reminders import run_expiry_reminders
from tests.test_leases import lease_body, make_property
from tests.test_portal import onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _lease_ending_in(client, headers, address, days):
    property_id = await make_property(client, headers, address)
    today = date.today()
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=days)),
            ),
            headers=headers,
        )
    ).json()["id"]


async def test_expiry_reminder_writes_notifications(client, db_session):
    headers = await landlord_headers(client, "exn@example.com")
    lease_id = await _lease_ending_in(client, headers, "Notify Way", 7)
    await onboard_tenant(client, db_session, headers, lease_id, "exn-t@example.com")

    sent = await run_expiry_reminders(db_session, date.today())
    assert sent == 1

    rows = (await db_session.execute(select(Notification))).scalars().all()
    # One for the landlord user, one for the joined tenant user.
    assert len(rows) == 2
    assert {r.category for r in rows} == {"lease_expiry"}
    assert all(r.link == f"/app/leases/{lease_id}" for r in rows)
    assert all(r.read_at is None for r in rows)


async def test_rerunning_adds_no_duplicate_notifications(client, db_session):
    headers = await landlord_headers(client, "exn2@example.com")
    lease_id = await _lease_ending_in(client, headers, "Dedup Way", 7)
    await onboard_tenant(client, db_session, headers, lease_id, "exn2-t@example.com")

    await run_expiry_reminders(db_session, date.today())
    assert await run_expiry_reminders(db_session, date.today()) == 0

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert len(rows) == 2
