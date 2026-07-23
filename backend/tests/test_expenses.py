from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.models import Expense, ExpenseCategory
from tests.test_calendar import _org_and_user
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
