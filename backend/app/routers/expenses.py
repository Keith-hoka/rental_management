import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Expense, Membership, Property
from app.routers.leases import manager
from app.schemas.expense import ExpenseCreate, ExpenseInfo

router = APIRouter(prefix="/api/v1", tags=["expenses"])


async def _check_property(property_id, membership: Membership, session: AsyncSession) -> None:
    """A property link must point inside the caller's own organization."""
    if property_id is None:
        return
    owned = (
        await session.execute(
            select(Property.id).where(
                Property.id == property_id,
                Property.organization_id == membership.organization_id,
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=400, detail="Unknown property")


@router.post("/expenses", status_code=201, response_model=ExpenseInfo)
async def create_expense(
    body: ExpenseCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Expense:
    """Record an expense for the organization."""
    await _check_property(body.property_id, membership, session)
    expense = Expense(
        organization_id=membership.organization_id,
        amount=body.amount,
        spent_on=body.spent_on,
        category=body.category,
        note=body.note,
        property_id=body.property_id,
        created_by=membership.user_id,
    )
    session.add(expense)
    await session.commit()
    await session.refresh(expense)
    return expense


@router.get("/expenses", response_model=list[ExpenseInfo])
async def list_expenses(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Expense]:
    """The organization's expenses, most recent spend first."""
    return list(
        (
            await session.execute(
                select(Expense)
                .where(Expense.organization_id == membership.organization_id)
                .order_by(Expense.spent_on.desc(), Expense.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


@router.delete("/expenses/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete an expense."""
    expense = (
        await session.execute(
            select(Expense).where(
                Expense.id == expense_id,
                Expense.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if expense is None:
        raise HTTPException(status_code=404, detail="Expense not found")
    await session.delete(expense)
    await session.commit()
    return Response(status_code=204)
