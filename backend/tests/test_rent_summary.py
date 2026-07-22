import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import event, select

from app.models import Charge, Membership, User
from app.services.payments import org_charge_statuses
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


async def _lease(client, headers, address):
    property_id = await make_property(client, headers, address)
    return (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]


async def _charge(db_session, org_id, lease_id, due: date, amount="1000"):
    db_session.add(
        Charge(
            organization_id=org_id,
            lease_id=uuid.UUID(lease_id),
            period_start=due,
            period_end=due + timedelta(days=29),
            due_date=due,
            amount_due=Decimal(amount),
        )
    )
    await db_session.commit()


def _count_queries(db_session):
    """Count SQL statements issued on this session's engine."""
    counter = {"n": 0}
    engine = db_session.get_bind()

    def before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", before)
    counter["stop"] = lambda: event.remove(engine, "before_cursor_execute", before)
    return counter


async def test_query_count_does_not_grow_with_lease_count(client, db_session):
    email = "qcount@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()

    lease_id = await _lease(client, headers, "1 Query St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=3))

    counter = _count_queries(db_session)
    await org_charge_statuses(db_session, org_id, today)
    one_lease = counter["n"]
    counter["stop"]()

    for i in range(4):
        extra = await _lease(client, headers, f"{i + 2} Query St")
        await _charge(db_session, org_id, extra, today - timedelta(days=3))

    counter = _count_queries(db_session)
    await org_charge_statuses(db_session, org_id, today)
    five_leases = counter["n"]
    counter["stop"]()

    assert five_leases == one_lease, (
        f"query count grew from {one_lease} to {five_leases} with lease count; "
        "the per-lease loop is back"
    )
