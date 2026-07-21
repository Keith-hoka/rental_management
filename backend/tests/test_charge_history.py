import uuid
from datetime import date

from sqlalchemy import select

from app.models import Charge, Lease
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


def _charge(lease, period_start):
    return Charge(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        period_start=period_start,
        period_end=period_start,
        due_date=period_start,
        amount_due=1500,
    )


async def test_charge_history_newest_first(client, db_session):
    headers = await landlord_headers(client, "ch@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)

    db_session.add(_charge(lease, date(2026, 1, 1)))
    db_session.add(_charge(lease, date(2026, 2, 1)))
    await db_session.commit()

    response = await client.get(f"/api/v1/leases/{lease.id}/charges", headers=headers)
    assert response.status_code == 200
    assert [c["due_date"] for c in response.json()] == ["2026-02-01", "2026-01-01"]


async def test_charge_history_cross_org_is_404(client, db_session):
    org_a = await landlord_headers(client, "cha@example.com")
    org_b = await landlord_headers(client, "chb@example.com")
    property_id = await make_property(client, org_a)
    lease = await _lease(client, db_session, org_a, property_id)
    response = await client.get(f"/api/v1/leases/{lease.id}/charges", headers=org_b)
    assert response.status_code == 404


async def test_charge_history_requires_auth(client, db_session):
    headers = await landlord_headers(client, "chauth@example.com")
    property_id = await make_property(client, headers)
    lease = await _lease(client, db_session, headers, property_id)
    response = await client.get(f"/api/v1/leases/{lease.id}/charges")
    assert response.status_code == 401
