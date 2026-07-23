import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import CalendarEvent, Membership, Property
from app.routers.leases import manager
from app.schemas.calendar import CalendarEventCreate, CalendarEventInfo, CalendarEventUpdate

router = APIRouter(prefix="/api/v1", tags=["calendar"])


async def _owned_event(
    event_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> CalendarEvent:
    event = (
        await session.execute(
            select(CalendarEvent).where(
                CalendarEvent.id == event_id,
                CalendarEvent.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


async def _check_property(property_id, membership: Membership, session: AsyncSession) -> None:
    """A property link must point inside the caller's own organization."""
    if property_id is None:
        return
    owned = (
        await session.execute(
            select(Property.id).where(
                Property.id == property_id,
                Property.organization_id == membership.organization_id,
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=400, detail="Unknown property")


@router.post("/calendar/events", status_code=201, response_model=CalendarEventInfo)
async def create_event(
    body: CalendarEventCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> CalendarEvent:
    """Create a custom calendar event for the organization."""
    if body.end_at < body.start_at:
        raise HTTPException(status_code=400, detail="end_at must not precede start_at")
    await _check_property(body.property_id, membership, session)
    event = CalendarEvent(
        organization_id=membership.organization_id,
        title=body.title,
        description=body.description,
        start_at=body.start_at,
        end_at=body.end_at,
        property_id=body.property_id,
        created_by=membership.user_id,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@router.patch("/calendar/events/{event_id}", response_model=CalendarEventInfo)
async def update_event(
    event_id: uuid.UUID,
    body: CalendarEventUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> CalendarEvent:
    """Edit a custom event; only the fields sent are changed."""
    event = await _owned_event(event_id, membership, session)
    data = body.model_dump(exclude_unset=True)
    if "property_id" in data:
        await _check_property(data["property_id"], membership, session)
    for field, value in data.items():
        setattr(event, field, value)
    if event.end_at < event.start_at:
        raise HTTPException(status_code=400, detail="end_at must not precede start_at")
    await session.commit()
    await session.refresh(event)
    return event


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_event(
    event_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a custom event."""
    event = await _owned_event(event_id, membership, session)
    await session.delete(event)
    await session.commit()
    return Response(status_code=204)
