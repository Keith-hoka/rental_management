import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Charge, ChargeReminder, Lease, Notification
from app.services.rent_reminders import run_rent_reminders
from tests.test_leases import lease_body, make_property
from tests.test_portal import onboard_tenant
from tests.test_properties_crud import landlord_headers

TODAY = date.today()


@pytest.fixture
def captured(monkeypatch):
    """Collect (to, subject) for every email the service sends."""
    calls: list[tuple[str, str]] = []

    async def fake_send(to, subject, html):
        calls.append((to, subject))

    monkeypatch.setattr("app.services.notify.send_email", fake_send)
    return calls


async def _lease(client, db_session, headers, address):
    property_id = await make_property(client, headers, address)
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(tenant_email="renter@example.com"),
            headers=headers,
        )
    ).json()["id"]
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    return lease_id, lease


async def _charge(db_session, lease, due_date, amount="1500"):
    charge = Charge(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        period_start=due_date,
        period_end=due_date + timedelta(days=29),
        due_date=due_date,
        amount_due=Decimal(amount),
    )
    db_session.add(charge)
    await db_session.commit()
    return charge


async def _notifications(db_session):
    # Ignore the acceptance notice that onboard_tenant now emits to the manager.
    return (
        (
            await db_session.execute(
                select(Notification).where(Notification.category != "invitation_accepted")
            )
        )
        .scalars()
        .all()
    )


async def test_due_soon_goes_to_tenants_only(client, db_session, captured):
    headers = await landlord_headers(client, "rrdue@example.com")
    _, lease = await _lease(client, db_session, headers, "Due St")
    await _charge(db_session, lease, TODAY + timedelta(days=2))

    assert await run_rent_reminders(db_session, TODAY) == 1

    recipients = {to for to, _ in captured}
    assert "renter@example.com" in recipients
    assert "rrdue@example.com" not in recipients  # the landlord is not told about upcoming rent
    # Nobody accepted a tenant invitation on this lease, so there is no account to post to;
    # the roster email above is the whole delivery. See the joined-tenant test below.
    assert await _notifications(db_session) == []


async def test_overdue_goes_to_tenants_and_managers(client, db_session, captured):
    headers = await landlord_headers(client, "rrover@example.com")
    _, lease = await _lease(client, db_session, headers, "Late St")
    await _charge(db_session, lease, TODAY - timedelta(days=7))

    assert await run_rent_reminders(db_session, TODAY) == 1

    recipients = {to for to, _ in captured}
    assert "renter@example.com" in recipients
    assert "rrover@example.com" in recipients
    rows = await _notifications(db_session)
    assert {r.category for r in rows} == {"rent_overdue"}


async def test_rerun_sends_nothing_more(client, db_session, captured):
    headers = await landlord_headers(client, "rrdedup@example.com")
    _, lease = await _lease(client, db_session, headers, "Dedup St")
    await _charge(db_session, lease, TODAY - timedelta(days=7))

    assert await run_rent_reminders(db_session, TODAY) == 1
    assert await run_rent_reminders(db_session, TODAY) == 0
    assert len(await _notifications(db_session)) == 1


async def test_partial_payment_still_reminded_with_remaining_balance(client, db_session, captured):
    headers = await landlord_headers(client, "rrpart@example.com")
    lease_id, lease = await _lease(client, db_session, headers, "Part St")
    await _charge(db_session, lease, TODAY - timedelta(days=7))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 500, "paid_on": str(TODAY), "method": "cash"},
        headers=headers,
    )

    assert await run_rent_reminders(db_session, TODAY) == 1

    body = (await _notifications(db_session))[0].body
    assert "1000" in body  # 1500 due minus 500 paid


async def test_paid_charge_is_skipped(client, db_session, captured):
    headers = await landlord_headers(client, "rrpaid@example.com")
    lease_id, lease = await _lease(client, db_session, headers, "Paid St")
    await _charge(db_session, lease, TODAY - timedelta(days=7))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 1500, "paid_on": str(TODAY), "method": "cash"},
        headers=headers,
    )

    assert await run_rent_reminders(db_session, TODAY) == 0
    assert await _notifications(db_session) == []


async def test_escalation_advances_over_time(client, db_session, captured):
    headers = await landlord_headers(client, "rresc@example.com")
    _, lease = await _lease(client, db_session, headers, "Esc St")
    due = TODAY - timedelta(days=7)
    charge = await _charge(db_session, lease, due)

    assert await run_rent_reminders(db_session, TODAY) == 1  # overdue_7
    assert await run_rent_reminders(db_session, due + timedelta(days=10)) == 0  # still overdue_7
    assert await run_rent_reminders(db_session, due + timedelta(days=14)) == 1  # overdue_14
    assert await run_rent_reminders(db_session, due + timedelta(days=30)) == 1  # overdue_30
    assert await run_rent_reminders(db_session, due + timedelta(days=60)) == 0  # capped

    kinds = (
        (
            await db_session.execute(
                select(ChargeReminder.kind).where(ChargeReminder.charge_id == charge.id)
            )
        )
        .scalars()
        .all()
    )
    assert set(kinds) == {"overdue_7", "overdue_14", "overdue_30"}


async def test_joined_tenant_gets_an_inbox_notification(client, db_session, captured):
    headers = await landlord_headers(client, "rrinbox@example.com")
    lease_id, lease = await _lease(client, db_session, headers, "Inbox St")
    await onboard_tenant(client, db_session, headers, lease_id, "rrinbox-t@example.com")
    await _charge(db_session, lease, TODAY + timedelta(days=2))

    await run_rent_reminders(db_session, TODAY)

    rows = await _notifications(db_session)
    assert len(rows) == 1  # tenants only for due_soon
    assert rows[0].link == f"/app/leases/{lease_id}"
