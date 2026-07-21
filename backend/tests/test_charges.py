from datetime import date

from sqlalchemy import select

from app.models import Charge, Lease, LeaseFrequency
from app.services.charges import _period_start, _period_starts, generate_charges
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


def test_period_start_monthly_clamps_month_end():
    assert _period_start(date(2026, 1, 31), LeaseFrequency.monthly, 1) == date(2026, 2, 28)
    assert _period_start(date(2026, 1, 31), LeaseFrequency.monthly, 2) == date(2026, 3, 31)


def test_period_start_weekly():
    assert _period_start(date(2026, 1, 1), LeaseFrequency.weekly, 3) == date(2026, 1, 22)


def test_period_start_fortnightly():
    assert _period_start(date(2026, 1, 1), LeaseFrequency.fortnightly, 2) == date(2026, 1, 29)


def test_period_starts_monthly_up_to_horizon():
    lease = Lease(
        start_date=date(2026, 1, 15),
        end_date=date(2026, 12, 31),
        rent_frequency=LeaseFrequency.monthly,
    )
    assert _period_starts(lease, date(2026, 3, 20)) == [
        date(2026, 1, 15),
        date(2026, 2, 15),
        date(2026, 3, 15),
    ]


def test_period_starts_stops_at_lease_end():
    lease = Lease(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 15),
        rent_frequency=LeaseFrequency.monthly,
    )
    # horizon is far out; the cap is lease.end_date, so only Jan 1 and Feb 1 qualify.
    assert _period_starts(lease, date(2026, 12, 31)) == [date(2026, 1, 1), date(2026, 2, 1)]


async def _make_lease(client, headers, property_id, **overrides):
    body = lease_body(**overrides)
    return (
        await client.post(f"/api/v1/properties/{property_id}/leases", json=body, headers=headers)
    ).json()


async def test_generates_monthly_charges_up_to_horizon(client, db_session):
    headers = await landlord_headers(client, "chg1@example.com")
    property_id = await make_property(client, headers)
    await _make_lease(
        client,
        headers,
        property_id,
        start_date="2026-01-01",
        end_date="2026-12-31",
        rent_frequency="monthly",
        rent_amount=1500,
    )

    count = await generate_charges(db_session, date(2026, 3, 20))

    assert count == 3
    charges = (
        (await db_session.execute(select(Charge).order_by(Charge.period_start))).scalars().all()
    )
    assert [c.period_start for c in charges] == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    assert all(c.due_date == c.period_start for c in charges)
    assert charges[0].period_end == date(2026, 1, 31)
    assert float(charges[0].amount_due) == 1500.0


async def test_generation_is_idempotent(client, db_session):
    headers = await landlord_headers(client, "chgidem@example.com")
    property_id = await make_property(client, headers)
    await _make_lease(client, headers, property_id, start_date="2026-01-01", end_date="2026-12-31")

    first = await generate_charges(db_session, date(2026, 3, 20))
    second = await generate_charges(db_session, date(2026, 3, 20))

    assert first == 3
    assert second == 0


async def test_horizon_boundary_is_inclusive(client, db_session):
    headers = await landlord_headers(client, "chghz@example.com")
    property_id = await make_property(client, headers)
    # Weekly from 2026-06-01; with lead 7, horizon = 2026-06-08.
    await _make_lease(
        client,
        headers,
        property_id,
        start_date="2026-06-01",
        end_date="2026-12-31",
        rent_frequency="weekly",
    )

    await generate_charges(db_session, date(2026, 6, 1))

    starts = {c.period_start for c in (await db_session.execute(select(Charge))).scalars().all()}
    assert date(2026, 6, 8) in starts  # today + 7 == horizon, included
    assert date(2026, 6, 15) not in starts  # beyond horizon, excluded


async def test_last_period_end_capped_at_lease_end(client, db_session):
    headers = await landlord_headers(client, "chgcap@example.com")
    property_id = await make_property(client, headers)
    await _make_lease(
        client,
        headers,
        property_id,
        start_date="2026-01-01",
        end_date="2026-03-15",
        rent_frequency="monthly",
    )

    await generate_charges(db_session, date(2026, 3, 15))

    charges = (
        (await db_session.execute(select(Charge).order_by(Charge.period_start))).scalars().all()
    )
    assert [c.period_start for c in charges] == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    assert charges[-1].period_end == date(2026, 3, 15)


async def test_backfills_past_periods(client, db_session):
    headers = await landlord_headers(client, "chgback@example.com")
    property_id = await make_property(client, headers)
    await _make_lease(client, headers, property_id, start_date="2026-01-01", end_date="2026-12-31")

    count = await generate_charges(db_session, date(2026, 4, 1))

    assert count == 4  # Jan, Feb, Mar, Apr (Apr 1 <= horizon Apr 8)


async def test_amount_snapshot_unchanged_after_rent_edit(client, db_session):
    headers = await landlord_headers(client, "chgsnap@example.com")
    property_id = await make_property(client, headers)
    created = await _make_lease(
        client,
        headers,
        property_id,
        start_date="2026-01-01",
        end_date="2026-12-31",
        rent_frequency="monthly",
        rent_amount=1500,
    )

    await generate_charges(db_session, date(2026, 1, 20))  # Jan charge at 1500
    await client.patch(
        f"/api/v1/leases/{created['id']}", json={"rent_amount": 2000}, headers=headers
    )
    # Mimic a fresh scheduler run: drop cached lease state so the new rent is read.
    db_session.expire_all()
    await generate_charges(db_session, date(2026, 2, 20))  # Feb charge at 2000

    amounts = {
        c.period_start: float(c.amount_due)
        for c in (await db_session.execute(select(Charge))).scalars().all()
    }
    assert amounts[date(2026, 1, 1)] == 1500.0
    assert amounts[date(2026, 2, 1)] == 2000.0
