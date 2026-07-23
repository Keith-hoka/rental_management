import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import CalendarEvent, Charge, Lease, MaintenanceRequest, Membership, Property
from app.routers.leases import manager
from app.schemas.calendar import (
    CalendarEntry,
    CalendarEventCreate,
    CalendarEventInfo,
    CalendarEventUpdate,
)

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


@router.get("/calendar", response_model=list[CalendarEntry])
async def calendar_feed(
    start: date,
    end: date,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[CalendarEntry]:
    """Every dated record in [start, end] for the org: derived kinds plus events."""
    org = membership.organization_id
    entries: list[CalendarEntry] = []

    leases = (
        await session.execute(
            select(Lease, Property.address)
            .join(Property, Property.id == Lease.property_id)
            .where(Lease.organization_id == org)
        )
    ).all()
    for lease, address in leases:
        if start <= lease.start_date <= end:
            entries.append(
                CalendarEntry(
                    kind="lease_start",
                    title=f"Lease starts: {address}",
                    all_day=True,
                    date=lease.start_date,
                    link=f"/app/leases/{lease.id}",
                )
            )
        if start <= lease.end_date <= end:
            entries.append(
                CalendarEntry(
                    kind="lease_end",
                    title=f"Lease ends: {address}",
                    all_day=True,
                    date=lease.end_date,
                    link=f"/app/leases/{lease.id}",
                )
            )

    charges = (
        (
            await session.execute(
                select(Charge).where(
                    Charge.organization_id == org,
                    Charge.due_date >= start,
                    Charge.due_date <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    entries += [
        CalendarEntry(
            kind="rent_due",
            title=f"Rent due ${c.amount_due}",
            all_day=True,
            date=c.due_date,
            link=f"/app/leases/{c.lease_id}",
        )
        for c in charges
    ]

    requests = (
        (
            await session.execute(
                select(MaintenanceRequest).where(MaintenanceRequest.organization_id == org)
            )
        )
        .scalars()
        .all()
    )
    for r in requests:
        created = r.created_at.date()
        if start <= created <= end:
            entries.append(
                CalendarEntry(
                    kind="maintenance",
                    title=r.title,
                    all_day=True,
                    date=created,
                    link="/app/maintenance",
                )
            )

    events = (
        (await session.execute(select(CalendarEvent).where(CalendarEvent.organization_id == org)))
        .scalars()
        .all()
    )
    for e in events:
        if e.start_at.date() <= end and e.end_at.date() >= start:
            entries.append(
                CalendarEntry(
                    kind="event",
                    title=e.title,
                    all_day=False,
                    start_at=e.start_at,
                    end_at=e.end_at,
                    event_id=e.id,
                )
            )
    return entries
