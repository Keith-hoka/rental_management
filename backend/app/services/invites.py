import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invitation, InvitationStatus


async def reject_duplicate_invite(
    session: AsyncSession,
    email: str,
    organization_id: uuid.UUID,
    lease_id: uuid.UUID | None = None,
) -> None:
    """Refuse a second pending invitation for the same email and scope.

    Each invitation carries its own token, so duplicates leave the list showing
    two identical rows and revoking one still leaves the other able to accept.

    Scope is the organization for a team invite and the lease for a tenant one,
    which keeps one person invitable to two different leases.
    """
    query = select(Invitation.id).where(
        Invitation.email == email,
        Invitation.organization_id == organization_id,
        Invitation.status == InvitationStatus.pending,
    )
    query = query.where(
        Invitation.lease_id.is_(None) if lease_id is None else Invitation.lease_id == lease_id
    )
    if (await session.execute(query)).first() is not None:
        raise HTTPException(status_code=409, detail="An invitation is already pending")
