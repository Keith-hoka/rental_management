import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.uploads import save_image
from app.models import (
    Lease,
    LeaseTenant,
    MaintenanceRequest,
    MaintenanceStatus,
    Property,
    User,
)
from app.schemas.maintenance import MaintenanceCreate, MaintenanceInfo

router = APIRouter(prefix="/api/v1", tags=["maintenance"])


async def _to_info(session: AsyncSession, request: MaintenanceRequest) -> MaintenanceInfo:
    """Build the response for a request, resolving the property address and reporter."""
    address = (
        await session.execute(select(Property.address).where(Property.id == request.property_id))
    ).scalar_one()
    reporter = (
        await session.execute(select(User.name).where(User.id == request.created_by))
    ).scalar_one_or_none()
    return MaintenanceInfo(
        id=request.id,
        property_address=address,
        title=request.title,
        description=request.description,
        priority=request.priority,
        status=request.status,
        image_urls=request.image_urls,
        reported_by=reporter or "",
        created_at=request.created_at,
    )


async def _tenant_lease(lease_id: uuid.UUID, user: User, session: AsyncSession) -> Lease:
    """The lease, if the caller is one of its tenants; 404 otherwise."""
    owned = (
        await session.execute(
            select(LeaseTenant.id).where(
                LeaseTenant.lease_id == lease_id, LeaseTenant.user_id == user.id
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    return (await session.execute(select(Lease).where(Lease.id == lease_id))).scalar_one()


async def _tenant_request(
    request_id: uuid.UUID, user: User, session: AsyncSession
) -> MaintenanceRequest:
    """The request, if the caller reported it; 404 otherwise."""
    request = (
        await session.execute(select(MaintenanceRequest).where(MaintenanceRequest.id == request_id))
    ).scalar_one_or_none()
    if request is None or request.created_by != user.id:
        raise HTTPException(status_code=404, detail="Request not found")
    return request


@router.post("/me/leases/{lease_id}/maintenance", status_code=201, response_model=MaintenanceInfo)
async def create_request(
    lease_id: uuid.UUID,
    body: MaintenanceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """A tenant of the lease reports a maintenance issue."""
    lease = await _tenant_lease(lease_id, user, session)
    request = MaintenanceRequest(
        organization_id=lease.organization_id,
        property_id=lease.property_id,
        lease_id=lease.id,
        created_by=user.id,
        title=body.title,
        description=body.description,
        priority=body.priority,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)


@router.get("/me/leases/{lease_id}/maintenance", response_model=list[MaintenanceInfo])
async def list_my_requests(
    lease_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MaintenanceInfo]:
    """List maintenance requests for a lease the caller is a tenant of, newest first."""
    await _tenant_lease(lease_id, user, session)
    result = await session.execute(
        select(MaintenanceRequest)
        .where(MaintenanceRequest.lease_id == lease_id)
        .order_by(MaintenanceRequest.created_at.desc())
    )
    return [await _to_info(session, r) for r in result.scalars().all()]


@router.post("/me/maintenance/{request_id}/images", response_model=MaintenanceInfo)
async def add_image(
    request_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """Attach an image to the caller's own maintenance request."""
    request = await _tenant_request(request_id, user, session)
    url = await save_image(file)
    request.image_urls = [*request.image_urls, url]
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)


@router.post("/me/maintenance/{request_id}/cancel", response_model=MaintenanceInfo)
async def cancel_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MaintenanceInfo:
    """Cancel the caller's own open or in-progress request."""
    request = await _tenant_request(request_id, user, session)
    if request.status not in (MaintenanceStatus.open, MaintenanceStatus.in_progress):
        raise HTTPException(status_code=409, detail="Request cannot be cancelled")
    request.status = MaintenanceStatus.cancelled
    await session.commit()
    await session.refresh(request)
    return await _to_info(session, request)
