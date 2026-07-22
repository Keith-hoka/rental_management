from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers

REQ = {"title": "Broken heater", "description": "No hot water", "priority": "urgent"}


async def _seed(client, db_session, prefix, address):
    headers = await landlord_headers(client, f"{prefix}@example.com")
    lease_id = await make_lease(client, headers, address)
    tenant = await onboard_tenant(client, db_session, headers, lease_id, f"{prefix}-t@example.com")
    rid = (
        await client.post(f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant)
    ).json()["id"]
    return headers, tenant, rid


async def test_manager_lists(client, db_session):
    headers, _, _ = await _seed(client, db_session, "mgl", "Mgr List St")

    body = (await client.get("/api/v1/maintenance", headers=headers)).json()
    assert len(body) == 1
    assert body[0]["title"] == "Broken heater"
    assert body[0]["reported_by"]


async def test_manager_filters_by_status(client, db_session):
    headers, _, _ = await _seed(client, db_session, "mgf", "Mgr Filter St")

    assert len((await client.get("/api/v1/maintenance?status=open", headers=headers)).json()) == 1
    assert (await client.get("/api/v1/maintenance?status=resolved", headers=headers)).json() == []


async def test_manager_gets_and_patches(client, db_session):
    headers, _, rid = await _seed(client, db_session, "mgp", "Mgr Patch St")

    assert (await client.get(f"/api/v1/maintenance/{rid}", headers=headers)).status_code == 200
    patched = await client.patch(
        f"/api/v1/maintenance/{rid}",
        json={"status": "in_progress", "priority": "high"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "in_progress"
    assert patched.json()["priority"] == "high"


async def test_manager_cross_org_404(client, db_session):
    _, _, rid = await _seed(client, db_session, "mgx", "Mgr Cross St")
    other = await landlord_headers(client, "mgx-other@example.com")

    assert (await client.get(f"/api/v1/maintenance/{rid}", headers=other)).status_code == 404
    assert (
        await client.patch(f"/api/v1/maintenance/{rid}", json={"status": "resolved"}, headers=other)
    ).status_code == 404


async def test_tenant_forbidden_on_manager_list(client, db_session):
    _, tenant, _ = await _seed(client, db_session, "mgt", "Mgr Tenant St")

    assert (await client.get("/api/v1/maintenance", headers=tenant)).status_code == 403
