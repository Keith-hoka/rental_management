import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Membership, Property, PropertyStatus, PropertyType, Role
from app.schemas.property import PropertyCreate, PropertyResponse, PropertyUpdate

router = APIRouter(prefix="/api/v1/properties", tags=["properties"])

manager = require_roles(Role.landlord, Role.property_manager)


@router.post("", status_code=201, response_model=PropertyResponse)
async def create_property(
    body: PropertyCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Property:
    """Create a property in the caller's organization."""
    prop = Property(organization_id=membership.organization_id, **body.model_dump())
    session.add(prop)
    await session.commit()
    await session.refresh(prop)
    return prop


@router.get("", response_model=list[PropertyResponse])
async def list_properties(
    search: str | None = None,
    status: PropertyStatus | None = None,
    type: PropertyType | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Property]:
    """List the caller org's properties, optionally searched and filtered."""
    query = select(Property).where(Property.organization_id == membership.organization_id)
    if search:
        query = query.where(Property.address.ilike(f"%{search}%"))
    if status:
        query = query.where(Property.status == status)
    if type:
        query = query.where(Property.type == type)
    result = await session.execute(query.order_by(Property.created_at.desc()))
    return list(result.scalars().all())


async def get_owned_property(
    property_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Property:
    """Fetch a property in the caller's org, or raise 404."""
    prop = (
        await session.execute(
            select(Property).where(
                Property.id == property_id,
                Property.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if prop is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Property:
    """Fetch a single property in the caller's organization."""
    return await get_owned_property(property_id, membership, session)


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: uuid.UUID,
    body: PropertyUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Property:
    """Update fields of a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    await session.commit()
    await session.refresh(prop)
    return prop


@router.delete("/{property_id}", status_code=204)
async def delete_property(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    await session.delete(prop)
    await session.commit()
    return Response(status_code=204)
