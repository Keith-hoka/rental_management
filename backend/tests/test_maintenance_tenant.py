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
