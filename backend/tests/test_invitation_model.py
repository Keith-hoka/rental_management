import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Invitation, InvitationStatus, Organization, Role


async def test_create_invitation(db_session):
    org = Organization(name="Keith Properties", currency="USD")
    db_session.add(org)
    await db_session.flush()

    invite = Invitation(
        organization_id=org.id,
        email="pm@example.com",
        role=Role.property_manager,
        token="tok-123",
        status=InvitationStatus.pending,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(invite)
    await db_session.commit()

    found = (
        await db_session.execute(select(Invitation).where(Invitation.token == "tok-123"))
    ).scalar_one()
    assert found.organization_id == org.id
    assert found.role == Role.property_manager
    assert found.status == InvitationStatus.pending
    assert isinstance(found.id, uuid.UUID)
