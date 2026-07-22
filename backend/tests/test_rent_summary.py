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


async def test_buckets_overdue_upcoming_and_settled(client, db_session):
    email = "buckets@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Bucket St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=5))
    await _charge(db_session, org_id, lease_id, today + timedelta(days=5))

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    assert [g["property_address"] for g in body["overdue"]] == ["1 Bucket St"]
    assert [g["property_address"] for g in body["upcoming"]] == ["1 Bucket St"]
    assert float(body["overdue"][0]["total"]) == 1000.0
    assert float(body["upcoming"][0]["total"]) == 1000.0


async def test_two_overdue_charges_are_one_row_with_the_sum(client, db_session):
    email = "twoover@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Sum St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=40))
    await _charge(db_session, org_id, lease_id, today - timedelta(days=10))

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    assert len(body["overdue"]) == 1, "one lease must not produce two rows"
    group = body["overdue"][0]
    assert float(group["total"]) == 2000.0
    assert len(group["charges"]) == 2
    assert group["oldest_due"] == str(today - timedelta(days=40))


async def test_partly_paid_charge_counts_only_the_remainder(client, db_session):
    email = "partpaid@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Part St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=5))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 400, "paid_on": str(today), "method": "bank_transfer"},
        headers=headers,
    )

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    assert float(body["overdue"][0]["total"]) == 600.0


async def test_fully_paid_charge_appears_in_neither_bucket(client, db_session):
    email = "settled@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Settled St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=5))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 1000, "paid_on": str(today), "method": "bank_transfer"},
        headers=headers,
    )

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    assert body["overdue"] == []
    assert body["upcoming"] == []


async def test_prepaid_future_charge_drops_out_of_upcoming(client, db_session):
    email = "prepaid@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Prepaid St")
    await _charge(db_session, org_id, lease_id, today + timedelta(days=5))
    await client.post(
        f"/api/v1/leases/{lease_id}/payments",
        json={"amount": 1000, "paid_on": str(today), "method": "bank_transfer"},
        headers=headers,
    )

    body = (await client.get("/api/v1/rent/summary", headers=headers)).json()

    # The same "still owed" rule governs both buckets: paying ahead settles the
    # future charge, so it drops out of upcoming exactly as a settled charge
    # drops out of overdue. Both cards answer "what is still owed".
    assert body["upcoming"] == []
    assert body["overdue"] == []


async def test_summary_is_org_scoped(client, db_session):
    email = "mineonly@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    today = date.today()
    lease_id = await _lease(client, headers, "1 Mine St")
    await _charge(db_session, org_id, lease_id, today - timedelta(days=5))

    stranger = await landlord_headers(client, "notmine@example.com")
    body = (await client.get("/api/v1/rent/summary", headers=stranger)).json()

    assert body == {"overdue": [], "upcoming": []}
