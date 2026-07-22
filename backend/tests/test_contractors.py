import uuid

from sqlalchemy import select

from app.models import Contractor, MaintenanceRequest, Organization
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers

REQ = {"title": "Broken heater", "description": "No hot water", "priority": "urgent"}


async def test_contractor_row_round_trips(client, db_session):
    await landlord_headers(client, "cmodel@example.com")
    organization = (await db_session.execute(select(Organization))).scalars().first()

    contractor = Contractor(
        organization_id=organization.id,
        name="Bob's Plumbing",
        trade="Plumber",
        phone="0400 123 456",
        email="bob@example.com",
    )
    db_session.add(contractor)
    await db_session.commit()

    stored = (
        await db_session.execute(select(Contractor).where(Contractor.id == contractor.id))
    ).scalar_one()
    assert stored.name == "Bob's Plumbing"
    assert stored.trade == "Plumber"
    assert stored.created_at is not None


async def test_request_contractor_id_defaults_to_none(client, db_session):
    headers = await landlord_headers(client, "cnull@example.com")
    lease_id = await make_lease(client, headers, "Null Contractor St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "cnull-t@example.com")
    rid = (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]

    request = (
        await db_session.execute(
            select(MaintenanceRequest).where(MaintenanceRequest.id == uuid.UUID(rid))
        )
    ).scalar_one()
    assert request.contractor_id is None
