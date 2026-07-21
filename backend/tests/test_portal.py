from sqlalchemy import select

from app.models import Invitation
from tests.test_leases import lease_body, make_property
from tests.test_properties_crud import landlord_headers


async def make_lease(client, headers, address="1 Portal St") -> str:
    property_id = await make_property(client, headers, address)
    created = (
        await client.post(
            f"/api/v1/properties/{property_id}/leases", json=lease_body(), headers=headers
        )
    ).json()
    return created["id"]


async def onboard_tenant(client, db_session, headers, lease_id, email, name="Tenant"):
    await client.post(f"/api/v1/leases/{lease_id}/invite", json={"email": email}, headers=headers)
    token = (
        (await db_session.execute(select(Invitation).where(Invitation.email == email)))
        .scalars()
        .first()
    ).token
    tokens = (
        await client.post(
            "/api/v1/invitations/accept",
            json={"token": token, "name": name, "password": "tenantpw1"},
        )
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_my_leases_shows_lease_and_landlord_contact(client, db_session):
    headers = await landlord_headers(client, "ll@example.com")
    await client.patch(
        "/api/v1/auth/me",
        json={"name": "Larry Landlord", "phone": "555-7777"},
        headers=headers,
    )
    lease_id = await make_lease(client, headers)
    tenant_headers = await onboard_tenant(client, db_session, headers, lease_id, "tp@example.com")

    response = await client.get("/api/v1/me/leases", headers=tenant_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["property_address"] == "1 Portal St"
    assert body[0]["landlord_name"] == "Larry Landlord"
    assert body[0]["landlord_phone"] == "555-7777"
    assert body[0]["state"] in {"active", "upcoming", "ended"}


async def test_my_leases_is_isolated_per_tenant(client, db_session):
    headers = await landlord_headers(client, "iso@example.com")
    lease_a = await make_lease(client, headers, "A St")
    lease_b = await make_lease(client, headers, "B St")
    ta = await onboard_tenant(client, db_session, headers, lease_a, "ta@example.com", "TA")
    await onboard_tenant(client, db_session, headers, lease_b, "tb@example.com", "TB")

    a_leases = (await client.get("/api/v1/me/leases", headers=ta)).json()
    assert [lease["property_address"] for lease in a_leases] == ["A St"]


async def test_my_leases_empty_for_landlord(client):
    headers = await landlord_headers(client, "notenant@example.com")
    response = await client.get("/api/v1/me/leases", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_my_leases_requires_auth(client):
    response = await client.get("/api/v1/me/leases")
    assert response.status_code == 401
