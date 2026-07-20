import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Lease, Membership, Property, Role
from app.routers.properties import get_owned_property
from app.schemas.lease import LeaseCreate, LeaseResponse, LeaseSummary, LeaseUpdate

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


async def get_owned_lease(
    lease_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Lease:
    """Fetch a lease in the caller's org, or raise 404."""
    lease = (
        await session.execute(
            select(Lease).where(
                Lease.id == lease_id,
                Lease.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if lease is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    return lease


@router.get("/properties/{property_id}/leases", response_model=list[LeaseResponse])
async def list_leases(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Lease]:
    """List a property's leases (newest first). 404 if the property is not in the org."""
    await get_owned_property(property_id, membership, session)
    result = await session.execute(
        select(Lease).where(Lease.property_id == property_id).order_by(Lease.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/leases/{lease_id}", response_model=LeaseResponse)
async def get_lease(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Fetch a single lease in the caller's organization."""
    return await get_owned_lease(lease_id, membership, session)


@router.patch("/leases/{lease_id}", response_model=LeaseResponse)
async def update_lease(
    lease_id: uuid.UUID,
    body: LeaseUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Update a lease; re-validate date order and overlap (excluding itself)."""
    lease = await get_owned_lease(lease_id, membership, session)
    data = body.model_dump(exclude_unset=True)
    start = data.get("start_date", lease.start_date)
    end = data.get("end_date", lease.end_date)
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if await overlapping_lease_exists(session, lease.property_id, start, end, exclude_id=lease.id):
        raise HTTPException(status_code=409, detail="Lease dates overlap an existing lease")

    for field, value in data.items():
        setattr(lease, field, value)
    await session.commit()
    await session.refresh(lease)
    return lease


@router.delete("/leases/{lease_id}", status_code=204)
async def delete_lease(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a lease in the caller's organization."""
    lease = await get_owned_lease(lease_id, membership, session)
    await session.delete(lease)
    await session.commit()
    return Response(status_code=204)


def _lease_state(lease: Lease, today: date) -> str:
    if lease.start_date > today:
        return "upcoming"
    if lease.end_date < today:
        return "ended"
    return "active"


@router.get("/leases", response_model=list[LeaseSummary])
async def list_all_leases(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[LeaseSummary]:
    """List every lease in the caller's organization with its property address and state."""
    today = datetime.now(UTC).date()
    result = await session.execute(
        select(Lease, Property.address)
        .join(Property, Lease.property_id == Property.id)
        .where(Lease.organization_id == membership.organization_id)
        .order_by(Lease.created_at.desc())
    )
    return [
        LeaseSummary(
            id=lease.id,
            property_id=lease.property_id,
            property_address=address,
            tenant_name=lease.tenant_name,
            rent_amount=lease.rent_amount,
            rent_frequency=lease.rent_frequency,
            start_date=lease.start_date,
            end_date=lease.end_date,
            state=_lease_state(lease, today),
        )
        for lease, address in result.all()
    ]
