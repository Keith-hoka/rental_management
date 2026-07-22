import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models import Notification, User
from app.schemas.notification import NotificationInfo, UnreadCount

router = APIRouter(prefix="/api/v1", tags=["notifications"])


def _to_info(notification: Notification) -> NotificationInfo:
    return NotificationInfo(
        id=notification.id,
        category=notification.category,
        title=notification.title,
        body=notification.body,
        link=notification.link,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


@router.get("/me/notifications", response_model=list[NotificationInfo])
async def list_notifications(
    unread: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[NotificationInfo]:
    """The caller's notifications, newest first (latest 100)."""
    query = select(Notification).where(Notification.user_id == user.id)
    if unread:
        query = query.where(Notification.read_at.is_(None))
    result = await session.execute(query.order_by(Notification.created_at.desc()).limit(100))
    return [_to_info(n) for n in result.scalars().all()]


@router.get("/me/notifications/unread_count", response_model=UnreadCount)
async def unread_count(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UnreadCount:
    """How many of the caller's notifications are unread."""
    count = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
    ).scalar_one()
    return UnreadCount(count=count)


@router.post("/me/notifications/{notification_id}/read", response_model=NotificationInfo)
async def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationInfo:
    """Mark one of the caller's notifications as read."""
    notification = (
        await session.execute(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(notification)
    return _to_info(notification)


@router.post("/me/notifications/read_all", response_model=UnreadCount)
async def mark_all_read(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UnreadCount:
    """Mark every unread notification of the caller as read."""
    result = await session.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    now = datetime.now(UTC)
    for notification in result.scalars().all():
        notification.read_at = now
    await session.commit()
    return UnreadCount(count=0)
