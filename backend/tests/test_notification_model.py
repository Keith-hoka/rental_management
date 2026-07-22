from sqlalchemy import select

from app.models import Membership, Notification, User
from tests.test_properties_crud import landlord_headers


async def _user_and_org(db_session, email):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    org_id = (
        await db_session.execute(
            select(Membership.organization_id).where(Membership.user_id == user.id)
        )
    ).scalar_one()
    return user, org_id


async def test_insert_and_read(client, db_session):
    email = "nmodel@example.com"
    await landlord_headers(client, email)
    user, org_id = await _user_and_org(db_session, email)

    db_session.add(
        Notification(
            organization_id=org_id,
            user_id=user.id,
            category="lease_expiry",
            title="Lease expiring in 7 days",
            body="The lease at 1 Main St expires soon.",
            link="/app/leases/abc",
        )
    )
    await db_session.commit()

    rows = (
        (await db_session.execute(select(Notification).where(Notification.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].category == "lease_expiry"
    assert rows[0].link == "/app/leases/abc"
    assert rows[0].read_at is None
    assert rows[0].created_at is not None
