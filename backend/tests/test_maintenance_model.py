import uuid

from sqlalchemy import select

from app.models import (
    Lease,
    MaintenancePriority,
    MaintenanceRequest,
    MaintenanceStatus,
    User,
)
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease_and_user(client, db_session, email):
    headers = await landlord_headers(client, email)
    property_id = await make_property(client, headers)
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    return headers, lease, user


def _request(lease, user, **overrides):
    data = {
        "organization_id": lease.organization_id,
        "property_id": lease.property_id,
        "lease_id": lease.id,
        "created_by": user.id,
        "title": "Leaky tap",
        "description": "Kitchen tap drips",
    }
    data.update(overrides)
    return MaintenanceRequest(**data)


async def test_insert_and_read(client, db_session):
    _, lease, user = await _lease_and_user(client, db_session, "mmodel@example.com")
    db_session.add(_request(lease, user, priority=MaintenancePriority.high))
    await db_session.commit()

    rows = (
        (
            await db_session.execute(
                select(MaintenanceRequest).where(MaintenanceRequest.lease_id == lease.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].priority == MaintenancePriority.high
    assert rows[0].status == MaintenanceStatus.open
    assert rows[0].image_urls == []


async def test_delete_lease_cascades(client, db_session):
    headers, lease, user = await _lease_and_user(client, db_session, "mcascade@example.com")
    db_session.add(_request(lease, user))
    await db_session.commit()

    await client.delete(f"/api/v1/leases/{lease.id}", headers=headers)

    rows = (
        (
            await db_session.execute(
                select(MaintenanceRequest).where(MaintenanceRequest.lease_id == lease.id)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []
