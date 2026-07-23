import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models import Charge, Expense, ExpenseCategory, Lease
from tests.test_calendar import _org_and_user
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def test_monthly_report_aggregates(client, db_session):
    email = "rep@example.com"
    headers = await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    property_id = await make_property(client, headers, "1 Report St")
    today = date.today()
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases",
            json=lease_body(
                start_date=str(today - timedelta(days=1)),
                end_date=str(today + timedelta(days=30)),
            ),
            headers=headers,
        )
    ).json()["id"]
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    db_session.add(
        Charge(
            organization_id=org_id,
            lease_id=lease.id,
            period_start=today,
            period_end=today + timedelta(days=29),
            due_date=today,
            amount_due=Decimal("1000"),
        )
    )
    db_session.add(
        Expense(
            organization_id=org_id,
            amount=Decimal("200"),
            spent_on=today,
            category=ExpenseCategory.maintenance,
            property_id=uuid.UUID(property_id),
            created_by=user_id,
        )
    )
    db_session.add(
        Expense(
            organization_id=org_id,
            amount=Decimal("50"),
            spent_on=today,
            category=ExpenseCategory.insurance,
            created_by=user_id,
        )
    )
    await db_session.commit()

    body = (await client.get("/api/v1/reports/monthly?months=12", headers=headers)).json()

    assert len(body["months"]) == 12
    this_month = f"{today.year:04d}-{today.month:02d}"
    point = next(m for m in body["months"] if m["month"] == this_month)
    assert point["income"] == 1000.0
    assert point["expenses"] == 250.0
    assert point["net"] == 750.0
    cats = {c["category"]: c["total"] for c in body["by_category"]}
    assert cats["maintenance"] == 200.0
    assert cats["insurance"] == 50.0
    props = {p["address"]: p for p in body["by_property"]}
    assert props["1 Report St"]["income"] == 1000.0
    assert props["1 Report St"]["expenses"] == 200.0
    assert props["(Unassigned)"]["expenses"] == 50.0


async def test_monthly_report_is_org_scoped(client, db_session):
    stranger = await landlord_headers(client, "repother@example.com")
    body = (await client.get("/api/v1/reports/monthly?months=3", headers=stranger)).json()
    assert body["by_category"] == []
    assert body["by_property"] == []
    assert all(m["income"] == 0 and m["expenses"] == 0 for m in body["months"])
