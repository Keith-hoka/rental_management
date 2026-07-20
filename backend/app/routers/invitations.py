import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.deps import require_roles
from app.core.email import send_email
from app.models import Invitation, Membership, Role
from app.schemas.invitation import InvitationCreate, InvitationResponse

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
