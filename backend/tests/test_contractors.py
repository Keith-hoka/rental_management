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


CONTRACTOR = {
    "name": "Bob's Plumbing",
    "trade": "Plumber",
    "phone": "0400 123 456",
    "email": "bob@example.com",
}


async def test_create_and_list_contractors(client):
    headers = await landlord_headers(client, "ccrud@example.com")
    created = await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)
    assert created.status_code == 201
    assert created.json()["name"] == "Bob's Plumbing"

    listed = (await client.get("/api/v1/contractors", headers=headers)).json()
    assert [c["name"] for c in listed] == ["Bob's Plumbing"]


async def test_contractor_list_is_org_scoped(client):
    mine = await landlord_headers(client, "cmine@example.com")
    await client.post("/api/v1/contractors", json=CONTRACTOR, headers=mine)
    stranger = await landlord_headers(client, "cstranger@example.com")

    assert (await client.get("/api/v1/contractors", headers=stranger)).json() == []


async def test_update_contractor(client):
    headers = await landlord_headers(client, "cupd@example.com")
    cid = (await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)).json()["id"]

    updated = await client.patch(
        f"/api/v1/contractors/{cid}", json={"phone": "0400 999 000"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "0400 999 000"
    assert updated.json()["name"] == "Bob's Plumbing"


async def test_delete_contractor(client):
    headers = await landlord_headers(client, "cdel@example.com")
    cid = (await client.post("/api/v1/contractors", json=CONTRACTOR, headers=headers)).json()["id"]

    assert (await client.delete(f"/api/v1/contractors/{cid}", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/contractors", headers=headers)).json() == []


async def test_other_orgs_contractor_is_404(client):
    owner = await landlord_headers(client, "cowner@example.com")
    cid = (await client.post("/api/v1/contractors", json=CONTRACTOR, headers=owner)).json()["id"]
    stranger = await landlord_headers(client, "cthief@example.com")

    patched = await client.patch(
        f"/api/v1/contractors/{cid}", json={"name": "Mine now"}, headers=stranger
    )
    assert patched.status_code == 404
    # Not just the status: a missing route also 404s, so this would pass against
    # no isolation at all. The detail proves get_owned_contractor refused it.
    assert patched.json()["detail"] == "Contractor not found"
    assert (await client.delete(f"/api/v1/contractors/{cid}", headers=stranger)).status_code == 404
