import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models import Lease, LeaseTenant, Membership, Property, Role, User
from app.routers.leases import _lease_state
from app.schemas.charge import ChargeInfo
from app.schemas.tenant import TenantLease
from app.services.payments import lease_balance, lease_statuses

router = APIRouter(prefix="/api/v1/me", tags=["portal"])


@router.get("/leases", response_model=list[TenantLease])
async def my_leases(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TenantLease]:
    """List leases the current user is a tenant of, with landlord contact and balance."""
    today = datetime.now(UTC).date()
    result = await session.execute(
        select(Lease, Property.address)
        .join(LeaseTenant, LeaseTenant.lease_id == Lease.id)
        .join(Property, Property.id == Lease.property_id)
        .where(LeaseTenant.user_id == user.id)
        .order_by(Lease.start_date.desc())
    )

    leases: list[TenantLease] = []
    for lease, address in result.all():
        landlord = (
            await session.execute(
                select(User.name, User.email, User.phone)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.organization_id == lease.organization_id,
                    Membership.role == Role.landlord,
                )
            )
        ).first()
        balance = await lease_balance(session, lease.id, today)
        leases.append(
            TenantLease(
                id=lease.id,
                property_address=address,
                rent_amount=lease.rent_amount,
                rent_frequency=lease.rent_frequency,
                start_date=lease.start_date,
                end_date=lease.end_date,
                bond_amount=lease.bond_amount,
                notice_period_days=lease.notice_period_days,
                state=_lease_state(lease, today),
                landlord_name=landlord.name if landlord else "",
                landlord_email=landlord.email if landlord else "",
                landlord_phone=landlord.phone if landlord else None,
                outstanding=balance.outstanding,
                overdue_amount=balance.overdue_amount,
            )
        )
    return leases


@router.get("/leases/{lease_id}/charges", response_model=list[ChargeInfo])
async def my_lease_charges(
    lease_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ChargeInfo]:
    """List rent charges with status for a lease the current user is a tenant of."""
    owned = (
        await session.execute(
            select(LeaseTenant.id).where(
                LeaseTenant.lease_id == lease_id, LeaseTenant.user_id == user.id
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    statuses = await lease_statuses(session, lease_id, datetime.now(UTC).date())
    statuses.reverse()
    return [
        ChargeInfo(
            id=s.charge.id,
            period_start=s.charge.period_start,
            period_end=s.charge.period_end,
            due_date=s.charge.due_date,
            amount_due=s.charge.amount_due,
            amount_paid=s.amount_paid,
            status=s.status,
            overdue=s.overdue,
        )
        for s in statuses
    ]
