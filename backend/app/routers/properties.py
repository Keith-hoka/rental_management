from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.models import Membership, Property, Role
from app.schemas.property import PropertyCreate, PropertyResponse

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
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Property]:
    """List the caller organization's properties, newest first."""
    result = await session.execute(
        select(Property)
        .where(Property.organization_id == membership.organization_id)
        .order_by(Property.created_at.desc())
    )
    return list(result.scalars().all())
