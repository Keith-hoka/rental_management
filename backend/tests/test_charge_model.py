import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Charge, Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease(client, db_session, headers, property_id):
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    return lease


def _charge(lease, period_start=date(2026, 1, 1)):
    return Charge(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        period_start=period_start,
        period_end=date(2026, 1, 31),
        due_date=period_start,
        amount_due=1500,
    )


async def test_insert_and_read_charge(client, db_session):
    headers = await landlord_headers(client, "cmodel@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_charge(lease))
    await db_session.commit()

    rows = (
        (await db_session.execute(select(Charge).where(Charge.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].due_date == date(2026, 1, 1)
    assert float(rows[0].amount_due) == 1500.0


async def test_unique_lease_period_start(client, db_session):
    headers = await landlord_headers(client, "cunique@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_charge(lease))
    await db_session.commit()
    db_session.add(_charge(lease))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_delete_lease_cascades_charges(client, db_session):
    headers = await landlord_headers(client, "ccascade@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_charge(lease))
    await db_session.commit()

    await client.delete(f"/api/v1/leases/{lease.id}", headers=headers)

    rows = (
        (await db_session.execute(select(Charge).where(Charge.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert rows == []
