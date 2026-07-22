import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Contractor, MaintenanceRequest, Membership, Role
from app.schemas.contractor import ContractorCreate, ContractorInfo, ContractorUpdate

router = APIRouter(prefix="/api/v1/contractors", tags=["contractors"])

manager = require_roles(Role.landlord, Role.property_manager)


async def get_owned_contractor(
    contractor_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Contractor:
    """Fetch a contractor in the caller's organization, or raise 404."""
    contractor = (
        await session.execute(
            select(Contractor).where(
                Contractor.id == contractor_id,
                Contractor.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if contractor is None:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return contractor


@router.post("", status_code=201, response_model=ContractorInfo)
async def create_contractor(
    body: ContractorCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Contractor:
    """Add a contractor to the caller's organization directory."""
    contractor = Contractor(organization_id=membership.organization_id, **body.model_dump())
    session.add(contractor)
    await session.commit()
    await session.refresh(contractor)
    return contractor


@router.get("", response_model=list[ContractorInfo])
async def list_contractors(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Contractor]:
    """The organization's contractors, by name."""
    result = await session.execute(
        select(Contractor)
        .where(Contractor.organization_id == membership.organization_id)
        .order_by(Contractor.name)
    )
    return list(result.scalars().all())


@router.patch("/{contractor_id}", response_model=ContractorInfo)
async def update_contractor(
    contractor_id: uuid.UUID,
    body: ContractorUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Contractor:
    """Update a contractor's details."""
    contractor = await get_owned_contractor(contractor_id, membership, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contractor, field, value)
    await session.commit()
    await session.refresh(contractor)
    return contractor


@router.delete("/{contractor_id}", status_code=204)
async def delete_contractor(
    contractor_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a contractor, unless requests still point at them.

    Refusing beats silently unassigning those jobs, and beats surfacing a raw
    foreign-key error.
    """
    contractor = await get_owned_contractor(contractor_id, membership, session)
    assigned = (
        await session.execute(
            select(func.count())
            .select_from(MaintenanceRequest)
            .where(MaintenanceRequest.contractor_id == contractor_id)
        )
    ).scalar_one()
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=f"Contractor is assigned to {assigned} maintenance requests",
        )
    await session.delete(contractor)
    await session.commit()
    return Response(status_code=204)
