import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.models import Charge, Membership, User
from app.services.stats import dashboard_stats
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _org_id(db_session, email):
    return (
        await db_session.execute(
            select(Membership.organization_id)
            .join(User, User.id == Membership.user_id)
            .where(User.email == email)
        )
    ).scalar_one()


async def test_dashboard_stats(client, db_session):
    email = "stats1@example.com"
    headers = await landlord_headers(client, email)
    property_id = await make_property(client, headers)
    today = date.today()
    lease = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=30)),
                rent_amount=1000,
            ),
            headers=headers,
        )
    ).json()
    org_id = await _org_id(db_session, email)

    db_session.add(
        Charge(
            organization_id=org_id,
            lease_id=uuid.UUID(lease["id"]),
            period_start=date(2020, 1, 1),
            period_end=date(2020, 1, 31),
            due_date=date(2020, 1, 1),
            amount_due=1000,
        )
    )
    await db_session.commit()
    await client.post(
        f"/api/v1/leases/{lease['id']}/payments",
        json={"amount": 300, "paid_on": str(today), "method": "cash", "note": None},
        headers=headers,
    )

    stats = await dashboard_stats(db_session, org_id, today)

    assert float(stats.collected_this_month) == 300.0
    assert float(stats.outstanding) == 700.0
    assert float(stats.overdue) == 700.0
    assert stats.properties_total == 1
    assert stats.properties_occupied == 1
    assert stats.active_leases == 1
    assert stats.tenants == 0
    assert len(stats.monthly_income) == 6
    assert stats.monthly_income[-1].month == f"{today.year:04d}-{today.month:02d}"
    assert float(stats.monthly_income[-1].amount) == 300.0


async def test_empty_org_zeros(client, db_session):
    email = "statsempty@example.com"
    await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)

    stats = await dashboard_stats(db_session, org_id, date.today())

    assert float(stats.outstanding) == 0.0
    assert float(stats.overdue) == 0.0
    assert float(stats.collected_this_month) == 0.0
    assert stats.properties_total == 0
    assert stats.properties_occupied == 0
    assert stats.active_leases == 0
    assert stats.tenants == 0
    assert len(stats.monthly_income) == 6
    assert all(float(m.amount) == 0.0 for m in stats.monthly_income)


async def test_stats_org_isolation(client, db_session):
    a_email = "statsa@example.com"
    a_headers = await landlord_headers(client, a_email)
    a_property = await make_property(client, a_headers)
    today = date.today()
    a_lease = (
        await client.post(
            f"/api/v1/properties/{a_property}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=30)),
            ),
            headers=a_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/leases/{a_lease['id']}/payments",
        json={"amount": 500, "paid_on": str(today), "method": "cash", "note": None},
        headers=a_headers,
    )

    await landlord_headers(client, "statsb@example.com")
    b_org = await _org_id(db_session, "statsb@example.com")

    stats = await dashboard_stats(db_session, b_org, today)
    assert float(stats.collected_this_month) == 0.0
    assert stats.properties_total == 0
