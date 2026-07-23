import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.deps import require_roles
from app.core.email import send_email
from app.core.security import hash_password
from app.models import Invitation, InvitationStatus, LeaseTenant, Membership, Role, User
from app.routers.auth import issue_tokens
from app.services.invites import reject_duplicate_invite
from app.services.notify import manager_user_ids, notify_users
from app.schemas.auth import TokenPair
from app.schemas.invitation import (
    AcceptInvitationRequest,
    InvitationCreate,
    InvitationResponse,
)

router = APIRouter(prefix="/api/v1/invitations", tags=["invitations"])

landlord_only = require_roles(Role.landlord)

INVITE_TTL_DAYS = 7


@router.post("", status_code=201, response_model=InvitationResponse)
async def create_invitation(
    body: InvitationCreate,
    membership: Membership = Depends(landlord_only),
    session: AsyncSession = Depends(get_session),
) -> Invitation:
    """Invite a team member (property_manager) to the caller's organization."""
    await reject_duplicate_invite(session, body.email, membership.organization_id)
    invite = Invitation(
        organization_id=membership.organization_id,
        email=body.email,
        role=Role(body.role),
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    accept_url = f"{settings.frontend_url}/accept-invite?token={invite.token}"
    html = (
        "<p>You have been invited to join a team on Rental Management.</p>"
        f'<p><a href="{accept_url}">Accept the invitation</a></p>'
        "<p>This link expires in 7 days.</p>"
    )
    try:
        await send_email(invite.email, "You have been invited", html)
    except Exception:  # noqa: BLE001 - email failure must not fail the invite
        logging.getLogger(__name__).exception("Failed to send invite email to %s", invite.email)

    return invite


@router.get("", response_model=list[InvitationResponse])
async def list_invitations(
    membership: Membership = Depends(landlord_only),
    session: AsyncSession = Depends(get_session),
) -> list[Invitation]:
    """List pending invitations for the caller's organization, newest first."""
    result = await session.execute(
        select(Invitation)
        .where(
            Invitation.organization_id == membership.organization_id,
            Invitation.status == InvitationStatus.pending,
        )
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    membership: Membership = Depends(landlord_only),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Revoke a pending invitation in the caller's organization."""
    invite = (
        await session.execute(
            select(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    invite.status = InvitationStatus.revoked
    await session.commit()
    return Response(status_code=204)


@router.post("/accept", status_code=201, response_model=TokenPair)
async def accept_invitation(
    body: AcceptInvitationRequest, session: AsyncSession = Depends(get_session)
) -> TokenPair:
    """Accept an invitation: create the user + membership and log them in."""
    invite = (
        await session.execute(select(Invitation).where(Invitation.token == body.token))
    ).scalar_one_or_none()
    if (
        invite is None
        or invite.status != InvitationStatus.pending
        or invite.expires_at < datetime.now(UTC)
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")

    existing = (
        await session.execute(select(User).where(User.email == invite.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=invite.email, hashed_password=hash_password(body.password), name=body.name)
    session.add(user)
    await session.flush()
    session.add(
        Membership(user_id=user.id, organization_id=invite.organization_id, role=invite.role)
    )
    if invite.lease_id is not None:
        session.add(LeaseTenant(lease_id=invite.lease_id, user_id=user.id))
    invite.status = InvitationStatus.accepted

    # Tell the organization's managers who joined, excluding the person who just
    # accepted (a new manager should not be notified about their own arrival).
    recipients = [
        uid for uid in await manager_user_ids(session, invite.organization_id) if uid != user.id
    ]
    if invite.lease_id is None:
        body, link = f"{user.name} accepted your invitation and joined the team.", "/app/team"
    else:
        body, link = (
            f"{user.name} accepted your invitation and joined the lease.",
            f"/app/leases/{invite.lease_id}",
        )
    await notify_users(
        session,
        recipients,
        invite.organization_id,
        "invitation_accepted",
        "Invitation accepted",
        body,
        link,
    )
    await session.commit()
    return issue_tokens(str(user.id))
