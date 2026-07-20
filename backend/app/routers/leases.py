import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Lease, Membership, Role
from app.routers.properties import get_owned_property
from app.schemas.lease import LeaseCreate, LeaseResponse

router = APIRouter(prefix="/api/v1", tags=["leases"])

manager = require_roles(Role.landlord, Role.property_manager)


async def overlapping_lease_exists(
    session: AsyncSession,
    property_id: uuid.UUID,
    start_date: date,
    end_date: date,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """True if another lease on the property overlaps the given date range (inclusive)."""
    query = select(Lease.id).where(
        Lease.property_id == property_id,
        Lease.start_date <= end_date,
        start_date <= Lease.end_date,
    )
    if exclude_id is not None:
        query = query.where(Lease.id != exclude_id)
    return (await session.execute(query)).first() is not None


@router.post("/properties/{property_id}/leases", status_code=201, response_model=LeaseResponse)
async def create_lease(
    property_id: uuid.UUID,
    body: LeaseCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Create a lease for a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    if body.start_date > body.end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if await overlapping_lease_exists(session, property_id, body.start_date, body.end_date):
        raise HTTPException(status_code=409, detail="Lease dates overlap an existing lease")

    lease = Lease(
        organization_id=prop.organization_id, property_id=property_id, **body.model_dump()
    )
    session.add(lease)
    await session.commit()
    await session.refresh(lease)
    return lease
