import uuid

from sqlalchemy import select

from app.models import MaintenanceRequest, MaintenanceStatus
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers

REQ = {"title": "Leaky tap", "description": "Kitchen tap drips", "priority": "high"}


async def test_tenant_creates_request(client, db_session):
    headers = await landlord_headers(client, "mtc@example.com")
    lease_id = await make_lease(client, headers, "Maint St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mtc-t@example.com")

    resp = await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "open"
    assert body["priority"] == "high"
    assert body["property_address"] == "Maint St"
    assert body["title"] == "Leaky tap"


async def test_create_requires_lease_tenant(client, db_session):
    headers = await landlord_headers(client, "mreq@example.com")
    lease_a = await make_lease(client, headers, "A Maint")
    lease_b = await make_lease(client, headers, "B Maint")
    ta = await onboard_tenant(client, db_session, headers, lease_a, "mreq-a@example.com", "TA")
    await onboard_tenant(client, db_session, headers, lease_b, "mreq-b@example.com", "TB")

    resp = await client.post(f"/api/v1/me/leases/{lease_b}/maintenance", json=REQ, headers=ta)
    assert resp.status_code == 404


async def test_manager_cannot_create(client, db_session):
    headers = await landlord_headers(client, "mmgr@example.com")
    lease_id = await make_lease(client, headers, "Mgr Maint")

    resp = await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=headers)
    assert resp.status_code == 404


async def test_tenant_lists_own_requests(client, db_session):
    headers = await landlord_headers(client, "mlist@example.com")
    lease_id = await make_lease(client, headers, "List Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mlist-t@example.com")
    await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)

    body = (await client.get(f"/api/v1/me/leases/{lease_id}/maintenance", headers=tenant)).json()
    assert len(body) == 1
    assert body[0]["title"] == "Leaky tap"


async def _make_request(client, tenant, lease_id):
    return (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]


async def test_tenant_uploads_image(client, db_session):
    headers = await landlord_headers(client, "mimg@example.com")
    lease_id = await make_lease(client, headers, "Img Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mimg-t@example.com")
    rid = await _make_request(client, tenant, lease_id)

    resp = await client.post(
        f"/api/v1/me/maintenance/{rid}/images",
        files={"file": ("p.png", b"imgbytes", "image/png")},
        headers=tenant,
    )
    assert resp.status_code == 200
    assert len(resp.json()["image_urls"]) == 1


async def test_image_rejects_bad_type(client, db_session):
    headers = await landlord_headers(client, "mbad@example.com")
    lease_id = await make_lease(client, headers, "Bad Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mbad-t@example.com")
    rid = await _make_request(client, tenant, lease_id)

    resp = await client.post(
        f"/api/v1/me/maintenance/{rid}/images",
        files={"file": ("p.txt", b"x", "text/plain")},
        headers=tenant,
    )
    assert resp.status_code == 400


async def test_image_non_owner_404(client, db_session):
    headers = await landlord_headers(client, "mown@example.com")
    lease_a = await make_lease(client, headers, "OwnA")
    lease_b = await make_lease(client, headers, "OwnB")
    ta = await onboard_tenant(client, db_session, headers, lease_a, "mown-a@example.com", "TA")
    tb = await onboard_tenant(client, db_session, headers, lease_b, "mown-b@example.com", "TB")
    rid = await _make_request(client, ta, lease_a)

    resp = await client.post(
        f"/api/v1/me/maintenance/{rid}/images",
        files={"file": ("p.png", b"x", "image/png")},
        headers=tb,
    )
    assert resp.status_code == 404


async def test_tenant_cancels(client, db_session):
    headers = await landlord_headers(client, "mcan@example.com")
    lease_id = await make_lease(client, headers, "Can Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mcan-t@example.com")
    rid = await _make_request(client, tenant, lease_id)

    resp = await client.post(f"/api/v1/me/maintenance/{rid}/cancel", headers=tenant)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_cancel_resolved_conflicts(client, db_session):
    headers = await landlord_headers(client, "mres@example.com")
    lease_id = await make_lease(client, headers, "Res Maint")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mres-t@example.com")
    rid = await _make_request(client, tenant, lease_id)
    request = (
        await db_session.execute(
            select(MaintenanceRequest).where(MaintenanceRequest.id == uuid.UUID(rid))
        )
    ).scalar_one()
    request.status = MaintenanceStatus.resolved
    await db_session.commit()

    resp = await client.post(f"/api/v1/me/maintenance/{rid}/cancel", headers=tenant)
    assert resp.status_code == 409


async def test_tenant_sees_the_assigned_contractor(client, db_session):
    headers = await landlord_headers(client, "tsee@example.com")
    lease_id = await make_lease(client, headers, "Tenant Sees St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "tsee-t@example.com")
    rid = (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]
    cid = (
        await client.post(
            "/api/v1/contractors",
            json={"name": "Bob's Plumbing", "phone": "0400 123 456"},
            headers=headers,
        )
    ).json()["id"]
    await client.post(
        f"/api/v1/maintenance/{rid}/assign", json={"contractor_id": cid}, headers=headers
    )

    mine = (await client.get(f"/api/v1/me/leases/{lease_id}/maintenance", headers=tenant)).json()
    assert mine[0]["contractor_name"] == "Bob's Plumbing"
    assert mine[0]["contractor_phone"] == "0400 123 456"
