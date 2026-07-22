import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Charge, ChargeReminder, Lease
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease(client, db_session, headers, address):
    property_id = await make_property(client, headers, address)
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    return (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()


async def _charge(db_session, lease):
    charge = Charge(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        due_date=date(2026, 1, 1),
        amount_due=Decimal("1500"),
    )
    db_session.add(charge)
    await db_session.commit()
    return charge


async def test_insert_and_read(client, db_session):
    headers = await landlord_headers(client, "crmodel@example.com")
    charge = await _charge(db_session, await _lease(client, db_session, headers, "Ledger St"))

    db_session.add(ChargeReminder(charge_id=charge.id, kind="overdue_7"))
    await db_session.commit()

    rows = (await db_session.execute(select(ChargeReminder))).scalars().all()
    assert len(rows) == 1
    assert rows[0].kind == "overdue_7"
    assert rows[0].created_at is not None


async def test_same_kind_twice_is_rejected(client, db_session):
    headers = await landlord_headers(client, "crdup@example.com")
    charge = await _charge(db_session, await _lease(client, db_session, headers, "Dup St"))

    db_session.add(ChargeReminder(charge_id=charge.id, kind="due_soon"))
    await db_session.commit()

    db_session.add(ChargeReminder(charge_id=charge.id, kind="due_soon"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
