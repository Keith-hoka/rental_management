import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Contractor, MaintenanceRequest, Property
from app.services.notify import (
    lease_tenant_user_ids,
    manager_emails,
    manager_user_ids,
    notify_users,
    safe_send,
    user_emails,
)

MANAGER_LINK = "/app/maintenance"
TENANT_LINK = "/app"


async def _address(session: AsyncSession, request: MaintenanceRequest) -> str:
    return (
        await session.execute(select(Property.address).where(Property.id == request.property_id))
    ).scalar_one()


async def _managers(session: AsyncSession, organization_id) -> tuple[list[str], list[uuid.UUID]]:
    """The organization's manager emails and user ids."""
    return (
        await manager_emails(session, organization_id),
        await manager_user_ids(session, organization_id),
    )


async def _deliver(
    session: AsyncSession,
    request: MaintenanceRequest,
    emails: list[str],
    user_ids: list[uuid.UUID],
    category: str,
    subject: str,
    title: str,
    body: str,
    link: str,
) -> None:
    """Email the recipients, post the in-app notifications, and commit them."""
    html = f'<p>{body}</p><p><a href="{settings.frontend_url}{link}">Open the request</a></p>'
    for email in emails:
        await safe_send(email, subject, html)
    await notify_users(session, user_ids, request.organization_id, category, title, body, link)
    await session.commit()


async def notify_new_request(session: AsyncSession, request: MaintenanceRequest) -> None:
    """Tell the organization's managers that a tenant filed a request."""
    address = await _address(session, request)
    emails, user_ids = await _managers(session, request.organization_id)
    await _deliver(
        session,
        request,
        emails,
        user_ids,
        "maintenance_new",
        f"New maintenance request - {address}",
        "New maintenance request",
        f"{request.title} was reported at {address} ({request.priority.value} priority).",
        MANAGER_LINK,
    )


async def notify_status_change(session: AsyncSession, request: MaintenanceRequest) -> None:
    """Tell the reporting tenant that a manager changed the request's status."""
    address = await _address(session, request)
    await _deliver(
        session,
        request,
        await user_emails(session, [request.created_by]),
        [request.created_by],
        "maintenance_status",
        f"Maintenance update - {address}",
        f"Maintenance request {request.status.value}",
        f"{request.title} at {address} is now {request.status.value}.",
        TENANT_LINK,
    )


async def notify_cancelled(session: AsyncSession, request: MaintenanceRequest) -> None:
    """Tell the organization's managers that the tenant cancelled a request."""
    address = await _address(session, request)
    emails, user_ids = await _managers(session, request.organization_id)
    await _deliver(
        session,
        request,
        emails,
        user_ids,
        "maintenance_cancelled",
        f"Maintenance request cancelled - {address}",
        "Maintenance request cancelled",
        f"{request.title} at {address} was cancelled by the tenant.",
        MANAGER_LINK,
    )


async def notify_assigned(
    session: AsyncSession, request: MaintenanceRequest, contractor: Contractor
) -> None:
    """Send the contractor their work order and tell the tenants who is coming.

    The work order deliberately omits the tenant's phone number. Giving a tenant
    a contractor's details is the manager sharing their own supplier; giving an
    outside contractor the tenant's number shares data the tenant never agreed
    to share. The address, issue and a manager to reply to are enough.
    """
    address = await _address(session, request)
    if contractor.email:
        managers = await manager_emails(session, request.organization_id)
        reply_to = managers[0] if managers else settings.email_from
        await safe_send(
            contractor.email,
            f"Maintenance job - {address}",
            f"<p>{request.title} at {address} ({request.priority.value} priority).</p>"
            f"<p>{request.description}</p>"
            f"<p>Reply to {reply_to}.</p>",
        )

    await notify_users(
        session,
        await lease_tenant_user_ids(session, request.lease_id),
        request.organization_id,
        "maintenance_assigned",
        "Contractor assigned",
        f"{contractor.name} has been assigned to {request.title} at {address}.",
        TENANT_LINK,
    )
    await session.commit()
