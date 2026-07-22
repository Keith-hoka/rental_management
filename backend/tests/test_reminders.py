from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import LeaseReminder
from app.services.reminders import _bucket, run_expiry_reminders
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers

THRESHOLDS = [60, 30, 7]


@pytest.mark.parametrize(
    ("days_left", "expected"),
    [
        (61, None),
        (60, 60),
        (45, 60),
        (31, 60),
        (30, 30),
        (8, 30),
        (7, 7),
        (0, 7),
        (-1, None),
    ],
)
def test_bucket(days_left, expected):
    assert _bucket(days_left, THRESHOLDS) == expected


@pytest.fixture
def captured(monkeypatch):
    """Collect (to, subject) for every send_email call the service makes."""
    calls: list[tuple[str, str]] = []

    async def fake_send(to, subject, html):
        calls.append((to, subject))

    monkeypatch.setattr("app.services.notify.send_email", fake_send)
    return calls


async def _make_lease(client, headers, property_id, *, end_date, **overrides):
    body = lease_body(
        start_date=str(date.today() - timedelta(days=1)),
        end_date=str(end_date),
        **overrides,
    )
    return (
        await client.post(f"/api/v1/properties/{property_id}/leases", json=body, headers=headers)
    ).json()["id"]


async def test_sends_to_managers_and_roster(client, db_session, captured):
    headers = await landlord_headers(client, "send7@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await _make_lease(
        client,
        headers,
        property_id,
        end_date=today + timedelta(days=7),
        tenant_email="main@example.com",
        co_tenants=[{"name": "Co", "email": "co@example.com", "phone": ""}],
    )

    count = await run_expiry_reminders(db_session, today)

    assert count == 1
    recipients = {to for to, _ in captured}
    assert "send7@example.com" in recipients  # landlord (manager)
    assert "main@example.com" in recipients  # main tenant
    assert "co@example.com" in recipients  # co-tenant


async def test_dedup_runs_twice_sends_once(client, db_session, captured):
    headers = await landlord_headers(client, "dedup@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await _make_lease(client, headers, property_id, end_date=today + timedelta(days=7))

    first = await run_expiry_reminders(db_session, today)
    second = await run_expiry_reminders(db_session, today)

    assert first == 1
    assert second == 0


async def test_bucket_advances_over_time(client, db_session, captured):
    headers = await landlord_headers(client, "advance@example.com")
    property_id = await make_property(client, headers)
    base = date.today()
    end = base + timedelta(days=30)
    await _make_lease(client, headers, property_id, end_date=end)

    assert await run_expiry_reminders(db_session, base) == 1  # 30 days -> bucket 30
    assert await run_expiry_reminders(db_session, base + timedelta(days=22)) == 0  # 8 left
    assert await run_expiry_reminders(db_session, base + timedelta(days=23)) == 1  # 7 -> bucket 7


async def test_window_excludes_far(client, db_session, captured):
    headers = await landlord_headers(client, "windowfar@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    # 61 days out: outside the window.
    await _make_lease(client, headers, property_id, end_date=today + timedelta(days=61))
    assert await run_expiry_reminders(db_session, today) == 0


async def test_window_excludes_ended(client, db_session, captured):
    headers = await landlord_headers(client, "windowended@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    # Ended yesterday: end_date < today, excluded by the window.
    body = lease_body(
        start_date=str(today - timedelta(days=2)),
        end_date=str(today - timedelta(days=1)),
    )
    await client.post(f"/api/v1/properties/{property_id}/leases", json=body, headers=headers)
    assert await run_expiry_reminders(db_session, today) == 0


async def test_sends_on_expiry_day(client, db_session, captured):
    headers = await landlord_headers(client, "expiryday@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    await _make_lease(client, headers, property_id, end_date=today)  # 0 days left
    assert await run_expiry_reminders(db_session, today) == 1


async def test_email_failure_still_records(client, db_session, monkeypatch):
    async def boom(to, subject, html):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("app.services.notify.send_email", boom)
    headers = await landlord_headers(client, "boom@example.com")
    property_id = await make_property(client, headers)
    today = date.today()
    lease_id = await _make_lease(client, headers, property_id, end_date=today + timedelta(days=7))

    count = await run_expiry_reminders(db_session, today)

    assert count == 1
    rows = (
        (await db_session.execute(select(LeaseReminder).where(LeaseReminder.threshold_days == 7)))
        .scalars()
        .all()
    )
    assert any(str(r.lease_id) == lease_id for r in rows)


async def test_renewed_leases_stop_getting_expiry_reminders(client, db_session, captured):
    headers = await landlord_headers(client, "renewed@example.com")
    property_id = await make_property(client, headers, "9 Reminder St")
    today = date.today()
    lease_id = await _make_lease(client, headers, property_id, end_date=today + timedelta(days=7))

    await client.post(
        f"/api/v1/leases/{lease_id}/renew",
        json={"end_date": str(today + timedelta(days=372))},
        headers=headers,
    )

    sent = await run_expiry_reminders(db_session, today)

    assert sent == 0, "a renewed lease should not generate an expiry reminder"
    assert captured == [], "no reminder email should go out for a renewed lease"
