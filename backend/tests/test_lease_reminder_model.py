import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import LeaseReminder
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _make_lease_id(client, headers, property_id) -> str:
    created = await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(),
        headers=headers,
    )
    return created.json()["id"]


async def test_insert_and_read_reminder(client, db_session):
    headers = await landlord_headers(client, "rmodel@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)

    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30))
    await db_session.commit()

    rows = (
        (
            await db_session.execute(
                select(LeaseReminder).where(LeaseReminder.lease_id == uuid.UUID(lease_id))
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].threshold_days == 30
    assert rows[0].sent_at is not None


async def test_unique_lease_threshold(client, db_session):
    headers = await landlord_headers(client, "runique@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)

    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30))
    await db_session.commit()
    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_delete_lease_cascades_reminders(client, db_session):
    headers = await landlord_headers(client, "rcascade@example.com")
    property_id = await make_property(client, headers)
    lease_id = await _make_lease_id(client, headers, property_id)

    db_session.add(LeaseReminder(lease_id=uuid.UUID(lease_id), threshold_days=30))
    await db_session.commit()

    await client.delete(f"/api/v1/leases/{lease_id}", headers=headers)

    rows = (
        (
            await db_session.execute(
                select(LeaseReminder).where(LeaseReminder.lease_id == uuid.UUID(lease_id))
            )
        )
        .scalars()
        .all()
    )
    assert rows == []
