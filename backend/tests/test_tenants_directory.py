from tests.test_leases import lease_body, make_property
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers


async def test_lists_roster_with_property_and_joined_flag(client, db_session):
    headers = await landlord_headers(client, "td1@example.com")
    lease_id = await make_lease(client, headers, "1 Directory St")
    await onboard_tenant(client, db_session, headers, lease_id, "tina@example.com")

    body = (await client.get("/api/v1/tenants", headers=headers)).json()

    assert len(body) == 1
    assert body[0]["name"] == "Tina Tenant"
    assert body[0]["email"] == "tina@example.com"
    assert body[0]["property_address"] == "1 Directory St"
    assert body[0]["lease_id"] == lease_id
    assert body[0]["joined"] is True


async def test_includes_co_tenants_and_marks_them_not_joined(client):
    headers = await landlord_headers(client, "td2@example.com")
    property_id = await make_property(client, headers, "2 Directory St")
    await client.post(
        f"/api/v1/properties/{property_id}/leases",
        json=lease_body(co_tenants=[{"name": "Coco", "email": "coco@example.com", "phone": ""}]),
        headers=headers,
    )

    body = (await client.get("/api/v1/tenants", headers=headers)).json()

    assert [t["name"] for t in body] == ["Tina Tenant", "Coco"]
    assert all(t["joined"] is False for t in body)


async def test_other_organizations_are_not_visible(client):
    owner = await landlord_headers(client, "td3@example.com")
    await make_lease(client, owner, "3 Directory St")

    other = await landlord_headers(client, "td3-other@example.com")
    assert (await client.get("/api/v1/tenants", headers=other)).json() == []


async def test_tenants_are_refused(client, db_session):
    headers = await landlord_headers(client, "td4@example.com")
    lease_id = await make_lease(client, headers, "4 Directory St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "td4-t@example.com")

    assert (await client.get("/api/v1/tenants", headers=tenant)).status_code == 403
