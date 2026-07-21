import uuid
from datetime import date

from sqlalchemy import select

from app.models import Charge, Lease
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def _add_charge(db_session, lease_id, due, amount):
    lease = (
        await db_session.execute(select(Lease).where(Lease.id == uuid.UUID(lease_id)))
    ).scalar_one()
    db_session.add(
        Charge(
            organization_id=lease.organization_id,
            lease_id=lease.id,
            period_start=due,
            period_end=due,
            due_date=due,
            amount_due=amount,
        )
    )
    await db_session.commit()


async def test_my_leases_includes_balance(client, db_session):
    headers = await landlord_headers(client, "tcb@example.com")
    lease_id = await make_lease(client, headers, "Bal St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "tcb-t@example.com")
    await _add_charge(db_session, lease_id, date(2020, 1, 1), 1200)  # past due, unpaid

    body = (await client.get("/api/v1/me/leases", headers=tenant)).json()
    assert float(body[0]["outstanding"]) == 1200.0
    assert float(body[0]["overdue_amount"]) == 1200.0


async def test_my_lease_charges_returns_status(client, db_session):
    headers = await landlord_headers(client, "tcs@example.com")
    lease_id = await make_lease(client, headers, "Chg St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "tcs-t@example.com")
    await _add_charge(db_session, lease_id, date(2020, 1, 1), 1000)

    resp = await client.get(f"/api/v1/me/leases/{lease_id}/charges", headers=tenant)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "unpaid"
    assert data[0]["overdue"] is True


async def test_my_lease_charges_other_tenant_404(client, db_session):
    headers = await landlord_headers(client, "tco@example.com")
    lease_a = await make_lease(client, headers, "A2 St")
    lease_b = await make_lease(client, headers, "B2 St")
    ta = await onboard_tenant(client, db_session, headers, lease_a, "tco-a@example.com", "TA")
    await onboard_tenant(client, db_session, headers, lease_b, "tco-b@example.com", "TB")

    resp = await client.get(f"/api/v1/me/leases/{lease_b}/charges", headers=ta)
    assert resp.status_code == 404


async def test_my_lease_charges_landlord_404(client, db_session):
    headers = await landlord_headers(client, "tcl@example.com")
    lease_id = await make_lease(client, headers, "LL St")
    resp = await client.get(f"/api/v1/me/leases/{lease_id}/charges", headers=headers)
    assert resp.status_code == 404
