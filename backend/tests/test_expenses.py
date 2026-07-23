from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models import Expense, ExpenseCategory
from tests.test_calendar import _org_and_user
from tests.test_leases import make_property
from tests.test_properties_crud import landlord_headers


async def test_expense_round_trip(client, db_session):
    email = "expmodel@example.com"
    await landlord_headers(client, email)
    org_id, user_id = await _org_and_user(db_session, email)
    expense = Expense(
        organization_id=org_id,
        amount=Decimal("125.50"),
        spent_on=date(2026, 7, 10),
        category=ExpenseCategory.insurance,
        created_by=user_id,
    )
    db_session.add(expense)
    await db_session.commit()
    stored = (
        await db_session.execute(select(Expense).where(Expense.id == expense.id))
    ).scalar_one()
    assert stored.category == ExpenseCategory.insurance
    assert stored.amount == Decimal("125.50")
    assert stored.property_id is None


def _body(amount="80.00", spent_on="2026-07-05", category="utilities", **kw):
    return {"amount": amount, "spent_on": spent_on, "category": category, **kw}


async def test_create_list_delete_expense(client):
    headers = await landlord_headers(client, "expcrud@example.com")
    created = await client.post("/api/v1/expenses", json=_body(note="Water"), headers=headers)
    assert created.status_code == 201
    expense_id = created.json()["id"]
    listed = (await client.get("/api/v1/expenses", headers=headers)).json()
    assert [e["id"] for e in listed] == [expense_id]
    assert listed[0]["category"] == "utilities"
    assert (
        await client.delete(f"/api/v1/expenses/{expense_id}", headers=headers)
    ).status_code == 204


async def test_expense_rejects_foreign_property(client):
    owner = await landlord_headers(client, "expprop@example.com")
    stranger = await landlord_headers(client, "exppropx@example.com")
    foreign = await make_property(client, stranger, "9 Foreign St")
    r = await client.post("/api/v1/expenses", json=_body(property_id=foreign), headers=owner)
    assert r.status_code == 400


async def test_cross_org_expense_delete_is_404(client):
    owner = await landlord_headers(client, "expowner@example.com")
    expense_id = (await client.post("/api/v1/expenses", json=_body(), headers=owner)).json()["id"]
    stranger = await landlord_headers(client, "expthief@example.com")
    assert (
        await client.delete(f"/api/v1/expenses/{expense_id}", headers=stranger)
    ).status_code == 404
