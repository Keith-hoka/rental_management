import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.uploads import save_image
from app.models import Lease, Membership, Property, PropertyStatus, PropertyType, Role
from app.schemas.property import ActiveLease, PropertyCreate, PropertyResponse, PropertyUpdate

router = APIRouter(prefix="/api/v1/properties", tags=["properties"])

manager = require_roles(Role.landlord, Role.property_manager)


async def active_leases_by_property(
    session: AsyncSession,
    organization_id: uuid.UUID,
    property_ids: list[uuid.UUID],
) -> dict[uuid.UUID, Lease]:
    """Map each property id to its lease active today (start <= today <= end), if any."""
    if not property_ids:
        return {}
    today = datetime.now(UTC).date()
    result = await session.execute(
        select(Lease).where(
            Lease.organization_id == organization_id,
            Lease.property_id.in_(property_ids),
            Lease.start_date <= today,
            today <= Lease.end_date,
        )
    )
    return {lease.property_id: lease for lease in result.scalars().all()}


def build_property_response(prop: Property, active_lease: Lease | None) -> PropertyResponse:
    """Build a property response with status derived from its active lease."""
    return PropertyResponse(
        id=prop.id,
        organization_id=prop.organization_id,
        address=prop.address,
        type=prop.type,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        parking=prop.parking,
        description=prop.description,
        image_urls=prop.image_urls,
        status=PropertyStatus.occupied if active_lease else PropertyStatus.vacant,
        active_lease=ActiveLease.model_validate(active_lease) if active_lease else None,
    )


@router.post("", status_code=201, response_model=PropertyResponse)
async def create_property(
    body: PropertyCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PropertyResponse:
    """Create a property in the caller's organization (new properties are vacant)."""
    prop = Property(organization_id=membership.organization_id, **body.model_dump())
    session.add(prop)
    await session.commit()
    await session.refresh(prop)
    return build_property_response(prop, None)


@router.get("", response_model=list[PropertyResponse])
async def list_properties(
    search: str | None = None,
    status: PropertyStatus | None = None,
    type: PropertyType | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[PropertyResponse]:
    """List the caller org's properties, optionally searched and filtered."""
    query = select(Property).where(Property.organization_id == membership.organization_id)
    if search:
        query = query.where(Property.address.ilike(f"%{search}%"))
    if type:
        query = query.where(Property.type == type)
    result = await session.execute(query.order_by(Property.created_at.desc()))
    props = list(result.scalars().all())

    active = await active_leases_by_property(
        session, membership.organization_id, [p.id for p in props]
    )
    if status == PropertyStatus.occupied:
        props = [p for p in props if p.id in active]
    elif status == PropertyStatus.vacant:
        props = [p for p in props if p.id not in active]
    return [build_property_response(p, active.get(p.id)) for p in props]


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
) -> PropertyResponse:
    """Fetch a single property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    active = await active_leases_by_property(session, membership.organization_id, [prop.id])
    return build_property_response(prop, active.get(prop.id))


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: uuid.UUID,
    body: PropertyUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PropertyResponse:
    """Update fields of a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    await session.commit()
    await session.refresh(prop)
    active = await active_leases_by_property(session, membership.organization_id, [prop.id])
    return build_property_response(prop, active.get(prop.id))


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


@router.post("/{property_id}/images", response_model=PropertyResponse)
async def upload_image(
    property_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PropertyResponse:
    """Upload an image for a property and append its URL to the property."""
    prop = await get_owned_property(property_id, membership, session)
    url = await save_image(file)
    prop.image_urls = [*prop.image_urls, url]
    await session.commit()
    await session.refresh(prop)
    active = await active_leases_by_property(session, membership.organization_id, [prop.id])
    return build_property_response(prop, active.get(prop.id))
