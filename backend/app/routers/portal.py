from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models import Lease, LeaseTenant, Membership, Property, Role, User
from app.routers.leases import _lease_state
from app.schemas.tenant import TenantLease

router = APIRouter(prefix="/api/v1/me", tags=["portal"])


@router.get("/leases", response_model=list[TenantLease])
async def my_leases(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TenantLease]:
    """List leases the current user is a tenant of, with landlord contact."""
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
            )
        )
    return leases
