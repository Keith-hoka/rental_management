import uuid
from datetime import date

from sqlalchemy import select

from app.models import Lease, Payment, PaymentMethod
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def _lease(client, db_session, headers, property_id):
    lease_id = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()["id"]
    return (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()


def _payment(lease, method=PaymentMethod.cash, note="first"):
    return Payment(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        amount=1000,
        paid_on=date(2026, 1, 5),
        method=method,
        note=note,
    )


async def test_insert_and_read_payment(client, db_session):
    headers = await landlord_headers(client, "pmodel@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_payment(lease))
    await db_session.commit()

    rows = (
        (await db_session.execute(select(Payment).where(Payment.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert float(rows[0].amount) == 1000.0
    assert rows[0].method == PaymentMethod.cash


async def test_delete_lease_cascades_payments(client, db_session):
    headers = await landlord_headers(client, "pcascade@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_payment(lease, method=PaymentMethod.other, note=None))
    await db_session.commit()

    await client.delete(f"/api/v1/leases/{lease.id}", headers=headers)

    rows = (
        (await db_session.execute(select(Payment).where(Payment.lease_id == lease.id)))
        .scalars()
        .all()
    )
    assert rows == []
