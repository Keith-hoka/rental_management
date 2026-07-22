import uuid

from sqlalchemy import select

from app.models import Membership, Notification, User
from app.services.notify import lease_tenant_user_ids, manager_user_ids, notify_users
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _org_id(db_session, email):
    return (
        await db_session.execute(
            select(Membership.organization_id)
            .join(User, User.id == Membership.user_id)
            .where(User.email == email)
        )
    ).scalar_one()


async def test_manager_user_ids(client, db_session):
    email = "nmu@example.com"
    await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)

    ids = await manager_user_ids(db_session, org_id)
    assert len(ids) == 1


async def test_lease_tenant_user_ids(client, db_session):
    headers = await landlord_headers(client, "nlt@example.com")
    lease_id = await make_lease(client, headers, "Notify St")
    await onboard_tenant(client, db_session, headers, lease_id, "nlt-t@example.com")

    ids = await lease_tenant_user_ids(db_session, uuid.UUID(lease_id))
    assert len(ids) == 1


async def test_notify_users_writes_one_row_each(client, db_session):
    email = "nnu@example.com"
    await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    ids = await manager_user_ids(db_session, org_id)

    await notify_users(db_session, ids, org_id, "lease_expiry", "Title", "Body", "/app/leases/x")
    await db_session.commit()

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert len(rows) == len(ids) == 1
    assert rows[0].category == "lease_expiry"
    assert rows[0].title == "Title"
    assert rows[0].link == "/app/leases/x"
    assert rows[0].read_at is None
