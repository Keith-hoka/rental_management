import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email
from app.models import Lease, LeaseTenant, Membership, Notification, Role, User

logger = logging.getLogger(__name__)


async def safe_send(to: str, subject: str, html: str) -> None:
    """Send one email; a failure is logged and swallowed, never aborting the caller."""
    try:
        await send_email(to, subject, html)
    except Exception:  # noqa: BLE001 - a failed email must not abort the caller
        logger.exception("Failed to send notification email to %s", to)


async def manager_emails(session: AsyncSession, organization_id) -> list[str]:
    """Emails of the landlords and property managers in the organization."""
    result = await session.execute(
        select(User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == organization_id,
            Membership.role.in_([Role.landlord, Role.property_manager]),
        )
    )
    return [email for (email,) in result.all()]


def roster_emails(lease: Lease) -> list[str]:
    """The tenant contact emails on the lease (main tenant plus co-tenants)."""
    return [lease.tenant_email] + [c["email"] for c in lease.co_tenants]


async def user_emails(session: AsyncSession, user_ids) -> list[str]:
    """The emails of specific users."""
    result = await session.execute(select(User.email).where(User.id.in_(user_ids)))
    return [email for (email,) in result.all()]


async def manager_user_ids(session: AsyncSession, organization_id) -> list[uuid.UUID]:
    """User ids of the landlords and property managers in the organization."""
    result = await session.execute(
        select(Membership.user_id).where(
            Membership.organization_id == organization_id,
            Membership.role.in_([Role.landlord, Role.property_manager]),
        )
    )
    return [user_id for (user_id,) in result.all()]


async def lease_tenant_user_ids(session: AsyncSession, lease_id) -> list[uuid.UUID]:
    """User ids of the tenants who have joined the lease."""
    result = await session.execute(
        select(LeaseTenant.user_id).where(LeaseTenant.lease_id == lease_id)
    )
    return [user_id for (user_id,) in result.all()]


async def notify_users(
    session: AsyncSession,
    user_ids,
    organization_id,
    category: str,
    title: str,
    body: str,
    link: str | None = None,
) -> None:
    """Queue one in-app notification per recipient user. The caller commits."""
    for user_id in user_ids:
        session.add(
            Notification(
                organization_id=organization_id,
                user_id=user_id,
                category=category,
                title=title,
                body=body,
                link=link,
            )
        )
