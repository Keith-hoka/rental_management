import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.uploads import save_image
from app.models import Inspection, InspectionItem, Lease, Membership, Property, User
from app.routers.documents import _tenant_lease_or_404
from app.routers.leases import manager
from app.schemas.inspection import (
    InspectionCreate,
    InspectionInfo,
    InspectionItemInfo,
    InspectionUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["inspections"])


async def _owned(inspection_id, membership, session) -> Inspection:
    inspection = (
        await session.execute(
            select(Inspection).where(
                Inspection.id == inspection_id,
                Inspection.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


async def _check_in_org(model, obj_id, membership, session, detail) -> None:
    if obj_id is None:
        return
    found = (
        await session.execute(
            select(model.id).where(
                model.id == obj_id,
                model.organization_id == membership.organization_id,
            )
        )
    ).first()
    if found is None:
        raise HTTPException(status_code=400, detail=detail)


async def _set_items(session, inspection_id, items) -> None:
    existing = (
        (
            await session.execute(
                select(InspectionItem).where(InspectionItem.inspection_id == inspection_id)
            )
        )
        .scalars()
        .all()
    )
    for it in existing:
        await session.delete(it)
    await session.flush()
    for i, item in enumerate(items):
        session.add(
            InspectionItem(
                inspection_id=inspection_id,
                position=i,
                area=item.area,
                condition=item.condition,
                note=item.note,
            )
        )


async def _info(session, inspection) -> InspectionInfo:
    items = (
        (
            await session.execute(
                select(InspectionItem)
                .where(InspectionItem.inspection_id == inspection.id)
                .order_by(InspectionItem.position)
            )
        )
        .scalars()
        .all()
    )
    return InspectionInfo(
        id=inspection.id,
        property_id=inspection.property_id,
        lease_id=inspection.lease_id,
        type=inspection.type,
        status=inspection.status,
        scheduled_for=inspection.scheduled_for,
        note=inspection.note,
        image_urls=inspection.image_urls,
        items=[
            InspectionItemInfo(id=it.id, area=it.area, condition=it.condition, note=it.note)
            for it in items
        ],
        created_at=inspection.created_at,
    )


@router.post("/inspections", status_code=201, response_model=InspectionInfo)
async def create_inspection(
    body: InspectionCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> InspectionInfo:
    await _check_in_org(Property, body.property_id, membership, session, "Unknown property")
    await _check_in_org(Lease, body.lease_id, membership, session, "Unknown lease")
    inspection = Inspection(
        organization_id=membership.organization_id,
        property_id=body.property_id,
        lease_id=body.lease_id,
        type=body.type,
        status=body.status,
        scheduled_for=body.scheduled_for,
        note=body.note,
        created_by=membership.user_id,
    )
    session.add(inspection)
    await session.flush()
    await _set_items(session, inspection.id, body.items)
    await session.commit()
    await session.refresh(inspection)
    return await _info(session, inspection)


@router.get("/inspections", response_model=list[InspectionInfo])
async def list_inspections(
    property_id: uuid.UUID | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[InspectionInfo]:
    query = select(Inspection).where(Inspection.organization_id == membership.organization_id)
    if property_id is not None:
        query = query.where(Inspection.property_id == property_id)
    inspections = (
        (await session.execute(query.order_by(Inspection.scheduled_for.desc()))).scalars().all()
    )
    return [await _info(session, i) for i in inspections]


@router.patch("/inspections/{inspection_id}", response_model=InspectionInfo)
async def update_inspection(
    inspection_id: uuid.UUID,
    body: InspectionUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> InspectionInfo:
    inspection = await _owned(inspection_id, membership, session)
    data = body.model_dump(exclude_unset=True)
    for field in ("status", "note", "scheduled_for"):
        if field in data:
            setattr(inspection, field, data[field])
    if "items" in data:
        await _set_items(session, inspection.id, body.items or [])
    await session.commit()
    await session.refresh(inspection)
    return await _info(session, inspection)


@router.delete("/inspections/{inspection_id}", status_code=204)
async def delete_inspection(
    inspection_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    inspection = await _owned(inspection_id, membership, session)
    await session.delete(inspection)
    await session.commit()
    return Response(status_code=204)


@router.post("/inspections/{inspection_id}/images", response_model=InspectionInfo)
async def add_image(
    inspection_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> InspectionInfo:
    inspection = await _owned(inspection_id, membership, session)
    url = await save_image(file)
    inspection.image_urls = [*inspection.image_urls, url]
    await session.commit()
    await session.refresh(inspection)
    return await _info(session, inspection)


@router.get("/me/leases/{lease_id}/inspections", response_model=list[InspectionInfo])
async def list_my_inspections(
    lease_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[InspectionInfo]:
    await _tenant_lease_or_404(lease_id, user, session)
    inspections = (
        (
            await session.execute(
                select(Inspection)
                .where(Inspection.lease_id == lease_id)
                .order_by(Inspection.scheduled_for.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _info(session, i) for i in inspections]
