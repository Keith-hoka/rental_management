from sqlalchemy import select

from app.models import Notification, User
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _user_id(db_session, email):
    return (await db_session.execute(select(User.id).where(User.email == email))).scalar_one()


async def _categories(db_session, user_id):
    rows = (
        (
            await db_session.execute(
                select(Notification.category).where(Notification.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    return sorted(rows)


async def _setup(client, db_session, prefix):
    headers = await landlord_headers(client, f"{prefix}@example.com")
    lease_id = await make_lease(client, headers, f"{prefix} St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, f"{prefix}-t@example.com")
    request_id = (
        await client.post(
            f"/api/v1/me/leases/{lease_id}/maintenance",
            json={"title": "Leaking tap", "description": "Kitchen", "priority": "medium"},
            headers=tenant,
        )
    ).json()["id"]
    return headers, tenant, request_id


async def test_new_request_notifies_managers_only(client, db_session):
    await _setup(client, db_session, "mnnew")
    landlord_id = await _user_id(db_session, "mnnew@example.com")
    tenant_id = await _user_id(db_session, "mnnew-t@example.com")

    assert await _categories(db_session, landlord_id) == ["maintenance_new"]
    assert await _categories(db_session, tenant_id) == []


async def test_status_change_notifies_the_reporting_tenant(client, db_session):
    headers, _, request_id = await _setup(client, db_session, "mnstat")
    tenant_id = await _user_id(db_session, "mnstat-t@example.com")

    await client.patch(
        f"/api/v1/maintenance/{request_id}", json={"status": "in_progress"}, headers=headers
    )

    assert await _categories(db_session, tenant_id) == ["maintenance_status"]


async def test_same_status_notifies_nobody(client, db_session):
    headers, _, request_id = await _setup(client, db_session, "mnsame")
    tenant_id = await _user_id(db_session, "mnsame-t@example.com")

    await client.patch(
        f"/api/v1/maintenance/{request_id}", json={"status": "open"}, headers=headers
    )

    assert await _categories(db_session, tenant_id) == []


async def test_priority_only_change_notifies_nobody(client, db_session):
    headers, _, request_id = await _setup(client, db_session, "mnprio")
    tenant_id = await _user_id(db_session, "mnprio-t@example.com")

    await client.patch(
        f"/api/v1/maintenance/{request_id}", json={"priority": "urgent"}, headers=headers
    )

    assert await _categories(db_session, tenant_id) == []


async def test_tenant_cancel_notifies_managers(client, db_session):
    _, tenant, request_id = await _setup(client, db_session, "mncan")
    landlord_id = await _user_id(db_session, "mncan@example.com")

    await client.post(f"/api/v1/me/maintenance/{request_id}/cancel", headers=tenant)

    assert await _categories(db_session, landlord_id) == [
        "maintenance_cancelled",
        "maintenance_new",
    ]
