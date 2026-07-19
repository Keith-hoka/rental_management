import uuid

from sqlalchemy import select

from app.models import Membership, Organization, Role, User


async def test_create_user_with_org_and_membership(db_session):
    org = Organization(name="Keith Properties", currency="USD")
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x", name="Keith")
    db_session.add_all([org, user])
    await db_session.flush()

    membership = Membership(user_id=user.id, organization_id=org.id, role=Role.landlord)
    db_session.add(membership)
    await db_session.commit()

    found = (
        await db_session.execute(select(Membership).where(Membership.user_id == user.id))
    ).scalar_one()
    assert found.role == Role.landlord
    assert found.organization_id == org.id
